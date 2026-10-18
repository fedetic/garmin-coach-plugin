"""Garmin Connect helpers that don't need network access: exercise taxonomy
lookup, building `upload_workout` payloads for strength and run/ride/walk
sessions, and parsing
`get_activity_exercise_sets` output into rows for the database.

Payload rules here were verified against Garmin Connect (2026-08/09):
- every exercise with sets > 1 is a RepeatGroupDTO (endCondition iterations/7),
  otherwise Garmin shows 1 set and rest only fires once
- stepOrder is one global counter across the whole workout, nested steps included
- reps end condition is conditionTypeId 10 / key "reps" (not "reps.value")
- weight is weightValue in plain kg + weightUnit kilogram/8/factor 1000
- category/exerciseName must exist in Garmin's taxonomy or the upload 400s
- a self-paced warm-up (lap.button) first step stops the watch dropping the
  athlete straight into a working set
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

TAXONOMY = Path(__file__).parent / "data" / "garmin_exercises.json"

STRENGTH = {"sportTypeId": 5, "sportTypeKey": "strength_training"}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"}
KG = {"unitId": 8, "unitKey": "kilogram", "factor": 1000}
COND = {
    "lap": {"conditionTypeId": 1, "conditionTypeKey": "lap.button"},
    "time": {"conditionTypeId": 2, "conditionTypeKey": "time"},
    "distance": {"conditionTypeId": 3, "conditionTypeKey": "distance"},
    "iterations": {"conditionTypeId": 7, "conditionTypeKey": "iterations"},
    "reps": {"conditionTypeId": 10, "conditionTypeKey": "reps"},
}
STEP = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup"},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval"},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery"},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest"},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat"},
}
_ALIASES = {"DB": "DUMBBELL", "BB": "BARBELL", "KB": "KETTLEBELL", "OHP": "OVERHEAD_PRESS",
            "RDL": "ROMANIAN_DEADLIFT", "PULLUP": "PULL_UP", "CHINUP": "CHIN_UP", "PUSHUP": "PUSH_UP",
            "EZ": "EZ_BAR", "BW": "BODY_WEIGHT", "BODYWEIGHT": "BODY_WEIGHT"}


@lru_cache(maxsize=1)
def taxonomy() -> dict:
    return json.loads(TAXONOMY.read_text())["categories"]


def _norm(text: str) -> str:
    t = re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")
    return "_".join(_ALIASES.get(p, p) for p in t.split("_"))


def is_valid(category: str, exercise: str) -> bool:
    return exercise in taxonomy().get(category, {}).get("exercises", {})


def find_exercise(query: str, category: str | None = None, limit: int = 8) -> list[dict]:
    q = _norm(query)
    qtok = set(q.split("_"))
    scored = []
    for cat, body in taxonomy().items():
        if category and cat != category:
            continue
        for ex, meta in body.get("exercises", {}).items():
            etok = set(ex.split("_"))
            hit = len(qtok & etok)
            if not hit and q not in ex:
                continue
            score = hit / len(qtok) + hit / len(etok) + (2 if ex == q else 0) + (0.5 if q in ex else 0)
            scored.append((score, cat, ex, meta))
    scored.sort(key=lambda s: (-s[0], len(s[2])))
    return [{"category": c, "exercise": e, "score": round(s, 2),
             "primary_muscles": m.get("primaryMuscles", []),
             "secondary_muscles": m.get("secondaryMuscles", [])}
            for s, c, e, m in scored[:limit]]


def muscles(category: str | None, exercise: str | None) -> tuple[list[str], list[str]]:
    meta = taxonomy().get(category or "", {}).get("exercises", {}).get(exercise or "", {})
    return meta.get("primaryMuscles", []), meta.get("secondaryMuscles", [])


def _resolve(item: dict, warnings: list[str]) -> tuple[str | None, str | None]:
    cat, ex = item.get("category"), item.get("exercise")
    if cat and ex:
        if is_valid(cat, ex):
            return cat, ex
        warnings.append(f"{item.get('name')}: {cat}/{ex} is not in Garmin's taxonomy - created as a plain step")
        return None, None
    if item.get("plain"):
        return None, None
    cands = find_exercise(item.get("name", ""), limit=3)
    if cands and cands[0]["score"] >= 2.5:  # exact name match
        return cands[0]["category"], cands[0]["exercise"]
    warnings.append(
        f"{item.get('name')}: no exact Garmin exercise - created as a plain step. "
        f"Pass category+exercise to fix; closest: {[c['category'] + '/' + c['exercise'] for c in cands]}"
    )
    return None, None


def build_strength_workout(name: str, exercises: list[dict], warmup: bool = True,
                           cooldown: bool = False, description: str = "") -> dict:
    """exercises: [{name, category?, exercise?, sets=1, reps? | duration_sec?, weight_kg?,
    rest_sec?, note?, plain?}]. Neither reps nor duration -> ends on lap button."""
    warnings: list[str] = []
    order = 0
    steps: list[dict] = []

    def nxt() -> int:
        nonlocal order
        order += 1
        return order

    if warmup:
        steps.append({"type": "ExecutableStepDTO", "stepOrder": nxt(), "stepType": STEP["warmup"],
                      "endCondition": COND["lap"], "description": "Warm-up (self-paced, press lap when ready)",
                      "targetType": NO_TARGET})

    for item in exercises:
        cat, ex = _resolve(item, warnings)
        sets = int(item.get("sets") or 1)
        weight = item.get("weight_kg")
        label = item.get("name") or (ex or "exercise").replace("_", " ").title()
        if weight:
            label += f" {weight:g}kg"
        if item.get("reps"):
            label += f" x{item['reps']}"
        if item.get("duration_sec") and not item.get("reps"):
            label += f" {int(item['duration_sec'])}s"
        if item.get("note"):
            label += f" ({item['note']})"

        def work() -> dict:
            s = {"type": "ExecutableStepDTO", "stepOrder": nxt(), "stepType": STEP["interval"],
                 "description": label[:512], "targetType": NO_TARGET}
            if item.get("reps"):
                s.update(endCondition=COND["reps"], endConditionValue=int(item["reps"]))
            elif item.get("duration_sec"):
                s.update(endCondition=COND["time"], endConditionValue=int(item["duration_sec"]))
            else:
                s.update(endCondition=COND["lap"])
            if cat:
                s.update(category=cat, exerciseName=ex)
            if weight:
                s.update(weightValue=float(weight), weightUnit=KG)
            return s

        def rest() -> dict | None:
            if not item.get("rest_sec"):
                return None
            return {"type": "ExecutableStepDTO", "stepOrder": nxt(), "stepType": STEP["rest"],
                    "endCondition": COND["time"], "endConditionValue": int(item["rest_sec"]),
                    "targetType": NO_TARGET}

        if sets > 1:
            group = {"type": "RepeatGroupDTO", "stepOrder": nxt(), "stepType": STEP["repeat"],
                     "numberOfIterations": sets, "smartRepeat": False, "endCondition": COND["iterations"],
                     "workoutSteps": []}
            group["workoutSteps"].append(work())
            r = rest()
            if r:
                group["workoutSteps"].append(r)
            steps.append(group)
        else:
            steps.append(work())
            r = rest()
            if r:
                steps.append(r)

    if cooldown:
        steps.append({"type": "ExecutableStepDTO", "stepOrder": nxt(), "stepType": STEP["cooldown"],
                      "endCondition": COND["lap"], "description": "Cool-down (self-paced)",
                      "targetType": NO_TARGET})

    workout = {"workoutName": name[:80], "description": description[:1024], "sportType": STRENGTH,
               "workoutSegments": [{"segmentOrder": 1, "sportType": STRENGTH, "workoutSteps": steps}]}
    return {"workout": workout, "warnings": warnings, "step_count": order,
            "next": "pass `workout` to the garmin server's upload_workout, then verify with get_workout_by_id"}


# ---------------------------------------------------------------- endurance

SPORTS = {"running": {"sportTypeId": 1, "sportTypeKey": "running"},
          "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling"},
          "walking": {"sportTypeId": 12, "sportTypeKey": "walking"}}
_SPORT_ALIASES = {"run": "running", "ride": "cycling", "bike": "cycling", "walk": "walking"}
HR_ZONE = {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone"}
PACE_ZONE = {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone"}
PARTS = ("warmup", "main", "intervals", "cooldown")


def endurance_structure(structure: dict, week_override: dict | None = None) -> dict:
    """Merge a week's override into a session structure. Overrides are either a part
    ({main: {duration_min: 35}}) or a flat '<part>_<field>' key (main_duration_min: 35)."""
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in (structure or {}).items()}
    for k, v in (week_override or {}).items():
        if k in PARTS and isinstance(v, dict):
            out[k] = {**(out.get(k) or {}), **v}
        elif (m := re.match(r"^(warmup|main|intervals|cooldown)_(.+)$", k)):
            out.setdefault(m.group(1), {})[m.group(2)] = v
        elif k == "repeats":
            out.setdefault("intervals", {})["repeats"] = v
    return out


def _pace_ms(pace: str) -> float:
    """'5:30' min/km -> m/s."""
    mm, ss = str(pace).split(":")
    return 1000 / (int(mm) * 60 + int(ss))


def _target(t, warnings: list[str], where: str) -> tuple[dict, str]:
    """Target spec -> (step fields, label). Supported: {hr_zone: 2} or "Z2",
    {hr_bpm: [135, 148]}, {pace_min_km: ["5:50", "5:30"]} (running/walking)."""
    if t in (None, "", {}):
        return {"targetType": NO_TARGET}, ""
    if isinstance(t, (str, int)):
        m = re.fullmatch(r"z?([1-5])", str(t).strip().lower())
        t = {"hr_zone": int(m.group(1))} if m else {"unparsed": t}
    if "hr_zone" in t:
        z = int(re.sub(r"\D", "", str(t["hr_zone"])) or 0)
        if 1 <= z <= 5:
            return {"targetType": HR_ZONE, "zoneNumber": z}, f"Z{z}"
    if "hr_bpm" in t and len(t["hr_bpm"]) == 2:
        lo, hi = sorted(float(x) for x in t["hr_bpm"])
        return {"targetType": HR_ZONE, "targetValueOne": lo, "targetValueTwo": hi}, f"{lo:g}-{hi:g}bpm"
    if "pace_min_km" in t and len(t["pace_min_km"]) == 2:
        lo, hi = sorted(_pace_ms(p) for p in t["pace_min_km"])
        slow, fast = sorted(t["pace_min_km"], key=_pace_ms)
        return {"targetType": PACE_ZONE, "targetValueOne": round(lo, 4), "targetValueTwo": round(hi, 4)}, \
            f"{fast}-{slow}/km"
    warnings.append(f"{where}: target {t!r} not understood (use hr_zone 1-5, hr_bpm [lo, hi] or "
                    "pace_min_km [slow, fast]); step has no target")
    return {"targetType": NO_TARGET}, f" {t}" if not isinstance(t, dict) else ""


def _end(part: dict, warnings: list[str], where: str) -> tuple[dict, str]:
    if part.get("distance_km"):
        km = float(part["distance_km"])
        return {"endCondition": COND["distance"], "endConditionValue": km * 1000}, f"{km:g} km"
    sec = part.get("duration_sec") or (part.get("duration_min") and float(part["duration_min"]) * 60)
    if sec:
        sec = float(sec)
        return {"endCondition": COND["time"], "endConditionValue": sec}, \
            f"{sec / 60:g} min" if sec % 60 == 0 else f"{sec:g}s"
    if where not in ("warmup", "cooldown"):
        warnings.append(f"{where}: no duration_min / duration_sec / distance_km; ends on lap button")
    return {"endCondition": COND["lap"]}, "until lap"


def build_endurance_workout(name: str, sport: str, structure: dict, description: str = "") -> dict:
    """structure: {warmup?, main?, intervals?, cooldown?}. warmup/main/cooldown:
    {duration_min | duration_sec | distance_km, target?}. intervals: {repeats, work: {...},
    recovery?: {...}}. Targets: see _target. Order on the watch: warmup, main, intervals, cooldown."""
    warnings: list[str] = []
    key = _SPORT_ALIASES.get(str(sport).lower(), str(sport).lower())
    if key not in SPORTS:
        raise ValueError(f"sport {sport!r} not supported for push; use one of {sorted(SPORTS)}")
    sp = SPORTS[key]
    order, steps, summary = 0, [], []

    def nxt() -> int:
        nonlocal order
        order += 1
        return order

    def step(kind: str, part: dict, where: str, label: str) -> dict:
        end, end_txt = _end(part, warnings, where)
        tgt, tgt_txt = _target(part.get("target"), warnings, where)
        text = " ".join(x for x in (label, end_txt, tgt_txt.strip()) if x)
        summary.append(text)
        return {"type": "ExecutableStepDTO", "stepOrder": nxt(), "stepType": STEP[kind],
                "description": (part.get("note") or text)[:512], **end, **tgt}

    s = structure or {}
    unknown = set(s) - set(PARTS)
    if unknown:
        warnings.append(f"ignored structure keys {sorted(unknown)}; use {list(PARTS)}")
    if s.get("warmup"):
        steps.append(step("warmup", s["warmup"], "warmup", "Warm-up"))
    if s.get("main"):
        steps.append(step("interval", s["main"], "main", "Main"))
    iv = s.get("intervals")
    if iv:
        reps = int(iv.get("repeats") or 1)
        if not iv.get("work"):
            warnings.append("intervals: no work step")
        group = {"type": "RepeatGroupDTO", "stepOrder": nxt(), "stepType": STEP["repeat"],
                 "numberOfIterations": reps, "smartRepeat": False, "endCondition": COND["iterations"],
                 "endConditionValue": float(reps), "workoutSteps": []}
        n = len(summary)
        group["workoutSteps"].append(step("interval", iv.get("work") or {}, "intervals.work", "Rep"))
        if iv.get("recovery"):
            group["workoutSteps"].append(step("recovery", iv["recovery"], "intervals.recovery", "Easy"))
        summary[n:] = [f"{reps}x(" + " / ".join(summary[n:]) + ")"]
        steps.append(group)
    if s.get("cooldown"):
        steps.append(step("cooldown", s["cooldown"], "cooldown", "Cool-down"))
    if not steps:
        raise ValueError("empty structure: give at least main or intervals")

    workout = {"workoutName": name[:80], "description": (description or " + ".join(summary))[:1024],
               "sportType": sp, "workoutSegments": [{"segmentOrder": 1, "sportType": sp, "workoutSteps": steps}]}
    return {"workout": workout, "warnings": warnings, "step_count": order}


def parse_exercise_sets(sets: list[dict]) -> list[dict]:
    """Accepts raw Garmin `exerciseSets` entries or compact rows
    {exercise, category, weight_kg, reps, duration_sec, rpe}. Rest sets are dropped."""
    rows = []
    for s in sets:
        if "setType" in s:
            if s.get("setType") != "ACTIVE":
                continue
            top = (s.get("exercises") or [{}])[0]
            cat = top.get("category")
            rows.append({
                "category": None if cat in (None, "UNKNOWN") else cat,
                "exercise": top.get("name"),
                "weight_kg": round(s["weight"] / 1000, 2) if s.get("weight") else None,
                "reps": s.get("repetitionCount"),
                "duration_sec": s.get("duration"),
                "rpe": None,
            })
        else:
            rows.append({k: s.get(k) for k in ("category", "exercise", "weight_kg", "reps", "duration_sec", "rpe")})
    for i, r in enumerate(rows, 1):
        r["set_order"] = i
    return rows
