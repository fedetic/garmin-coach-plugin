---
name: coach-daily
description: Short daily readiness check for the garmin-coach - pulls last night's Garmin recovery data, compares each factor to the athlete's own baseline, looks at today's planned session and returns GO / MODIFY / REST with the specific change. Use for "morning check", "daily check-in", "should I train today", "how's my recovery", or before a planned session.
---

# Daily check-in

Load `coach-core` first (`../coach-core/SKILL.md`). Keep it short: the athlete
reads this on their phone before training.

## Steps

1. `workspace_status`, then read the active block yml for **today's
   planned session** (also `get_scheduled_workouts` for today, which may
   differ if the athlete moved it).
2. Pull from Garmin for today (the night just ended): HRV, RHR, sleep
   (hours and score), Body Battery, stress, training readiness if the watch
   has it. Map them to canonical metrics
   (`../coach-core/references/garmin-data.md`) and call `record_metrics`.
   Skip metrics that came back empty, and say they're missing.
   - If `latest_health_metrics_date` was more than a day old, also backfill
     the missing days so the 7-day window is honest.
3. `readiness_report()` for each factor vs baseline.
4. Since the last session: any new activity (`get_activities_by_date`
   yesterday-today)? If it was a planned workout, `import_activity` it (with
   sets for strength).
5. Ask at most 2 quick questions, only if relevant: soreness or pain
   anywhere (always ask if there's an open injury), and anything unusual
   (illness, alcohol, travel, a big stress day).

## Decision

| Situation | Call |
|---|---|
| No ORANGE factors, at most one YELLOW, no pain | **GO**: as planned |
| 2+ YELLOW or 1 ORANGE, or `repeated_deterioration` | **MODIFY**: keep the session, cut intensity (-5-10% load / drop top set / quality run becomes easy) or volume (-30%) |
| ORANGE on HRV *and* RHR, or illness symptoms, or concerning pain | **REST** or easy mobility/walk; illness: symptom-free for 24h or more before resuming |
| Test/max day | stricter: GO only if no ORANGE and no illness; otherwise move the test |

Respect the block's own `readiness_gate` if the session defines one. Never
call REST from one bad metric alone; say which factors drove the call.

If MODIFY changes loads or structure, update today's Garmin workout
(`coach-garmin-sync`, single session) or, if it's a small change, tell
the athlete exactly what to do differently and note it.

## Output (about 6-10 lines)

```
GO / MODIFY / REST - <one-line reason>
Today: <session name> -> <change, if any>
Recovery vs your baseline: HRV 49 (base 52±3, YELLOW) · RHR 56 (base 54, GREEN) · Sleep 5.6h (base 7.1h, ORANGE, 4 of last 7 nights) · BB 62 · stress 31
Watch: <one thing, e.g. "bedtime is the limiter - 3rd short night">
```

## Log

`log` to `checkins`: `{date, kind: 'daily', status: GO|MODIFY|REST, risk, summary}`.
New injury reports go to `injuries`. Update `journal/context.md` only if
something changed that the next session needs.
