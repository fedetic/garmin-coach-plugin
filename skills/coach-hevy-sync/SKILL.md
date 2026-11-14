---
name: coach-hevy-sync
description: Writes garmin-coach block sessions into the athlete's Hevy app as routines (one per planned strength session, updated in place each week, in a "Coach" folder), reads them back to verify, and helps pick Hevy exercises. Use when a block activates, when a weekly check-in changes next week's sessions, when a daily check modifies today's workout, or when the user asks to push or fix their Hevy routines. Only for athletes with `integrations.hevy` on. Not for reading Hevy history.
---

# Hevy routine sync

Load `coach-core` (`../coach-core/SKILL.md`). The block yml is the source of
truth: edit it first, then push. Hevy needs Hevy Pro and an API key saved on
this computer (`workspace_status.integrations.hevy_key_found`); setup
(`../coach-setup/SKILL.md`, Hevy part) explains how to create and save it.

## How Hevy differs from Garmin

- **No calendar.** A Hevy routine is a template in their library, so there is
  nothing to "schedule". Each routine's notes say the planned date, and the
  weekly check-in tells them which routine is for which day.
- **One routine per planned session, updated in place** each week (title
  `Mon - Bench heavy (wk3)`), in a folder called `Coach` (`hevy_folder` in
  `coach.yml` changes the name). The library doesn't fill up with old weeks,
  and their logged history is untouched. If they edited a routine by hand,
  the next push overwrites it: say so when they ask to keep a tweak, and put
  the tweak in the block yml instead.
- **Strength only.** Run, ride and walk sessions are skipped (reported as
  such). Describe them in the check-in; with a Garmin watch also on, they go
  through `coach-garmin-sync`.
- **The API can't delete routines.** A write Hevy stored wrongly is reported
  and fixed by pushing again (it overwrites), never "undone".
- Hevy's routine sets have no RPE target: the target RPE and the note go into
  the exercise note. A rep range (`reps: "8-12"`) becomes a rep range.

## Push (normal path)

1. Every strength exercise in the target week needs `hevy: {template_id}` in
   the yml. Find it with `hevy_find_exercise(name)`: the athlete's whole Hevy
   library plus their custom exercises. Take a result with `score` 2 or more
   (the same words); with several close ones (`Pull Up` vs `Pull Up
   (Assisted)`), ask which they use. Nothing fits: offer a close one, or
   tell them to create the exercise in Hevy, then search again with
   `refresh=true`. Plank-style holds use `duration_sec`.
2. `validate_block()` and fix errors first (the Hevy template warning is
   advice: the push also matches an exact name by itself).
3. `hevy_push_week(week=N, dry_run=true)` when anything is unusual (new
   block, moved days, first push): per session `would create`,
   `would update the existing routine` or `unchanged`.
4. `hevy_push_week(week=N)`. For each session it builds the routine from the
   yml, creates or updates it, **reads it back and compares every exercise
   and set**, and records it. Unchanged sessions aren't rewritten.
   - Move sessions: `dates={session_id: "YYYY-MM-DD"}`.
   - Defaults: active block, current week; past dates skipped unless
     `include_past=true`.
5. Read the result:
   - `created, verified` / `updated in place, verified`: done.
   - `skipped: no Hevy exercise chosen for: ...`: the message lists
     candidates. Pick one, write it into the yml, push again.
   - `skipped: Hevy routines hold strength sessions`: expected for runs.
   - `FAILED verification`: Hevy stored something different from the plan
     (`problems` says what). Check the yml values; if they are right, push
     again, and if it repeats, tell the athlete which routine to check in
     the app.
   - `created (the old routine was gone from Hevy)`: they deleted it; fine.
   - A Hevy error about a routine limit means the account isn't on Pro:
     tell them, and give the week in the chat instead.

## Report

One line per session: `Tue 11-17 - Lower body (wk2) -> "Coach" folder ✓
updated`, plus anything they must know. Remind them once: open the routine
in Hevy on the day and start it from there, so the coach can match the
workout to the plan.
