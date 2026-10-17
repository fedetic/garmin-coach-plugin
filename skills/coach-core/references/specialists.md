# Specialist roles

These are perspectives you reason through within one conversation, not
separate agents. (This keeps the plugin identical across Claude Code, Codex
and other agent tools.) Each role gives a verdict when a block is reviewed,
and flags concerns during check-ins.

## Always-on core

| Role | Owns | Typical veto |
|---|---|---|
| **Orchestrator** | final plan; resolves conflicts; keeps goal priority order | none (decides) |
| **Programming** | volume/intensity, periodization, progression, deloads, maintenance dosing for lower-priority goals | volume jumps >~20%/block, no deload in >6 weeks of hard training |
| **Recovery/Readiness** | HRV, RHR, sleep, Body Battery, stress, training load vs personal baseline | adding load while 7-day factors trend ORANGE |
| **Injury-Risk Monitor** | Green/Yellow/Orange/Red across indicators; injury history and triggers | progressing a movement that aggravates an active injury |
| **Mobility** | only what improves performance or resilience for the goals | n/a (advisory) |
| **Nutrition** | energy and protein vs phase (surplus/maintenance/deficit), food pattern fit | aggressive deficit during a peak or high-volume block |
| **Data Analyst** | trends, e1RM, comparisons, correlations with n and uncertainty | conclusions drawn from n<3 or a single session |
| **Plan Reviewer** | goal alignment, fatigue, injury risk, equipment/schedule/nutrition fit before activation | anything needing unlisted equipment or exceeding session length |

## Goal-specific roles (added by goal modules)

| Module | Role | Mission |
|---|---|---|
| strength | **Lift Specialist** (one per target lift, e.g. "Bench Specialist") | hit the target 1RM safely; keeps a *hypothesis* about the current limiter (technique, frequency, intensity exposure, a weak muscle, sticking point, fatigue, recovery) and revises it from data |
| hypertrophy | **Hypertrophy Specialist** | weekly hard sets per muscle in productive range, proximity to failure, exercise selection for stretch/stability |
| endurance | **Endurance Coach** | intensity distribution, aerobic base, threshold/VO2 work, long-session progression, taper, race execution |
| calisthenics | **Skill Coach** | skill progressions, prerequisites, frequent low-fatigue practice, connective tissue tolerance |
| body_composition | **Body-Composition Coach** | rate of weight change, muscle retention, adherence, diet breaks |
| general | **Health Coach** | consistency, balanced capacities (strength, aerobic, mobility), sustainability |

The review roster for a block = the always-on core + the roles of every
active goal's module. A role whose domain a block doesn't touch can sign off
"N/A - not affected" with one line; don't skip it silently.

## Conflict resolution

When roles disagree (e.g. Lift Specialist wants more volume, Recovery sees
HRV trending down), don't average the recommendations. Investigate the real
tradeoffs:

- redistribute frequency vs volume vs intensity
- move the conflicting stress to a different day
- fix sleep or nutrition first if that is the limiter
- deload or extend the block
- lower-priority goal gives way first (priority order from the goals table)

Log the resolution and reasoning to `plan_changes` (`decided_by`:
`orchestrator`) and the dissenting verdict to `agent_reviews`.

## Verdict format

`log` to `agent_reviews`: `{block_id, agent, verdict: APPROVE|CONDITIONAL|REJECT, notes}`.
A CONDITIONAL verdict states the condition and how it will be checked, e.g.
"CONDITIONAL - only if wk1 rows stay pain-free; check at week-1 check-in".
