---
name: coach-weekly
description: Weekly check-in for the garmin-coach - pulls the week's Garmin training and recovery data, compares it to the block plan and the athlete's baselines, classifies progress (AHEAD to AT RISK) with facts separated from hypotheses, applies justified plan changes, and pushes next week's workouts to Garmin. Use for "weekly check-in", "weekly review", "how did my week go", or at the end of a training week.
---

# Weekly check-in

Load `coach-core` first (`../coach-core/SKILL.md`), plus the goal module(s)
for the athlete's active goals.

## 1. Gather (never fabricate; report gaps)

- `workspace_status` and `journal/context.md` (open questions from last time).
- `garmin_sync_since()` (one call; defaults to everything since the last
  weekly check-in). It imports the week's activities (strength sets parsed),
  backfills recovery metrics and VO2max, and returns:
  - `proposed`: draft **status** and **risk** with the reasons behind them
  - `adherence` (planned vs done, `rate`, `missed`), `sessions` (sets,
    loads, duration, effort per session), `effort_logging` quality,
    `unclassified_sets_total`
  - `recovery_7d_vs_baseline`, `repeated_deterioration`, `garmin_hrv_status`,
    `body_weight_avg`, `vo2max`, `goal_progress`, `open_injuries`
  - `block`: week X of Y, exit criteria, cautions, and `next_week` sessions
    with their loads and whether each is already `on_garmin`
- Endurance goals, if the garmin server is available: `get_training_status`,
  `get_training_load_balance`, `get_race_predictions`, `get_running_tolerance`.
- Ask the athlete only what the data can't tell you: missed sessions and
  why, pain/injury updates, RPE where Garmin's is missing or flat, sleep or
  life context, nutrition consistency. Ask once, batched.

If `garmin_sync_since` fails with a Garmin login error, tell the athlete the
fix it names. With the garmin server available, fall back to
`get_activities_by_date` + `import_activity`, `record_metrics`,
`readiness_report()`, `training_summary(week_start, today)` and
`goal_progress()`.

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
role, multiple indicators). Start from `proposed`: it applies adherence, goal
trends, 7-day recovery and injuries, but not what the athlete tells you or
sessions done without starting the Garmin workout. Confirm it or override
it with a reason. RED only comes from reported red-flag symptoms
(`../coach-core/references/safety.md`). `status: null` means the data can't
tell, so classify from the conversation.

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
3. `push_week(week=<next week>)`: it rebuilds only the sessions that
   changed, verifies them, and removes the superseded versions (run/ride
   sessions still go through `coach-garmin-sync`)

If nothing changes, still push next week if any `block.next_week` session
has `on_garmin: false`.

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

- `checkins`: `{date, kind: 'weekly', status, risk, summary}`; if you
  overrode `proposed`, say why in `summary`
- `observations`: new facts, calculations, hypotheses (with confidence),
  decisions. Close resolved hypotheses with `update_record` (status
  confirmed/refuted).
- `milestones`: achieved rungs (`status`, `achieved_at`, `achieved_value`),
  revised estimates.
- `athlete/profile.md`: only durable changes (new max, injury resolved,
  new successful strategy).
- `journal/context.md`: overwrite with the week's handover (what was pushed,
  open questions for next time).
