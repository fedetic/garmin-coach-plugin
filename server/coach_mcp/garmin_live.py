"""Direct Garmin Connect access for the compound tools.

Uses the same library (python-garminconnect) and the same login tokens
(~/.garminconnect, or $GARMINTOKENS) as the garmin MCP server, so there is no
second login. Every function returns small, already-parsed values; raw Garmin
JSON never leaves this module.

Field names verified against live responses (garminconnect 0.3.2, 2026-10).
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta

AUTH_HINT = ("Garmin login missing or expired. Run once in a terminal: "
             "uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth")

_client = None


def set_client(client) -> None:
    """Inject a client (tests) or reset (None)."""
    global _client
    _client = client


def client():
    global _client
    if _client is None:
        from garminconnect import Garmin
        path = os.path.expanduser(os.path.expandvars(os.environ.get("GARMINTOKENS") or "~/.garminconnect"))
        if not os.path.exists(path):
            raise RuntimeError(AUTH_HINT)
        g = Garmin()
        try:
            g.login(path)
        except Exception as e:  # expired/invalid tokens
            raise RuntimeError(f"{AUTH_HINT} ({e})") from e
        _client = g
    return _client


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None


def days(start: str, end: str) -> list[str]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return [(a + timedelta(n)).isoformat() for n in range((b - a).days + 1)]


# ---------------------------------------------------------------- daily metrics

def fetch_day(day: str) -> dict:
    """Canonical metrics for one day (the night that ended that morning).
    Returns {"metrics": {name: value}, "context": {...}}; missing values are omitted."""
    g = client()
    m: dict[str, float] = {}
    ctx: dict = {}

    s = _safe(g.get_sleep_data, day) or {}
    dto = s.get("dailySleepDTO") or {}
    if dto.get("sleepTimeSeconds"):
        m["sleep_hours"] = round(dto["sleepTimeSeconds"] / 3600, 2)
    score = ((dto.get("sleepScores") or {}).get("overall") or {})
    if score.get("value") is not None:
        m["sleep_score"] = score["value"]
        ctx["sleep_quality"] = score.get("qualifierKey")
    if s.get("avgOvernightHrv") is not None:
        m["hrv_overnight_ms"] = s["avgOvernightHrv"]
    if s.get("hrvStatus"):
        ctx["garmin_hrv_status"] = s["hrvStatus"]
    if s.get("restingHeartRate"):
        m["rhr_bpm"] = s["restingHeartRate"]

    st = _safe(g.get_stats, day) or {}
    if "rhr_bpm" not in m and st.get("restingHeartRate"):
        m["rhr_bpm"] = st["restingHeartRate"]
    if st.get("averageStressLevel") is not None and st["averageStressLevel"] >= 0:
        m["stress_avg"] = st["averageStressLevel"]
    bb = st.get("bodyBatteryAtWakeTime") or st.get("bodyBatteryHighestValue")
    if bb is not None:
        m["body_battery_morning"] = bb
    if st.get("totalSteps") is not None:
        m["steps"] = st["totalSteps"]

    tr = _safe(g.get_training_readiness, day)
    if isinstance(tr, list) and tr and tr[0].get("score") is not None:
        m["training_readiness"] = tr[0]["score"]
        ctx["training_readiness_level"] = tr[0].get("level")

    w = _safe(g.get_daily_weigh_ins, day) or {}
    weights = [x for x in (w.get("dateWeightList") or []) if x.get("weight")]
    if weights:
        m["weight_kg"] = round(weights[-1]["weight"] / 1000, 2)
        if weights[-1].get("bodyFat"):
            m["body_fat_pct"] = weights[-1]["bodyFat"]
    return {"metrics": m, "context": ctx}


def fetch_hrv_status(day: str) -> dict | None:
    """Garmin's own weekly HRV status + baseline band (context, not a verdict)."""
    h = _safe(client().get_hrv_data, day) or {}
    s = h.get("hrvSummary") or {}
    if not s:
        return None
    b = s.get("baseline") or {}
    return {"status": s.get("status"), "weekly_avg": s.get("weeklyAvg"), "last_night": s.get("lastNightAvg"),
            "garmin_balanced_band": [b.get("balancedLow"), b.get("balancedUpper")]}


def fetch_vo2max(day: str) -> dict:
    ts = _safe(client().get_training_status, day) or {}
    v = ts.get("mostRecentVO2Max") or {}
    out = {}
    for kind in ("generic", "cycling"):
        k = v.get(kind) or {}
        val = k.get("vo2MaxPreciseValue") or k.get("vo2MaxValue")
        if val:
            out["vo2max" if kind == "generic" else "vo2max_cycling"] = val
    return out


# ---------------------------------------------------------------- activities

def list_activities(start: str, end: str) -> list[dict]:
    out = []
    for a in client().get_activities_by_date(start, end) or []:  # the library paginates internally
        out.append({
            "garmin_activity_id": str(a["activityId"]),
            "date": (a.get("startTimeLocal") or "")[:10],
            "name": a.get("activityName"),
            "sport": (a.get("activityType") or {}).get("typeKey"),
            "duration_sec": a.get("duration"),
            "distance_m": a.get("distance") or None,
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "calories": a.get("calories"),
            "garmin_workout_id": str(a["workoutId"]) if a.get("workoutId") else None,
        })
    return sorted(out, key=lambda x: x["date"])


def activity_effort(activity_id: str) -> dict:
    """Self-reported effort (1-10) and feel (0-100) if the athlete set them."""
    a = _safe(client().get_activity, int(activity_id)) or {}
    sd = a.get("summaryDTO") or {}
    out = {}
    if sd.get("directWorkoutRpe") is not None:
        out["rpe"] = sd["directWorkoutRpe"] / 10
    if sd.get("directWorkoutFeel") is not None:
        out["feel"] = sd["directWorkoutFeel"]
    return out


def exercise_sets(activity_id: str) -> list[dict]:
    r = _safe(client().get_activity_exercise_sets, int(activity_id)) or {}
    return r.get("exerciseSets") or []


# ---------------------------------------------------------------- calendar + workouts

def scheduled(start: str, end: str) -> list[dict]:
    q = {"query": f'query{{workoutScheduleSummariesScalar(startDate:"{start}", endDate:"{end}")}}'}
    r = client().query_garmin_graphql(q) or {}
    rows = (r.get("data") or {}).get("workoutScheduleSummariesScalar") or []
    return [{"date": x.get("scheduleDate"), "scheduled_workout_id": x.get("scheduledWorkoutId"),
             "workout_id": str(x.get("workoutId")) if x.get("workoutId") else None,
             "name": x.get("workoutName"), "sport": x.get("workoutType"),
             "completed": x.get("associatedActivityId") is not None} for x in rows]


def upload(workout: dict) -> str:
    r = client().upload_workout(workout)
    wid = (r or {}).get("workoutId")
    if not wid:
        raise RuntimeError(f"upload_workout returned no workoutId: {str(r)[:200]}")
    return str(wid)


def get_workout(workout_id: str) -> dict:
    return client().get_workout_by_id(int(workout_id))


def schedule(workout_id: str, day: str) -> str:
    """Idempotent: Garmin's schedule endpoint creates duplicates on repeat POSTs."""
    if any(s["workout_id"] == str(workout_id) for s in scheduled(day, day)):
        return "already scheduled"
    resp = client().client.post("connectapi", f"workout-service/schedule/{int(workout_id)}", json={"date": day})
    code = getattr(resp, "status_code", 200)
    if code != 200:
        raise RuntimeError(f"schedule failed: HTTP {code}")
    return "scheduled"


def unschedule(scheduled_workout_id) -> None:
    client().unschedule_workout(int(scheduled_workout_id))


def delete(workout_id: str) -> None:
    client().delete_workout(int(workout_id))


def pause() -> None:
    """Small gap between bulk calls so a 60-day backfill doesn't trip rate limits."""
    time.sleep(float(os.environ.get("COACH_GARMIN_PAUSE", "0.25")))
