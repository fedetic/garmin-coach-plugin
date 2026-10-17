---
name: coach-weekly
description: Weekly check-in for the garmin-coach - pulls the week's Garmin training and recovery data, compares it to the block plan and the athlete's baselines, classifies progress (AHEAD to AT RISK) with facts separated from hypotheses, applies justified plan changes, and pushes next week's workouts to Garmin. Use for "weekly check-in", "weekly review", "how did my week go", or at the end of a training week.
---

# Weekly check-in

Load `coach-core` first (`../coach-core/SKILL.md`), plus the goal module(s)
for the athlete's active goals.

## 1. Gather (never fabricate; report gaps)

- `workspace_status`, `journal/context.md`, the active block yml (this
  week's and next week's prescriptions, exit criteria, cautions).
- Garmin, since the last weekly check-in:
  - activities (`get_activities_by_date`): for each, `import_activity`
    (strength: with `get_activity_exercise_sets`; also `workout_rpe`/`feel`
    from `get_activity`)
  - daily recovery metrics for every day missing in the db: `record_metrics`
  - weight (`get_weigh_ins`) and nutrition logs if any
  - endurance goals: `get_vo2max_trend`, `get_training_status`,
    `get_training_load_balance`, `get_race_predictions`, `get_running_tolerance`
- Coach server: `readiness_report()`, `training_summary(week_start, today)`
  and the same for the previous week, and `goal_progress()`.
- Ask the athlete only what the data can't tell you: missed sessions and
  why, pain/injury updates, RPE where Garmin's is missing or flat, sleep or
  life context, nutrition consistency. Ask once, batched.

## 2. Analyse

- **Adherence**: planned vs done (sessions, sets, loads, durations).
- **Performance**: actual vs prescribed loads/RPE/paces; e1RM or key-metric
  trend; PRs.
- **Recovery**: each factor's 7-day mean vs baseline, repeated deterioration.
- **Plan fit**: is the block on course for its exit criteria? Is the
  specialist's limiter hypothesis supported or contradicted?
- Compare against: last week, the block's start, and the longer baseline.

Classify **status**: AHEAD / ON TRACK / SLIGHTLY BEHIND / SIGNIFICANTLY
BEHIND / AT RISK. Classify **risk**: GREEN / YELLOW / ORANGE / RED (Injury-Risk
role, multiple indicators).

## 3. Decide changes (only if the evidence justifies them)

Go through the relevant specialist roles
(`../coach-core/references/specialists.md`). Typical outcomes: progress
as written / hold / adjust next week / insert a deload / retest early /
modify around an injury / extend or end the block (exit criteria met).
Resolve conflicts properly (frequency vs volume vs intensity, sleep or food
first, priority order) and don't average.

If the plan changes:
1. edit the block yml (next week's prescription; add a `log` line)
2. `log` to `plan_changes` (date, block_id, change, reason, decided_by)
3. push next week to Garmin with `coach-garmin-sync`, and clean up
   superseded templates

If nothing changes, still push next week's workouts if they aren't on the
calendar yet.

Block finished (exit criteria met or time is up): run `coach-plan` to fill
the next block (it was PROJECTED), then `coach-review` before activating.

## 4. Report

```
## Status: ON TRACK · Risk: YELLOW
<2-3 sentence summary>

**Observed facts**
- ...
**Hypotheses** (confidence)
- ...

### <Primary goal> - e1RM/metric, trend, distance to next milestone, block week X/Y
### Training - adherence, volume/intensity, RPE accuracy, PRs
### Recovery - HRV · RHR · sleep · Body Battery · stress vs baseline (each with flag)
### <Secondary goals> - one line each (skills, maintenance lifts, mobility/core)
### Nutrition - weight trend, intake vs phase target
### Risks - Green/Yellow/Orange/Red items with what triggers escalation
### Changes for next week - what changed and why (or "none, progressing as planned")
### Next week on Garmin - day: session (pushed ✓)
```

## 5. Log

- `checkins`: `{date, kind: 'weekly', status, risk, summary}`
- `observations`: new facts, calculations, hypotheses (with confidence),
  decisions. Close resolved hypotheses with `update_record` (status
  confirmed/refuted).
- `milestones`: achieved rungs (`status`, `achieved_at`, `achieved_value`),
  revised estimates.
- `athlete/profile.md`: only durable changes (new max, injury resolved,
  new successful strategy).
- `journal/context.md`: overwrite with the week's handover (what was pushed,
  open questions for next time).
