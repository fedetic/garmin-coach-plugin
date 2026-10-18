---
name: coach-garmin-sync
description: Pushes garmin-coach block sessions to Garmin Connect as structured workouts and schedules them on the athlete's calendar - strength, runs, rides and walks from the block yml in one call - then verifies them and cleans up superseded templates. Use when a block activates, when a weekly check-in changes next week's sessions, when a daily check modifies today's workout, or when the user asks to push, fix or reschedule Garmin workouts. Not for reading Garmin history.
---

# Garmin workout sync

Load `coach-core` (`../coach-core/SKILL.md`). The block yml is the source of
truth: edit it first, then push.

## Push (normal path)

1. Make sure every session in the target week is pushable:
   - strength: each exercise has `garmin: {category, exercise}`. Missing:
     `find_garmin_exercise(name)`, pick the right one and write it into the
     yml. Things Garmin has no exercise for (handstand hold, mobility
     circuit) get `plain: true`.
   - run/ride/walk: `sport` and a `structure` in the format of
     `../coach-core/references/plan-format.md`.
2. After editing the yml, `validate_block()` and fix any errors first.
3. `push_week(week=N, dry_run=true)` when anything is unusual (new block,
   moved days, first push): it shows per session `would create`,
   `would replace <id>` or `would keep (unchanged)`, plus builder warnings.
4. `push_week(week=N)`. For each session it builds the workout from the yml,
   uploads it, reads it back and compares it step by step (a mismatch
   deletes the upload and reports `FAILED verification` with the
   differences), schedules it, then unschedules and deletes the version it
   replaces. Unchanged sessions keep their existing template.
   - Move sessions: `dates={session_id: "YYYY-MM-DD"}`.
   - Defaults: active block, current week; past dates skipped unless
     `include_past=true`.
5. Read the result:
   - `warnings`: steps the watch won't recognise (unknown exercise, target
     not understood). Fix the yml and push again.
   - `skipped: ...`: the reason says what's missing.
   - `FAILED verification`: don't retry blindly. Check the yml values the
     `problems` name; if the yml is right, report it.
   - `other_workouts_that_day`: something not from this push is on the
     calendar (an old manual workout, a Garmin Coach plan). Ask before
     removing it.

Names come out as `"<Day> - <session name> (wkN)"`. Keep session names short;
Garmin truncates around 32 characters.

## Manual path (fallback)

Use it when `push_week` reports a Garmin login error, or for a sport it
doesn't build yet (swimming and other sports). It needs the garmin server.

1. Build: `build_strength_workout(name, exercises)` for strength. For other
   sports, use the garmin server's `upload_workout` with the sportType from
   `workout://reference/structure`. Don't use `create_strength_workout`:
   its sets are decorative and its weights are dropped.
2. Upload with `upload_workout`, then `get_workout_by_id` and diff every
   step against the yml (category/exercise, weight, reps or duration,
   repeat counts, targets).
3. `schedule_workout(workout_id, date)`, then
   `register_garmin_workout(id, name, block_id, week, session, scheduled_date)`.
4. Replacing: `unschedule_workout` the old entry, `delete_workout` its
   template unless another date uses it, and
   `update_record("garmin_workouts", id, {"status": "replaced"})`.

Don't leave duplicate or orphaned templates in the athlete's library.

## Report

One line per day: `Tue 10-20 - Lower body (wk2) ✓ scheduled` (or
`unchanged`, `skipped: <reason>`), plus any warning the athlete should know
about.
