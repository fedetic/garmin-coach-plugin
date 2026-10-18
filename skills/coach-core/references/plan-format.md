# Plan file formats

## `plan/roadmap.yml`

```yaml
version: 3
updated: 2026-10-17
goals:                     # mirrors the goals table, priority order
  - {priority: 1, name: bench_120, module: strength, metric: e1rm:BARBELL_BENCH_PRESS,
     target: 120, unit: kg, current: "100 (tested 2026-09-09)"}
  - {priority: 2, name: sub_50_10k, module: endurance, metric: race:10k, target: 3000, unit: s,
     current: "Garmin race predictor 52:40"}
milestones:                # rungs toward each goal; dates are estimates, revised every block
  - {goal: bench_120, ladder: [105, 110, 115, 120], confidence: "MEDIUM for next rung, LOW beyond"}
blocks:
  list:
    - {id: block_01, file: block-01-strength-base.yml, status: complete}
    - {id: block_02, file: block-02-peak.yml, status: active}
    - {id: block_03, file: block-03-test.yml, status: planned}
timeline:                  # chained estimates; re-chain (don't relabel) when a block over/under-runs
  - {block: block_02, weeks: 5, start: 2026-09-14, end: 2026-10-18}
  - {block: block_03, weeks: 1, start: 2026-10-19, end: 2026-10-25}
notes: >
  Why the plan is shaped this way, in a few sentences. Include rejected alternatives.
```

## `plan/blocks/block-NN-<slug>.yml`

```yaml
id: block_02
name: "Peak to 105kg"
status: planned | active | complete | merged
purpose: >
  One paragraph: what this block is for and why now.
duration_weeks: 5
start_date: 2026-09-14
end_date: 2026-10-18       # estimate, slides with exit criteria
data_status: PROJECTED | MEASURED   # PROJECTED = loads are %-of-something not yet confirmed
planned_fill_trigger:      # required while PROJECTED
  when: "previous block's test result is in"
  basis: ["tested 1RM", "readiness green"]
primary_adaptations: ["peak strength expression"]
sessions_per_week: 4
nutrition_target: "maintenance (peaking block)"
progression_strategy: >
  How load/volume/intensity move week to week, and what RPE overrides.
deload_strategy: "weeks 4-5 taper"
secondary_goals:
  endurance: "2x easy Z2 runs, 30-40 min, never the day before heavy bench"
exit_criteria:
  - "RPE 7-9 logged across weeks 1-3"
  - "no injury flare"
cautions:
  - "rows capped at 45kg (lower-back history)"

sessions:
  - id: mon_heavy
    day: Monday
    name: "Mon - Bench heavy"
    kind: strength
    # test: true             # test/max day: stricter readiness rules (also inferred from "test"/"max"/"1RM" in the name)
    exercises:
      - exercise: barbell_bench_press
        garmin: {category: BENCH_PRESS, exercise: BARBELL_BENCH_PRESS}
        rest_sec: 240
        weeks:               # per-week prescription; omit `weeks` if constant
          1: {sets: 3, reps: 2, pct_1rm: 0.90, weight_kg: 90, rpe: 7}
          2: {sets: 2, reps: 2, pct_1rm: 0.94, weight_kg: 95, rpe: 7.5}
      - exercise: dead_bug
        garmin: {category: HIP_STABILITY, exercise: DEAD_BUG}
        sets: 3
        reps: 10
        note: "per side"
  - id: wed_easy_run
    day: Wednesday
    name: "Wed - Easy run"
    kind: endurance
    sport: running
    structure:               # maps to garmin create_run_workout / create_run_interval_workout
      warmup: {duration_min: 10, target: "Z1-Z2"}
      main: {duration_min: 30, target: {hr_zone: 2}}
      cooldown: {duration_min: 5}
    weeks:
      1: {main_duration_min: 30}
      2: {main_duration_min: 35}

log:                         # dated actuals and decisions, newest first, one or two lines each
  - "2026-09-28 wk3 Mon: 2x1 @97.5kg, workout_rpe 80 = RPE8, matches target"
garmin:                      # pushed workout ids (also in the garmin_workouts table)
  week_1: {mon_heavy: "<garmin_workout_id>"}
reviews: "see agent_reviews WHERE block_id='block_02'"
```

Conventions:
- `weight_kg` is always the rounded, buildable load (`prescribe_load`), and
  `pct_1rm` keeps the reasoning.
- Put actuals and changes in `log`, not as comments scattered through the file.
- Changing a block = edit the yml + `log` to `plan_changes` + re-push the
  affected Garmin workouts.
- Mirror status/dates in the db with `upsert_training_block`.
