"""Readiness relative to the athlete's own baseline, factor by factor.

Deliberately no composite score: each metric is reported against its own
personal history so a single number can't hide what is driving it.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

# canonical metric name -> (unit, which direction is good)
METRICS = {
    "hrv_overnight_ms": ("ms", "higher"),
    "rhr_bpm": ("bpm", "lower"),
    "sleep_hours": ("h", "higher"),
    "sleep_score": ("score", "higher"),
    "body_battery_morning": ("score", "higher"),
    "stress_avg": ("score", "lower"),
    "training_readiness": ("score", "higher"),
    "vo2max": ("ml/kg/min", "higher"),
    "acute_load": ("load", None),
    "steps": ("steps", None),
}

BASELINE_DAYS = 60   # baseline window, excluding the most recent week
RECENT_DAYS = 7
MIN_BASELINE_N = 14


def _flag(z: float | None, good: str | None) -> str:
    if z is None or good is None:
        return "n/a"
    bad_z = -z if good == "higher" else z  # positive = worse than usual
    if bad_z >= 2:
        return "ORANGE"
    if bad_z >= 1:
        return "YELLOW"
    return "GREEN"


def assess(rows: list[dict], on: str | None = None) -> dict:
    """rows: [{date, metric, value}] from health_metrics."""
    day = date.fromisoformat(on) if on else date.today()
    recent_start = day - timedelta(days=RECENT_DAYS - 1)
    base_start = day - timedelta(days=BASELINE_DAYS + RECENT_DAYS - 1)
    by_metric: dict[str, list[tuple[date, float]]] = {}
    for r in rows:
        if r["value"] is None:
            continue
        by_metric.setdefault(r["metric"], []).append((date.fromisoformat(r["date"]), float(r["value"])))

    factors = {}
    for metric, series in sorted(by_metric.items()):
        unit, good = METRICS.get(metric, ("", None))
        series = [s for s in series if base_start <= s[0] <= day]
        today = next((v for d, v in series if d == day), None)
        recent = [v for d, v in series if recent_start <= d <= day]
        base = [v for d, v in series if d < recent_start]
        f = {"unit": unit, "good_direction": good, "today": today,
             "mean_7d": round(statistics.fmean(recent), 2) if recent else None,
             "n_7d": len(recent), "baseline_n": len(base)}
        if len(base) >= 3:
            mu = statistics.fmean(base)
            # floor the SD so a near-constant baseline doesn't turn tiny wiggles into ORANGE
            sd = max(statistics.pstdev(base), 0.03 * abs(mu), 1e-6)
            f.update(baseline_mean=round(mu, 2), baseline_sd=round(sd, 2),
                     baseline_range=[round(min(base), 2), round(max(base), 2)])
            f["z_today"] = round((today - mu) / sd, 2) if today is not None else None
            f["z_7d"] = round((f["mean_7d"] - mu) / sd, 2) if recent else None
            f["flag_today"] = _flag(f["z_today"], good)
            f["flag_7d"] = _flag(f["z_7d"], good)
            # repeated deterioration: count of recent days each worse than baseline by >= 1 SD
            worse = [v for v in recent if _flag((v - mu) / sd, good) != "GREEN"]
            f["bad_days_last_7"] = len(worse)
        if len(base) < MIN_BASELINE_N:
            f["caveat"] = f"baseline has only {len(base)} days (<{MIN_BASELINE_N}); treat flags as LOW confidence"
        factors[metric] = f

    flags = [f.get("flag_7d") for f in factors.values()] + [f.get("flag_today") for f in factors.values()]
    return {
        "date": day.isoformat(),
        "factors": factors,
        "summary": {
            "orange": sorted(m for m, f in factors.items() if "ORANGE" in (f.get("flag_today"), f.get("flag_7d"))),
            "yellow": sorted(m for m, f in factors.items() if "YELLOW" in (f.get("flag_today"), f.get("flag_7d"))
                             and "ORANGE" not in (f.get("flag_today"), f.get("flag_7d"))),
            "repeated_deterioration": sorted(m for m, f in factors.items() if f.get("bad_days_last_7", 0) >= 3),
            "missing_today": sorted(m for m, f in factors.items() if f["today"] is None),
        },
        "how_to_read": "z = SDs from the athlete's own 60-day baseline (excl. last 7 days). "
                       "YELLOW = 1-2 SD worse than usual, ORANGE = >2 SD worse. One flag is not a verdict; "
                       "repeated_deterioration (3+ bad days in 7) is worth acting on even if each value looks normal."
                       if flags else "no data recorded yet - call record_metrics first",
    }


# factors that speak to overnight recovery (vo2max/load/steps are context, not readiness)
RECOVERY = ("hrv_overnight_ms", "rhr_bpm", "sleep_hours", "sleep_score", "body_battery_morning",
            "stress_avg", "training_readiness")


def propose_call(rep: dict, test_day: bool = False) -> dict:
    """Draft GO / MODIFY / REST from the daily decision table, using data only.

    The athlete-reported half of the table (pain, illness) is not known here, so
    this is a draft: the coach confirms or overrides it after asking."""
    worst = {}
    for m in RECOVERY:
        f = rep["factors"].get(m) or {}
        flags = {f.get("flag_today"), f.get("flag_7d")}
        worst[m] = "ORANGE" if "ORANGE" in flags else "YELLOW" if "YELLOW" in flags else None
    orange = [m for m, w in worst.items() if w == "ORANGE"]
    yellow = [m for m, w in worst.items() if w == "YELLOW"]
    repeated = [m for m in rep["summary"]["repeated_deterioration"] if m in RECOVERY]
    flagged = orange + yellow + repeated
    low_conf = sorted({m for m in flagged if rep["factors"][m].get("caveat")})

    if "hrv_overnight_ms" in orange and "rhr_bpm" in orange:
        call, rule = "REST", "ORANGE on both HRV and RHR"
    elif test_day and orange:
        call, rule = "MODIFY", "test/max day with an ORANGE factor: move the test, train as a normal session"
    elif orange or len(yellow) >= 2 or repeated:
        parts = ([f"ORANGE: {', '.join(orange)}"] if orange else []) + \
                ([f"YELLOW: {', '.join(yellow)}"] if len(yellow) >= 2 else []) + \
                ([f"3+ bad days in 7: {', '.join(repeated)}"] if repeated else [])
        call, rule = "MODIFY", "; ".join(parts)
    else:
        call = "GO"
        rule = "no ORANGE, at most one YELLOW" + (f" ({yellow[0]})" if yellow else "")
    return {
        "call": call, "rule": rule,
        "confidence": "LOW" if low_conf or not any(rep["factors"].get(m) for m in RECOVERY) else "NORMAL",
        "low_confidence_factors": low_conf or None,
        "not_checked": "pain, illness, unusual stress - ask; illness or concerning pain overrides to REST",
    }
