# Goal module: strength

For 1RM targets (bench, squat, deadlift, overhead press, weighted pull-up/dip)
and powerlifting-style goals.

## Making it measurable

| Goal | `metric` | Baseline source |
|---|---|---|
| Lift a 1RM | `e1rm:<GARMIN_EXERCISE>` (e.g. `e1rm:BARBELL_BENCH_PRESS`) | a tested single (best), or a recent heavy set with an honest RPE; Garmin set history gives e1RM with "no RPE" caveats |
| Rep target ("20 pull-ups") | manual, tracked via milestones | a test set |
| Total (powerlifting) | manual: the sum of the three e1RMs | |

Milestone ladder: break the gap into rungs of about 5-7% for intermediates
and 2-4% for advanced lifters. Estimate dates from realistic rates
(beginner: weekly progress; intermediate: about 2-5% per 8-12 weeks;
advanced: slower), never from a straight line on a few points.

Before planning, find out **how the current max was established**: a tested
single, a rep max, or a recalled number from years ago? A big gap between
working sets and claimed max points either to untapped intensity (a fast
fix) or to an inflated max (rebase).

## Roles

Add a **Lift Specialist** per target lift. It keeps one explicit
**limiter hypothesis**, revised from evidence and never assumed. Candidate
limiters:
- technique (bar path, setup, leg drive, bracing)
- frequency (practice per week)
- intensity exposure (never trains above ~85%)
- a lagging muscle (triceps, quads, upper back...)
- the sticking point
- accumulated fatigue
- recovery (sleep, food)

Log the hypothesis as an `observation` (type `hypothesis`) and say what data
would confirm or refute it.

## Block archetypes

| Block | Weeks | Focus | Intensity | Volume |
|---|---|---|---|---|
| Base / hypertrophy | 4-8 | work capacity, muscle in limiting areas | 65-77% (RPE 6-8) | high |
| Strength accumulation | 4-6 | heavier sets of 3-6 | 75-87% (RPE 7-8.5) | moderate |
| Peak / realization | 3-5 | heavy singles/doubles, taper at the end | 85-97% (RPE 7-9) | low, dropping |
| Test | 1 | max attempt, fresh | openers about 90-92% of expected | minimal |
| Deload | 1 | recover | about 60-70%, half the sets | low |

Skip a block when the evidence says it's unnecessary. Example: a lifter
whose working sets prove the strength is there but who never trains heavy
needs a peak, not 10 weeks of base. Document skipped phases and why.

Frequency: a target lift trained 2-4x/week (heavy / volume / light-speed
split) usually beats once a week for intermediates.

## Progression rules

- Prescribe from %1RM (confirmed max) using `prescribe_load`, then regulate by RPE:
  - RPE 1+ below target on all sets for 2 sessions in a row: progress next week
  - RPE 1+ above target: hold, check readiness, and don't progress
  - 2 sessions in a row of 1.5+ above target: investigate (fatigue? a wrong max?)
- Change one variable at a time at block transitions, so results can be attributed.
- Retest early when RPE data shows the max is clearly outdated.
- Maintenance for lower-priority lifts: about 1/3 of build volume at similar
  intensity, 1-2x/week, capped around RPE 7.

## Tests

Warm-up ramp (e.g. bar x10, 50% x5, 70% x3, 80% x1, 87% x1), then 3 attempts:
opener about 92% of expected (a sure lift), second about 97% (RPE-gated),
third the target. Rest 4-8 min between attempts. Write the attempt rules into
the block's test session. A spotter or safety arms are required.

## Daily modifiers

- Readiness ORANGE on 2+ factors: keep the session, drop intensity by 5-10%
  or remove the top set; no tests.
- Joint irritation on a lift: swap to a pain-free variation (grip/ROM/tempo)
  and log it to `injuries` as monitoring.

## Garmin

Strength sessions are pushed with `build_strength_workout`. Map exercises
with `find_garmin_exercise`. Garmin rep counting misses or mislabels sets,
so ask the athlete to correct the set list in the Connect app, or confirm
actuals at check-in.
