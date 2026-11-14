---
name: coach-setup
description: First-time onboarding for the garmin-coach - asks which data sources the athlete uses (Garmin watch, Hevy app, neither), creates the athlete workspace, pulls Garmin or Hevy history to pre-fill what it can, then interviews the athlete conversationally about goals, training, injuries, schedule, equipment and food, and ends with a first roadmap. Use when there is no coach.yml yet, when the user says "set me up", "onboard", "start coaching me", or when goals, equipment, schedule or injuries change substantially.
---

# Athlete setup

Load `coach-core` first (`../coach-core/SKILL.md`).

The aim is a complete enough picture to plan safely, collected as a
conversation rather than a form. **Data first, questions second**: anything a
connected app already knows doesn't need asking.

## 0. Data sources (the very first question)

Ask these two, one at a time, before anything else. Plain words, no jargon:

1. "Do you have a **Garmin** watch that syncs to Garmin Connect?" Yes means
   `garmin: true`: recovery data and workouts on the watch.
2. "Do you log your workouts in the **Hevy** app?" (Only if you want to:
   if they say no, don't push it.) Yes means `hevy: true`: the coach reads
   what you lifted and writes your plan into Hevy as routines. It needs
   **Hevy Pro**. If they have Hevy but not Pro, say what they'd get without
   it: the coach still plans, they enter the sessions in Hevy by hand.

If the answer to 1 is no, also ask which watch or ring they use, if any
(Apple Watch, Whoop, Oura, Fitbit...). Tell them plainly that only Garmin is
connected today, so the coach will ask a few quick questions instead of
reading recovery data, and that nothing about the plan suffers apart from
the automatic morning readiness numbers. Put it in `profile.md` (for example
"wearable: Apple Watch, not connected").

Both no is a valid answer: the coach works from conversation and `plan/`
files. Pass the answers to `init_workspace(garmin=..., hevy=...)` below, or,
in an existing workspace, to `set_integrations`.

## 1. Workspace

- If `workspace_status` finds a workspace, this is an update: skip to the
  sections that changed.
- Otherwise ask where to keep the data. The default is the current folder if
  it's empty, else `~/coach`. Then call `init_workspace(path, athlete_name,
  units, timezone, weekly_checkin_day, garmin, hevy)` with the answers from
  section 0.
- More than one device? Suggest making the workspace a **private** git repo
  and setting `git_sync: true` in `coach.yml`. The session hooks then pull
  at start and commit/push at end. Only the text dump `data/coach.sql` is
  committed, and `coach.db` is rebuilt from it, so there are no binary merge
  conflicts.
- Tell them in one line: their health data stays in this folder on their
  machine; the plugin holds no data.

## 2. Pre-fill from their apps (before asking anything else)

Pick the part that matches `integrations`. Both on: Garmin first, then Hevy
(`hevy_history` merges the two records of one session). Neither: skip to
section 3 and ask everything.

### Garmin (`garmin: true`)

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

### Hevy (`hevy: true`)

Needs the Hevy API key on this computer: if `workspace_status` shows
`integrations.hevy_key_found: false`, give them the steps and wait. Never ask
them to paste the key into the chat.

1. In Hevy (web app, Pro): Settings, Developer, create an API key
   (https://hevy.com/settings?developer).
2. In a terminal, once: the `coach-hevy-auth` command `set_integrations`
   returns in `next`. It asks for the key without showing it and saves it
   owner-only in `~/.hevy/api-key`.

Then call `hevy_history()` (about a minute). It imports the last 12 weeks of
workouts and returns sessions per week and usual days, top exercises with
heaviest set and e1RM floor, whether they log RPE, and body weight. Present
it as "Here's what I can see in your Hevy" in a few lines and let them correct
it. Hevy doesn't know age, sex, height, sleep or injuries: those go to the
conversation. Exercises Hevy names differently from the standard list come
through under their Hevy name; that is fine.
If it fails with a Hevy key error, help them redo the login and retry. Hevy
Pro is also needed for the key to work at all.

## 3. Conversation (one topic at a time, 1-3 questions per turn)

Ask only what their apps didn't answer (with no app, everything, including
age, sex, height and weight, which the energy estimate needs). Cover:

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
6. **Lifestyle**: sleep (compare their own estimate with Garmin's if they
   have it; the gap is often informative), job stress, recovery habits.
7. **Nutrition**: eating pattern, restrictions/intolerances, budget and
   cooking habits, whether they log food, protein estimate, weight direction
   wanted, and roughly what they eat now if they know (it calibrates the
   energy estimate below).

Stop asking once you have enough to plan the first block safely. Gaps go into
the profile as TODO and get filled in during check-ins.

## 4. Write it down

- `athlete/profile.md`, `athlete/equipment.yml`, `athlete/schedule.yml`,
  `athlete/nutrition.md`: replace every TODO you can.
- The energy estimate in `nutrition.md` (skip it, and keep to protein and
  fuelling, if the safety screening flagged disordered eating):
  - BMR by Mifflin-St Jeor from their height, weight, age and sex (Garmin's
    profile if connected, otherwise what they told you):
    10 × kg + 6.25 × cm − 5 × age, then +5 (men) or −161 (women).
  - TDEE = BMR × an activity factor from their *actual* training
    (`training_last_weeks`) plus daily life: about 1.4 for 1-3 sessions a
    week and a desk job, 1.55 for 3-5, 1.7 for 6+ or long endurance
    weeks. Give training-day and rest-day values as a ±10% range.
  - Wearable calorie numbers are rough: don't use them as the answer.
    Confidence is LOW until a weight trend at a known intake confirms it
    (`coach-weekly` recalibrates). Say this to the athlete in one line.
- db via `log`:
  - `goals` (name, module, priority, metric, target_value, unit,
    baseline_value, baseline_date, target_date)
  - `manual_values` for each current number they give for a goal metric
    (a 1RM, a race time: date, metric, value, unit, source `stated` or
    `tested`), so `goal_progress` starts from it
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
`coach-review`, then push week 1: `coach-garmin-sync` (Garmin),
`coach-hevy-sync` (Hevy), both if both. Finish with:
- the roadmap in 3-5 lines
- week 1 on their Garmin calendar and/or as routines in their Hevy app (or,
  with neither, written out in the chat)
- how check-ins work: a daily check before training days ("morning check")
  and a weekly check-in on their chosen day, run by asking the coach in this
  folder

## Updating later

When goals, equipment, schedule or injuries change: update the affected
files and db rows, `log` a `plan_changes` row, and re-run `coach-plan` for
the active block if it's affected.
