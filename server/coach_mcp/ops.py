"""Compound coach operations: fetch from Garmin, store, compute, summarize.

These replace long chains of raw tool calls with one call each, so a small
local model (or a frontier model on a token budget) only sees a compact
summary and spends its effort on judgment, not plumbing:

    daily_snapshot(day)          -> readiness vs baseline + today's plan
    sync_since(start, end)       -> week of activities/metrics imported + summary
    push_week(block_id, week)    -> block yml -> verified, scheduled Garmin workouts
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import calc, db, garmin, garmin_live as gl, readiness

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
BODY = ("weight_kg", "body_fat_pct")


# ---------------------------------------------------------------- storage helpers

def store_metrics(con, rows: list[dict]) -> dict:
    """rows: [{date, metric, value, unit?, source?}] -> health_metrics / body_metrics."""
    health, body = [], {}
    for r in rows:
        if r.get("value") is None:
            continue
        if r["metric"] in BODY:
            body.setdefault(r["date"], {"date": r["date"], "source": r.get("source", "garmin")})[r["metric"]] = r["value"]
        else:
            unit = r.get("unit") or readiness.METRICS.get(r["metric"], ("",))[0]
            health.append({"date": r["date"], "metric": r["metric"], "value": r["value"], "unit": unit,
                           "source": r.get("source", "garmin")})
    n = db.upsert(con, "health_metrics", health, ["date", "metric"]) if health else 0
    m = db.upsert(con, "body_metrics", list(body.values()), ["date", "source"]) if body else 0
    return {"health_rows": n, "body_rows": m}


def sync_metrics(con, start: str, end: str, refresh_from: str | None = None) -> dict:
    """Fetch days missing from the db (and always re-fetch days >= refresh_from, since
    Garmin finalizes sleep/HRV late). Returns per-day Garmin context for the last day."""
    have = {r["date"] for r in con.execute(
        "SELECT date FROM health_metrics WHERE date BETWEEN ? AND ? GROUP BY date HAVING count(*) >= 3",
        (start, end))}
    fetched, last_ctx = [], {}
    for day in gl.days(start, end):
        if day in have and not (refresh_from and day >= refresh_from):
            continue
        r = gl.fetch_day(day)
        store_metrics(con, [{"date": day, "metric": k, "value": v} for k, v in r["metrics"].items()])
        fetched.append(day)
        if day == end:
            last_ctx = r["context"]
        gl.pause()
    return {"days_fetched": len(fetched), "context": last_ctx}


def sync_activities(con, start: str, end: str) -> list[dict]:
    """Import Garmin activities in range (idempotent). Strength sets are parsed server-side.
    Effort/feel are re-checked while still missing (athletes often rate later)."""
    imported = []
    for a in gl.list_activities(start, end):
        row = con.execute("SELECT id, rpe FROM workouts WHERE garmin_activity_id=?",
                          (a["garmin_activity_id"],)).fetchone()
        n_sets = con.execute("SELECT count(*) FROM workout_sets WHERE workout_id=?",
                             (row["id"],)).fetchone()[0] if row else 0
        rec = {k: v for k, v in a.items() if v is not None}
        if not row or row["rpe"] is None:
            rec.update(gl.activity_effort(a["garmin_activity_id"]))
        db.upsert(con, "workouts", [rec], ["garmin_activity_id"])
        wid = con.execute("SELECT id FROM workouts WHERE garmin_activity_id=?",
                          (a["garmin_activity_id"],)).fetchone()["id"]
        if a["sport"] == "strength_training" and n_sets == 0:
            sets = garmin.parse_exercise_sets(gl.exercise_sets(a["garmin_activity_id"]))
            if sets:
                db.insert(con, "workout_sets", [dict(s, workout_id=wid) for s in sets])
        imported.append(a["garmin_activity_id"])
        gl.pause()
    return imported


# ---------------------------------------------------------------- plan helpers

def _active_block(root: Path, con, block_id: str | None = None) -> tuple[dict | None, dict | None]:
    sql = "SELECT * FROM training_blocks WHERE id=?" if block_id else \
        "SELECT * FROM training_blocks WHERE status='active' ORDER BY start_date DESC LIMIT 1"
    row = con.execute(sql, (block_id,) if block_id else ()).fetchone()
    blocks_dir = root / "plan" / "blocks"
    path = None
    if row and row["file"]:
        path = blocks_dir / row["file"]
    elif block_id or row:
        bid = block_id or row["id"]
        for p in sorted(blocks_dir.glob("*.yml")):
            if (yaml.safe_load(p.read_text()) or {}).get("id") == bid:
                path = p
                break
    if not path or not path.exists():
        return (dict(row) if row else None), None
    return (dict(row) if row else None), (yaml.safe_load(path.read_text()) or {})


def _start(block: dict, row: dict | None) -> date | None:
    s = str(block.get("start_date") or (row or {}).get("start_date") or "")[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def week_of(block: dict, row: dict | None, day: date) -> int | None:
    s = _start(block, row)
    return None if s is None else (day - s).days // 7 + 1


def _week_key(weeks: dict | None, week: int) -> dict:
    for k, v in (weeks or {}).items():
        m = re.search(r"\d+", str(k))
        if m and int(m.group()) == week:
            return v or {}
    return {}


def prescription(item: dict, week: int) -> dict:
    """An exercise's fields with that week's overrides applied."""
    out = {k: v for k, v in item.items() if k != "weeks"}
    out.update(_week_key(item.get("weeks"), week))
    return out


def session_date(block: dict, row: dict | None, session: dict, week: int) -> date | None:
    if session.get("date"):
        return date.fromisoformat(str(session["date"])[:10])
    s, d = _start(block, row), str(session.get("day", ""))[:3].lower()
    if s is None or d not in WEEKDAYS:
        return None
    return s + timedelta(days=7 * (week - 1) + (WEEKDAYS.index(d) - s.weekday()) % 7)


def _label(p: dict) -> str:
    name = p.get("name") or str(p.get("exercise", "exercise")).replace("_", " ").title()
    s = name
    if p.get("sets") or p.get("reps"):
        s += f" {p.get('sets', 1)}x{p.get('reps') or str(int(p.get('duration_sec', 0))) + 's'}"
    elif p.get("duration_sec"):
        s += f" {int(p['duration_sec'])}s"
    if p.get("weight_kg"):
        s += f" @{p['weight_kg']:g}kg"
    if p.get("rpe"):
        s += f" RPE{p['rpe']:g}"
    return s


def is_test(session: dict) -> bool:
    """Explicit `test: true`, or a name that says test/max/1RM."""
    if "test" in session:
        return bool(session["test"])
    return bool(re.search(r"\b(test|max|1rm)\b", str(session.get("name", "")), re.I))


def session_summary(session: dict, week: int) -> dict:
    out = {"id": session.get("id"), "name": session.get("name"), "kind": session.get("kind", "strength")}
    if out["kind"] == "strength":
        out["exercises"] = [_label(prescription(e, week)) for e in session.get("exercises", [])]
    else:
        out["sport"] = session.get("sport")
        out["structure"] = garmin.endurance_structure(session.get("structure"), _week_key(session.get("weeks"), week))
    if session.get("readiness_gate"):
        out["readiness_gate"] = session["readiness_gate"]
    if is_test(session):
        out["test_day"] = True
    return out


# ---------------------------------------------------------------- readiness formatting

def _compact_readiness(rep: dict) -> dict:
    out = {}
    for m, f in rep["factors"].items():
        if m in ("steps", "acute_load"):
            continue
        e = {"today": f["today"], "mean_7d": f["mean_7d"]}
        if "baseline_mean" in f:
            e["baseline"] = f"{f['baseline_mean']:g}±{f['baseline_sd']:g}"
            e["flag_today"], e["flag_7d"] = f["flag_today"], f["flag_7d"]
            if f.get("bad_days_last_7"):
                e["bad_days_last_7"] = f["bad_days_last_7"]
        if f.get("caveat"):
            e["low_confidence"] = True
        out[m] = e
    return out


def readiness_on(root: Path, day: str) -> dict:
    start = (date.fromisoformat(day) - timedelta(days=70)).isoformat()
    rows = db.query(root, "SELECT date, metric, value FROM health_metrics WHERE date >= ?", [start], limit=100000)
    return readiness.assess(rows, day)


# ---------------------------------------------------------------- 1. daily snapshot

def daily_snapshot(root: Path, day: str = "", backfill_days: int = 0) -> dict:
    con = db.connect(root)
    d = date.fromisoformat(day) if day else date.today()
    days_back = max(7, backfill_days)
    yesterday = (d - timedelta(days=1)).isoformat()
    sync = sync_metrics(con, (d - timedelta(days=days_back)).isoformat(), d.isoformat(), refresh_from=yesterday)
    new_acts = sync_activities(con, yesterday, d.isoformat())
    rep = readiness_on(root, d.isoformat())

    row, block = _active_block(root, con)
    plan, todays = None, []
    if block:
        week = week_of(block, row, d)
        todays = [s for s in block.get("sessions", []) if week and session_date(block, row, s, week) == d]
        plan = {"block": block.get("id"), "block_name": block.get("name"), "week": week,
                "of_weeks": block.get("duration_weeks"),
                "today": [session_summary(s, week) for s in todays] or "rest day (no session planned)",
                "cautions": block.get("cautions") or None}
    proposed = readiness.propose_call(rep, test_day=any(is_test(s) for s in todays))
    gates = [s["readiness_gate"] for s in todays if s.get("readiness_gate")]
    if gates:
        proposed["also_apply_session_gate"] = gates
    injuries = [f"{r['area']} ({r['status']})" for r in con.execute(
        "SELECT area, status FROM injuries WHERE status != 'resolved'")]

    try:
        cal = [f"{s['name']}{' (done)' if s['completed'] else ''}" for s in gl.scheduled(d.isoformat(), d.isoformat())]
    except Exception as e:
        cal = f"unavailable: {e}"
    done_today = [dict(r) for r in con.execute(
        "SELECT name, sport, round(duration_sec/60) AS min, rpe FROM workouts WHERE date=?", (d.isoformat(),))]
    return {
        "date": d.isoformat(), "weekday": d.strftime("%A"),
        "proposed_call": proposed,
        "readiness_vs_your_baseline": _compact_readiness(rep),
        "repeated_deterioration": rep["summary"]["repeated_deterioration"] or None,
        "missing_today": rep["summary"]["missing_today"] or None,
        "garmin_context": sync["context"] or None,
        "plan": plan or "no active block",
        "garmin_calendar_today": cal or "nothing scheduled",
        "already_done_today": done_today or None,
        "open_injuries": injuries or None,
        "sync": {"metric_days_fetched": sync["days_fetched"], "activities_checked": len(new_acts)},
        "how_to_read": "flags compare against the athlete's own 60-day baseline; YELLOW 1-2 SD worse, "
                       "ORANGE >2 SD worse. proposed_call applies the decision table to the data only - "
                       "confirm or override it after asking about pain/illness.",
    }


# ---------------------------------------------------------------- 2. weekly sync

def _strength_lines(con, workout_id: int) -> tuple[list[str], int]:
    rows = con.execute("SELECT category, exercise, weight_kg, reps, duration_sec FROM workout_sets "
                       "WHERE workout_id=? ORDER BY set_order", (workout_id,)).fetchall()
    by: dict[str, list] = {}
    unknown = 0
    for r in rows:
        if not r["exercise"]:
            unknown += 1
            continue
        by.setdefault(r["exercise"], []).append(r)
    lines = []
    for ex, sets in by.items():
        reps = [s["reps"] for s in sets if s["reps"]]
        top = max((s["weight_kg"] or 0) for s in sets)
        if reps:
            rep_txt = f"{reps[0]}" if len(set(reps)) == 1 else "/".join(map(str, reps))
            lines.append(f"{ex} {len(sets)}x{rep_txt}" + (f" @{top:g}kg" if top else ""))
        else:
            lines.append(f"{ex} {len(sets)}x{int(sets[0]['duration_sec'] or 0)}s")
    return lines, unknown


def sync_since(root: Path, start: str = "", end: str = "") -> dict:
    con = db.connect(root)
    end_d = date.fromisoformat(end) if end else date.today()
    if not start:
        last = con.execute("SELECT max(date) FROM checkins WHERE kind='weekly'").fetchone()[0]
        start = last[:10] if last else (end_d - timedelta(days=7)).isoformat()
    end = end_d.isoformat()
    m = sync_metrics(con, (date.fromisoformat(start) - timedelta(days=1)).isoformat(), end,
                     refresh_from=(end_d - timedelta(days=1)).isoformat())
    sync_activities(con, start, end)
    endu = gl.fetch_endurance(end)
    vo2 = endu["vo2max"]
    acute = (endu["context"].get("training_status") or {}).get("acute_load")
    store_metrics(con, [{"date": end, "metric": k, "value": v} for k, v in vo2.items()] +
                  ([{"date": end, "metric": "acute_load", "value": acute}] if acute is not None else []))

    planned = [dict(r) for r in con.execute(
        "SELECT garmin_workout_id, name, block_id, week, session, scheduled_date FROM garmin_workouts "
        "WHERE status='scheduled' AND scheduled_date BETWEEN ? AND ? ORDER BY scheduled_date", (start, end))]
    acts = [dict(r) for r in con.execute(
        "SELECT * FROM workouts WHERE date BETWEEN ? AND ? ORDER BY date", (start, end))]
    done_ids = {a["garmin_workout_id"] for a in acts if a.get("garmin_workout_id")}

    sessions, rpe_points, unknown_total = [], [], 0
    for a in acts:
        s = {"date": a["date"], "name": a["name"], "sport": a["sport"],
             "min": round((a["duration_sec"] or 0) / 60), "rpe": a["rpe"], "feel": a["feel"]}
        if a.get("distance_m"):
            s["km"] = round(a["distance_m"] / 1000, 2)
        if a.get("avg_hr"):
            s["avg_hr"] = a["avg_hr"]
        plan_match = next((p for p in planned if p["garmin_workout_id"] == a.get("garmin_workout_id")), None)
        s["planned"] = f"{plan_match['session']} wk{plan_match['week']}" if plan_match else \
            ("started from a Garmin workout not registered by the coach" if a.get("garmin_workout_id") else "unplanned")
        if a["sport"] == "strength_training":
            lines, unknown = _strength_lines(con, a["id"])
            s["sets"] = lines
            if unknown:
                s["unclassified_sets"] = unknown
                unknown_total += unknown
            top = con.execute("SELECT max(weight_kg) FROM workout_sets WHERE workout_id=?", (a["id"],)).fetchone()[0]
            if top:
                rpe_points.append((top, a["rpe"]))
        sessions.append(s)

    missed = [f"{p['scheduled_date']} {p['name']}" for p in planned
              if p["garmin_workout_id"] not in done_ids and p["scheduled_date"] < end]
    rated = [r for _, r in rpe_points if r is not None]
    if not rpe_points:
        rpe_note = "no strength sessions"
    elif not rated:
        rpe_note = "effort never rated on the watch - ask the athlete for RPE per session"
    elif len(rated) >= 3 and len(set(rated)) == 1 and len({w for w, _ in rpe_points}) > 1:
        rpe_note = f"effort stuck at {rated[0]:g} across different loads - likely not logged deliberately"
    else:
        rpe_note = f"rated {len(rated)}/{len(rpe_points)} strength sessions"

    def wavg(a, b):
        r = con.execute("SELECT avg(weight_kg) FROM body_metrics WHERE date BETWEEN ? AND ?", (a, b)).fetchone()[0]
        return round(r, 2) if r else None
    w_now = wavg((end_d - timedelta(days=6)).isoformat(), end)
    w_prev = wavg((end_d - timedelta(days=13)).isoformat(), (end_d - timedelta(days=7)).isoformat())

    rep = readiness_on(root, end)
    done_planned = len(done_ids & {p["garmin_workout_id"] for p in planned})
    due = done_planned + len(missed)  # today's session isn't missed yet
    return {
        "range": [start, end],
        "adherence": {"planned": len(planned), "done_as_planned": done_planned,
                      "rate": round(done_planned / due, 2) if due else None,
                      "missed": missed or None, "total_sessions": len(acts)},
        "sessions": sessions,
        "effort_logging": rpe_note,
        "unclassified_sets_total": unknown_total or None,
        "recovery_7d_vs_baseline": _compact_readiness(rep),
        "repeated_deterioration": rep["summary"]["repeated_deterioration"] or None,
        "garmin_hrv_status": gl.fetch_hrv_status(end),
        "body_weight_avg": {"last_7d": w_now, "prev_7d": w_prev,
                            "change": round(w_now - w_prev, 2) if w_now and w_prev else None},
        "vo2max": vo2 or None,
        "garmin_endurance": endu["context"] or None,
        "open_injuries": [dict(r) for r in con.execute(
            "SELECT area, status, severity FROM injuries WHERE status != 'resolved'")] or None,
        "block": _block_outlook(root, con, end_d),
        "sync": {"metric_days_fetched": m["days_fetched"], "activities": len(acts)},
    }


def _block_outlook(root: Path, con, day: date) -> dict | None:
    """Where the active block stands, and next week's sessions with their Garmin push status."""
    row, block = _active_block(root, con)
    if not block:
        return None
    week = week_of(block, row, day) or 1
    nxt = week + 1
    dur = block.get("duration_weeks")
    pushed = {r["session"] for r in con.execute(
        "SELECT session FROM garmin_workouts WHERE block_id=? AND week=? AND status='scheduled'",
        (block.get("id"), nxt))}
    sessions = []
    if not dur or nxt <= dur:
        for sess in block.get("sessions", []):
            when = session_date(block, row, sess, nxt)
            sessions.append({**session_summary(sess, nxt), "date": when.isoformat() if when else None,
                             "on_garmin": sess.get("id") in pushed})
    return {"id": block.get("id"), "name": block.get("name"), "week": week, "of_weeks": dur,
            "ends_after_this_week": bool(dur and week >= dur),
            "exit_criteria": block.get("exit_criteria") or None, "cautions": block.get("cautions") or None,
            "next_week": sessions or None}


WEEKLY_STATUS = ["AHEAD", "ON TRACK", "SLIGHTLY BEHIND", "SIGNIFICANTLY BEHIND", "AT RISK"]


def propose_weekly(summary: dict, rep: dict, goals: list[dict], today: date | None = None) -> dict:
    """Draft weekly status + risk from data only (adherence, goal trends, recovery, injuries).
    Athlete-reported context (pain, illness, life) is not known here, so it is a draft."""
    today = today or date.today()
    rec = {m: rep["factors"][m] for m in readiness.RECOVERY if m in rep["factors"]}
    orange_7d = [m for m, f in rec.items() if f.get("flag_7d") == "ORANGE"]
    yellow_7d = [m for m, f in rec.items() if f.get("flag_7d") == "YELLOW"]
    repeated = [m for m in rep["summary"]["repeated_deterioration"] if m in rec]
    injuries = summary.get("open_injuries") or []
    active_inj = [i["area"] for i in injuries if i["status"] == "active"]

    why_risk = []
    if len(orange_7d) >= 2 or len(repeated) >= 2 or active_inj:
        risk = "ORANGE"
        why_risk += [f"7-day ORANGE: {', '.join(orange_7d)}"] if len(orange_7d) >= 2 else []
        why_risk += [f"3+ bad days in 7: {', '.join(repeated)}"] if len(repeated) >= 2 else []
        why_risk += [f"active injury: {', '.join(active_inj)}"] if active_inj else []
    elif orange_7d or len(yellow_7d) >= 2 or repeated or injuries:
        risk = "YELLOW"
        why_risk += [f"7-day ORANGE: {', '.join(orange_7d)}"] if orange_7d else []
        why_risk += [f"7-day YELLOW: {', '.join(yellow_7d)}"] if len(yellow_7d) >= 2 else []
        why_risk += [f"3+ bad days in 7: {', '.join(repeated)}"] if repeated else []
        why_risk += [f"injury being monitored: {', '.join(i['area'] for i in injuries)}"] if injuries else []
    else:
        risk = "GREEN"
        why_risk.append("recovery near baseline, no open injuries")

    rate = summary["adherence"]["rate"]
    away, late, early, measured = [], [], [], 0
    for g in goals:
        slope, rem = g.get("trend_per_week"), g.get("remaining")
        if slope is None or rem is None:
            continue
        measured += 1
        if rem and slope and (rem > 0) != (slope > 0):
            away.append(g["goal"])
        elif g.get("target_date") and g.get("naive_weeks_to_target") is not None:
            left = (date.fromisoformat(str(g["target_date"])[:10]) - today).days / 7
            if g["naive_weeks_to_target"] > left:
                late.append(g["goal"])
            elif g["naive_weeks_to_target"] < 0.8 * left:
                early.append(g["goal"])

    why = []
    if rate is None and not measured:
        status = None
        why.append("no planned sessions due and no goal with a measured trend - classify from the conversation")
    elif risk == "ORANGE" and ((rate is not None and rate < 0.5) or away):
        status = "AT RISK"
    elif (rate is not None and rate < 0.5) or away:
        status = "SIGNIFICANTLY BEHIND"
    elif (rate is not None and rate < 0.8) or late:
        status = "SLIGHTLY BEHIND"
    elif measured and early and not late and len(early) == measured and (rate is None or rate >= 0.8):
        status = "AHEAD"
    else:
        status = "ON TRACK"
    if rate is not None:
        why.append(f"adherence {rate:.0%} of due planned sessions")
    why += [f"moving away from target: {', '.join(away)}"] if away else []
    why += [f"projected after target date: {', '.join(late)}"] if late else []
    why += [f"projected well before target date: {', '.join(early)}"] if early else []
    return {"status": status, "risk": risk, "status_reasons": why, "risk_reasons": why_risk,
            "not_checked": "pain, illness, life stress, sessions done without starting the Garmin workout, "
                           "goals without an automatic series (skills, race times) - ask and adjust; "
                           "RED risk comes only from reported red-flag symptoms"}


# ---------------------------------------------------------------- 3. push week

def _flatten(steps: list) -> list[tuple]:
    out = []
    for s in steps:
        if s.get("type") == "RepeatGroupDTO":
            out.append(("repeat", int(s.get("numberOfIterations") or 0)))
            out.extend(_flatten(s.get("workoutSteps") or []))
        else:
            ev = s.get("endConditionValue")
            out.append(((s.get("stepType") or {}).get("stepTypeKey"), s.get("category"), s.get("exerciseName"),
                        round(float(s["weightValue"]), 2) if s.get("weightValue") else None,
                        round(float(ev)) if ev else None, _target_of(s)))
    return out


def _target_of(step: dict) -> tuple | None:
    key = (step.get("targetType") or {}).get("workoutTargetTypeKey")
    if key in (None, "no.target"):
        return None
    if step.get("zoneNumber"):
        return key, int(step["zoneNumber"])
    return key, *(round(float(step[k]), 3) if step.get(k) is not None else None
                  for k in ("targetValueOne", "targetValueTwo"))


def verify(built: dict, fetched: dict) -> list[str]:
    a = _flatten(built["workoutSegments"][0]["workoutSteps"])
    b = _flatten((fetched.get("workoutSegments") or [{}])[0].get("workoutSteps") or [])
    if a == b:
        return []
    diffs = [f"step {i + 1}: planned {x} got {y}" for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(a) != len(b):
        diffs.append(f"step count planned {len(a)} got {len(b)}")
    return diffs[:10]


def build_session(s: dict, name: str, week: int) -> dict:
    """Block session -> garmin.build_* result. ValueError if it can't be pushed."""
    if s.get("kind", "strength") == "strength":
        exercises = []
        for e in s.get("exercises", []):
            p = prescription(e, week)
            g = p.get("garmin") or {}
            exercises.append({k: v for k, v in {
                "name": p.get("name") or str(p.get("exercise", "")).replace("_", " ").title(),
                "category": g.get("category"), "exercise": g.get("exercise"),
                "sets": p.get("sets"), "reps": p.get("reps"), "duration_sec": p.get("duration_sec"),
                "weight_kg": p.get("weight_kg"), "rest_sec": p.get("rest_sec"), "note": p.get("note"),
                "plain": p.get("plain"),
            }.items() if v is not None})
        if not exercises:
            raise ValueError("strength session has no exercises")
        return garmin.build_strength_workout(name, exercises, warmup=s.get("warmup", True),
                                             cooldown=s.get("cooldown", False))
    if not s.get("structure"):
        raise ValueError(f"{s.get('kind')} session has no `structure` to build a Garmin workout from")
    return garmin.build_endurance_workout(name, s.get("sport", "running"),
                                          garmin.endurance_structure(s["structure"], _week_key(s.get("weeks"), week)))


def push_week(root: Path, block_id: str = "", week: int = 0, dates: dict | None = None,
              dry_run: bool = False, include_past: bool = False) -> dict:
    con = db.connect(root)
    row, block = _active_block(root, con, block_id or None)
    if not block:
        return {"error": f"block {block_id or '(active)'} not found - check training_blocks.file / plan/blocks"}
    bid = block.get("id") or (row or {}).get("id")
    today = date.today()
    week = week or week_of(block, row, today) or 1
    results = []
    for s in block.get("sessions", []):
        sid = s.get("id") or re.sub(r"\W+", "_", str(s.get("name", "session"))).lower()
        when = date.fromisoformat(dates[sid]) if dates and sid in dates else session_date(block, row, s, week)
        res = {"session": sid, "date": when.isoformat() if when else None}
        if when is None:
            res["status"] = "skipped: no date (set block start_date + session day, or pass dates)"
            results.append(res)
            continue
        if when < today and not include_past:
            res["status"] = "skipped: date is in the past"
            results.append(res)
            continue
        day_label = when.strftime("%a")
        name = f"{day_label} - {s.get('name', sid)}".replace(f"{day_label} - {day_label} - ", f"{day_label} - ")
        name = f"{name} (wk{week})"[:80]
        try:
            built = build_session(s, name, week)
        except ValueError as e:
            res["status"] = f"skipped: {e}"
            results.append(res)
            continue
        workout = built["workout"]
        h = hashlib.sha256(json.dumps(workout, sort_keys=True).encode()).hexdigest()[:16]
        res.update(name=name, steps=built["step_count"], warnings=built["warnings"] or None)
        old = [dict(r) for r in con.execute(
            "SELECT * FROM garmin_workouts WHERE block_id=? AND week=? AND session=? AND status='scheduled'",
            (bid, week, sid))]
        same = next((o for o in old if o["payload_hash"] == h and o["scheduled_date"] == when.isoformat()), None)

        if dry_run:
            res["status"] = "would keep (unchanged)" if same else \
                ("would replace " + ", ".join(o["garmin_workout_id"] for o in old) if old else "would create")
            results.append(res)
            continue
        if same:
            gl.schedule(same["garmin_workout_id"], when.isoformat())  # self-heal if removed from calendar
            res["status"] = "unchanged (kept existing template)"
            res["garmin_workout_id"] = same["garmin_workout_id"]
            results.append(res)
            continue

        new_id = gl.upload(workout)
        problems = verify(workout, gl.get_workout(new_id))
        if problems:
            gl.delete(new_id)
            res.update(status="FAILED verification - upload removed", problems=problems)
            results.append(res)
            continue
        gl.schedule(new_id, when.isoformat())
        db.insert(con, "garmin_workouts", [{"garmin_workout_id": new_id, "name": name, "block_id": bid,
                                            "week": week, "session": sid, "scheduled_date": when.isoformat(),
                                            "payload_hash": h}])
        replaced = []
        for o in old:
            for entry in gl.scheduled(o["scheduled_date"], o["scheduled_date"]):
                if entry["workout_id"] == o["garmin_workout_id"] and not entry["completed"]:
                    gl.unschedule(entry["scheduled_workout_id"])
            still_used = con.execute("SELECT count(*) FROM garmin_workouts WHERE garmin_workout_id=? AND "
                                     "status='scheduled' AND id != ?", (o["garmin_workout_id"], o["id"])).fetchone()[0]
            if not still_used:
                gl.delete(o["garmin_workout_id"])
            db.update(con, "garmin_workouts", o["id"], {"status": "replaced"})
            replaced.append(o["garmin_workout_id"])
        others = [e["name"] for e in gl.scheduled(when.isoformat(), when.isoformat())
                  if e["workout_id"] != new_id and e["workout_id"] not in replaced]
        res.update(status="created, verified, scheduled", garmin_workout_id=new_id,
                   replaced=replaced or None,
                   other_workouts_that_day=others or None)
        results.append(res)
    return {"block": bid, "week": week, "dry_run": dry_run, "sessions": results}


# ---------------------------------------------------------------- 4. validate block

def _implement_for(exercise: dict, loads: dict) -> tuple[str | None, dict | None]:
    name = exercise.get("implement") or next(
        (k for k in ("barbell", "dumbbell", "kettlebell", "cable") if k in str(exercise.get("exercise", "")).lower()
         or k in str((exercise.get("garmin") or {}).get("exercise", "")).lower()), None)
    return name, loads.get(name) if name else None


def _strength_minutes(s: dict, week: int) -> float:
    sec = 300.0 if s.get("warmup", True) else 0.0
    for e in s.get("exercises", []):
        p = prescription(e, week)
        sets = int(p.get("sets") or 1)
        work = float(p.get("duration_sec") or 0) or 4 * float(p.get("reps") or 8) + 15
        sec += sets * work + max(sets - 1, 0) * float(p.get("rest_sec") or 90) + 60  # +1 min changeover
    return sec / 60


def _endurance_minutes(st: dict) -> float | None:
    def part(p):
        if not p:
            return 0.0
        if p.get("distance_km"):
            raise LookupError
        return float(p.get("duration_sec") or 0) / 60 + float(p.get("duration_min") or 0)
    try:
        iv = st.get("intervals") or {}
        reps = int(iv.get("repeats") or 1)
        return part(st.get("warmup")) + part(st.get("main")) + part(st.get("cooldown")) + \
            reps * (part(iv.get("work")) + part(iv.get("recovery")))
    except LookupError:
        return None  # distance steps: duration depends on pace


def validate_block(root: Path, block: str = "") -> dict:
    """Check a block yml before it is activated or pushed. block: file name under plan/blocks,
    block id, or empty for the active block. Builds every session for every week."""
    con = db.connect(root)
    blocks_dir = root / "plan" / "blocks"
    path = None
    if block.endswith((".yml", ".yaml")):
        path = blocks_dir / Path(block).name
    else:
        row, _ = _active_block(root, con, block or None)
        if row and row.get("file"):
            path = blocks_dir / row["file"]
        else:
            for p in sorted(blocks_dir.glob("*.yml")):
                if (yaml.safe_load(p.read_text()) or {}).get("id") == (block or (row or {}).get("id")):
                    path = p
    if not path or not path.exists():
        return {"ok": False, "errors": [f"block {block or '(active)'} not found under plan/blocks"]}
    errors, warnings = [], []
    try:
        b = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        return {"ok": False, "file": path.name, "errors": [f"yml does not parse: {e}"]}

    for k in ("id", "name", "start_date", "duration_weeks", "sessions"):
        if not b.get(k):
            errors.append(f"missing top-level `{k}`")
    start = _start(b, None)
    if b.get("start_date") and start is None:
        errors.append(f"start_date {b['start_date']!r} is not YYYY-MM-DD")
    elif start and start.weekday() != 0:
        warnings.append(f"start_date {start} is a {start:%A}; weeks count from it, so 'week 1' starts mid-week")
    try:
        weeks = int(b.get("duration_weeks") or 0)
    except (TypeError, ValueError):
        weeks = 0
        errors.append("duration_weeks must be a whole number")
    if not b.get("exit_criteria"):
        warnings.append("no exit_criteria: the weekly check-in can't tell when the block is done")
    row = con.execute("SELECT file, status FROM training_blocks WHERE id=?", (b.get("id"),)).fetchone()
    if not row:
        warnings.append(f"block {b.get('id')} is not in the database: call upsert_training_block(file={path.name!r})")
    elif row["file"] != path.name:
        warnings.append(f"training_blocks.file is {row['file']!r}, expected {path.name!r}")

    root_cfg = root / "athlete"
    sched = yaml.safe_load((root_cfg / "schedule.yml").read_text()) if (root_cfg / "schedule.yml").exists() else {}
    loads = (yaml.safe_load((root_cfg / "equipment.yml").read_text()) or {}).get("loads") or {} \
        if (root_cfg / "equipment.yml").exists() else {}
    cap = sched.get("session_length_min") if isinstance(sched.get("session_length_min"), (int, float)) else None
    pref = [str(d)[:3].lower() for d in sched.get("preferred_days") or []] \
        if isinstance(sched.get("preferred_days"), list) else []

    seen = set()
    sessions = b.get("sessions") or []
    for i, s in enumerate(sessions):
        sid = s.get("id") or f"session[{i}]"
        where = f"{sid}:"
        if not s.get("id"):
            errors.append(f"{where} missing `id`")
        elif sid in seen:
            errors.append(f"{where} duplicate id")
        seen.add(sid)
        day = str(s.get("day", ""))[:3].lower()
        if not s.get("date") and day not in WEEKDAYS:
            errors.append(f"{where} `day` must be a weekday name (got {s.get('day')!r})")
        elif pref and day and day not in pref:
            warnings.append(f"{where} {s.get('day')} is not in schedule.yml preferred_days")
        for wk in (s.get("weeks") or {}):
            n = re.search(r"\d+", str(wk))
            if weeks and n and int(n.group()) > weeks:
                warnings.append(f"{where} has an override for week {wk} but the block is {weeks} weeks")
        kind = s.get("kind", "strength")
        if kind != "strength" and not s.get("structure"):
            warnings.append(f"{where} no `structure`: shown in the plan but not pushed to Garmin")
            continue
        prev: dict[str, float] = {}
        for week in range(1, max(weeks, 1) + 1):
            tag = f"{where} wk{week}"
            try:
                built = build_session(s, f"check {sid}", week)
            except (ValueError, KeyError, TypeError) as e:
                errors.append(f"{tag} can't be built for Garmin: {e}")
                break
            for w in built["warnings"]:  # a wrong key or target loses intent silently; a missing mapping doesn't
                bad = "not in Garmin's taxonomy" in w or "not understood" in w
                (errors if bad else warnings).append(f"{tag} {w}")
            if kind == "strength":
                minutes = _strength_minutes(s, week)
                for e in s.get("exercises", []):
                    p = prescription(e, week)
                    ex = p.get("exercise") or p.get("name") or "exercise"
                    if not (p.get("reps") or p.get("duration_sec")):
                        errors.append(f"{tag} {ex}: needs reps or duration_sec")
                    if not p.get("sets"):
                        warnings.append(f"{tag} {ex}: no sets (1 assumed)")
                    if p.get("pct_1rm") and float(p["pct_1rm"]) > 1.0:
                        errors.append(f"{tag} {ex}: pct_1rm {p['pct_1rm']} > 1.0 (write 0.85, not 85)")
                    if p.get("pct_1rm") and not p.get("weight_kg"):
                        errors.append(f"{tag} {ex}: pct_1rm without weight_kg (use prescribe_load)")
                    if p.get("rpe") is not None and not 5 <= float(p["rpe"]) <= 10:
                        errors.append(f"{tag} {ex}: rpe {p['rpe']} outside 5-10")
                    elif p.get("rpe") and float(p["rpe"]) > 9.5 and not is_test(s):
                        warnings.append(f"{tag} {ex}: RPE {p['rpe']} outside a test session")
                    w = p.get("weight_kg")
                    if w:
                        imp_name, imp = _implement_for(p, loads)
                        if imp:
                            r = calc.round_load(float(w), imp)
                            if abs(r["load"] - float(w)) > 0.01:
                                warnings.append(f"{tag} {ex}: {w:g}kg isn't buildable on your {imp_name} "
                                                f"(nearest {r['load']:g}kg)")
                        if ex in prev and prev[ex] and float(w) > prev[ex] * 1.10:
                            warnings.append(f"{tag} {ex}: load jumps {prev[ex]:g} -> {w:g}kg (>10% in a week)")
                        prev[ex] = float(w)
            else:
                minutes = _endurance_minutes(garmin.endurance_structure(s.get("structure"),
                                                                         _week_key(s.get("weeks"), week)))
            if cap and minutes and minutes > cap * 1.15:
                warnings.append(f"{tag} estimated {minutes:.0f} min vs session_length_min {cap}")
    if pref and len(sessions) and isinstance(sched.get("sessions_per_week"), int) \
            and len(sessions) > sched["sessions_per_week"]:
        warnings.append(f"{len(sessions)} sessions/week vs schedule.yml sessions_per_week "
                        f"{sched['sessions_per_week']}")
    return {"ok": not errors, "file": path.name, "block": b.get("id"), "weeks_checked": weeks,
            "sessions": len(sessions), "errors": _dedupe_weeks(errors) or None,
            "warnings": _dedupe_weeks(warnings) or None}


def _dedupe_weeks(items: list[str]) -> list[str]:
    """The same problem in every week -> one line with a count."""
    counts: dict[str, int] = {}
    first: dict[str, str] = {}
    for it in items:
        key = re.sub(r" wk\d+", "", it, count=1)
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, it)
    return [first[k] + (f" (+{n - 1} more weeks)" if n > 1 else "") for k, n in counts.items()]


# ---------------------------------------------------------------- 5. setup history

def history(root: Path, weeks: int = 12, backfill_days: int = 60) -> dict:
    """First-setup pull: profile and watch, recovery baselines, the last `weeks` of training
    imported and summarized, strength top sets, endurance context, body weight."""
    con = db.connect(root)
    today = date.today()
    start = (today - timedelta(weeks=weeks)).isoformat()
    profile = gl.fetch_profile(today.isoformat())
    m = sync_metrics(con, (today - timedelta(days=backfill_days)).isoformat(), today.isoformat())
    sync_activities(con, start, today.isoformat())
    endu = gl.fetch_endurance(today.isoformat())
    store_metrics(con, [{"date": today.isoformat(), "metric": k, "value": v} for k, v in endu["vo2max"].items()])

    acts = [dict(r) for r in con.execute(
        "SELECT * FROM workouts WHERE date >= ? ORDER BY date", (start,))]
    by_sport: dict[str, list] = {}
    for a in acts:
        by_sport.setdefault(a["sport"] or "other", []).append(a)
    training = {}
    for sport, xs in sorted(by_sport.items(), key=lambda kv: -len(kv[1])):
        days = [date.fromisoformat(a["date"]).strftime("%a") for a in xs if a["date"]]
        common = sorted(set(days), key=lambda d: -days.count(d))[:4]
        t = {"sessions": len(xs), "per_week": round(len(xs) / weeks, 1),
             "avg_min": round(sum(a["duration_sec"] or 0 for a in xs) / len(xs) / 60),
             "usual_days": common}
        km = [a["distance_m"] / 1000 for a in xs if a.get("distance_m")]
        if km:
            t["avg_km"] = round(sum(km) / len(km), 1)
        hr = [a["avg_hr"] for a in xs if a.get("avg_hr")]
        if hr:
            t["avg_hr"] = round(sum(hr) / len(hr))
        training[sport] = t

    lifts = []
    rows = con.execute(
        "SELECT s.exercise, s.weight_kg, s.reps, w.date FROM workout_sets s JOIN workouts w ON w.id = s.workout_id "
        "WHERE w.date >= ? AND s.exercise IS NOT NULL", (start,)).fetchall()
    by_ex: dict[str, list] = {}
    for r in rows:
        by_ex.setdefault(r["exercise"], []).append(r)
    for ex, sets in sorted(by_ex.items(), key=lambda kv: -len({r["date"] for r in kv[1]}))[:10]:
        weighted = [r for r in sets if r["weight_kg"] and r["reps"]]
        item = {"exercise": ex, "sessions": len({r["date"] for r in sets})}
        if weighted:
            top = max(weighted, key=lambda r: (r["weight_kg"], r["reps"]))
            best = max(weighted, key=lambda r: calc.e1rm(r["weight_kg"], r["reps"])["e1rm"] if r["reps"] <= 10 else 0)
            item["heaviest"] = f"{top['weight_kg']:g}kg x{top['reps']} ({top['date']})"
            if best["reps"] <= 10:
                item["e1rm_floor"] = calc.e1rm(best["weight_kg"], best["reps"])["e1rm"]
        else:
            reps = [r["reps"] for r in sets if r["reps"]]
            if reps:
                item["best_reps"] = max(reps)
        lifts.append(item)
    total_sets = con.execute("SELECT count(*) FROM workout_sets s JOIN workouts w ON w.id = s.workout_id "
                             "WHERE w.date >= ?", (start,)).fetchone()[0]
    unknown = con.execute("SELECT count(*) FROM workout_sets s JOIN workouts w ON w.id = s.workout_id "
                          "WHERE w.date >= ? AND s.exercise IS NULL", (start,)).fetchone()[0]
    strength = [a for a in acts if a["sport"] == "strength_training"]
    rated = [a["rpe"] for a in strength if a["rpe"] is not None]

    rep = readiness_on(root, today.isoformat())
    baselines = {}
    for metric, f in rep["factors"].items():
        if metric in readiness.RECOVERY and "baseline_mean" in f:
            baselines[metric] = f"{round(f['baseline_mean'], 1):g}±{round(f['baseline_sd'], 1):g} (n={f['baseline_n']})"
    w = con.execute("SELECT date, weight_kg FROM body_metrics WHERE weight_kg IS NOT NULL AND date >= ? "
                    "ORDER BY date", (start,)).fetchall()
    return {
        "profile": profile,
        "training_last_weeks": {"weeks": weeks, "by_sport": training or "no activities recorded"},
        "strength_top_exercises": lifts or None,
        "strength_data_quality": {
            "sets_logged": total_sets, "unclassified_sets": unknown,
            "effort_rated": f"{len(rated)}/{len(strength)} sessions" if strength else None,
            "effort_varies": len(set(rated)) > 1 if len(rated) >= 3 else None,
        } if strength else None,
        "recovery_baselines": baselines or "not enough days yet",
        "garmin_endurance": {**({"vo2max": endu["vo2max"]} if endu["vo2max"] else {}), **endu["context"]} or None,
        "body_weight": {"first": f"{w[0]['weight_kg']:g}kg ({w[0]['date']})",
                        "latest": f"{w[-1]['weight_kg']:g}kg ({w[-1]['date']})"} if w else None,
        "sync": {"metric_days_fetched": m["days_fetched"], "activities_imported": len(acts)},
        "how_to_read": "e1rm_floor assumes every set went to failure, so the true max is likely higher; "
                       "confirm numbers with the athlete. watch_cannot_measure lists metrics never to ask "
                       "Garmin for or report as missing.",
    }


# ---------------------------------------------------------------- 6. on-demand lookups

LOOKUPS = {"hr_zones": 0, "nutrition": 14, "vo2max_trend": 84}  # topic -> default days back


def lookup(root: Path, topic: str, start: str = "", end: str = "") -> dict:
    """Occasional Garmin data, pre-parsed: hr_zones, nutrition, vo2max_trend."""
    if topic not in LOOKUPS:
        return {"error": f"unknown topic {topic!r}; one of {sorted(LOOKUPS)}"}
    end_d = date.fromisoformat(end) if end else date.today()
    start_d = date.fromisoformat(start) if start else end_d - timedelta(days=LOOKUPS[topic] - 1)
    if topic == "hr_zones":
        zones = gl.fetch_hr_zones()
        return {"hr_zones": zones or "no zones saved in Garmin",
                "note": "workout targets use these zones on the watch: hr_zone N in a block structure means "
                        "the athlete's own ZN range here"}
    if topic == "nutrition":
        start_d = max(start_d, end_d - timedelta(days=60))
        days = gl.fetch_nutrition(start_d.isoformat(), end_d.isoformat())
        logged = [d for d in days if d["items"] >= 3 and d["kcal"]]
        partial = [d["date"] for d in days if 0 < d["items"] < 3]
        def avg(k):
            xs = [d[k] for d in logged if d[k] is not None]
            return round(sum(xs) / len(xs)) if xs else None
        return {"range": [start_d.isoformat(), end_d.isoformat()],
                "days_logged": len(logged), "days_in_range": (end_d - start_d).days + 1,
                "avg_on_logged_days": {k: avg(k) for k in ("kcal", "protein_g", "carbs_g", "fat_g")} if logged else None,
                "partial_days": partial or None,
                "days": days or "nothing logged in Garmin for this range",
                "note": "averages use days with 3+ logged items only; partial days read as low intake"}
    # vo2max_trend
    start_d = max(start_d, end_d - timedelta(days=89))
    pts = gl.fetch_vo2max_history(start_d.isoformat(), end_d.isoformat())
    source = "garmin"
    if not pts:  # fall back to what earlier syncs stored
        rows = db.connect(root).execute(
            "SELECT date, metric, value FROM health_metrics WHERE metric IN ('vo2max', 'vo2max_cycling') "
            "AND date BETWEEN ? AND ? ORDER BY date", (start_d.isoformat(), end_d.isoformat())).fetchall()
        by: dict[str, dict] = {}
        for r in rows:
            by.setdefault(r["date"], {"date": r["date"]})[r["metric"]] = r["value"]
        pts, source = list(by.values()), "coach database"
    else:
        store_metrics(db.connect(root), [{"date": p["date"], "metric": k, "value": v}
                                         for p in pts for k, v in p.items() if k != "date"])
    out = {"range": [start_d.isoformat(), end_d.isoformat()], "source": source,
           "points": pts or "no VO2max recorded (needs outdoor runs/rides with GPS and HR)"}
    for k in ("vo2max", "vo2max_cycling"):
        xs = [p[k] for p in pts if k in p]
        if len(xs) >= 2:
            out[f"{k}_change"] = round(xs[-1] - xs[0], 1)
    out["note"] = "changes under 0.5 are noise; read the 4-6 week direction"
    return out
