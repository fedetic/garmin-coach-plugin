"""Garmin Connect helpers that don't need network access: exercise taxonomy
lookup, building `upload_workout` payloads for strength sessions, and parsing
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
    "iterations": {"conditionTypeId": 7, "conditionTypeKey": "iterations"},
    "reps": {"conditionTypeId": 10, "conditionTypeKey": "reps"},
}
STEP = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup"},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval"},
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
