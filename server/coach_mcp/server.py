"""garmin-coach MCP server: the deterministic half of the coach.

The LLM does interpretation and planning; anything that should give the same
answer every time (baselines, e1RM, load rounding, workout payloads, logging
with validated enums) lives here, so it is identical across Claude Code,
Codex, or any other MCP client.
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta

import yaml
from mcp.server.fastmcp import FastMCP

from . import calc, db, garmin, ops, readiness, workspace

mcp = FastMCP("coach")


def _root(path: str | None = None):
    return workspace.resolve(path)


def _con():
    return db.connect(_root())


# ---------------------------------------------------------------- workspace

@mcp.tool()
def workspace_status(workspace_path: str = "") -> dict:
    """Call first in every coach session. Activates the athlete workspace (pass the
    absolute path of the session's working directory) and reports what is set up,
    what is due (daily/weekly check-in), the active block, open injuries and data freshness."""
    try:
        root = _root(workspace_path or None)
    except workspace.WorkspaceError as e:
        return {"workspace": None, "error": str(e), "next": "run the coach-setup skill"}
    con = db.connect(root)
    cfg = workspace.settings(root)
    today = date.today()

    def one(sql, *p):
        r = con.execute(sql, p).fetchone()
        return dict(r) if r else None

    last_daily = one("SELECT date, status FROM checkins WHERE kind='daily' ORDER BY date DESC LIMIT 1")
    last_weekly = one("SELECT date, status, risk FROM checkins WHERE kind='weekly' ORDER BY date DESC LIMIT 1")
    days_since_weekly = (today - date.fromisoformat(last_weekly["date"][:10])).days if last_weekly else None
    checkin_day = cfg.get("weekly_checkin_day", "Sunday")
    return {
        "workspace": str(root),
        "settings": cfg,
        "files": workspace.inventory(root),
        "active_block": one("SELECT id, name, file, start_date, end_date FROM training_blocks WHERE status='active'"),
        "goals": [dict(r) for r in con.execute(
            "SELECT name, module, priority, metric, target_value, unit FROM goals WHERE status='active' ORDER BY priority")],
        "open_injuries": [dict(r) for r in con.execute(
            "SELECT id, area, status, description FROM injuries WHERE status != 'resolved'")],
        "open_hypotheses": one("SELECT count(*) AS n FROM observations WHERE type='hypothesis' AND status='open'")["n"],
        "last_daily_checkin": last_daily,
        "last_weekly_checkin": last_weekly,
        "due": {
            "daily_checkin": not last_daily or last_daily["date"][:10] != today.isoformat(),
            "weekly_checkin": days_since_weekly is None or days_since_weekly >= 7
                              or (today.strftime("%A") == checkin_day and days_since_weekly >= 5),
        },
        "latest_health_metrics_date": (one("SELECT max(date) AS d FROM health_metrics") or {}).get("d"),
        "today": today.isoformat(),
        "weekday": today.strftime("%A"),
    }


@mcp.tool()
def init_workspace(path: str, athlete_name: str = "", units: str = "kg", timezone: str = "",
                   weekly_checkin_day: str = "Sunday") -> dict:
    """Create a new athlete workspace from templates (never overwrites existing files)
    and an empty database. Used by the coach-setup skill."""
    root, created = workspace.init(path, athlete_name, units, timezone, weekly_checkin_day)
    db.connect(root).close()
    return {"workspace": str(root), "created": created + ["data/coach.db"]}


# ---------------------------------------------------------------- database

@mcp.tool()
def query(sql: str, params: list | None = None, limit: int = 200) -> list[dict]:
    """Read-only SQL (single SELECT/WITH) against the athlete database.
    Tables: profile, goals, milestones, health_metrics, body_metrics, workouts, workout_sets,
    injuries, training_blocks, agent_reviews, plan_changes, observations, checkins, garmin_workouts.
    Use `PRAGMA table_info(<table>)` to see columns."""
    return db.query(_root(), sql, params, limit)


@mcp.tool()
def log(table: str, records: list[dict]) -> dict:
    """Insert rows. Enums are validated: observations.type in fact|calculation|interpretation|
    hypothesis|decision, observations.confidence/milestones.confidence in HIGH|MEDIUM|LOW,
    agent_reviews.verdict in APPROVE|CONDITIONAL|REJECT, checkins.kind in daily|weekly|block_review|test,
    checkins.risk in GREEN|YELLOW|ORANGE|RED, injuries.status in active|monitoring|resolved.
    Dates are ISO YYYY-MM-DD."""
    return {"table": table, "inserted_ids": db.insert(_con(), table, records)}


@mcp.tool()
def update_record(table: str, record_id: str, fields: dict, key: str = "id") -> dict:
    """Update one row by key (e.g. close a hypothesis: observations id=12 {status:'confirmed'};
    activate a block: training_blocks id='block_02' {status:'active'})."""
    return {"updated": db.update(_con(), table, record_id, fields, key)}


@mcp.tool()
def upsert_training_block(id: str, name: str, file: str = "", purpose: str = "", start_date: str = "",
                          end_date: str = "", primary_adaptations: str = "", exit_criteria: str = "",
                          status: str = "planned") -> dict:
    """Create or update a training block row (mirror of plan/blocks/<file>). Only one block
    should be status='active'."""
    rec = {k: v for k, v in dict(id=id, name=name, file=file, purpose=purpose, start_date=start_date,
                                 end_date=end_date, primary_adaptations=primary_adaptations,
                                 exit_criteria=exit_criteria, status=status).items() if v != ""}
    con = _con()
    if status == "active":
        con.execute("UPDATE training_blocks SET status='complete' WHERE status='active' AND id != ?", (id,))
    db.upsert(con, "training_blocks", [rec], ["id"])
    return {"block": rec}


# ---------------------------------------------------------------- readiness

@mcp.tool()
def record_metrics(rows: list[dict]) -> dict:
    """Store daily wearable metrics pulled from Garmin, one row per {date, metric, value}.
    Re-recording a date overwrites it. Canonical metrics: hrv_overnight_ms, rhr_bpm, sleep_hours,
    sleep_score, body_battery_morning, stress_avg, training_readiness, vo2max, acute_load, steps.
    Body weight: metric 'weight_kg' (and optional 'body_fat_pct') goes to body_metrics.
    Never invent values - skip a metric Garmin didn't return."""
    out = ops.store_metrics(_con(), rows)
    unknown = sorted({r["metric"] for r in rows} - set(readiness.METRICS) - set(ops.BODY))
    return {**out, "non_canonical_metrics": unknown or None}


@mcp.tool()
def readiness_report(on_date: str = "") -> dict:
    """Each recorded metric vs the athlete's OWN 60-day baseline: today, 7-day mean, z-scores,
    GREEN/YELLOW/ORANGE flags per factor, repeated-deterioration count. No composite score by design."""
    start = (date.fromisoformat(on_date) if on_date else date.today()) - timedelta(days=70)
    rows = db.query(_root(), "SELECT date, metric, value FROM health_metrics WHERE date >= ?",
                    [start.isoformat()], limit=100000)
    return readiness.assess(rows, on_date or None)


# ---------------------------------------------------------------- strength math

def _implement(name: str) -> dict | None:
    p = _root() / "athlete" / "equipment.yml"
    if not p.exists():
        return None
    loads = (yaml.safe_load(p.read_text()) or {}).get("loads") or {}
    return loads.get(name)


@mcp.tool()
def estimate_1rm(weight_kg: float, reps: int, rpe: float | None = None) -> dict:
    """e1RM from a set using the RPE/%1RM chart (RPE10 = 0 reps in reserve). Without RPE the set
    is treated as to-failure and the estimate is flagged as likely low."""
    return calc.e1rm(weight_kg, reps, rpe)


@mcp.tool()
def prescribe_load(one_rm_kg: float, reps: int, rpe: float = 0, pct: float = 0,
                   implement: str = "barbell", mode: str = "nearest") -> dict:
    """Load for a set, from either RPE (reps @ rpe) or a fixed fraction of 1RM (pct, e.g. 0.85),
    rounded to what the athlete can build with athlete/equipment.yml `loads.<implement>`."""
    if not (rpe or pct):
        raise ValueError("give rpe or pct")
    raw = one_rm_kg * (pct or calc.pct_of_1rm(reps, rpe))
    out = calc.round_load(raw, _implement(implement), mode)
    out["basis"] = f"{pct:.0%} of 1RM" if pct else f"{reps} reps @ RPE {rpe} = {calc.pct_of_1rm(reps, rpe):.1%} of 1RM"
    return out


@mcp.tool()
def round_load(target_kg: float, implement: str = "barbell", mode: str = "nearest") -> dict:
    """Round a target to a buildable load for an implement in athlete/equipment.yml `loads`
    (barbell plates, dumbbell set, machine stack). mode: nearest | down | up."""
    return calc.round_load(target_kg, _implement(implement), mode)


# ---------------------------------------------------------------- garmin payloads

@mcp.tool()
def find_garmin_exercise(query: str, category: str = "", limit: int = 8) -> list[dict]:
    """Search Garmin's exercise taxonomy (category + exercise key + muscles). Use before building a
    workout for any exercise without a known mapping - invalid keys make upload_workout fail."""
    return garmin.find_exercise(query, category or None, limit)


@mcp.tool()
def build_strength_workout(name: str, exercises: list[dict], warmup: bool = True,
                           cooldown: bool = False, description: str = "") -> dict:
    """Build a correct Garmin `upload_workout` payload for a strength session.
    exercises: [{name, category?, exercise?, sets, reps | duration_sec, weight_kg?, rest_sec?, note?, plain?}]
    - sets > 1 become native repeat groups (watch shows 'set X of N', rest between every set)
    - category/exercise are validated; unknown ones become plain text steps with a warning
    - plain: true for things Garmin has no exercise for (handstand hold, mobility circuit)
    Returns {workout, warnings}. Upload `workout` with the garmin server, then record it with
    register_garmin_workout."""
    return garmin.build_strength_workout(name, exercises, warmup, cooldown, description)


@mcp.tool()
def register_garmin_workout(garmin_workout_id: str, name: str, block_id: str = "", week: int = 0,
                            session: str = "", scheduled_date: str = "") -> dict:
    """Remember a workout template pushed to Garmin so later check-ins can find and clean up
    stale ones (query garmin_workouts WHERE status='scheduled')."""
    ids = db.insert(_con(), "garmin_workouts", [{
        "garmin_workout_id": garmin_workout_id, "name": name, "block_id": block_id or None,
        "week": week or None, "session": session or None, "scheduled_date": scheduled_date or None}])
    return {"id": ids[0]}


@mcp.tool()
def import_activity(garmin_activity_id: str, date: str, name: str, sport: str = "strength_training",
                    duration_sec: float = 0, distance_m: float = 0, avg_hr: float = 0, max_hr: float = 0,
                    calories: float = 0, rpe: float = 0, feel: float = 0, block_id: str = "",
                    notes: str = "", sets: list[dict] | None = None) -> dict:
    """Store a completed Garmin activity (idempotent on garmin_activity_id). For strength, pass
    `sets` either as raw get_activity_exercise_sets `exerciseSets` entries or compact rows
    {exercise, category, weight_kg, reps, duration_sec, rpe}. rpe = Garmin workout_rpe / 10
    (only meaningful if the athlete actually sets it - check it varies with load)."""
    con = _con()
    rec = {k: v for k, v in dict(
        garmin_activity_id=str(garmin_activity_id), date=date, name=name, sport=sport,
        duration_sec=duration_sec, distance_m=distance_m, avg_hr=avg_hr, max_hr=max_hr, calories=calories,
        rpe=rpe, feel=feel, block_id=block_id, notes=notes).items() if v not in (0, "", None)}
    db.upsert(con, "workouts", [rec], ["garmin_activity_id"])
    wid = con.execute("SELECT id FROM workouts WHERE garmin_activity_id=?", (str(garmin_activity_id),)).fetchone()["id"]
    n = 0
    if sets:
        con.execute("DELETE FROM workout_sets WHERE workout_id=?", (wid,))
        rows = [dict(r, workout_id=wid) for r in garmin.parse_exercise_sets(sets)]
        n = len(db.insert(con, "workout_sets", rows))
    return {"workout_id": wid, "sets_stored": n}


# ---------------------------------------------------------------- analysis

@mcp.tool()
def training_summary(start_date: str, end_date: str) -> dict:
    """Per-exercise sets/reps/tonnage/top-set/best e1RM, and weekly hard sets per muscle group
    (primary = 1 set, secondary = 0.5) between two dates. e1RM here assumes logged RPE, else to-failure."""
    rows = db.query(_root(), """
        SELECT w.date, w.sport, s.category, s.exercise, s.weight_kg, s.reps, s.duration_sec, s.rpe
        FROM workout_sets s JOIN workouts w ON w.id = s.workout_id
        WHERE w.date BETWEEN ? AND ? ORDER BY w.date""", [start_date, end_date], limit=100000)
    ex: dict[str, dict] = {}
    muscle_sets: dict[str, float] = {}
    for r in rows:
        key = r["exercise"] or "UNLABELLED"
        e = ex.setdefault(key, {"category": r["category"], "sets": 0, "reps": 0, "tonnage_kg": 0.0,
                                "top_set": None, "best_e1rm": None, "dates": set()})
        e["sets"] += 1
        e["dates"].add(r["date"])
        if r["reps"]:
            e["reps"] += r["reps"]
            if r["weight_kg"]:
                e["tonnage_kg"] += r["weight_kg"] * r["reps"]
                if not e["top_set"] or r["weight_kg"] > e["top_set"]["weight_kg"]:
                    e["top_set"] = {"weight_kg": r["weight_kg"], "reps": r["reps"], "date": r["date"]}
                if r["reps"] <= 12:
                    est = calc.e1rm(r["weight_kg"], r["reps"], r["rpe"])["e1rm"]
                    if not e["best_e1rm"] or est > e["best_e1rm"]["e1rm"]:
                        e["best_e1rm"] = {"e1rm": est, "from": f"{r['weight_kg']}x{r['reps']}"
                                          + (f"@{r['rpe']}" if r["rpe"] else " (no RPE)"), "date": r["date"]}
        prim, sec = garmin.muscles(r["category"], r["exercise"])
        for m in prim:
            muscle_sets[m] = muscle_sets.get(m, 0) + 1
        for m in sec:
            muscle_sets[m] = muscle_sets.get(m, 0) + 0.5
    weeks = max(1, ((date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1) / 7)
    for e in ex.values():
        e["sessions"] = len(e.pop("dates"))
        e["tonnage_kg"] = round(e["tonnage_kg"], 1)
    return {"range": [start_date, end_date], "weeks": round(weeks, 2), "exercises": ex,
            "sets_per_muscle_per_week": {m: round(v / weeks, 1) for m, v in sorted(muscle_sets.items(), key=lambda x: -x[1])}}


def _goal_series(metric: str) -> list[tuple[str, float]]:
    root = _root()
    if metric.startswith("e1rm:"):
        exname = metric.split(":", 1)[1]
        rows = db.query(root, """SELECT w.date, s.weight_kg, s.reps, s.rpe FROM workout_sets s
            JOIN workouts w ON w.id=s.workout_id WHERE s.exercise=? AND s.weight_kg>0 AND s.reps BETWEEN 1 AND 10""",
                        [exname], limit=100000)
        best: dict[str, float] = {}
        for r in rows:
            v = calc.e1rm(r["weight_kg"], r["reps"], r["rpe"])["e1rm"]
            best[r["date"]] = max(best.get(r["date"], 0), v)
        return sorted(best.items())
    if metric.startswith("health:"):
        rows = db.query(root, "SELECT date, value FROM health_metrics WHERE metric=? ORDER BY date",
                        [metric.split(":", 1)[1]], limit=100000)
        return [(r["date"], r["value"]) for r in rows]
    if metric.startswith("body:"):
        col = metric.split(":", 1)[1]
        if col not in ("weight_kg", "body_fat_pct"):
            raise ValueError("body: metric must be weight_kg or body_fat_pct")
        rows = db.query(root, f"SELECT date, {col} AS v FROM body_metrics WHERE {col} IS NOT NULL ORDER BY date",
                        limit=100000)
        return [(r["date"], r["v"]) for r in rows]
    return []


@mcp.tool()
def goal_progress(weeks: int = 8) -> list[dict]:
    """For every active goal with a measurable `metric`, current value, distance to target,
    trend over the last `weeks` (least-squares slope per week) and a naive linear projection.
    metric conventions: e1rm:<GARMIN_EXERCISE> (e.g. e1rm:BARBELL_BENCH_PRESS), health:<metric>
    (e.g. health:vo2max), body:weight_kg. Other metrics (race times, skills) are tracked through
    milestones/observations and are reported as manual. The projection is a straight line - say so."""
    out = []
    goals = db.query(_root(), "SELECT * FROM goals WHERE status='active' ORDER BY priority")
    cutoff = (date.today() - timedelta(weeks=weeks)).isoformat()
    for g in goals:
        item = {"goal": g["name"], "metric": g["metric"], "target": g["target_value"], "unit": g["unit"],
                "baseline": g["baseline_value"], "target_date": g["target_date"]}
        series = _goal_series(g["metric"] or "")
        if not series:
            item["status"] = "manual - no automatic series for this metric"
            out.append(item)
            continue
        cur_date, cur = series[-1]
        recent = [(d, v) for d, v in series if d >= cutoff]
        item.update(current=round(cur, 2), current_date=cur_date, n_points_window=len(recent))
        if g["target_value"] is not None:
            item["remaining"] = round(g["target_value"] - cur, 2)
            if g["baseline_value"] not in (None, g["target_value"]):
                item["pct_of_way"] = round(100 * (cur - g["baseline_value"]) / (g["target_value"] - g["baseline_value"]), 1)
        if len(recent) >= 3:
            t0 = datetime.fromisoformat(recent[0][0])
            xs = [(datetime.fromisoformat(d) - t0).days / 7 for d, _ in recent]
            ys = [v for _, v in recent]
            if len(set(xs)) > 1:
                slope = statistics.linear_regression(xs, ys).slope
                item["trend_per_week"] = round(slope, 3)
                rem = item.get("remaining")
                if rem is not None and slope and (rem > 0) == (slope > 0):
                    item["naive_weeks_to_target"] = round(rem / slope, 1)
                item["caveat"] = (f"linear fit on n={len(recent)} points; small n and non-linear adaptation "
                                  "make this a rough indication, not a forecast")
        out.append(item)
    return out


# ---------------------------------------------------------------- compound (fetch Garmin directly)

@mcp.tool()
def garmin_daily_snapshot(date: str = "", backfill_days: int = 0) -> dict:
    """THE daily check in one call. Fetches last night's Garmin recovery data (and any days missing
    from the last week), stores it, compares every factor to the athlete's own baseline, imports
    yesterday's/today's activities, and returns today's planned session from the active block plus
    what is on the Garmin calendar. Compact output - no raw Garmin JSON.
    backfill_days: use 60 on first setup so baselines exist from day one (slow: ~3 Garmin calls/day)."""
    return ops.daily_snapshot(_root(), date, backfill_days)


@mcp.tool()
def garmin_sync_since(start_date: str = "", end_date: str = "") -> dict:
    """THE weekly data pull in one call. Imports every activity (strength sets parsed server-side,
    effort/feel ratings), backfills daily metrics and VO2max, then returns a compact summary:
    adherence (planned vs done vs missed), per-session sets/duration/effort, effort-logging quality,
    unclassified sets, recovery 7-day vs baseline, Garmin HRV status, body-weight change, goal progress,
    open injuries, block week + exit criteria + next week's sessions (and whether they're on Garmin).
    `proposed` drafts status (AHEAD..AT RISK) and risk (GREEN..ORANGE) from the data - confirm or
    override after asking the athlete what the data can't show.
    Defaults: start = last weekly check-in (or 7 days ago), end = today."""
    out = ops.sync_since(_root(), start_date, end_date)
    out["goal_progress"] = goal_progress()
    proposed = ops.propose_weekly(out, ops.readiness_on(_root(), out["range"][1]), out["goal_progress"])
    return {"range": out.pop("range"), "proposed": proposed, **out}


@mcp.tool()
def push_week(block_id: str = "", week: int = 0, dates: dict | None = None, dry_run: bool = False,
              include_past: bool = False) -> dict:
    """Turn a block yml week into Garmin workouts in one call: builds every strength session
    (that week's sets/reps/loads) and run/ride/walk session (its `structure` with that week's
    overrides), uploads it, verifies the stored workout matches the plan
    step by step (removes it again if not), schedules it, replaces and deletes the coach's old
    version, and records it. Unchanged sessions keep their existing template.
    Defaults: active block, current week. dates: {session_id: YYYY-MM-DD} to move sessions.
    Run with dry_run=true first when unsure; past dates are skipped unless include_past.
    Edit the block yml BEFORE calling - the yml is the source of truth."""
    return ops.push_week(_root(), block_id, week, dates, dry_run, include_past)


@mcp.tool()
def garmin_history(weeks: int = 12, backfill_days: int = 60) -> dict:
    """THE first-setup Garmin pull in one call: profile (age, sex, height, weight, units, timezone),
    watch model and which metrics it can measure, the last `weeks` of activities imported and
    summarized per sport (sessions/week, duration, usual days), strength top exercises with
    heaviest set and e1RM floor, effort-logging quality, `backfill_days` of recovery metrics stored
    with the resulting baselines, endurance context, body weight. Slow (~1-2 min): say so first."""
    return ops.history(_root(), weeks, backfill_days)


@mcp.tool()
def validate_block(block: str = "") -> dict:
    """Check a block yml before activating or pushing it: required fields, every session buildable
    for Garmin in every week (exercise keys, targets), reps/sets present, pct_1rm/RPE sane, loads
    buildable with the athlete's plates, >10% weekly load jumps, session length vs schedule.yml.
    block: file name, block id, or empty for the active block. Fix every error, then call again;
    warnings are judgment calls - fix or explain them."""
    return ops.validate_block(_root(), block)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
