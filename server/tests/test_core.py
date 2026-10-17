import json
from datetime import date, timedelta

import pytest

from coach_mcp import calc, db, garmin, readiness, workspace


def test_pct_chart_anchor_points():
    assert calc.pct_of_1rm(1, 10) == 1.0
    assert calc.pct_of_1rm(1, 9) == 0.955       # 1 @ 9 == 2 @ 10
    assert calc.pct_of_1rm(1, 9.5) == pytest.approx(0.9775, abs=1e-3)
    assert calc.pct_of_1rm(5, 8) == calc.pct_of_1rm(7, 10)


def test_e1rm_flags_missing_rpe():
    est = calc.e1rm(100, 3, 8)
    assert est["e1rm"] == pytest.approx(100 / 0.862, abs=0.2)
    assert "assumed to failure" in calc.e1rm(100, 3)["notes"]


def test_round_load_plates():
    eq = {"bar_kg": 20, "plates_kg": {20: 4, 10: 2, 5: 2, 2.5: 2, 1.25: 2}}
    assert calc.round_load(101.3, eq)["load"] == 102.5  # 1.25 plates -> 2.5kg steps
    assert calc.round_load(98.9, eq)["load"] == 100.0
    assert calc.round_load(101.2, eq, "down")["load"] == 100.0
    assert calc.round_load(500, eq)["warning"]
    assert calc.round_load(13, {"weights_kg": [10, 12.5, 15]})["load"] == 12.5


def test_find_exercise_exact():
    top = garmin.find_exercise("barbell bench press")[0]
    assert (top["category"], top["exercise"]) == ("BENCH_PRESS", "BARBELL_BENCH_PRESS")
    assert garmin.find_exercise("RDL")[0]["exercise"].startswith("ROMANIAN_DEADLIFT")


def test_build_workout_structure():
    out = garmin.build_strength_workout("Mon - heavy", [
        {"name": "Barbell Bench Press", "sets": 3, "reps": 2, "weight_kg": 101.25, "rest_sec": 240},
        {"name": "Handstand hold", "duration_sec": 30, "plain": True},
        {"name": "Plank", "category": "PLANK", "exercise": "PLANK", "sets": 2, "duration_sec": 45, "rest_sec": 60},
        {"name": "Mystery move", "sets": 1, "reps": 5},
    ])
    steps = out["workout"]["workoutSegments"][0]["workoutSteps"]
    assert steps[0]["stepType"]["stepTypeKey"] == "warmup"
    bench = steps[1]
    assert bench["type"] == "RepeatGroupDTO" and bench["numberOfIterations"] == 3
    work, rest = bench["workoutSteps"]
    assert work["exerciseName"] == "BARBELL_BENCH_PRESS" and work["weightValue"] == 101.25
    assert work["endCondition"]["conditionTypeKey"] == "reps" and rest["endConditionValue"] == 240
    assert "category" not in steps[2]
    orders = []

    def walk(ss):
        for s in ss:
            orders.append(s["stepOrder"])
            walk(s.get("workoutSteps", []))
    walk(steps)
    assert orders == list(range(1, len(orders) + 1))
    assert any("Mystery move" in w for w in out["warnings"])


def test_parse_raw_sets():
    raw = [{"setType": "ACTIVE", "exercises": [{"category": "BENCH_PRESS", "name": "INCLINE_BARBELL_BENCH_PRESS"}],
            "repetitionCount": 6, "weight": 65000.0, "duration": 41},
           {"setType": "REST", "exercises": [], "duration": 120},
           {"setType": "ACTIVE", "exercises": [{"category": "UNKNOWN", "name": None}], "repetitionCount": 6, "weight": None}]
    rows = garmin.parse_exercise_sets(raw)
    assert len(rows) == 2 and rows[0]["weight_kg"] == 65 and rows[1]["category"] is None


def test_readiness_flags_relative_to_baseline():
    today = date(2026, 10, 17)
    rows = [{"date": (today - timedelta(days=i)).isoformat(), "metric": "hrv_overnight_ms",
             "value": 52 + (i % 3)} for i in range(7, 60)]
    rows += [{"date": (today - timedelta(days=i)).isoformat(), "metric": "hrv_overnight_ms", "value": 40}
             for i in range(0, 7)]
    out = readiness.assess(rows, today.isoformat())
    f = out["factors"]["hrv_overnight_ms"]
    assert f["flag_today"] == "ORANGE" and f["bad_days_last_7"] == 7
    assert "hrv_overnight_ms" in out["summary"]["repeated_deterioration"]


def test_workspace_and_db(tmp_path):
    root, created = workspace.init(str(tmp_path / "me"), athlete_name="Test")
    assert "athlete/profile.md" in created and (root / "AGENTS.md").exists()
    con = db.connect(root)
    db.insert(con, "observations", [{"date": "2026-10-17", "type": "fact", "statement": "x", "confidence": "HIGH"}])
    with pytest.raises(ValueError):
        db.insert(con, "observations", [{"type": "guess"}])
    with pytest.raises(ValueError):
        db.query(root, "DELETE FROM observations")
    assert db.query(root, "SELECT count(*) n FROM observations")[0]["n"] == 1
    # re-init never overwrites
    (root / "athlete/profile.md").write_text("mine")
    workspace.init(str(root))
    assert (root / "athlete/profile.md").read_text() == "mine"


def test_codex_install_roundtrip(tmp_path, monkeypatch):
    import tomllib
    from coach_mcp import codex
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("CODEX_SKILLS_DIR", str(tmp_path / "skills"))
    (tmp_path / "codex").mkdir()
    (tmp_path / "codex" / "config.toml").write_text('model = "x"\n')
    codex.install()
    codex.install()  # idempotent
    cfg = tomllib.loads((tmp_path / "codex" / "config.toml").read_text())
    assert cfg["model"] == "x" and set(cfg["mcp_servers"]) == {"coach", "garmin"}
    assert (tmp_path / "skills" / "coach-core" / "SKILL.md").exists()
    codex.uninstall()
    assert tomllib.loads((tmp_path / "codex" / "config.toml").read_text()) == {"model": "x"}
    assert not list((tmp_path / "skills").iterdir())
    assert (codex.PLUGIN_ROOT / "skills" / "coach-core" / "SKILL.md").exists()


def test_session_dump_and_restore(tmp_path, monkeypatch, capsys):
    from coach_mcp import session
    root, _ = workspace.init(str(tmp_path / "ws"))
    db.insert(db.connect(root), "checkins", [{"date": "2000-01-01", "kind": "weekly", "status": "ON_TRACK"}])
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setattr("sys.argv", ["coach-session", "end"])
    session.main()
    (root / "data" / "coach.db").unlink()
    monkeypatch.setattr("sys.argv", ["coach-session", "start"])
    session.main()
    out = capsys.readouterr().out
    assert "rebuilt" in out and "weekly check-in" in out
    assert db.query(root, "SELECT count(*) n FROM checkins")[0]["n"] == 1
