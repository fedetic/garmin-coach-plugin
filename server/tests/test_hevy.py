"""Hevy and no-Garmin flows against a fake Hevy API shaped like the published OpenAPI spec."""
import copy
import sqlite3
from datetime import date, timedelta

import pytest
import yaml

from coach_mcp import db, hevy, hevy_ops, ops, server, workspace

TODAY = date.today()
MONDAY = TODAY - timedelta(days=TODAY.weekday())
TEMPLATES = [
    {"id": "05293BCA", "title": "Bench Press (Barbell)", "type": "weight_reps", "primary_muscle_group": "chest",
     "equipment": "barbell", "is_custom": False},
    {"id": "D04AC939", "title": "Deadlift (Barbell)", "type": "weight_reps", "primary_muscle_group": "lower_back",
     "equipment": "barbell", "is_custom": False},
    {"id": "11111111", "title": "Pull Up", "type": "reps_only", "primary_muscle_group": "lats",
     "equipment": "none", "is_custom": False},
    {"id": "22222222", "title": "Pull Up (Assisted)", "type": "weight_reps", "primary_muscle_group": "lats",
     "equipment": "machine", "is_custom": False},
    {"id": "33333333", "title": "Plank", "type": "duration", "primary_muscle_group": "abdominals",
     "equipment": "none", "is_custom": False},
]


def _workout(wid, day, routine_id=None, rpe=8):
    t = f"{day}T17:00:00+00:00"
    return {"id": wid, "title": "Bench day", "routine_id": routine_id, "description": None,
            "start_time": t, "end_time": f"{day}T17:50:00+00:00",
            "exercises": [{"index": 0, "title": "Bench Press (Barbell)", "exercise_template_id": "05293BCA", "sets": [
                {"index": 0, "type": "warmup", "weight_kg": 40, "reps": 8, "rpe": None},
                {"index": 1, "type": "normal", "weight_kg": 90, "reps": 3, "rpe": rpe},
                {"index": 2, "type": "normal", "weight_kg": 90, "reps": 3, "rpe": rpe}]},
                {"index": 1, "title": "Plank", "exercise_template_id": "33333333", "sets": [
                    {"index": 0, "type": "normal", "weight_kg": None, "reps": None, "duration_seconds": 45}]}]}


class FakeHevy:
    def __init__(self):
        self.workouts, self.routines, self.folders, self.calls = [], {}, [], []
        self.mangle = False
        self.next = 0

    def request(self, method, path, params=None, body=None):
        self.calls.append((method, path))
        page, size = (params or {}).get("page", 1), (params or {}).get("pageSize", 10)

        def paged(key, items):
            items = list(items)
            return {"page": page, "page_count": max(1, -(-len(items) // size)),
                    key: items[(page - 1) * size: page * size]}
        if path == "/v1/user/info":
            return {"data": {"username": "lifter", "weight_unit": "kg", "distance_unit": "kilometers", "is_pro": True}}
        if path == "/v1/workouts":
            return paged("workouts", sorted(self.workouts, key=lambda w: w["start_time"], reverse=True))
        if path == "/v1/body_measurements":
            return paged("body_measurements", [{"date": str(TODAY - timedelta(days=1)), "weight_kg": 82.4,
                                                "fat_percent": None}])
        if path == "/v1/exercise_templates":
            return paged("exercise_templates", TEMPLATES)
        if path == "/v1/routine_folders" and method == "GET":
            return paged("routine_folders", self.folders)
        if path == "/v1/routine_folders":
            f = {"id": 42, "title": body["routine_folder"]["title"]}
            self.folders.append(f)
            return f
        if path == "/v1/routines" and method == "POST":
            self.next += 1
            return {"routine": self._store(f"rt-{self.next}", body)}
        rid = path.rsplit("/", 1)[-1]
        if path.startswith("/v1/routines/") and method == "PUT":
            if rid not in self.routines:
                raise hevy.HevyError("Hevy PUT -> HTTP 404: not found")
            return {"routine": self._store(rid, body)}
        if path.startswith("/v1/routines/"):
            return {"routine": self.routines[rid]}
        raise AssertionError(f"unexpected {method} {path}")

    def _store(self, rid, body):
        r = copy.deepcopy(body["routine"])
        titles = {t["id"]: t["title"] for t in TEMPLATES}
        for i, ex in enumerate(r["exercises"]):
            ex["index"], ex["title"] = i, titles[ex["exercise_template_id"]]
            for j, s in enumerate(ex["sets"]):
                s["index"] = j
                if self.mangle and i == 0 and j == 0:
                    s["weight_kg"] = 0  # Hevy drops the load
        r["id"] = rid
        self.routines[rid] = r
        return r


BLOCK = {
    "id": "block_01", "name": "Test block", "start_date": MONDAY.isoformat(), "duration_weeks": 4,
    "sessions": [
        {"id": "today_lift", "day": TODAY.strftime("%A"), "name": "Bench heavy", "kind": "strength",
         "exercises": [
             {"exercise": "barbell_bench_press", "hevy": {"template_id": "05293BCA"}, "rest_sec": 240,
              "weeks": {1: {"sets": 3, "reps": 3, "weight_kg": 90, "rpe": 7},
                        2: {"sets": 2, "reps": 3, "weight_kg": 95, "rpe": 7.5}}},
             {"exercise": "plank", "sets": 2, "duration_sec": 30, "note": "slow"}]},
        {"id": "easy_run", "day": TODAY.strftime("%A"), "name": "Easy run", "kind": "endurance", "sport": "running",
         "structure": {"main": {"duration_min": 30}}},
    ]}


@pytest.fixture
def hws(tmp_path):
    fake = FakeHevy()
    hevy.set_client(fake)
    root, _ = workspace.init(str(tmp_path / "ws"), garmin=False, hevy=True)
    (root / "plan" / "blocks" / "block-01-test.yml").write_text(yaml.safe_dump(BLOCK))
    con = db.connect(root)
    db.upsert(con, "training_blocks", [{"id": "block_01", "name": "Test block", "file": "block-01-test.yml",
                                        "start_date": MONDAY.isoformat(), "status": "active"}], ["id"])
    yield root, fake
    hevy.set_client(None)


# ---------------------------------------------------------------- integrations setting

def test_integrations_default_and_legacy(tmp_path):
    root, _ = workspace.init(str(tmp_path / "a"))
    assert workspace.integrations(workspace.settings(root)) == {"garmin": True, "hevy": False}
    legacy = {"athlete": "x", "units": "kg"}  # a workspace made before the setting existed
    assert workspace.integrations(legacy) == {"garmin": True, "hevy": False}
    root2, _ = workspace.init(str(tmp_path / "b"), garmin=False, hevy=True)
    assert workspace.integrations(workspace.settings(root2)) == {"garmin": False, "hevy": True}
    workspace.set_integrations(root2, garmin=True)
    assert workspace.integrations(workspace.settings(root2)) == {"garmin": True, "hevy": True}


def test_garmin_tools_refuse_when_garmin_is_off(hws):
    root, _ = hws
    workspace.set_active(root)
    for out in (server.garmin_daily_snapshot(), server.garmin_sync_since(), server.garmin_history(),
                server.push_week(), server.garmin_lookup("hr_zones")):
        assert "not turned on" in out["error"]


def test_hevy_tools_refuse_when_hevy_is_off(tmp_path):
    root, _ = workspace.init(str(tmp_path / "g"))  # Garmin-only athlete
    workspace.set_active(root)
    assert "not turned on" in server.hevy_history()["error"]
    assert "not turned on" in server.hevy_push_week()["error"]


def test_workspace_status_reports_integrations(hws, monkeypatch):
    root, _ = hws
    monkeypatch.setenv("HEVY_API_KEY", "abc")
    st = server.workspace_status(str(root))
    assert st["integrations"] == {"garmin": False, "hevy": True, "hevy_key_found": True}


def test_old_database_is_migrated(tmp_path):
    """A database from before Hevy support gets the new columns, the index and the table."""
    root = tmp_path / "old"
    (root / "data").mkdir(parents=True)
    con = sqlite3.connect(root / "data" / "coach.db")
    con.executescript("CREATE TABLE schema_version (version INTEGER NOT NULL); INSERT INTO schema_version VALUES (3);"
                      "CREATE TABLE workouts (id INTEGER PRIMARY KEY, garmin_activity_id TEXT UNIQUE, date TEXT, "
                      "name TEXT, sport TEXT, duration_sec REAL, distance_m REAL, avg_hr REAL, max_hr REAL, "
                      "calories REAL, rpe REAL, feel REAL, block_id TEXT, notes TEXT, garmin_workout_id TEXT);")
    con.close()
    con = db.connect(root)
    assert "hevy_workout_id" in db.columns(con, "workouts")
    assert db.columns(con, "hevy_routines")


# ---------------------------------------------------------------- parsing

def test_parse_workout_drops_warmups_and_maps_exercises():
    row, sets = hevy.parse_workout(_workout("w1", "2026-11-02", routine_id="rt-1"))
    assert row["hevy_workout_id"] == "w1" and row["hevy_routine_id"] == "rt-1" and row["date"] == "2026-11-02"
    assert row["duration_sec"] == 3000
    assert [(s["exercise"], s["weight_kg"], s["reps"]) for s in sets][:2] == [
        ("BARBELL_BENCH_PRESS", 90, 3), ("BARBELL_BENCH_PRESS", 90, 3)]   # same key as Garmin's, warm-up gone
    assert sets[0]["category"] == "BENCH_PRESS"
    assert sets[2]["exercise"] == "PLANK" and sets[2]["duration_sec"] == 45


def test_find_templates_exact_vs_ambiguous():
    hevy.set_client(FakeHevy())
    try:
        assert hevy.resolve_template("barbell bench press")[0] == "05293BCA"
        tid, cands = hevy.resolve_template("pull up")
        assert tid == "11111111"                       # exact words beat "Pull Up (Assisted)"
        tid, cands = hevy.resolve_template("deadlift")
        assert tid is None and cands[0]["id"] == "D04AC939"   # close but not the same words: ask, don't guess
    finally:
        hevy.set_client(None)


# ---------------------------------------------------------------- history + weekly sync

def test_hevy_history(hws):
    root, fake = hws
    fake.workouts = [_workout(f"w{i}", str(TODAY - timedelta(days=3 + 7 * i))) for i in range(4)]
    out = hevy_ops.history(root, weeks=8)
    assert out["profile"]["hevy_pro"] is True
    assert out["training_last_weeks"]["strength"]["sessions"] == 4
    lift = out["strength_top_exercises"][0]
    assert lift["exercise"] == "BARBELL_BENCH_PRESS" and lift["heaviest"].startswith("90kg x3")
    assert out["body_weight"]["latest"].startswith("82.4kg")
    assert "sleep" in out["not_in_hevy"]
    n = lambda: db.connect(root).execute("SELECT count(*) FROM workouts").fetchone()[0]
    assert n() == 4
    hevy_ops.history(root, weeks=8)                       # re-running adds nothing
    assert n() == 4


def test_weekly_sync_adherence_and_proposal(hws):
    root, fake = hws
    workspace.set_active(root)
    # push first so the routine exists, then "train" from it today
    hevy_ops.push_week(root, week=1, include_past=True)
    rid = db.connect(root).execute("SELECT hevy_routine_id FROM hevy_routines").fetchone()[0]
    fake.workouts = [_workout("w1", TODAY.isoformat(), routine_id=rid)]
    out = server.hevy_sync_since((TODAY - timedelta(days=6)).isoformat())
    assert out["adherence"]["done_as_planned"] == 1 and out["adherence"]["rate"] == 1.0
    assert out["sessions"][0]["planned"] == "today_lift wk1"
    assert out["sessions"][0]["avg_set_rpe"] == 8.0
    assert out["effort_logging"].startswith("RPE logged")
    assert "no wearable" in out["recovery_7d_vs_baseline"]
    assert out["proposed"]["status"] and "sleep" in out["proposed"]["not_checked"]
    assert out["block"]["next_week"][0]["in_hevy"] is False  # week 2 not pushed yet


def test_missed_session_counts_against_adherence(hws):
    root, fake = hws
    # a planned lift two days ago that never happened
    blk = copy.deepcopy(BLOCK)
    blk["sessions"][0]["day"] = (TODAY - timedelta(days=2)).strftime("%A")
    blk["start_date"] = (TODAY - timedelta(days=2) - timedelta(days=(TODAY - timedelta(days=2)).weekday())).isoformat()
    (root / "plan" / "blocks" / "block-01-test.yml").write_text(yaml.safe_dump(blk))
    con = db.connect(root)
    db.update(con, "training_blocks", "block_01", {"start_date": blk["start_date"]})
    out = hevy_ops.sync_since(root, (TODAY - timedelta(days=6)).isoformat())
    assert out["adherence"]["missed"] and out["adherence"]["rate"] == 0.0


def test_garmin_and_hevy_records_of_one_session_merge(hws):
    root, fake = hws
    con = db.connect(root)
    d = str(TODAY - timedelta(days=1))
    db.insert(con, "workouts", [{"garmin_activity_id": "9", "date": d, "name": "Strength", "sport": "strength_training",
                                 "avg_hr": 120}])
    gid = con.execute("SELECT id FROM workouts WHERE garmin_activity_id='9'").fetchone()[0]
    db.insert(con, "workout_sets", [{"workout_id": gid, "set_order": 1, "exercise": None, "reps": 6}])
    fake.workouts = [_workout("w1", d)]
    hevy_ops.sync_since(root, d)
    rows = con.execute("SELECT * FROM workouts WHERE date=?", (d,)).fetchall()
    assert len(rows) == 1 and rows[0]["garmin_activity_id"] == "9" and rows[0]["hevy_workout_id"] == "w1"
    assert rows[0]["avg_hr"] == 120                         # watch data kept
    sets = con.execute("SELECT exercise FROM workout_sets WHERE workout_id=?", (rows[0]["id"],)).fetchall()
    assert [s[0] for s in sets] == ["BARBELL_BENCH_PRESS", "BARBELL_BENCH_PRESS", "PLANK"]  # Hevy's sets won


# ---------------------------------------------------------------- push week

def test_push_week_creates_updates_and_keeps(hws):
    root, fake = hws
    out = hevy_ops.push_week(root, week=1, include_past=True)
    lift, run = out["sessions"]
    assert lift["status"] == "created, verified" and run["status"].startswith("skipped: Hevy routines hold strength")
    r = fake.routines[lift["hevy_routine_id"]]
    assert r["folder_id"] == 42 and fake.folders[0]["title"] == "Coach"
    bench, plank = r["exercises"]
    assert [(s["weight_kg"], s["reps"]) for s in bench["sets"]] == [(90, 3)] * 3
    assert bench["rest_seconds"] == 240 and bench["notes"] == "target RPE 7"
    assert plank["exercise_template_id"] == "33333333" and plank["sets"][0]["duration_seconds"] == 30
    assert f"Planned {TODAY.strftime('%a')}" in r["notes"]

    again = hevy_ops.push_week(root, week=1, include_past=True)["sessions"][0]
    assert again["status"].startswith("unchanged")
    posts = [c for c in fake.calls if c[0] == "POST" and c[1] == "/v1/routines"]
    assert len(posts) == 1

    week2 = hevy_ops.push_week(root, week=2, include_past=True)["sessions"][0]
    assert week2["status"] == "updated in place, verified" and week2["hevy_routine_id"] == lift["hevy_routine_id"]
    assert [s["weight_kg"] for s in fake.routines[lift["hevy_routine_id"]]["exercises"][0]["sets"]] == [95, 95]
    assert len(fake.routines) == 1                            # still one routine for the slot


def test_push_week_recreates_a_routine_the_athlete_deleted(hws):
    root, fake = hws
    first = hevy_ops.push_week(root, week=1, include_past=True)["sessions"][0]
    fake.routines.clear()
    out = hevy_ops.push_week(root, week=2, include_past=True)["sessions"][0]
    assert out["status"].startswith("created (the old routine was gone")
    assert out["hevy_routine_id"] != first["hevy_routine_id"]


def test_push_week_dry_run_writes_nothing(hws):
    root, fake = hws
    out = hevy_ops.push_week(root, week=1, include_past=True, dry_run=True)
    assert out["sessions"][0]["status"] == "would create"
    assert not any(c[0] in ("POST", "PUT") for c in fake.calls)


def test_push_week_reports_a_write_hevy_got_wrong(hws):
    root, fake = hws
    fake.mangle = True
    out = hevy_ops.push_week(root, week=1, include_past=True)["sessions"][0]
    assert out["status"].startswith("FAILED verification") and out["problems"]
    row = db.connect(root).execute("SELECT status, payload_hash FROM hevy_routines").fetchone()
    assert row["status"] == "needs_attention" and row["payload_hash"] is None   # next push retries
    fake.mangle = False
    assert hevy_ops.push_week(root, week=1, include_past=True)["sessions"][0]["status"] == "updated in place, verified"


def test_push_week_skips_an_exercise_it_cannot_match(hws):
    root, fake = hws
    blk = copy.deepcopy(BLOCK)
    blk["sessions"][0]["exercises"][1] = {"exercise": "deadlift", "sets": 3, "reps": 5, "weight_kg": 120}
    (root / "plan" / "blocks" / "block-01-test.yml").write_text(yaml.safe_dump(blk))
    out = hevy_ops.push_week(root, week=1, include_past=True)["sessions"][0]
    assert out["status"].startswith("skipped: no Hevy exercise chosen for: deadlift")
    assert "D04AC939 Deadlift (Barbell)" in out["status"]
    assert not any(c[0] == "POST" and c[1] == "/v1/routines" for c in fake.calls)


def test_push_week_skips_past_sessions(hws):
    root, fake = hws
    blk = copy.deepcopy(BLOCK)
    blk["sessions"][0]["date"] = str(TODAY - timedelta(days=1))
    (root / "plan" / "blocks" / "block-01-test.yml").write_text(yaml.safe_dump(blk))
    assert hevy_ops.push_week(root, week=1)["sessions"][0]["status"] == "skipped: date is in the past"
    assert not any(c[0] == "POST" and c[1] == "/v1/routines" for c in fake.calls)
    moved = hevy_ops.push_week(root, week=1, dates={"today_lift": str(TODAY + timedelta(days=1))})["sessions"][0]
    assert moved["status"] == "created, verified"


# ---------------------------------------------------------------- daily check without a wearable

def test_daily_context_has_no_made_up_call(hws):
    root, fake = hws
    fake.workouts = [_workout("w1", str(TODAY - timedelta(days=1)))]
    db.insert(db.connect(root), "injuries", [{"area": "left shoulder", "status": "monitoring"}])
    out = hevy_ops.daily_context(root)
    assert out["proposed_call"] is None and "decision table" in out["why_no_proposal"]
    assert out["plan"]["today"][0]["name"] == "Bench heavy"
    assert out["training_last_7_days"][0]["name"] == "Bench day"
    assert out["open_injuries"] == ["left shoulder (monitoring)"]


def test_daily_context_survives_hevy_being_down(hws):
    root, fake = hws
    fake.request = lambda *a, **k: (_ for _ in ()).throw(hevy.HevyError("down"))
    out = hevy_ops.daily_context(root)
    assert "Hevy not refreshed" in out["hevy"] and out["plan"]["today"]


def test_self_reported_sleep_builds_a_baseline(hws):
    root, _ = hws
    con = db.connect(root)
    ops.store_metrics(con, [{"date": str(TODAY - timedelta(days=n)), "metric": "sleep_hours", "value": 7.5,
                             "source": "self"} for n in range(1, 30)] +
                      [{"date": str(TODAY), "metric": "sleep_hours", "value": 4.0, "source": "self"}])
    out = hevy_ops.daily_context(root)["self_reported_vs_baseline"]
    assert out["sleep_hours"]["flag_today"] == "ORANGE"


# ---------------------------------------------------------------- the real HTTP client (local server)

@pytest.fixture
def http_server(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    seen = {"headers": [], "hits": 0, "mode": "ok"}

    class H(BaseHTTPRequestHandler):
        def _go(self):
            seen["hits"] += 1
            seen["headers"].append({k.lower(): v for k, v in self.headers.items()})
            n = int(self.headers.get("content-length") or 0)
            seen["body"] = self.rfile.read(n).decode() if n else None
            if seen["mode"] == "ratelimit" and seen["hits"] == 1:
                self.send_response(429)
                self.send_header("Retry-After", "0")
                self.end_headers()
                return
            if seen["mode"] == "denied":
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error":"Unauthorized"}')
                return
            if seen["mode"] == "limit":
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'{"error":"routine-limit-exceeded","message":"Free accounts are limited"}')
                return
            out = json.dumps({"ok": True, "path": self.path}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(out)
        do_GET = do_POST = do_PUT = _go

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(hevy, "API", f"http://127.0.0.1:{srv.server_port}")
    yield seen
    srv.shutdown()


def test_client_sends_key_and_json(http_server):
    out = hevy.Client("secret-key").request("POST", "/v1/routines", {"page": 2}, {"routine": {"title": "x"}})
    assert out["path"] == "/v1/routines?page=2"
    h = http_server["headers"][0]
    assert h["api-key"] == "secret-key" and h["content-type"] == "application/json"
    assert http_server["body"] == '{"routine": {"title": "x"}}'


def test_client_retries_rate_limit(http_server):
    http_server["mode"] = "ratelimit"
    assert hevy.Client("k").request("GET", "/v1/user/info")["ok"] and http_server["hits"] == 2


def test_client_turns_a_bad_key_into_the_login_hint(http_server):
    http_server["mode"] = "denied"
    with pytest.raises(hevy.HevyError, match="coach-hevy-auth"):
        hevy.Client("bad").request("GET", "/v1/user/info")


def test_client_keeps_the_routine_limit_message(http_server):
    http_server["mode"] = "limit"
    with pytest.raises(hevy.HevyError, match="routine-limit-exceeded"):
        hevy.Client("k").request("POST", "/v1/routines", body={})


def test_key_lookup_prefers_env_then_file(tmp_path, monkeypatch):
    monkeypatch.delenv("HEVY_API_KEY", raising=False)
    monkeypatch.setenv("HEVY_KEY_FILE", str(tmp_path / "k"))
    assert hevy.api_key() is None and not hevy.configured()
    (tmp_path / "k").write_text("from-file\n")
    assert hevy.api_key() == "from-file"
    monkeypatch.setenv("HEVY_API_KEY", "from-env")
    assert hevy.api_key() == "from-env"
    hevy.set_client(None)
    monkeypatch.delenv("HEVY_API_KEY")
    (tmp_path / "k").unlink()
    with pytest.raises(hevy.HevyError, match="Hevy Pro"):
        hevy.client()


def test_auth_command_saves_an_owner_only_key(tmp_path, monkeypatch, http_server, capsys):
    monkeypatch.setenv("HEVY_KEY_FILE", str(tmp_path / "sub" / "api-key"))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "  pasted-key \n")
    hevy.auth_main()
    p = tmp_path / "sub" / "api-key"
    assert p.read_text().strip() == "pasted-key" and (p.stat().st_mode & 0o777) == 0o600
    assert http_server["headers"][0]["api-key"] == "pasted-key"
    assert "Connected" in capsys.readouterr().out
    http_server["mode"] = "denied"
    p.unlink()
    with pytest.raises(SystemExit, match="didn't work"):
        hevy.auth_main()
    assert not p.exists()                                   # a rejected key is never saved


# ---------------------------------------------------------------- validate_block for non-Garmin athletes

def _validatable(root, garmin_key=None):
    blk = copy.deepcopy(BLOCK)
    blk["exit_criteria"] = ["RPE logged"]
    bench = blk["sessions"][0]["exercises"][0]
    bench.pop("weeks")
    bench.update(sets=3, reps=3, weight_kg=90, rpe=7)
    if garmin_key:
        bench["garmin"] = garmin_key
    (root / "plan" / "blocks" / "block-01-test.yml").write_text(yaml.safe_dump(blk))


def test_validate_block_ignores_garmin_when_garmin_is_off(hws):
    root, _ = hws
    _validatable(root, garmin_key={"category": "NOPE", "exercise": "NOPE"})   # invalid for Garmin, irrelevant here
    out = ops.validate_block(root)
    assert out["ok"], out
    assert any("plank" in w and "template_id" in w for w in out["warnings"])    # Hevy ids are advised
    assert not any("barbell_bench_press" in w and "template_id" in w for w in out["warnings"])


def test_validate_block_still_checks_garmin_keys_for_garmin_athletes(hws):
    root, _ = hws
    _validatable(root, garmin_key={"category": "NOPE", "exercise": "NOPE"})
    workspace.set_integrations(root, garmin=True)
    out = ops.validate_block(root)
    assert not out["ok"] and any("not in Garmin's taxonomy" in e for e in out["errors"])


def test_exercise_library_is_cached_until_refreshed():
    fake = FakeHevy()
    hevy.set_client(fake)
    try:
        hevy.find_templates("plank")
        hevy.find_templates("plank")
        n = lambda: len([c for c in fake.calls if c[1] == "/v1/exercise_templates"])
        assert n() == 1
        TEMPLATES.append({"id": "99999999", "title": "Copenhagen Plank", "type": "duration",
                          "primary_muscle_group": "adductors", "equipment": "none", "is_custom": True})
        try:
            assert hevy.find_templates("copenhagen plank")[0]["title"] != "Copenhagen Plank"   # stale
            assert hevy.find_templates("copenhagen plank", refresh=True)[0]["id"] == "99999999"
        finally:
            TEMPLATES.pop()
    finally:
        hevy.set_client(None)


def test_dated_session_is_planned_once_not_once_per_week(hws):
    root, fake = hws
    blk = copy.deepcopy(BLOCK)
    blk["sessions"][0]["date"] = str(TODAY - timedelta(days=1))
    (root / "plan" / "blocks" / "block-01-test.yml").write_text(yaml.safe_dump(blk))
    out = hevy_ops.sync_since(root, (TODAY - timedelta(days=3)).isoformat())
    assert out["adherence"]["planned"] == 1 and len(out["adherence"]["missed"]) == 1


def test_push_week_explains_a_reps_value_hevy_cannot_hold(hws):
    root, fake = hws
    blk = copy.deepcopy(BLOCK)
    blk["sessions"][0]["exercises"][0].pop("weeks")
    blk["sessions"][0]["exercises"][0].update(sets=3, reps="AMRAP", weight_kg=60)
    (root / "plan" / "blocks" / "block-01-test.yml").write_text(yaml.safe_dump(blk))
    msg = hevy_ops.push_week(root, week=1, include_past=True)["sessions"][0]["status"]
    assert "AMRAP" in msg and "range like 8-12" in msg
    blk["sessions"][0]["exercises"][0]["reps"] = "8-12"
    (root / "plan" / "blocks" / "block-01-test.yml").write_text(yaml.safe_dump(blk))
    out = hevy_ops.push_week(root, week=1, include_past=True)["sessions"][0]
    assert out["status"] == "created, verified"
    assert fake.routines[out["hevy_routine_id"]]["exercises"][0]["sets"][0]["rep_range"] == {"start": 8, "end": 12}
