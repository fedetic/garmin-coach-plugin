-- garmin-coach athlete database. One file per athlete workspace: data/coach.db
-- Bump schema_version and add a migration in db.py when this changes.

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

-- Free-form durable facts about the athlete (mirrors athlete/profile.md for querying).
CREATE TABLE IF NOT EXISTS profile (
  key TEXT PRIMARY KEY, value TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- module: strength | hypertrophy | endurance | calisthenics | body_composition | general
-- metric/target_value/unit make the goal measurable (e.g. bench_1rm 140 kg, vo2max 55 ml/kg/min,
-- 10k_time 2700 s, body_weight 75 kg, muscle_up_reps 1 reps).
CREATE TABLE IF NOT EXISTS goals (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, module TEXT, priority INTEGER,
  metric TEXT, target_value REAL, unit TEXT, baseline_value REAL, baseline_date TEXT,
  direction TEXT DEFAULT 'increase', target_date TEXT, status TEXT DEFAULT 'active',
  notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS milestones (
  id INTEGER PRIMARY KEY, goal TEXT NOT NULL, target_value REAL, unit TEXT,
  estimated_date TEXT, confidence TEXT, prerequisites TEXT,
  status TEXT DEFAULT 'pending', achieved_at TEXT, achieved_value REAL
);

-- Daily wearable metrics, one row per (date, metric). Feed of the readiness tool.
-- Canonical metric names: see readiness.METRICS.
CREATE TABLE IF NOT EXISTS health_metrics (
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, metric TEXT NOT NULL, value REAL,
  unit TEXT, source TEXT DEFAULT 'garmin', UNIQUE(date, metric)
);

CREATE TABLE IF NOT EXISTS body_metrics (
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, weight_kg REAL, body_fat_pct REAL,
  source TEXT DEFAULT 'garmin', confidence TEXT DEFAULT 'HIGH', UNIQUE(date, source)
);

CREATE TABLE IF NOT EXISTS workouts (
  id INTEGER PRIMARY KEY, garmin_activity_id TEXT UNIQUE, date TEXT, name TEXT,
  sport TEXT, duration_sec REAL, distance_m REAL, avg_hr REAL, max_hr REAL,
  calories REAL, rpe REAL, feel REAL, block_id TEXT, notes TEXT,
  garmin_workout_id TEXT       -- the planned Garmin workout this session was started from
);

CREATE TABLE IF NOT EXISTS workout_sets (
  id INTEGER PRIMARY KEY, workout_id INTEGER NOT NULL, set_order INTEGER,
  category TEXT, exercise TEXT, weight_kg REAL, reps INTEGER, duration_sec REAL,
  rpe REAL, FOREIGN KEY(workout_id) REFERENCES workouts(id)
);

-- status: active | monitoring | resolved
CREATE TABLE IF NOT EXISTS injuries (
  id INTEGER PRIMARY KEY, area TEXT, description TEXT, first_reported TEXT,
  status TEXT, severity TEXT, trigger_movements TEXT, modifications TEXT, resolution TEXT
);

-- id is the block's string id from plan/roadmap.yml (e.g. block_01).
CREATE TABLE IF NOT EXISTS training_blocks (
  id TEXT PRIMARY KEY, name TEXT, file TEXT, purpose TEXT, start_date TEXT, end_date TEXT,
  primary_adaptations TEXT, exit_criteria TEXT, status TEXT DEFAULT 'planned'
);

-- One row per specialist verdict. verdict: APPROVE | CONDITIONAL | REJECT
CREATE TABLE IF NOT EXISTS agent_reviews (
  id INTEGER PRIMARY KEY, block_id TEXT, agent TEXT, verdict TEXT, notes TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plan_changes (
  id INTEGER PRIMARY KEY, date TEXT, block_id TEXT, change TEXT, reason TEXT, decided_by TEXT
);

-- type: fact | calculation | interpretation | hypothesis | decision
-- confidence: HIGH | MEDIUM | LOW
CREATE TABLE IF NOT EXISTS observations (
  id INTEGER PRIMARY KEY, date TEXT, type TEXT, statement TEXT, confidence TEXT,
  related_goal TEXT, status TEXT DEFAULT 'open'
);

-- kind: daily | weekly | block_review | test
-- status (weekly): AHEAD | ON_TRACK | SLIGHTLY_BEHIND | SIGNIFICANTLY_BEHIND | AT_RISK
-- status (daily): GO | MODIFY | REST
CREATE TABLE IF NOT EXISTS checkins (
  id INTEGER PRIMARY KEY, date TEXT, kind TEXT DEFAULT 'weekly', status TEXT,
  risk TEXT, summary TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Every workout template the coach pushed to Garmin, so stale ones can be cleaned up.
CREATE TABLE IF NOT EXISTS garmin_workouts (
  id INTEGER PRIMARY KEY, garmin_workout_id TEXT NOT NULL, name TEXT, block_id TEXT,
  week INTEGER, session TEXT, scheduled_date TEXT, status TEXT DEFAULT 'scheduled',
  payload_hash TEXT,           -- lets push_week reuse an unchanged template
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
