---
name: coach-plan
description: Builds or revises the garmin-coach long-term roadmap (goals, milestone ladder, block sequence, timeline) and fills in training blocks at session level - exercises, sets, reps, loads from %1RM or zones, progression, deloads, exit criteria. Use when creating the first plan after setup, when a block ends and the next must be filled in, when goals/equipment/schedule change, or when the user asks to plan, replan or restructure training.
---

# Planning

Load `coach-core` (`../coach-core/SKILL.md`), the goal module for every
active goal (`../coach-core/goals/`) and the file formats
(`../coach-core/references/plan-format.md`).

## Inputs

`athlete/profile.md`, `equipment.yml`, `schedule.yml`, `nutrition.md`,
`goals` and `injuries` tables, `goal_progress()`, recent
`training_summary`, `readiness_report()`, open hypotheses, previous blocks
and their logs/reviews.

## Roadmap (long term)

1. **Goals in priority order**, each measurable (metric, baseline, target).
2. **Milestone ladder** per primary goal. Rung sizes and realistic rates
   come from the goal module. Dates are estimates with a confidence level:
   MEDIUM at best for the next rung, LOW beyond. Don't extrapolate a line
   from a handful of points.
3. **Block sequence**: archetypes from the module, ordered to reach the next
   milestone. Secondary goals get a maintenance dose inside each block,
   and lower priorities give way when they conflict.
4. **Timeline**: chained block durations. Blocks end on exit criteria, not
   the calendar, so state that dates slide.
5. Write a `notes` paragraph explaining the shape of the plan and the
   alternatives you rejected.

## Blocks (detail only what's near)

- Active and next block: **session level**. Later blocks: purpose, duration
  and `planned_fill_trigger` only, with `data_status: PROJECTED`.
- For each session, fit `schedule.yml` (days, length). Estimate session
  duration from sets x (work + rest) and stay within the cap.
- Only equipment from `equipment.yml`; use substitutes per
  `../coach-core/references/equipment.md`.
- Loads: `prescribe_load(one_rm, reps, rpe|pct, implement)`. Store both
  `pct_1rm` and the rounded `weight_kg`. Endurance: zones/paces from the
  athlete's Garmin HR zones or LT data, written as a `structure` in the
  plan-format shape (one zone, a bpm range or a pace range per step) so
  `push_week` can build it.
- Each exercise gets a Garmin mapping (`find_garmin_exercise`) so syncing is
  mechanical.
- Periodize effort inside the block: conservative week 1, building, then a
  deload or taper where the archetype calls for it.
- Respect injuries: caps, swaps and monitoring rules go into `cautions`.
- Nutrition target per block (surplus / maintenance / deficit) to match the phase.
- Exit criteria that can actually be checked from data.

## Activation

1. Write `plan/roadmap.yml` and `plan/blocks/block-NN-<slug>.yml`.
2. `upsert_training_block` for every block (status planned, or active for
   the one starting now).
3. `goals`/`milestones` rows in the db match the roadmap.
4. `validate_block("<file>")` for every filled block. Fix each error in
   the yml and validate again until `ok`. Fix or justify each warning
   (a deliberate load jump, a longer test day).
5. Run `coach-review` before the block goes active. Fix or log anything it
   flags.
6. `coach-garmin-sync` to push the first week (or the current week).
7. `log` to `plan_changes` for any revision of an existing plan, with the reason.

## Revising mid-block

Change the minimum that the evidence supports. Changing one variable at a
time keeps cause and effect readable. Edit the yml, add a `log` line, update
`plan_changes`, and re-push affected Garmin workouts.
