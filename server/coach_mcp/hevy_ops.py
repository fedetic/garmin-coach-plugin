"""Compound coach operations for athletes who log their lifting in Hevy.

Same idea as ops.py (one call returns a compact, parsed summary) but with no
wearable assumed: recovery comes from what the athlete says, training comes from
the Hevy workouts they logged, and the plan goes back into Hevy as routines.

    hevy_history(weeks)            -> first-setup picture from Hevy
    hevy_sync_since(start, end)    -> week of workouts imported + adherence summary
    hevy_push_week(block, week)    -> block yml week -> verified Hevy routines
    daily_context(day)             -> today's plan and context for the no-wearable daily check
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from . import calc, db, hevy as hv, ops, workspace

DEFAULT_FOLDER = "Coach"


# ---------------------------------------------------------------- import

def import_workouts(con, workouts: list[dict]) -> int:
    """Upsert Hevy workouts and replace their sets (athletes edit workouts after the fact)."""
    for w in workouts:
        row, sets = hv.parse_workout(w)
        db.upsert(con, "workouts", [{k: v for k, v in row.items() if v is not None}], ["hevy_workout_id"])
        wid = con.execute("SELECT id FROM workouts WHERE hevy_workout_id=?", (row["hevy_workout_id"],)).fetchone()["id"]
        con.execute("DELETE FROM workout_sets WHERE workout_id=?", (wid,))
        con.commit()
        if sets:
            db.insert(con, "workout_sets", [dict(s, workout_id=wid) for s in sets])
    return len(workouts)


def merge_duplicates(con, start: str, end: str) -> int:
    """An athlete with both a Garmin watch and Hevy has each lifting session twice (a Garmin activity
    and a Hevy workout). When a day has exactly one of each, keep the Garmin row (heart rate, calories)
    and give it Hevy's sets and ids: Hevy's sets are what the athlete typed, the watch only counts reps."""
    merged = 0
    days = [r[0] for r in con.execute(
        "SELECT date FROM workouts WHERE date BETWEEN ? AND ? AND sport='strength_training' GROUP BY date "
        "HAVING sum(hevy_workout_id IS NOT NULL AND garmin_activity_id IS NULL) = 1 "
        "AND sum(garmin_activity_id IS NOT NULL AND hevy_workout_id IS NULL) = 1 AND count(*) = 2", (start, end))]
    for d in days:
        h = con.execute("SELECT * FROM workouts WHERE date=? AND hevy_workout_id IS NOT NULL "
                        "AND garmin_activity_id IS NULL", (d,)).fetchone()
        g = con.execute("SELECT * FROM workouts WHERE date=? AND garmin_activity_id IS NOT NULL "
                        "AND hevy_workout_id IS NULL AND sport='strength_training'", (d,)).fetchone()
        con.execute("DELETE FROM workout_sets WHERE workout_id=?", (g["id"],))
        con.execute("UPDATE workout_sets SET workout_id=? WHERE workout_id=?", (g["id"], h["id"]))
        con.execute("DELETE FROM workouts WHERE id=?", (h["id"],))
        con.execute("UPDATE workouts SET hevy_workout_id=?, hevy_routine_id=?, name=COALESCE(?, name) WHERE id=?",
                    (h["hevy_workout_id"], h["hevy_routine_id"], h["name"], g["id"]))
        merged += 1
    con.commit()
    return merged


def import_body(con, start: str, end: str) -> int:
    rows = []
    for m in hv.body_measurements(start, end):
        rows += [{"date": m["date"], "metric": k, "value": m[k], "source": "hevy"}
                 for k in ("weight_kg", "body_fat_pct") if m.get(k) is not None]
    ops.store_metrics(con, rows)
    return len({r["date"] for r in rows})


# ---------------------------------------------------------------- 1. first-setup history

def history(root: Path, weeks: int = 12) -> dict:
    con = db.connect(root)
    today = date.today()
    start = (today - timedelta(weeks=weeks)).isoformat()
    info = hv.user_info()
    n = import_workouts(con, hv.list_workouts(start, today.isoformat()))
    bodies = import_body(con, start, today.isoformat())
    merge_duplicates(con, start, today.isoformat())

    acts = [dict(r) for r in con.execute(
        "SELECT * FROM workouts WHERE date >= ? AND hevy_workout_id IS NOT NULL ORDER BY date", (start,))]
    days = [date.fromisoformat(a["date"]).strftime("%a") for a in acts if a["date"]]
    training = {
        "sessions": len(acts), "per_week": round(len(acts) / weeks, 1),
        "avg_min": round(sum(a["duration_sec"] or 0 for a in acts) / len(acts) / 60) if acts else None,
        "usual_days": sorted(set(days), key=lambda d: -days.count(d))[:4],
    } if acts else None

    by_ex: dict[str, list] = {}
    for r in con.execute(
            "SELECT s.exercise, s.weight_kg, s.reps, s.rpe, w.date FROM workout_sets s JOIN workouts w ON w.id = s.workout_id "
            "WHERE w.date >= ? AND w.hevy_workout_id IS NOT NULL AND s.exercise IS NOT NULL", (start,)):
        by_ex.setdefault(r["exercise"], []).append(r)
    lifts = []
    for ex, sets in sorted(by_ex.items(), key=lambda kv: -len({r["date"] for r in kv[1]}))[:10]:
        weighted = [r for r in sets if r["weight_kg"] and r["reps"]]
        item = {"exercise": ex, "sessions": len({r["date"] for r in sets})}
        if weighted:
            top = max(weighted, key=lambda r: (r["weight_kg"], r["reps"]))
            item["heaviest"] = f"{top['weight_kg']:g}kg x{top['reps']} ({top['date']})"
            low = [r for r in weighted if r["reps"] <= 10]
            if low:
                best = max(low, key=lambda r: calc.e1rm(r["weight_kg"], r["reps"], r["rpe"])["e1rm"])
                item["e1rm_floor"] = calc.e1rm(best["weight_kg"], best["reps"], best["rpe"])["e1rm"]
        else:
            reps = [r["reps"] for r in sets if r["reps"]]
            if reps:
                item["best_reps"] = max(reps)
        lifts.append(item)

    total = con.execute("SELECT count(*) FROM workout_sets s JOIN workouts w ON w.id=s.workout_id "
                        "WHERE w.date >= ? AND w.hevy_workout_id IS NOT NULL", (start,)).fetchone()[0]
    rated = con.execute("SELECT count(*) FROM workout_sets s JOIN workouts w ON w.id=s.workout_id "
                        "WHERE w.date >= ? AND w.hevy_workout_id IS NOT NULL AND s.rpe IS NOT NULL", (start,)).fetchone()[0]
    w = con.execute("SELECT date, weight_kg FROM body_metrics WHERE weight_kg IS NOT NULL AND date >= ? "
                    "ORDER BY date", (start,)).fetchall()
    return {
        "profile": {"hevy_user": info.get("username") or info.get("name"), "units": info.get("weight_unit"),
                    "hevy_pro": info.get("is_pro")},
        "training_last_weeks": {"weeks": weeks, "strength": training or "no Hevy workouts in this period"},
        "strength_top_exercises": lifts or None,
        "strength_data_quality": {"sets_logged": total, "sets_with_rpe": f"{rated}/{total}",
                                  "effort_rated": rated > 0} if total else None,
        "body_weight": {"first": f"{w[0]['weight_kg']:g}kg ({w[0]['date']})",
                        "latest": f"{w[-1]['weight_kg']:g}kg ({w[-1]['date']})"} if w else None,
        "not_in_hevy": "age, sex, height, sleep, HRV, resting heart rate, runs/rides unless logged as Hevy "
                       "cardio, injuries, goals - ask the athlete (or read them from a wearable they also have)",
        "sync": {"workouts_imported": n, "body_measurement_days": bodies},
        "how_to_read": "e1rm_floor comes from sets as logged (RPE used when logged, else assumed to failure), "
                       "so the true max is likely higher; confirm numbers with the athlete. Warm-up sets are excluded.",
    }


# ---------------------------------------------------------------- 2. weekly sync

def _planned_sessions(root: Path, con, start: str, end: str) -> list[dict]:
    """Strength sessions the active block put in [start, end], with the Hevy routine each is kept in."""
    row, block = ops._active_block(root, con)
    if not block:
        return []
    routines = {r["session"]: r["hevy_routine_id"] for r in con.execute(
        "SELECT session, hevy_routine_id FROM hevy_routines WHERE block_id=?", (block.get("id"),))}
    last = block.get("duration_weeks") or (ops.week_of(block, row, date.fromisoformat(end)) or 1) + 1
    out, seen = [], set()
    for week in range(1, int(last) + 1):
        for s in block.get("sessions", []):
            if s.get("kind", "strength") != "strength":
                continue
            d = ops.session_date(block, row, s, week)
            sid = s.get("id") or s.get("name")
            # a session with an explicit `date` has that date in every week: count it once
            if d and start <= d.isoformat() <= end and (sid, d) not in seen:
                seen.add((sid, d))
                out.append({"session": sid, "name": s.get("name"), "date": d.isoformat(), "week": week,
                            "routine_id": routines.get(sid)})
    return sorted(out, key=lambda p: p["date"])


def _match(plan: list[dict], acts: list[dict]) -> dict[int, dict]:
    """planned index -> the workout that did it: started from its routine within 3 days, else same day."""
    used, out = set(), {}
    for i, p in enumerate(plan):
        d = date.fromisoformat(p["date"])
        for a in acts:
            if a["id"] in used:
                continue
            same_day = a["date"] == p["date"]
            from_routine = p["routine_id"] and a.get("hevy_routine_id") == p["routine_id"] and \
                abs((date.fromisoformat(a["date"]) - d).days) <= 3
            if same_day or from_routine:
                used.add(a["id"])
                out[i] = a
                break
    return out


def sync_since(root: Path, start: str = "", end: str = "") -> dict:
    con = db.connect(root)
    end_d = date.fromisoformat(end) if end else date.today()
    if not start:
        last = con.execute("SELECT max(date) FROM checkins WHERE kind='weekly'").fetchone()[0]
        start = last[:10] if last else (end_d - timedelta(days=7)).isoformat()
    end = end_d.isoformat()
    n = import_workouts(con, hv.list_workouts(start, end))
    import_body(con, (end_d - timedelta(days=14)).isoformat(), end)
    merge_duplicates(con, start, end)

    acts = [dict(r) for r in con.execute(
        "SELECT * FROM workouts WHERE date BETWEEN ? AND ? AND sport='strength_training' ORDER BY date", (start, end))]
    plan = _planned_sessions(root, con, start, end)
    matched = _match(plan, acts)
    matched_ids = {a["id"]: i for i, a in matched.items()}

    sessions, unknown_total = [], 0
    for a in acts:
        lines, unknown = ops._strength_lines(con, a["id"])
        unknown_total += unknown
        p = next((plan[i] for i, w in matched.items() if w["id"] == a["id"]), None)
        s = {"date": a["date"], "name": a["name"], "min": round((a["duration_sec"] or 0) / 60), "sets": lines,
             "planned": f"{p['session']} wk{p['week']}" if p else "unplanned"}
        if a.get("avg_hr"):
            s["avg_hr"] = a["avg_hr"]
        r = con.execute("SELECT avg(rpe), count(rpe), count(*) FROM workout_sets WHERE workout_id=?", (a["id"],)).fetchone()
        if r[1]:
            s["avg_set_rpe"] = round(r[0], 1)
        sessions.append(s)

    missed = [f"{p['date']} {p['name']}" for i, p in enumerate(plan) if i not in matched and p["date"] < end]
    done_planned = len(matched)
    due = done_planned + len(missed)  # today's session isn't missed yet
    tot, rated = con.execute(
        "SELECT count(*), count(s.rpe) FROM workout_sets s JOIN workouts w ON w.id=s.workout_id "
        "WHERE w.date BETWEEN ? AND ? AND w.sport='strength_training'", (start, end)).fetchone()
    if not tot:
        effort = "no strength sets logged"
    elif not rated:
        effort = "no RPE logged in Hevy - ask the athlete for RPE per session (or turn on RPE per set in Hevy)"
    else:
        effort = f"RPE logged on {rated}/{tot} sets"

    def wavg(a, b):
        r = con.execute("SELECT avg(weight_kg) FROM body_metrics WHERE date BETWEEN ? AND ?", (a, b)).fetchone()[0]
        return round(r, 2) if r else None
    w_now = wavg((end_d - timedelta(days=6)).isoformat(), end)
    w_prev = wavg((end_d - timedelta(days=13)).isoformat(), (end_d - timedelta(days=7)).isoformat())
    rep = ops.readiness_on(root, end)
    return {
        "range": [start, end],
        "adherence": {"planned": len(plan), "done_as_planned": done_planned,
                      "rate": round(done_planned / due, 2) if due else None,
                      "missed": missed or None, "total_sessions": len(acts)},
        "sessions": sessions,
        "effort_logging": effort,
        "unclassified_sets_total": unknown_total or None,
        "recovery_7d_vs_baseline": ops._compact_readiness(rep) or "no wearable: ask the athlete about sleep, soreness, stress",
        "repeated_deterioration": rep["summary"]["repeated_deterioration"] or None,
        "body_weight_avg": {"last_7d": w_now, "prev_7d": w_prev,
                            "change": round(w_now - w_prev, 2) if w_now and w_prev else None},
        "open_injuries": [dict(r) for r in con.execute(
            "SELECT area, status, severity FROM injuries WHERE status != 'resolved'")] or None,
        "block": ops._block_outlook(root, con, end_d, source="hevy"),
        "sync": {"workouts_imported": n, "workouts_in_range": len(acts)},
    }


# ---------------------------------------------------------------- 3. push week

def _folder_title(root: Path) -> str:
    return str(workspace.settings(root).get("hevy_folder") or DEFAULT_FOLDER)


def push_week(root: Path, block_id: str = "", week: int = 0, dates: dict | None = None,
              dry_run: bool = False, include_past: bool = False) -> dict:
    con = db.connect(root)
    row, block = ops._active_block(root, con, block_id or None)
    if not block:
        return {"error": f"block {block_id or '(active)'} not found - check training_blocks.file / plan/blocks"}
    bid = block.get("id") or (row or {}).get("id")
    today = date.today()
    week = week or ops.week_of(block, row, today) or 1
    folder_title = _folder_title(root)
    folder_id = hv.find_folder(folder_title, create=not dry_run)
    results = []
    for s in block.get("sessions", []):
        sid = s.get("id") or "_".join(str(s.get("name", "session")).lower().split())
        when = date.fromisoformat(dates[sid]) if dates and sid in dates else ops.session_date(block, row, s, week)
        res = {"session": sid, "date": when.isoformat() if when else None}
        if when is None:
            res["status"] = "skipped: no date (set block start_date + session day, or pass dates)"
        elif when < today and not include_past:
            res["status"] = "skipped: date is in the past"
        elif s.get("kind", "strength") != "strength":
            res["status"] = ("skipped: Hevy routines hold strength sessions; do this one with your watch or "
                             "device and tell the coach how it went")
        if "status" in res:
            results.append(res)
            continue
        day = when.strftime("%a")
        name = str(s.get("name") or sid)
        title = f"{name} (wk{week})" if name.lower().startswith(day.lower()) else f"{day} - {name} (wk{week})"
        title = title[:60]
        notes = f"Planned {when.strftime('%a %Y-%m-%d')} - {block.get('name') or bid}, week {week}." + \
                (f" {s['notes']}" if s.get("notes") else "")
        try:
            payload = hv.build_routine(s, title, week, folder_id, notes, ops.prescription)
        except ValueError as e:
            res["status"] = f"skipped: {e}"
            results.append(res)
            continue
        h = hashlib.sha256(json.dumps([payload, when.isoformat()], sort_keys=True).encode()).hexdigest()[:16]
        res.update(title=title, exercises=len(payload["routine"]["exercises"]))
        old = con.execute("SELECT * FROM hevy_routines WHERE block_id=? AND session=?", (bid, sid)).fetchone()
        if old and old["payload_hash"] == h and old["status"] == "active":
            res.update(status="unchanged (kept existing routine)", hevy_routine_id=old["hevy_routine_id"])
            results.append(res)
            continue
        if dry_run:
            res["status"] = "would update the existing routine" if old else "would create"
            results.append(res)
            continue

        stored = hv.update_routine(old["hevy_routine_id"], payload) if old else None
        how = "updated in place"
        if stored is None:
            stored = hv.create_routine(payload)
            how = "created" if not old else "created (the old routine was gone from Hevy)"
        rid = stored["id"]
        problems = hv.verify(payload, hv.get_routine(rid))
        db.upsert(con, "hevy_routines", [{
            "block_id": bid, "session": sid, "hevy_routine_id": rid, "week": week, "title": title,
            "planned_date": when.isoformat(), "payload_hash": None if problems else h,
            "status": "needs_attention" if problems else "active"}], ["block_id", "session"])
        if problems:
            res.update(status="FAILED verification - routine left in Hevy as stored (the API can't delete it); "
                              "fix the yml and push again to overwrite it", problems=problems, hevy_routine_id=rid)
        else:
            res.update(status=f"{how}, verified", hevy_routine_id=rid)
        results.append(res)
    return {"block": bid, "week": week, "folder": folder_title, "dry_run": dry_run, "sessions": results,
            "note": "Hevy has no calendar: each routine's notes carry the planned date, and the same routine is "
                    "updated each week."}


# ---------------------------------------------------------------- 4. daily context (no wearable)

def daily_context(root: Path, day: str = "") -> dict:
    con = db.connect(root)
    d = date.fromisoformat(day) if day else date.today()
    cfg = workspace.integrations(workspace.settings(root))
    hevy_note = None
    if cfg["hevy"]:
        try:
            import_workouts(con, hv.list_workouts((d - timedelta(days=2)).isoformat(), d.isoformat()))
            merge_duplicates(con, (d - timedelta(days=2)).isoformat(), d.isoformat())
        except Exception as e:  # keep the check useful offline or with a missing key
            hevy_note = f"Hevy not refreshed: {e}"
    row, block = ops._active_block(root, con)
    plan, todays = None, []
    if block:
        week = ops.week_of(block, row, d)
        todays = [s for s in block.get("sessions", []) if week and ops.session_date(block, row, s, week) == d]
        plan = {"block": block.get("id"), "block_name": block.get("name"), "week": week,
                "of_weeks": block.get("duration_weeks"),
                "today": [ops.session_summary(s, week) for s in todays] or "rest day (no session planned)",
                "cautions": block.get("cautions") or None}
    recent = [dict(r) for r in con.execute(
        "SELECT date, name, round(duration_sec/60) AS min FROM workouts WHERE date BETWEEN ? AND ? ORDER BY date DESC",
        ((d - timedelta(days=6)).isoformat(), d.isoformat()))]
    rep = ops.readiness_on(root, d.isoformat())
    return {
        "date": d.isoformat(), "weekday": d.strftime("%A"),
        "proposed_call": None,
        "why_no_proposal": "no wearable data: decide from the athlete's answers (sleep, soreness, pain, stress, "
                           "illness) with the decision table in the coach-daily skill",
        "plan": plan or "no active block",
        "gate_for_today": [s["readiness_gate"] for s in todays if s.get("readiness_gate")] or None,
        "test_day": any(ops.is_test(s) for s in todays) or None,
        "training_last_7_days": recent or "nothing logged",
        "already_done_today": [r for r in recent if r["date"] == d.isoformat()] or None,
        "self_reported_vs_baseline": ops._compact_readiness(rep) or None,
        "open_injuries": [f"{r['area']} ({r['status']})" for r in con.execute(
            "SELECT area, status FROM injuries WHERE status != 'resolved'")] or None,
        "hevy": hevy_note,
    }
