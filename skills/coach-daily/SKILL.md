---
name: coach-daily
description: Short daily readiness check for the garmin-coach - with a Garmin watch it pulls last night's recovery data and compares each factor to the athlete's own baseline; without one it asks a few quick questions. Looks at today's planned session and returns GO / MODIFY / REST with the specific change. Use for "morning check", "daily check-in", "should I train today", "how's my recovery", or before a planned session.
---

# Daily check-in

Load `coach-core` first (`../coach-core/SKILL.md`). Keep it short: the athlete
reads this on their phone before training.

## Which path

`integrations.garmin` true: the Steps below. False (Hevy, or no app at all):
the **No Garmin data** path further down.

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

## No Garmin data (Hevy or nothing)

1. Call `daily_context()` (one call). It refreshes the last days from Hevy
   when that is on and returns today's planned session (this week's loads,
   `readiness_gate`, `test_day`), `training_last_7_days`, `open_injuries`,
   and `self_reported_vs_baseline` once the athlete has given sleep for a
   few weeks. It never proposes a call: there is no data to propose from.
2. Ask the athlete, in one message, the five things a watch would have told
   you: hours slept, how they feel (energy 1-5), soreness where, any pain
   (always, and by name if `open_injuries` is set), anything unusual
   (illness, alcohol, travel, a big stress day). Skip what they already said.
   Record the sleep with `record_metrics` (`metric: sleep_hours`, `source:
   "self"`): after a few weeks it becomes their own baseline and shows up in
   `self_reported_vs_baseline`.
3. Decide with this table, and say that it rests on what they told you:

| Situation | Call |
|---|---|
| Slept 6.5h or more (or their usual), energy 3+, no pain, no illness | **GO**: as planned |
| One of: under 6h or well below usual, energy 2, heavy soreness in a muscle the session trains, a rough few days, `readiness_gate` of the session unmet | **MODIFY**: keep the session, cut intensity (-5-10% load / drop the top set) or volume (-30%) |
| Two or more of those together, a hard session two days running with poor sleep, or any illness symptom below the neck, fever, or concerning pain | **REST** or easy mobility/walk; illness: symptom-free for 24h or more before resuming |
| Test/max day | stricter: GO only if all of the first row holds; otherwise move the test |

   Apart from illness or concerning pain, never call REST from one answer
   alone, and don't pretend precision: with no wearable this is a judgment
   call, so offer the trade-off rather than a verdict when it's close.
4. If MODIFY changes loads or structure, edit today's session in the block
   yml and push it (`coach-hevy-sync` for Hevy; with no app, tell them the
   exact change).

Output and log are the same as below; the `Recovery` line is what they told
you ("Slept 5.5h (usual 7), energy 2/5, calves sore").

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
