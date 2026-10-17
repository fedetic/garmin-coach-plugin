# Goal module: calisthenics / skills

For the muscle-up, handstand, front/back lever, planche, pistol squat, L-sit,
human flag and so on.

## Making it measurable

Skills are tracked as progression levels plus holds or reps. Use
`milestones` (goal, `target_value` = level/seconds/reps) and log each test as
an observation. Strength prerequisites (e.g. weighted pull-up) can use
`e1rm:` metrics.

## Role: Skill Coach

Owns progression choice, prerequisite checks, practice frequency and
connective-tissue tolerance (elbows, wrists, shoulders). Coordinates with
the other roles so skill work doesn't wreck the priority goal's recovery.
Example: heavy straight-arm pulling the day before max bench is a bad idea.

## Principles

- Skills are practice: frequent (3-6x/week), short, fresh, far from failure.
  Strength prerequisites are trained like strength.
- Pass the prerequisite before starting the next progression. Typical gates:
  - **Muscle-up**: 10+ strict pull-ups, 10+ straight-bar dips, chest-to-bar
    pull-ups, false-grip hang (rings); progress through explosive pull-ups,
    transitions on low rings/band, negatives
  - **Handstand**: 60s chest-to-wall hold, overhead mobility (open shoulder
    angle), wrist conditioning; then kick-ups, toe pulls, freestanding attempts
  - **Front lever**: 10+ pull-ups, hollow body 60s; tuck, advanced tuck,
    one leg, straddle, full (holds of about 3x10-15s before progressing)
  - **Pistol**: a full-depth assisted pistol, ankle dorsiflexion; then box
    pistols, counterbalance, full
- Straight-arm work (levers, planche) loads tendons, which adapt slowly.
  Progress over weeks, not sessions; elbow or biceps-tendon pain is an
  Injury-Risk flag.
- Garmin has no category for most holds: create them as plain steps with
  the target duration in the text (`build_strength_workout` with `plain: true`).

## Block fit

Skills run alongside other goals as embedded practice: 10-20 min at the
start of a session (fresh), or as separate micro-sessions. They get their
own block focus only when the skill is the top-priority goal.
