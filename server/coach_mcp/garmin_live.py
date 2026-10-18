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


# ---------------------------------------------------------------- profile

CAPABILITIES = {"hrvStatusCapable": "hrv_status", "trainingReadinessCapable": "training_readiness",
                "trainingStatusCapable": "training_status", "bodyBatteryCapable": "body_battery",
                "sleepScoreCapable": "sleep_score", "vo2MaxRunCapable": "vo2max_run",
                "vo2MaxBikeCapable": "vo2max_bike", "lactateThresholdCapable": "lactate_threshold",
                "racePredictionsRunCapable": "race_predictions", "acuteTrainingLoadCapable": "acute_load"}


def fetch_profile(today: str) -> dict:
    """Athlete basics + which metrics the primary watch can produce at all."""
    g = client()
    ud = (_safe(g.get_user_profile) or {}).get("userData") or {}
    st = _safe(g.get_userprofile_settings) or {}
    out = {}
    if ud.get("birthDate"):
        b, t = date.fromisoformat(ud["birthDate"][:10]), date.fromisoformat(today)
        out["age"] = t.year - b.year - ((t.month, t.day) < (b.month, b.day))
    out.update({k: v for k, v in {
        "sex": (ud.get("gender") or "").lower() or None,
        "height_cm": ud.get("height"),
        "weight_kg": round(ud["weight"] / 1000, 1) if ud.get("weight") else None,
        "units": ud.get("measurementSystem") or st.get("measurementSystem"),
        "timezone": st.get("timeZone"),
        "training_days_in_garmin_settings": [d[:3].title() for d in ud.get("availableTrainingDays") or []] or None,
    }.items() if v is not None})
    devices = [d for d in (_safe(g.get_devices) or []) if isinstance(d, dict)]
    dev = next((d for d in devices if d.get("primary")), devices[0] if devices else None)
    if dev:
        out["watch"] = dev.get("productDisplayName")
        out["watch_measures"] = sorted(v for k, v in CAPABILITIES.items() if dev.get(k))
        out["watch_cannot_measure"] = sorted(v for k, v in CAPABILITIES.items() if dev.get(k) is False) or None
    return out


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


def _device_record(by_device) -> dict:
    """Garmin keys some training data by device id: prefer the primary training device."""
    recs = [v for v in (by_device or {}).values() if isinstance(v, dict) and v]
    return next((r for r in recs if r.get("primaryTrainingDevice")), recs[0] if recs else {})


def _pace(mps: float | None) -> str | None:
    if not mps:
        return None
    sec = round(1000 / mps)
    return f"{sec // 60}:{sec % 60:02d}/km"


def _hms(sec) -> str | None:
    if not sec:
        return None
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def fetch_endurance(day: str) -> dict:
    """VO2max (stored as metrics) plus Garmin's endurance context: training status, acute/chronic
    load, load balance, race predictions, lactate threshold, FTP. Empty sections are omitted, so a
    strength-only athlete gets {}. Field names follow the garmin MCP server's curated parsers."""
    g = client()
    ts = _safe(g.get_training_status, day) or {}
    out: dict = {"vo2max": {}, "context": {}}
    v = ts.get("mostRecentVO2Max") or {}
    for kind, name in (("generic", "vo2max"), ("cycling", "vo2max_cycling")):
        val = (v.get(kind) or {}).get("vo2MaxPreciseValue") or (v.get(kind) or {}).get("vo2MaxValue")
        if val:
            out["vo2max"][name] = val
    ctx = out["context"]
    st = _device_record(((ts.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData")))
    acwr = st.get("acuteTrainingLoadDTO") or {}
    status = {k: x for k, x in {
        "status": st.get("trainingStatusFeedbackPhrase") or st.get("trainingStatus"),
        "fitness_trend": st.get("fitnessTrend"),
        "acute_load": acwr.get("dailyTrainingLoadAcute"), "chronic_load": acwr.get("dailyTrainingLoadChronic"),
        "acute_chronic_ratio": acwr.get("dailyAcuteChronicWorkloadRatio"), "ratio_status": acwr.get("acwrStatus"),
    }.items() if x is not None}
    if status:
        ctx["training_status"] = status
    lb = _device_record(((ts.get("mostRecentTrainingLoadBalance") or {}).get("metricsTrainingLoadBalanceDTOMap")))
    balance = {k: x for k, x in {
        "feedback": lb.get("trainingBalanceFeedbackPhrase"),
        "aerobic_low": lb.get("monthlyLoadAerobicLow"), "aerobic_high": lb.get("monthlyLoadAerobicHigh"),
        "anaerobic": lb.get("monthlyLoadAnaerobic"),
    }.items() if x is not None}
    if balance:
        ctx["load_balance_4wk"] = balance
    rp = _safe(g.get_race_predictions) or {}
    if isinstance(rp, list):
        rp = rp[-1] if rp else {}
    races = {k: _hms(rp.get(f)) for k, f in (("5k", "time5K"), ("10k", "time10K"),
                                              ("half", "timeHalfMarathon"), ("marathon", "timeMarathon"))}
    if any(races.values()):
        ctx["race_predictions"] = {k: x for k, x in races.items() if x}
    lt = _safe(g.get_lactate_threshold) or {}
    shr, pw = lt.get("speed_and_heart_rate") or {}, lt.get("power") or {}
    thr = {k: x for k, x in {
        "lt_hr_bpm": shr.get("heartRate"),
        "lt_pace": _pace(shr["speed"] * 10) if shr.get("speed") else None,  # raw unit is 0.1 m/s
        "ftp_w": pw.get("functionalThresholdPower"),
    }.items() if x is not None}
    if thr:
        ctx["thresholds"] = thr
    return out


# ---------------------------------------------------------------- on-demand lookups

def fetch_hr_zones() -> list[dict]:
    """Saved HR zone profiles (DEFAULT plus any sport overrides) as bpm ranges."""
    out = []
    for z in client().connectapi("/biometric-service/heartRateZones") or []:
        floors = [z.get(f"zone{i}Floor") for i in range(1, 6)]
        if not all(floors):
            continue
        top = z.get("maxHeartRateUsed")
        zones = {f"Z{i + 1}": f"{floors[i]}-{(floors[i + 1] - 1) if i < 4 else top or ''}" for i in range(5)}
        out.append({k: v for k, v in {
            "sport": (z.get("sport") or "DEFAULT").lower(), "method": z.get("trainingMethod"),
            "max_hr": top, "resting_hr": z.get("restingHeartRateUsed"),
            "lt_hr": z.get("lactateThresholdHeartRateUsed"), "zones_bpm": zones,
        }.items() if v is not None})
    return out


def fetch_nutrition(start: str, end: str) -> list[dict]:
    """Per-day logged intake. Field names follow the garmin MCP server's parser (61-day max)."""
    data = client().connectapi("/nutrition-service/food/logs/range",
                               params={"startDate": start, "endDate": end}) or {}
    out = []
    for d in data.get("dailyNutritionSummaries") or []:
        c = d.get("dailyNutritionContent") or {}
        out.append({"date": d.get("mealDate"), "kcal": c.get("calories"), "protein_g": c.get("protein"),
                    "carbs_g": c.get("carbs"), "fat_g": c.get("fat"),
                    "items": sum(len(m.get("loggedFoods") or []) for m in d.get("mealDetails") or [])})
    return out


def fetch_vo2max_history(start: str, end: str) -> list[dict]:
    """Days Garmin recomputed VO2max (no carried-forward days): [{date, vo2max?, vo2max_cycling?}]."""
    g = client()
    data = _safe(g.connectapi, f"{g.garmin_connect_metrics_url}/{start}/{end}") or []
    by_day: dict[str, dict] = {}
    for item in data if isinstance(data, list) else [data]:
        for kind, name in (("generic", "vo2max"), ("cycling", "vo2max_cycling")):
            sec = (item or {}).get(kind) or {}
            val = sec.get("vo2MaxPreciseValue") or sec.get("vo2MaxValue")
            day = sec.get("calendarDate") or (item or {}).get("calendarDate")
            if val and day:
                by_day.setdefault(day[:10], {"date": day[:10]})[name] = round(float(val), 1)
    return [by_day[d] for d in sorted(by_day)]


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
