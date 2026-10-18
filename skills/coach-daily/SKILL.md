---
name: coach-daily
description: Short daily readiness check for the garmin-coach - pulls last night's Garmin recovery data, compares each factor to the athlete's own baseline, looks at today's planned session and returns GO / MODIFY / REST with the specific change. Use for "morning check", "daily check-in", "should I train today", "how's my recovery", or before a planned session.
---

# Daily check-in

Load `coach-core` first (`../coach-core/SKILL.md`). Keep it short: the athlete
reads this on their phone before training.

## Steps

1. Call `garmin_daily_snapshot()` (one call). It fetches and stores last
   night's recovery data, backfills missing days, imports yesterday's and
   today's activities, and returns:
   - `proposed_call`: GO / MODIFY / REST from the decision table below,
     applied to the data only, with the `rule` that fired
   - `readiness_vs_your_baseline`: each factor vs the athlete's baseline
   - `plan.today`: today's session from the active block (loads for this
     week, `readiness_gate`, `test_day`), and `garmin_calendar_today`
     (differs if the athlete moved a workout)
   - `open_injuries`, `already_done_today`, `missing_today`
2. Ask at most 2 quick questions, batched: pain or soreness (always if
   `open_injuries` is set), and anything unusual (illness, alcohol, travel,
   a big stress day). Skip them if the athlete already said.
3. Decide: start from `proposed_call`, apply the session's
   `also_apply_session_gate`, then the answers. Override the draft when the
   evidence says so (an illness, pain, a factor you judge to be noise) and
   say why. `confidence: LOW` means a short baseline: lean less on flags.

If `garmin_daily_snapshot` fails with a Garmin login error, tell the athlete
the fix it names. If the garmin server is available, fall back to
pulling the metrics with its tools (`../coach-core/references/garmin-data.md`),
then `record_metrics` and `readiness_report()`.

## Decision table (what `proposed_call` applies)

| Situation | Call |
|---|---|
| No ORANGE factors, at most one YELLOW, no pain | **GO**: as planned |
| 2+ YELLOW or 1 ORANGE, or `repeated_deterioration` | **MODIFY**: keep the session, cut intensity (-5-10% load / drop top set / quality run becomes easy) or volume (-30%) |
| ORANGE on HRV *and* RHR, or illness symptoms, or concerning pain | **REST** or easy mobility/walk; illness: symptom-free for 24h or more before resuming |
| Test/max day | stricter: GO only if no ORANGE and no illness; otherwise move the test |

Never call REST from one bad metric alone; say which factors drove the call.

If MODIFY changes loads or structure, edit today's session in the block yml
and run `push_week()` (it replaces only what changed), or for a small change
tell the athlete exactly what to do differently and note it.

## Output (about 6-10 lines)

```
GO / MODIFY / REST - <one-line reason>
Today: <session name> -> <change, if any>
Recovery vs your baseline: HRV 49 (base 52±3, YELLOW) · RHR 56 (base 54, GREEN) · Sleep 5.6h (base 7.1h, ORANGE, 4 of last 7 nights) · BB 62 · stress 31
Watch: <one thing, e.g. "bedtime is the limiter - 3rd short night">
```

## Log

`log` to `checkins`: `{date, kind: 'daily', status: GO|MODIFY|REST, risk, summary}`.
If you overrode `proposed_call`, put the reason in `summary`. New injury
reports go to `injuries`. Update `journal/context.md` only if something
changed that the next session needs.
