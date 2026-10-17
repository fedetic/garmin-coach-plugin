---
name: coach-garmin-sync
description: Pushes garmin-coach block sessions to Garmin Connect as structured workouts and schedules them on the athlete's calendar - strength via validated repeat-group payloads, runs/rides via Garmin's workout tools - then verifies them and cleans up superseded templates. Use when a block activates, when a weekly check-in changes next week's sessions, when a daily check modifies today's workout, or when the user asks to push, fix or reschedule Garmin workouts. Not for reading Garmin history.
---

# Garmin workout sync

Load `coach-core` (`../coach-core/SKILL.md`). Inputs: the active block yml
(the target week's prescriptions), `athlete/schedule.yml`, and the dates to
schedule.

## Naming

`"<Day> - <session name>"`, plus `" (wkN)"` when loads differ by week, e.g.
`"Mon - Bench heavy (wk3)"`. Garmin truncates long names, so keep them under
about 32 characters.

## Strength sessions

1. **Map exercises.** Use each exercise's `garmin: {category, exercise}`
   from the yml. Missing ones: `find_garmin_exercise(name)`, pick the right
   one, and write it back into the yml so next time is mechanical. Things
   Garmin has no exercise for (handstand hold, mobility circuit, stretch
   routine) get `plain: true` with the target in the name.
2. **Build.** Call `build_strength_workout(name, exercises)`, where each
   exercise is `{name, category, exercise, sets, reps | duration_sec,
   weight_kg, rest_sec, note}` from that week's prescription. Include the
   **full session**, accessories, core and mobility as well as the main lifts.
   Check the exercise count against the yml. Read `warnings`: each one is
   a step that won't be recognised by the watch.
3. **Upload.** Send the returned `workout` to the garmin server's
   `upload_workout`.
4. **Verify.** `get_workout_by_id` on the new id. For every weighted step,
   check that category/exercise name are populated, weight and unit are
   present, and steps with sets > 1 are inside a repeat with the right count.
   Diff against the yml; don't eyeball it.

Why the builder instead of `create_strength_workout`: that tool's `sets`
field is decorative (one step per entry, no real repeats, rest fires once)
and its weight field is dropped. The builder encodes the payload rules that
Garmin actually accepts (see the module docstring in the coach server's
`garmin.py`). If a payload field is in doubt, the garmin server has
reference resources `workout://reference/structure` and
`workout://templates/strength-circuit`; read them rather than guessing.

## Endurance sessions

Use the garmin server's `create_run_workout`, `create_run_interval_workout`,
`create_walk_run_workout`, or `upload_workout` for custom structures (HR
zone or pace targets, other sports). Read the tool's docstring for target
formats and check `workout://reference/structure` for sport and target
type ids. Targets come from the athlete's Garmin HR zones or LT pace in the
block yml.

## Schedule

`schedule_week([{date, workout_id}, ...])` for a week, or
`schedule_workout(workout_id, date)` for one day. Both are idempotent. Then
`register_garmin_workout(id, name, block_id, week, session, scheduled_date)`
for each, and add the ids to the block yml under `garmin:`.

## Replace or correct

1. Find the old entries: `query("SELECT * FROM garmin_workouts WHERE
   status='scheduled' AND scheduled_date >= ?")` and/or
   `get_scheduled_workouts(start, end)`.
2. `unschedule_workout(scheduled_workout_id)`, then `delete_workout` the old
   template, unless another date still uses it.
3. `update_record("garmin_workouts", id, {"status": "replaced"})`.
4. Build, upload, verify and schedule the new one.

Don't leave duplicate or orphaned templates in the athlete's library.
Clean up in the same turn.

## Reuse

If a session is unchanged from a template already in Garmin (same exercises,
sets, reps, loads), reschedule the existing template instead of creating a
duplicate.

## Report

One line per day: `Tue 10-20 - Lower body (wk2) ✓ scheduled`, plus any
builder warnings the athlete should know about.
