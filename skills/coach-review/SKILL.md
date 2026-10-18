---
name: coach-review
description: Specialist review of a garmin-coach training block before it activates (or after a major change) - each relevant specialist role gives an APPROVE / CONDITIONAL / REJECT verdict with reasons, conflicts are resolved by the orchestrator, and everything is logged to agent_reviews. Use after coach-plan drafts or fills a block, or when the user asks to sanity-check a plan.
---

# Block review

Load `coach-core` (`../coach-core/SKILL.md`) and
`../coach-core/references/specialists.md`.

Start with `validate_block()`. Mechanical errors (missing reps, bad
Garmin keys, unbuildable loads) go back to `coach-plan` before any role
reviews; the roles judge the training, not the yml syntax. Hand its
warnings to the relevant role (load jumps to Programming, session length to
Recovery).

## Roster

The always-on core (Programming, Recovery/Readiness, Injury-Risk, Mobility,
Nutrition, Data Analyst, Plan Reviewer) plus the role of every active goal's
module (e.g. Bench Specialist, Endurance Coach, Skill Coach). The
Orchestrator decides at the end.

## Each role checks (only its own domain)

- **Programming**: volume and intensity vs the previous block, a sensible
  progression, deload placement, maintenance dose for secondary goals,
  session length within the cap.
- **Goal specialist**: does this block move the goal's metric? Does it
  address the current limiter hypothesis? Is it realistic vs the milestone?
- **Recovery**: fits current readiness trends, sleep and schedule, with no
  hard sessions stacked badly.
- **Injury-Risk**: active and monitoring injuries respected (caps, swaps),
  no aggravating movements progressed, test safety (spotter/safety arms,
  readiness gate).
- **Mobility**: anything the goals or injuries need, and nothing for its own sake.
- **Nutrition**: phase target matches the block and is workable with the food pattern.
- **Data Analyst**: are the loads anchored to confirmed numbers? Are the
  exit criteria measurable? PROJECTED values marked as such?
- **Plan Reviewer**: goal alignment, total fatigue, only listed equipment,
  schedule fit, every exercise has a Garmin mapping.

## Process

1. Read the block yml and its context (previous block's results, profile,
   injuries, readiness).
2. Draft each role's verdict with 1-3 lines of reasoning. A CONDITIONAL
   names the condition and when it gets checked.
3. Any REJECT, or conflicting CONDITIONALs: the Orchestrator resolves them
   (tradeoff space, not averaging) and the block is revised. Record the
   original verdict anyway.
4. `log` each verdict to `agent_reviews` `{block_id, agent, verdict, notes}`,
   and the resolution to `plan_changes`.
5. Add `reviews:` with a one-line summary to the block yml.

## Output to the athlete

A compact table (role, verdict, key note), then any changes the review
caused and conditions to watch. Don't bury the athlete in role-play. The
point is that nothing important was skipped.
