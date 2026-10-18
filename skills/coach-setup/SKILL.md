---
name: coach-setup
description: First-time onboarding for the garmin-coach - creates the athlete workspace, pulls Garmin history to pre-fill what it can, then interviews the athlete conversationally about goals, training, injuries, schedule, equipment and food, and ends with a first roadmap. Use when there is no coach.yml yet, when the user says "set me up", "onboard", "start coaching me", or when goals, equipment, schedule or injuries change substantially.
---

# Athlete setup

Load `coach-core` first (`../coach-core/SKILL.md`).

The aim is a complete enough picture to plan safely, collected as a
conversation rather than a form. **Garmin first, questions second**: anything
the watch already knows doesn't need asking.

## 1. Workspace

- If `workspace_status` finds a workspace, this is an update: skip to the
  sections that changed.
- Otherwise ask where to keep the data. The default is the current folder if
  it's empty, else `~/coach`. Then call `init_workspace(path, athlete_name,
  units, timezone, weekly_checkin_day)`.
- More than one device? Suggest making the workspace a **private** git repo
  and setting `git_sync: true` in `coach.yml`. The session hooks then pull
  at start and commit/push at end. Only the text dump `data/coach.sql` is
  committed, and `coach.db` is rebuilt from it, so there are no binary merge
  conflicts.
- Tell them in one line: their health data stays in this folder on their
  machine; the plugin holds no data.

## 2. Garmin check and pre-fill (before asking anything)

Tell the athlete this takes a minute or two, then call `garmin_history()`
(one call). It imports the last 12 weeks of activities and 60 days of
recovery metrics into the database, so baselines and readiness work from
day one, and returns:

- `profile`: age, sex, height, weight, units, timezone, the watch, and
  `watch_cannot_measure` (never ask Garmin for those or call them missing)
- `training_last_weeks`: per sport, sessions/week, duration, usual days
- `strength_top_exercises`: heaviest set and an e1RM floor per lift (sets
  assumed to failure, so the real max is likely higher)
- `strength_data_quality`: unclassified sets, whether effort is rated and
  whether it varies
- `recovery_baselines`, `garmin_endurance`, `body_weight`

Present it as "Here's what I can see from your Garmin" in a few lines and
let them correct it.

If it fails with a Garmin login error, help them run the command it
names. For an endurance goal add `garmin_lookup("hr_zones")`; for a nutrition or
body-composition goal, `garmin_lookup("nutrition")` (only has data if they
log food in Garmin Connect).

## 3. Conversation (one topic at a time, 1-3 questions per turn)

Ask only what Garmin didn't answer. Cover:

1. **Goals**: what they want and why, priority order, deadlines (races,
   events). Turn each into a measurable goal with the goal modules
   (`../coach-core/goals/*.md`): metric, baseline, target. Push back gently
   on unrealistic timelines with numbers.
2. **Training background**: training age, history, current numbers and how
   they were measured (tested vs recalled), what has worked or failed before.
3. **Health and injuries**: the light screening in
   `../coach-core/references/safety.md`, plus current and past injuries,
   triggers, what helps.
4. **Schedule**: sessions per week, session length, fixed days or flexible,
   time of day, upcoming travel or events, other sports.
5. **Environment**: home gym, commercial gym, minimal, bodyweight, or a mix.
   Start from a preset in `../coach-core/references/equipment.md`, confirm
   gaps, safety setup (safety arms/spotter), and plate/dumbbell inventory
   for `loads`.
6. **Lifestyle**: sleep (compare their own estimate with Garmin's; the gap
   is often informative), job stress, recovery habits.
7. **Nutrition**: eating pattern, restrictions/intolerances, budget and
   cooking habits, whether they log food, protein estimate, weight direction
   wanted.

Stop asking once you have enough to plan the first block safely. Gaps go into
the profile as TODO and get filled in during check-ins.

## 4. Write it down

- `athlete/profile.md`, `athlete/equipment.yml`, `athlete/schedule.yml`,
  `athlete/nutrition.md`: replace every TODO you can.
- db via `log`:
  - `goals` (name, module, priority, metric, target_value, unit,
    baseline_value, baseline_date, target_date)
  - `injuries`
  - `profile` key facts
  - `observations` for notable findings, e.g. "workout_rpe never set"
    (fact, HIGH), or "bench gap between working sets and claimed max
    suggests untapped intensity" (hypothesis, MEDIUM)
- `coach.yml`: units, check-in day.
- `AGENTS.md`, "Athlete-specific standing rules": only durable rules, e.g.
  "always a self-paced warm-up step", "no overhead pressing (shoulder)".

## 5. First plan

Hand over to `coach-plan` to build the roadmap and the first block, run
`coach-review`, then `coach-garmin-sync` to push week 1. Finish with:
- the roadmap in 3-5 lines
- week 1 on their calendar
- how check-ins work: a daily check before training days ("morning check")
  and a weekly check-in on their chosen day, run by asking the coach in this
  folder

## Updating later

When goals, equipment, schedule or injuries change: update the affected
files and db rows, `log` a `plan_changes` row, and re-run `coach-plan` for
the active block if it's affected.
