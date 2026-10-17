# Goal module: endurance

For VO2max, race times (5k to marathon, triathlon, cycling events) and
general aerobic fitness. This is the module that uses Garmin's data most heavily.

## Making it measurable

| Goal | `metric` | Garmin source |
|---|---|---|
| Raise VO2max | `health:vo2max` (record daily from `get_vo2max_trend`) | Garmin estimate from outdoor GPS runs/rides with HR. Changes slowly; trust 4-8 week trends, not day-to-day |
| Race time | manual (`race:10k`, seconds), plus `get_race_predictions` as a proxy | predictor follows VO2max and doesn't account for race-specific fitness; test with a time trial |
| Threshold | `get_lactate_threshold` (HR and pace) | needs a guided LT test or chest strap on many watches |
| Cycling | `get_cycling_ftp` | power meter required |
| Durability / volume | weekly duration or distance; `get_endurance_score` | |
| Hill ability | `get_hill_score` | |

Typical realistic VO2max change: a few points over 8-16 weeks for an
untrained or detrained person, smaller for trained ones. Set milestones in
those terms, plus a race or time-trial result.

## Intake extras

Current weekly volume (hours/km) over the last 8 weeks (verify against
Garmin activities); longest recent session; race calendar; surface and
terrain; injury history (shins, Achilles, knees, plantar fascia); HR strap
or wrist HR; whether they also lift.

## Role: Endurance Coach

Owns intensity distribution, aerobic base, quality sessions, long-session
progression, taper and race execution. Watches running tolerance and load
balance for injury risk.

## Intensity distribution

Use the athlete's Garmin HR zones (`get_heart_rate_zones`). Update them
after an LT test.

- About 75-80% of time easy (Z1-Z2: conversational), the rest moderate to
  hard. Polarized or pyramidal both work; most amateurs run their easy days
  too hard.
- Quality sessions per week: 1 (beginner) to 2-3 (experienced).
  - VO2max: e.g. 4-6 x 3-4 min at about 90-95% HRmax (Z5), equal-ish
    recovery; 30/30s for beginners
  - Threshold: 2-4 x 8-12 min at LT HR/pace (Z4)
  - Tempo/steady (Z3) for marathon-specific work
- Long session: builds aerobic durability; about 20-30% of weekly running
  volume, capped around 2.5-3h for runners.

## Block archetypes

| Block | Weeks | Focus |
|---|---|---|
| Base | 4-12 | volume build (about 5-10%/week, every 3rd-4th week easier), strides, hills |
| Build | 4-8 | add threshold, then VO2 work; long run grows |
| Specific / peak | 3-6 | race-pace work, race-specific long sessions |
| Taper | 1-3 (by distance) | volume -30 to -60%, keep some intensity |
| Race / test | 1 | race or time trial, then recovery |

VO2max as the goal: base, then a build block weighted toward VO2 intervals,
with 2 quality sessions per week. Retest from Garmin's trend and a time trial.

## Progression and injury rules

- Volume jumps: no more than about 10%/week sustained. Watch
  `get_running_tolerance` and the acute load trend; a load-balance status
  above Garmin's target range is a YELLOW flag.
- Pain on runs (shin, Achilles, foot) is Injury-Risk territory: cross-train
  (bike, elliptical, pool) at the same HR rather than pushing through.
- Hybrid athletes: put heavy lower-body lifting on the same day as hard
  runs (hard days hard), or 6h+ apart; easy runs never the day before heavy
  squats/deadlifts.

## Daily modifiers

Readiness flags downgrade quality sessions to easy aerobic sessions; they
don't turn them into rest unless the athlete is ill. A missed quality
session isn't made up by stacking.

## Garmin workouts

Push run sessions with the garmin server's `create_run_workout`,
`create_run_interval_workout` or `create_walk_run_workout` (beginners), or
`upload_workout` with HR/pace targets for custom structures. Schedule them
with `schedule_week`. Check the tool's own docstring for target formats.
For cycling/swimming, use `upload_workout` with the right sportType from
`workout://reference/structure`.
