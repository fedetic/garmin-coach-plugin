"""Strength math: e1RM from reps+RPE, load prescription from %1RM, rounding to
loads the athlete can actually build with their equipment."""
from __future__ import annotations

from itertools import product

# %1RM at RPE 10 for 1..12 reps (Tuchscherer/RTS chart). Each 0.5 RPE below 10
# is equivalent to half an extra rep, so any reps@RPE maps onto this one column.
_RPE10 = [100.0, 95.5, 92.2, 89.2, 86.3, 83.7, 81.1, 78.6, 76.2, 73.9, 70.7, 68.0]


def pct_of_1rm(reps: float, rpe: float = 10.0) -> float:
    """Fraction of 1RM that `reps` at `rpe` represents (RPE 10 = 0 reps in reserve)."""
    if reps < 1:
        raise ValueError("reps must be >= 1")
    if not 5 <= rpe <= 10:
        raise ValueError("rpe must be between 5 and 10")
    eff = reps + (10 - rpe)  # reps to failure
    if eff <= len(_RPE10):
        lo = int(eff)
        frac = eff - lo
        a = _RPE10[lo - 1]
        b = _RPE10[lo] if lo < len(_RPE10) else _RPE10[-1] * (1 + 12 / 30) / (1 + 13 / 30)
        return round((a + (b - a) * frac) / 100, 4)
    # beyond the chart: Epley, anchored to the chart's 12-rep value
    return round(_RPE10[-1] / 100 * (1 + 12 / 30) / (1 + eff / 30), 4)


def e1rm(weight: float, reps: int, rpe: float | None = None) -> dict:
    """Estimated 1RM. Without RPE the set is assumed to be to failure (RPE 10),
    which underestimates when reps were left in reserve; flag that."""
    used_rpe = 10.0 if rpe is None else rpe
    pct = pct_of_1rm(reps, used_rpe)
    est = weight / pct
    eff = reps + (10 - used_rpe)
    return {
        "e1rm": round(est, 1),
        "pct_of_1rm": pct,
        "reps_to_failure": eff,
        "confidence": "HIGH" if eff <= 5 and rpe is not None else "MEDIUM" if eff <= 10 else "LOW",
        "notes": ("no RPE given - assumed to failure, likely an underestimate" if rpe is None else "")
        + (" | >10 reps to failure: estimate is loose" if eff > 10 else ""),
    }


def load_for(one_rm: float, reps: int, rpe: float) -> float:
    return one_rm * pct_of_1rm(reps, rpe)


def achievable_loads(implement: dict) -> list[float]:
    """All loads buildable with an implement description from equipment.yml:

    barbell:   {bar_kg: 20, plates_kg: {25: 2, 20: 2, 10: 4, 5: 2, 2.5: 2, 1.25: 2}}  (counts = total plates)
    fixed:     {weights_kg: [10, 12.5, 15, ...]}   (dumbbells, kettlebells, fixed bars)
    stack:     {min_kg: 5, max_kg: 100, step_kg: 5}  (cable/machine stacks)
    """
    if "weights_kg" in implement:
        return sorted(float(w) for w in implement["weights_kg"])
    if "step_kg" in implement:
        lo, hi, step = implement.get("min_kg", 0), implement["max_kg"], implement["step_kg"]
        n = int(round((hi - lo) / step))
        return [round(lo + i * step, 3) for i in range(n + 1)]
    bar = float(implement.get("bar_kg", 20))
    plates = {float(k): int(v) for k, v in (implement.get("plates_kg") or {}).items()}
    pairs = [(w, c // 2) for w, c in plates.items() if c >= 2]
    loads = set()
    for combo in product(*[range(n + 1) for _, n in pairs]):
        loads.add(round(bar + 2 * sum(k * w for k, (w, _) in zip(combo, pairs)), 3))
    return sorted(loads)


def round_load(target: float, implement: dict | None = None, mode: str = "nearest") -> dict:
    """Round to a load the athlete can build. mode: nearest | down | up."""
    if not implement:
        implement = {"step_kg": 2.5, "min_kg": 0, "max_kg": 1000}
    loads = achievable_loads(implement)
    if mode == "down":
        cands = [x for x in loads if x <= target + 1e-9] or loads[:1]
        pick = cands[-1]
    elif mode == "up":
        cands = [x for x in loads if x >= target - 1e-9] or loads[-1:]
        pick = cands[0]
    else:
        pick = min(loads, key=lambda x: (abs(x - target), x))
    out = {"target": round(target, 2), "load": pick, "delta": round(pick - target, 3),
           "max_buildable": loads[-1]}
    if target > loads[-1]:
        out["warning"] = f"target exceeds the heaviest buildable load ({loads[-1]})"
    return out
