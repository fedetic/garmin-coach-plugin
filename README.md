# garmin-coach

An adaptive training coach for Garmin watch owners that runs inside your own
AI coding agent (Claude Code or OpenAI Codex) on your own subscription.

- **Onboarding**: reads your Garmin history first (activities, lifts, VO2max,
  HRV/sleep baselines), then asks about goals, injuries, schedule, equipment
  and food, one topic at a time.
- **Long-term plan**: measurable goals, a milestone ladder, and training
  blocks (base, build, peak, test, deload) detailed only when they're close.
- **Daily check**: last night's recovery vs *your own* 60-day baseline, factor
  by factor, then GO / MODIFY / REST for today's session.
- **Weekly check-in**: adherence, performance, recovery and progress
  toward goals, plan changes when the evidence supports them, and next week
  pushed to your Garmin calendar.
- **Specialist review**: every block is checked by programming, recovery,
  injury-risk, nutrition, data and goal-specific roles before it starts.
- **Goal modules**: strength (1RM), hypertrophy, endurance (VO2max, race
  times), calisthenics skills, body composition, general fitness.
- **Any environment**: commercial gym, home gym, minimal or bodyweight, with
  substitutions and load rounding to the plates or dumbbells you own.

Your data stays in a folder you own (your *workspace*). The plugin holds no
athlete data.

> Not medical advice. The Garmin connection uses the unofficial Garmin Connect
> API ([Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp)); it can
> break when Garmin changes things.

## Requirements

- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Python 3.10+ and git
- Claude Code or Codex CLI
- A Garmin Connect account

Log in to Garmin once (tokens are stored in `~/.garminconnect/` and last
about 6 months):

```sh
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
```

## Install: Claude Code

```sh
claude plugin marketplace add fedetic/garmin-coach-plugin
claude plugin install garmin-coach@garmin-coach
```

For development, from a clone: `claude --plugin-dir /path/to/garmin-coach-plugin`.

## Install: Codex

```sh
git clone https://github.com/fedetic/garmin-coach-plugin.git
bash garmin-coach-plugin/scripts/install-codex.sh        # --uninstall to remove
```

This symlinks the same `skills/` into `~/.agents/skills/` and registers the
same two MCP servers in `~/.codex/config.toml`. A `.codex-plugin/plugin.json`
and `.agents/plugins/marketplace.json` are also included for Codex's plugin
system. The script is the tested path.

## Use

```sh
mkdir ~/coach && cd ~/coach
claude          # or: codex
> set me up as a new athlete
```

Then, from that folder:

| Say | Skill | Claude Code | Codex |
|---|---|---|---|
| "set me up" / "my goals changed" | coach-setup | `/garmin-coach:coach-setup` | `$coach-setup` |
| "morning check" / "should I train today?" | coach-daily | `/garmin-coach:coach-daily` | `$coach-daily` |
| "weekly check-in" | coach-weekly | `/garmin-coach:coach-weekly` | `$coach-weekly` |
| "plan my next block" | coach-plan | `/garmin-coach:coach-plan` | `$coach-plan` |
| "review this block" | coach-review | `/garmin-coach:coach-review` | `$coach-review` |
| "push this week to Garmin" | coach-garmin-sync | `/garmin-coach:coach-garmin-sync` | `$coach-garmin-sync` |

Plain language works too: skills trigger from their descriptions.

## How it's built (and why it ports 1:1)

```
garmin-coach-plugin/
├── skills/                    # Agent Skills standard (SKILL.md: name + description), read by both tools
│   ├── coach-core/            # operating manual + references/ + goals/ (loaded by every other skill)
│   ├── coach-setup/ coach-daily/ coach-weekly/ coach-plan/ coach-review/ coach-garmin-sync/
├── server/                    # coach MCP server (Python, stdio): the deterministic half
├── hooks/hooks.json           # SessionStart/SessionEnd: status line + optional git sync
├── scripts/session.sh         # hook implementation
├── scripts/install-codex.sh   # Codex install
├── .mcp.json                  # MCP servers (coach + garmin) for Claude Code
├── .claude-plugin/            # Claude Code manifest + marketplace
├── .codex-plugin/             # Codex manifest
└── .agents/plugins/           # Codex marketplace
```

Portability rules:
- Only the parts both tools support go in the core: skills, stdio MCP
  servers, hooks. No Claude-only subagents or slash-command files. The
  specialist roles are reasoning perspectives described in a skill
  reference, not separate agents.
- Skills reference each other by relative path (`../coach-core/...`), so they
  work wherever the skill folders sit side by side.
- Anything that should give the same answer every time is an MCP tool, not a
  prompt: readiness baselines, e1RM/%1RM, load rounding, Garmin workout
  payloads, validated logging. This also makes the server reusable as the
  backend of a future app.

### Coach MCP tools

`workspace_status` · `init_workspace` · `query` · `log` · `update_record` ·
`upsert_training_block` · `record_metrics` · `readiness_report` ·
`estimate_1rm` · `prescribe_load` · `round_load` · `find_garmin_exercise` ·
`build_strength_workout` · `register_garmin_workout` · `import_activity` ·
`training_summary` · `goal_progress`

### Workspace layout

```
~/coach/
├── coach.yml                  # settings (units, check-in day, git_sync)
├── AGENTS.md, CLAUDE.md       # always-loaded pointer + your standing rules
├── athlete/                   # profile.md, equipment.yml, schedule.yml, nutrition.md
├── plan/                      # roadmap.yml, blocks/block-NN-*.yml
├── data/coach.db              # sqlite (coach.sql text dump is what git syncs)
└── journal/context.md         # session handover
```

Multiple devices: make the workspace a **private** git repo and set
`git_sync: true`. The session hooks pull at start and commit/push at end.
Only the text dump is committed, so there are no binary merge conflicts.
In Codex (where the installer doesn't set up hooks), run
`bash <plugin>/scripts/session.sh start|end` yourself, or add it to your
Codex hooks.

## Development

```sh
cd server && uv run --group dev pytest -q
claude plugin validate .
```
