"""Compound tools against a fake Garmin client shaped like real garminconnect 0.3.2 responses."""
import copy
from datetime import date, timedelta

import pytest
import yaml

from coach_mcp import db, garmin_live, ops, workspace

TODAY = date.today()


class FakeGarmin:
    def __init__(self):
        self.workouts, self.schedule, self.next_id, self.calls = {}, [], 100, []
        self.mangle = False
        self.activities = []

        class _Http:
            def __init__(s, outer):
                s.outer = outer

            def post(s, _api, url, json):
                wid = url.rsplit("/", 1)[1]
                s.outer.schedule.append({"scheduledWorkoutId": len(s.outer.schedule) + 1, "workoutId": int(wid),
                                         "workoutName": s.outer.workouts[wid]["workoutName"],
                                         "scheduleDate": json["date"], "associatedActivityId": None})
                return type("R", (), {"status_code": 200})()
        self.client = _Http(self)

    # recovery: HRV 52-54 normally, 40 in the last 3 days
    def get_sleep_data(self, d):
        bad = (TODAY - date.fromisoformat(d)).days < 3
        return {"dailySleepDTO": {"sleepTimeSeconds": 18000 if bad else 27000,
                                  "sleepScores": {"overall": {"value": 50 if bad else 80, "qualifierKey": "FAIR"}}},
                "avgOvernightHrv": 40 if bad else 52 + date.fromisoformat(d).day % 3,
                "hrvStatus": "UNBALANCED" if bad else "BALANCED", "restingHeartRate": 55}

    def get_stats(self, d):
        return {"restingHeartRate": 55, "averageStressLevel": 25, "bodyBatteryAtWakeTime": 80, "totalSteps": 8000}

    def get_training_readiness(self, d):
        return []

    def get_daily_weigh_ins(self, d):
        return {"dateWeightList": [{"weight": 75000.0, "bodyFat": None}]} if d.endswith("5") else {"dateWeightList": []}

    def get_hrv_data(self, d):
        return {"hrvSummary": {"status": "UNBALANCED", "weeklyAvg": 47, "lastNightAvg": 40,
                               "baseline": {"balancedLow": 50, "balancedUpper": 60}}}

    def get_training_status(self, d):
        return {"mostRecentVO2Max": None}

    def get_activities_by_date(self, a, b):
        return [x for x in self.activities if a <= x["startTimeLocal"][:10] <= b]

    def get_activity(self, i):
        return {"summaryDTO": {"directWorkoutRpe": 80, "directWorkoutFeel": 50}}

    def get_activity_exercise_sets(self, i):
        s = {"setType": "ACTIVE", "exercises": [{"category": "BENCH_PRESS", "name": "BARBELL_BENCH_PRESS"}],
             "repetitionCount": 2, "weight": 90000.0, "duration": 20}
        return {"exerciseSets": [s, {"setType": "REST"}, s,
                                 {"setType": "ACTIVE", "exercises": [{"category": "UNKNOWN", "name": None}],
                                  "repetitionCount": 6, "weight": None}]}

    def query_garmin_graphql(self, q):
        import re
        a, b = re.findall(r'"(\d{4}-\d{2}-\d{2})"', q["query"])
        return {"data": {"workoutScheduleSummariesScalar": [s for s in self.schedule if a <= s["scheduleDate"] <= b]}}

    def upload_workout(self, w):
        self.next_id += 1
        stored = copy.deepcopy(w)
        if self.mangle:  # simulate Garmin dropping the weight from the first lift
            stored["workoutSegments"][0]["workoutSteps"][1]["workoutSteps"][0].pop("weightValue", None)
        self.workouts[str(self.next_id)] = stored
        self.calls.append(("upload", self.next_id))
        return {"workoutId": self.next_id}

    def get_workout_by_id(self, i):
        return self.workouts[str(i)]

    def unschedule_workout(self, sid):
        self.calls.append(("unschedule", sid))
        self.schedule = [s for s in self.schedule if s["scheduledWorkoutId"] != sid]

    def delete_workout(self, i):
        self.calls.append(("delete", i))
        self.workouts.pop(str(i), None)


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_GARMIN_PAUSE", "0")
    fake = FakeGarmin()
    garmin_live.set_client(fake)
    root, _ = workspace.init(str(tmp_path / "ws"))
    monday = TODAY - timedelta(days=TODAY.weekday())
    block = {
        "id": "block_01", "name": "Test block", "start_date": monday.isoformat(), "duration_weeks": 4,
        "sessions": [
            {"id": "today_lift", "day": TODAY.strftime("%A"), "name": "Bench heavy", "kind": "strength",
             "readiness_gate": "no max if HRV ORANGE",
             "exercises": [
                 {"exercise": "barbell_bench_press", "garmin": {"category": "BENCH_PRESS", "exercise": "BARBELL_BENCH_PRESS"},
                  "rest_sec": 240, "weeks": {1: {"sets": 3, "reps": 2, "weight_kg": 90, "rpe": 7},
                                             2: {"sets": 2, "reps": 2, "weight_kg": 95, "rpe": 7.5}}},
                 {"exercise": "handstand_hold", "plain": True, "sets": 2, "duration_sec": 30}]},
            {"id": "easy_run", "day": TODAY.strftime("%A"), "name": "Easy run", "kind": "endurance",
             "structure": {"main": {"duration_min": 30}}},
        ]}
    (root / "plan" / "blocks" / "block-01-test.yml").write_text(yaml.safe_dump(block))
    con = db.connect(root)
    db.upsert(con, "training_blocks", [{"id": "block_01", "name": "Test block", "file": "block-01-test.yml",
                                        "start_date": monday.isoformat(), "status": "active"}], ["id"])
    db.insert(con, "injuries", [{"area": "left shoulder", "status": "monitoring"}])
    yield root, fake
    garmin_live.set_client(None)


def test_daily_snapshot(ws):
    root, fake = ws
    fake.activities = [{"activityId": 1, "activityName": "Mon - Bench heavy", "startTimeLocal": f"{TODAY} 12:00:00",
                        "activityType": {"typeKey": "strength_training"}, "duration": 1800, "workoutId": None}]
    out = ops.daily_snapshot(root, backfill_days=60)
    r = out["readiness_vs_your_baseline"]
    assert r["hrv_overnight_ms"]["today"] == 40 and r["hrv_overnight_ms"]["flag_today"] == "ORANGE"
    assert r["sleep_hours"]["today"] == 5.0
    assert "hrv_overnight_ms" in out["repeated_deterioration"]
    assert out["plan"]["week"] == 1
    assert out["proposed_call"]["call"] == "MODIFY" and "hrv_overnight_ms" in out["proposed_call"]["rule"]
    assert out["proposed_call"]["also_apply_session_gate"] == ["no max if HRV ORANGE"]
    lift = out["plan"]["today"][0]
    assert lift["exercises"][0] == "Barbell Bench Press 3x2 @90kg RPE7" and lift["readiness_gate"]
    assert out["open_injuries"] == ["left shoulder (monitoring)"]
    assert out["already_done_today"][0]["rpe"] == 8.0
    assert out["sync"]["metric_days_fetched"] == 61
    # second call only refreshes yesterday + today
    assert ops.daily_snapshot(root)["sync"]["metric_days_fetched"] == 2
    assert len(str(out)) < 4000  # compact: this is the whole point


def _rep(**flags):
    """Minimal readiness.assess() output: metric=(flag_today, flag_7d[, bad_days])."""
    factors = {m: {"flag_today": f[0], "flag_7d": f[1], "bad_days_last_7": f[2] if len(f) > 2 else 0}
               for m, f in flags.items()}
    return {"factors": factors, "summary": {
        "repeated_deterioration": sorted(m for m, f in factors.items() if f["bad_days_last_7"] >= 3)}}


@pytest.mark.parametrize("flags,test_day,call", [
    ({"hrv_overnight_ms": ("GREEN", "GREEN"), "rhr_bpm": ("YELLOW", "GREEN")}, False, "GO"),
    ({"hrv_overnight_ms": ("YELLOW", "GREEN"), "sleep_hours": ("GREEN", "YELLOW")}, False, "MODIFY"),
    ({"sleep_hours": ("GREEN", "GREEN", 4)}, False, "MODIFY"),
    ({"stress_avg": ("ORANGE", "GREEN")}, False, "MODIFY"),
    ({"hrv_overnight_ms": ("ORANGE", "YELLOW"), "rhr_bpm": ("GREEN", "ORANGE")}, False, "REST"),
    ({"steps": ("ORANGE", "ORANGE"), "vo2max": ("ORANGE", "ORANGE")}, False, "GO"),  # not recovery factors
])
def test_propose_call_rules(flags, test_day, call):
    from coach_mcp import readiness
    assert readiness.propose_call(_rep(**flags), test_day)["call"] == call


def test_propose_call_test_day_moves_test():
    from coach_mcp import readiness
    out = readiness.propose_call(_rep(sleep_hours=("ORANGE", "GREEN")), test_day=True)
    assert out["call"] == "MODIFY" and "move the test" in out["rule"]
    assert ops.is_test({"name": "Fri - Bench 1RM test"}) and not ops.is_test({"name": "Max", "test": False})


def test_push_week_create_keep_replace(ws):
    root, fake = ws
    out = ops.push_week(root, dry_run=True)
    assert out["sessions"][0]["status"] == "would create" and not fake.calls
    assert out["sessions"][1]["status"].startswith("skipped: non-strength")

    out = ops.push_week(root)
    s = out["sessions"][0]
    assert s["status"] == "created, verified, scheduled" and s["name"].endswith("(wk1)")
    first_id = s["garmin_workout_id"]
    assert len(fake.schedule) == 1 and fake.schedule[0]["scheduleDate"] == TODAY.isoformat()

    out = ops.push_week(root)  # nothing changed
    assert out["sessions"][0]["status"].startswith("unchanged") and len(fake.schedule) == 1

    p = root / "plan" / "blocks" / "block-01-test.yml"
    b = yaml.safe_load(p.read_text())
    b["sessions"][0]["exercises"][0]["weeks"][1]["weight_kg"] = 87.5  # coach lowers the load
    p.write_text(yaml.safe_dump(b))
    out = ops.push_week(root)
    s = out["sessions"][0]
    assert s["replaced"] == [first_id] and ("delete", int(first_id)) in fake.calls
    assert len(fake.schedule) == 1 and str(fake.schedule[0]["workoutId"]) == s["garmin_workout_id"]
    rows = db.query(root, "SELECT status FROM garmin_workouts ORDER BY id")
    assert [r["status"] for r in rows] == ["replaced", "scheduled"]


def test_push_week_rejects_unverified_upload(ws):
    root, fake = ws
    fake.mangle = True
    s = ops.push_week(root)["sessions"][0]
    assert s["status"].startswith("FAILED") and s["problems"]
    assert not fake.schedule and not fake.workouts  # removed again, nothing scheduled


def test_sync_since_summary(ws):
    root, fake = ws
    ops.push_week(root, include_past=True)
    wid = int(db.query(root, "SELECT garmin_workout_id FROM garmin_workouts")[0]["garmin_workout_id"])
    fake.activities = [{"activityId": 7, "activityName": "Bench heavy (wk1)", "startTimeLocal": f"{TODAY} 12:00:00",
                        "activityType": {"typeKey": "strength_training"}, "duration": 2400, "workoutId": wid}]
    out = ops.sync_since(root, (TODAY - timedelta(days=6)).isoformat())
    assert out["adherence"]["done_as_planned"] == 1
    sess = out["sessions"][0]
    assert sess["planned"] == "today_lift wk1" and sess["sets"] == ["BARBELL_BENCH_PRESS 2x2 @90kg"]
    assert sess["unclassified_sets"] == 1 and sess["rpe"] == 8.0
    assert out["garmin_hrv_status"]["status"] == "UNBALANCED"
    assert "rated 1/1" in out["effort_logging"]


def test_old_database_migrates(tmp_path):
    import sqlite3
    root, _ = workspace.init(str(tmp_path / "old"))
    p = db.path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.executescript("CREATE TABLE schema_version (version INTEGER); INSERT INTO schema_version VALUES (1);"
                      "CREATE TABLE workouts (id INTEGER PRIMARY KEY, garmin_activity_id TEXT UNIQUE, date TEXT);"
                      "CREATE TABLE garmin_workouts (id INTEGER PRIMARY KEY, garmin_workout_id TEXT);")
    con.close()
    con = db.connect(root)
    assert "garmin_workout_id" in db.columns(con, "workouts")
    assert "payload_hash" in db.columns(con, "garmin_workouts")
