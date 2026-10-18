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

    runner = False  # False: the empty shapes a strength-only account returns (probed 2026-10)

    def get_training_status(self, d):
        if not self.runner:
            return {"userId": 1, "mostRecentVO2Max": None, "mostRecentTrainingLoadBalance": None,
                    "mostRecentTrainingStatus": None, "heatAltitudeAcclimationDTO": None}
        return {"mostRecentVO2Max": {"generic": {"vo2MaxValue": 52.0, "vo2MaxPreciseValue": 51.8}, "cycling": None},
                "mostRecentTrainingStatus": {"latestTrainingStatusData": {
                    "111": {"deviceId": 111, "primaryTrainingDevice": True, "trainingStatus": 4,
                            "trainingStatusFeedbackPhrase": "PRODUCTIVE_3", "fitnessTrend": 1,
                            "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 640, "dailyTrainingLoadChronic": 520,
                                                     "dailyAcuteChronicWorkloadRatio": 1.2, "acwrStatus": "OPTIMAL"}}}},
                "mostRecentTrainingLoadBalance": {"metricsTrainingLoadBalanceDTOMap": {
                    "111": {"deviceId": 111, "primaryTrainingDevice": True, "monthlyLoadAerobicLow": 900,
                            "monthlyLoadAerobicHigh": 700, "monthlyLoadAnaerobic": 150,
                            "trainingBalanceFeedbackPhrase": "BALANCED"}}}}

    def get_user_profile(self):
        return {"id": 1, "userData": {"gender": "MALE", "birthDate": "1995-01-27", "height": 175.0, "weight": 75500.0,
                                      "measurementSystem": "metric", "availableTrainingDays": ["MONDAY", "FRIDAY"]}}

    def get_userprofile_settings(self):
        return {"measurementSystem": "metric", "timeZone": "Europe/Paris"}

    def get_devices(self):
        return [{"productDisplayName": "Venu 3S", "primary": True, "hrvStatusCapable": True,
                 "trainingReadinessCapable": False, "bodyBatteryCapable": True, "sleepScoreCapable": True}]

    garmin_connect_metrics_url = "/metrics-service/metrics/maxmet/daily"

    def connectapi(self, url, params=None):
        if url == "/biometric-service/heartRateZones":  # shape probed on a live account
            return [{"trainingMethod": "HR_MAX", "restingHeartRateUsed": 70, "lactateThresholdHeartRateUsed": None,
                     "zone1Floor": 95, "zone2Floor": 114, "zone3Floor": 133, "zone4Floor": 152, "zone5Floor": 171,
                     "maxHeartRateUsed": 190, "sport": "DEFAULT"}]
        if url == "/nutrition-service/food/logs/range":
            full = {"mealDetails": [{"loggedFoods": [1, 2]}, {"loggedFoods": [3, 4]}]}
            return {"dailyNutritionSummaries": [
                {"mealDate": params["startDate"], "dailyNutritionContent": {"calories": 2600, "protein": 150,
                                                                            "carbs": 300, "fat": 80}, **full},
                {"mealDate": params["endDate"], "dailyNutritionContent": {"calories": 2400, "protein": 130,
                                                                          "carbs": 280, "fat": 70}, **full},
                {"mealDate": "x-partial", "dailyNutritionContent": {"calories": 400}, "mealDetails": [{"loggedFoods": [1]}]}]}
        if url.startswith(self.garmin_connect_metrics_url):
            return [{"generic": {"calendarDate": f"{TODAY - timedelta(days=30)}", "vo2MaxPreciseValue": 50.2}},
                    {"generic": {"calendarDate": f"{TODAY - timedelta(days=2)}", "vo2MaxPreciseValue": 51.1}}] \
                if self.runner else []
        raise AssertionError(f"unexpected connectapi {url}")

    def get_race_predictions(self):
        return {"calendarDate": str(TODAY), "time5K": 1290, "time10K": 2700, "timeHalfMarathon": 6000,
                "timeMarathon": 12900} if self.runner else {}

    def get_lactate_threshold(self):
        return {"speed_and_heart_rate": {"speed": 0.3703, "heartRate": 171, "calendarDate": str(TODAY)},
                "power": {}} if self.runner else \
            {"speed_and_heart_rate": {"speed": None, "heartRate": None}, "power": {}}

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
        if self.mangle and w["sportType"]["sportTypeKey"] == "strength_training":  # Garmin drops the first lift's weight
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
             "sport": "running", "structure": {"warmup": {"duration_min": 10}, "main": {"duration_min": 30,
                                                                                      "target": {"hr_zone": 2}}},
             "weeks": {2: {"main_duration_min": 35}}},
            {"id": "mobility", "day": TODAY.strftime("%A"), "name": "Mobility", "kind": "mobility"},
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
    assert out["sessions"][1]["status"] == "would create"
    assert out["sessions"][2]["status"].startswith("skipped: mobility session has no `structure`")

    out = ops.push_week(root)
    s = out["sessions"][0]
    assert s["status"] == "created, verified, scheduled" and s["name"].endswith("(wk1)")
    first_id = s["garmin_workout_id"]
    assert out["sessions"][1]["status"] == "created, verified, scheduled"
    assert len(fake.schedule) == 2 and {x["scheduleDate"] for x in fake.schedule} == {TODAY.isoformat()}

    out = ops.push_week(root)  # nothing changed
    assert out["sessions"][0]["status"].startswith("unchanged") and len(fake.schedule) == 2

    p = root / "plan" / "blocks" / "block-01-test.yml"
    b = yaml.safe_load(p.read_text())
    b["sessions"][0]["exercises"][0]["weeks"][1]["weight_kg"] = 87.5  # coach lowers the load
    p.write_text(yaml.safe_dump(b))
    out = ops.push_week(root)
    s = out["sessions"][0]
    assert s["replaced"] == [first_id] and ("delete", int(first_id)) in fake.calls
    assert len(fake.schedule) == 2 and s["garmin_workout_id"] in {str(x["workoutId"]) for x in fake.schedule}
    assert out["sessions"][1]["status"].startswith("unchanged")
    rows = db.query(root, "SELECT session, status FROM garmin_workouts ORDER BY id")
    assert [(r["session"], r["status"]) for r in rows] == [
        ("today_lift", "replaced"), ("easy_run", "scheduled"), ("today_lift", "scheduled")]


def test_push_week_rejects_unverified_upload(ws):
    root, fake = ws
    fake.mangle = True
    s = ops.push_week(root)["sessions"][0]
    assert s["status"].startswith("FAILED") and s["problems"]
    assert [x["workoutName"] for x in fake.schedule] == [f"{TODAY:%a} - Easy run (wk1)"]  # lift never scheduled
    assert len(fake.workouts) == 1  # the bad upload was removed again


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
    assert out["adherence"]["rate"] == 1.0
    assert out["open_injuries"] == [{"area": "left shoulder", "status": "monitoring", "severity": None}]
    blk = out["block"]
    assert blk["week"] == 1 and not blk["ends_after_this_week"]
    nxt = {x["id"]: x for x in blk["next_week"]}
    assert nxt["today_lift"]["exercises"][0] == "Barbell Bench Press 2x2 @95kg RPE7.5"
    assert nxt["today_lift"]["on_garmin"] is False


def test_sync_since_endurance(ws):
    root, fake = ws
    start = (TODAY - timedelta(days=6)).isoformat()
    assert ops.sync_since(root, start)["garmin_endurance"] is None  # strength-only: no noise
    fake.runner = True
    out = ops.sync_since(root, start)
    e = out["garmin_endurance"]
    assert out["vo2max"] == {"vo2max": 51.8}
    assert e["training_status"]["status"] == "PRODUCTIVE_3" and e["training_status"]["ratio_status"] == "OPTIMAL"
    assert e["race_predictions"] == {"5k": "21:30", "10k": "45:00", "half": "1:40:00", "marathon": "3:35:00"}
    assert e["thresholds"] == {"lt_hr_bpm": 171, "lt_pace": "4:30/km"}
    assert e["load_balance_4wk"]["feedback"] == "BALANCED"
    assert db.query(root, "SELECT value FROM health_metrics WHERE metric='acute_load'")[0]["value"] == 640


def test_garmin_sync_since_tool_adds_proposal(ws):
    from coach_mcp import server
    root, fake = ws
    out = server.garmin_sync_since((TODAY - timedelta(days=6)).isoformat())
    assert list(out)[:2] == ["range", "proposed"]
    # HRV/sleep bad for 3 days + monitored shoulder; nothing planned, no goals -> no status draft
    assert out["proposed"]["risk"] in ("YELLOW", "ORANGE") and out["proposed"]["status"] is None


def _weekly(rate, injuries=None, **flags):
    return {"adherence": {"rate": rate}, "open_injuries": injuries}, _rep(**flags)


@pytest.mark.parametrize("rate,goals,flags,injuries,status,risk", [
    (1.0, [], {}, None, "ON TRACK", "GREEN"),
    (0.7, [], {}, None, "SLIGHTLY BEHIND", "GREEN"),
    (0.4, [], {}, None, "SIGNIFICANTLY BEHIND", "GREEN"),
    (0.4, [], {}, [{"area": "knee", "status": "active"}], "AT RISK", "ORANGE"),
    (1.0, [{"goal": "bench", "remaining": 10, "trend_per_week": -1}], {}, None, "SIGNIFICANTLY BEHIND", "GREEN"),
    (1.0, [{"goal": "bench", "remaining": 10, "trend_per_week": 1, "naive_weeks_to_target": 10,
            "target_date": (TODAY + timedelta(weeks=5)).isoformat()}], {}, None, "SLIGHTLY BEHIND", "GREEN"),
    (0.9, [{"goal": "bench", "remaining": 10, "trend_per_week": 2, "naive_weeks_to_target": 5,
            "target_date": (TODAY + timedelta(weeks=20)).isoformat()}], {}, None, "AHEAD", "GREEN"),
    (1.0, [], {"hrv_overnight_ms": ("GREEN", "ORANGE")}, None, "ON TRACK", "YELLOW"),
    (1.0, [], {"hrv_overnight_ms": ("GREEN", "ORANGE"), "sleep_hours": ("GREEN", "ORANGE")}, None, "ON TRACK", "ORANGE"),
    (None, [], {}, None, None, "GREEN"),
])
def test_propose_weekly_rules(rate, goals, flags, injuries, status, risk):
    summary, rep = _weekly(rate, injuries, **flags)
    out = ops.propose_weekly(summary, rep, goals, TODAY)
    assert (out["status"], out["risk"]) == (status, risk), out


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


def test_endurance_builder():
    from coach_mcp import garmin
    st = garmin.endurance_structure(
        {"warmup": {"duration_min": 10, "target": "Z1-Z2"},
         "intervals": {"repeats": 4, "work": {"distance_km": 1, "target": {"pace_min_km": ["4:10", "4:20"]}},
                       "recovery": {"duration_sec": 90}},
         "cooldown": {"duration_min": 5}},
        {"repeats": 5, "warmup_duration_min": 15})
    b = garmin.build_endurance_workout("Tue - Intervals (wk2)", "run", st)
    steps = b["workout"]["workoutSegments"][0]["workoutSteps"]
    assert [x["stepOrder"] for x in steps] == [1, 2, 5] and b["step_count"] == 5
    assert steps[0]["endConditionValue"] == 900 and steps[0]["targetType"]["workoutTargetTypeKey"] == "no.target"
    assert "Z1-Z2" in b["warnings"][0]  # zone ranges aren't a Garmin target - flagged, not guessed
    rep = steps[1]
    assert rep["numberOfIterations"] == 5 and [x["stepOrder"] for x in rep["workoutSteps"]] == [3, 4]
    work = rep["workoutSteps"][0]
    assert work["endCondition"]["conditionTypeKey"] == "distance" and work["endConditionValue"] == 1000
    assert work["targetValueOne"] == round(1000 / 260, 4) and work["targetValueTwo"] == round(1000 / 250, 4)
    assert b["workout"]["description"].startswith("Warm-up 15 min Z1-Z2 + 5x(Rep 1 km 4:10-4:20/km / Easy 90s)")
    with pytest.raises(ValueError):
        garmin.build_endurance_workout("x", "swimming", {"main": {"duration_min": 30}})


def test_verify_catches_target_change():
    from coach_mcp import garmin
    b = garmin.build_endurance_workout("Easy", "running", {"main": {"duration_min": 30, "target": {"hr_zone": 2}}})
    fetched = copy.deepcopy(b["workout"])
    assert ops.verify(b["workout"], fetched) == []
    fetched["workoutSegments"][0]["workoutSteps"][0]["zoneNumber"] = 3
    assert ops.verify(b["workout"], fetched)


def test_validate_block(ws):
    root, fake = ws
    out = ops.validate_block(root)
    assert out["file"] == "block-01-test.yml" and out["weeks_checked"] == 4
    errs = "\n".join(out["errors"])
    # bench only has week 1-2 prescriptions -> weeks 3-4 have no reps; reported once with a count
    assert "today_lift: wk3 barbell_bench_press: needs reps or duration_sec (+1 more weeks)" in errs
    warns = "\n".join(out["warnings"])
    assert "mobility: no `structure`" in warns and "exit_criteria" in warns
    assert not out["ok"]

    p = root / "plan" / "blocks" / "block-01-test.yml"
    b = yaml.safe_load(p.read_text())
    bench = b["sessions"][0]["exercises"][0]
    bench["weeks"] = {1: {"sets": 3, "reps": 2, "weight_kg": 90, "rpe": 7},
                      2: {"sets": 3, "reps": 2, "weight_kg": 101, "rpe": 7.5},
                      3: {"sets": 3, "reps": 2, "weight_kg": 92.5, "pct_1rm": 92, "rpe": 8},
                      4: {"sets": 2, "reps": 3, "weight_kg": 80, "rpe": 6}}
    bench["garmin"]["exercise"] = "BARBELL_BENCH_PRES"  # typo
    b["sessions"][1]["structure"]["main"]["target"] = "Z1-Z2"
    b["exit_criteria"] = ["RPE logged"]
    p.write_text(yaml.safe_dump(b))
    out = ops.validate_block(root, "block-01-test.yml")
    errs, warns = "\n".join(out["errors"]), "\n".join(out["warnings"])
    assert "BARBELL_BENCH_PRES is not in Garmin's taxonomy" in errs
    assert "pct_1rm 92 > 1.0" in errs
    assert "easy_run: wk1 main: target 'Z1-Z2' not understood" in errs
    assert "load jumps 90 -> 101kg" in warns
    assert "101kg isn't buildable on your barbell (nearest 100kg)" in warns or "isn't buildable" in warns
    assert ops.validate_block(root, "nope.yml")["ok"] is False


def test_history(ws):
    root, fake = ws
    fake.activities = [{"activityId": 10 + i, "activityName": "Push", "activityType": {"typeKey": "strength_training"},
                        "startTimeLocal": f"{TODAY - timedelta(days=7 * i)} 18:00:00", "duration": 3600}
                       for i in range(4)] + \
                      [{"activityId": 99, "activityName": "Run", "activityType": {"typeKey": "running"},
                        "startTimeLocal": f"{TODAY - timedelta(days=2)} 07:00:00", "duration": 1800,
                        "distance": 5000.0, "averageHR": 150}]
    h = ops.history(root, weeks=4, backfill_days=30)
    p = h["profile"]
    assert p["sex"] == "male" and p["weight_kg"] == 75.5 and p["watch"] == "Venu 3S" and 30 <= p["age"] <= 32
    assert "training_readiness" in p["watch_cannot_measure"] and "hrv_status" in p["watch_measures"]
    sp = h["training_last_weeks"]["by_sport"]
    assert sp["strength_training"]["sessions"] == 4 and sp["strength_training"]["per_week"] == 1.0
    assert sp["running"] == {"sessions": 1, "per_week": 0.2, "avg_min": 30,
                             "usual_days": [(TODAY - timedelta(days=2)).strftime("%a")], "avg_km": 5.0, "avg_hr": 150}
    bench = h["strength_top_exercises"][0]
    assert bench["exercise"] == "BARBELL_BENCH_PRESS" and bench["sessions"] == 4
    assert bench["heaviest"].startswith("90kg x2") and bench["e1rm_floor"] > 90
    assert h["strength_data_quality"]["unclassified_sets"] == 4 and h["strength_data_quality"]["effort_varies"] is False
    assert "hrv_overnight_ms" in h["recovery_baselines"] and h["garmin_endurance"] is None
    assert len(str(h)) < 3500


def test_lookup(ws):
    root, fake = ws
    z = ops.lookup(root, "hr_zones")["hr_zones"][0]
    assert z["zones_bpm"] == {"Z1": "95-113", "Z2": "114-132", "Z3": "133-151", "Z4": "152-170", "Z5": "171-190"}
    n = ops.lookup(root, "nutrition", (TODAY - timedelta(days=200)).isoformat())
    assert n["range"][0] == (TODAY - timedelta(days=60)).isoformat()  # clamped to Garmin's 61-day limit
    assert n["days_logged"] == 2 and n["avg_on_logged_days"]["kcal"] == 2500 and n["partial_days"] == ["x-partial"]
    v = ops.lookup(root, "vo2max_trend")
    assert v["source"] == "coach database" and isinstance(v["points"], str)
    fake.runner = True
    v = ops.lookup(root, "vo2max_trend")
    assert v["source"] == "garmin" and v["vo2max_change"] == 0.9 and len(v["points"]) == 2
    fake.runner = False
    assert ops.lookup(root, "vo2max_trend")["source"] == "coach database"  # stored on the previous call
    assert "error" in ops.lookup(root, "sleep")
