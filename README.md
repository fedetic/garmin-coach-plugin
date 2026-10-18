# garmin-coach

An adaptive training coach for Garmin watch owners that runs inside your own
AI assistant (Claude Code, OpenAI Codex, or opencode with a local model) on
your own subscription or hardware. It
creates your workouts and syncs them to your Garmin watch automatically.

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

Your data stays in a folder on your computer (`~/coach`). The plugin holds
no athlete data. What does leave your computer, and to whom, is spelled out in
[Security and privacy](#security-and-privacy).

> Not medical advice. The Garmin connection uses the unofficial Garmin Connect
> API ([Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp)); it can
> break when Garmin changes things.

## What you need

- A Garmin watch synced to a **Garmin Connect** account
- A **Claude Pro or Max** plan (for Claude Code), a ChatGPT plan that
  includes **Codex**, *or* [opencode](https://opencode.ai) with any provider,
  including a local model on your own GPU (see [Local models](#local-models-opencode))
- A Mac, Windows 10/11 or Linux computer

Everything else (git, uv, Python, Claude Code) is installed by the setup command.

## Quick start: one command

**1. Open a terminal**

| Mac | Windows | Linux |
|---|---|---|
| Press `Cmd + Space`, type **Terminal**, press Enter | Press the Windows key, type **PowerShell**, press Enter (not "as administrator") | Open your Terminal app |

**2. Paste the command for your computer and press Enter**

Mac / Linux:
```sh
curl -fsSL https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.sh | bash
```

Windows (PowerShell):
```powershell
irm https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.ps1 | iex
```

<details>
<summary>Using Codex instead of Claude Code?</summary>

Install [Codex](https://developers.openai.com/codex/cli) first, then:

```sh
# Mac / Linux
curl -fsSL https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.sh | bash -s -- --codex
```
```powershell
# Windows
$env:COACH_TOOL="codex"; irm https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.ps1 | iex
```
</details>

<details>
<summary>Using opencode (e.g. with a local model)?</summary>

Install [opencode](https://opencode.ai) first, then:

```sh
# Mac / Linux
curl -fsSL https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.sh | bash -s -- --opencode
```
```powershell
# Windows
$env:COACH_TOOL="opencode"; irm https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.ps1 | iex
```
In opencode, press **Tab** to switch to the `coach` agent. For a local model,
read [Local models](#local-models-opencode) first.
</details>

The script walks through 6 steps and skips anything that's already done, so
it's safe to run again if something fails halfway:

1. **git**: needed to download the Garmin connector (Windows: installed via winget, or straight from Git for Windows if winget is missing; Mac: the developer-tools popup)
2. **uv**: runs the coach and Garmin servers, and installs Python by itself
3. **Claude Code** (or checks that Codex or opencode is there; on Windows it offers to install them, plus Node.js, and asks before allowing PowerShell to run them)
4. **The garmin-coach plugin**
5. **Garmin Connect login**: your email, password and MFA code if you use one. Only a login token is saved, in `~/.garminconnect` on your computer, and it lasts about 6 months.
6. **Your coaching folder**: `~/coach`

**3. Start coaching**

```sh
cd ~/coach
claude          # or: codex, opencode
```

The first time, Claude Code asks you to log in in your browser. Then type:

```
set me up as a new athlete
```

## Step-by-step setup (if you prefer, or if the script stops)

Run these in the same terminal. After each install step, **close and reopen
the terminal** if the next command says "not found" or "not recognized".

<details>
<summary><b>1. git</b></summary>

| Mac | Windows | Linux (Ubuntu/Debian) |
|---|---|---|
| `xcode-select --install` | `winget install --id Git.Git -e` | `sudo apt install git` |

Check: `git --version`
</details>

<details>
<summary><b>2. uv</b></summary>

| Mac / Linux | Windows |
|---|---|
| `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |

Check: `uv --version`
</details>

<details>
<summary><b>3. Claude Code</b> (skip if you use Codex)</summary>

| Mac / Linux | Windows |
|---|---|
| `curl -fsSL https://claude.ai/install.sh \| bash` | `irm https://claude.ai/install.ps1 \| iex` |

Check: `claude --version`. More options: [Claude Code setup docs](https://code.claude.com/docs/en/setup).
</details>

<details>
<summary><b>4. The plugin</b></summary>

Claude Code (all systems):
```sh
claude plugin marketplace add fedetic/garmin-coach-plugin
claude plugin install garmin-coach@garmin-coach
```

Codex:
```sh
# Mac / Linux
git clone https://github.com/fedetic/garmin-coach-plugin.git ~/.garmin-coach/plugin
uv run --project ~/.garmin-coach/plugin/server coach-codex install
```
```powershell
# Windows
git clone https://github.com/fedetic/garmin-coach-plugin.git $HOME\.garmin-coach\plugin
uv run --project $HOME\.garmin-coach\plugin\server coach-codex install
```
This links the same skills into `~/.agents/skills` and registers the same
two servers in `~/.codex/config.toml`. Remove with `... coach-codex uninstall`.

opencode: the same two commands with `coach-opencode install` (add
`--with-garmin` to also turn on the full Garmin server). It links the skills
into `~/.agents/skills`, adds the servers to `~/.config/opencode/opencode.json`
(merged, never overwritten), and writes a `coach` agent and a small session
plugin into `~/.config/opencode/`. Remove with `... coach-opencode uninstall`.
</details>

<details>
<summary><b>5. Garmin login</b></summary>

All systems:
```sh
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp@202913fde53c9d15890d661fc9748dc6d0d5af52 garmin-mcp-auth
```
Run it again whenever the coach says the Garmin login has expired.
</details>

<details>
<summary><b>6. Coaching folder</b></summary>

| Mac / Linux | Windows |
|---|---|
| `mkdir ~/coach && cd ~/coach` | `mkdir ~\coach; cd ~\coach` |
</details>

## Use

Always start the coach **from your coaching folder**:

```sh
cd ~/coach
claude          # or: codex, opencode
```

Just talk to it in plain language. These are the main things it does (you
can also call them directly):

| Say | What happens | Claude Code | Codex |
|---|---|---|---|
| "set me up" / "my goals changed" | onboarding, or updating goals/equipment/schedule | `/garmin-coach:coach-setup` | `$coach-setup` |
| "morning check" | today's GO / MODIFY / REST | `/garmin-coach:coach-daily` | `$coach-daily` |
| "weekly check-in" | weekly report + next week on Garmin | `/garmin-coach:coach-weekly` | `$coach-weekly` |
| "plan my next block" | build or revise the plan | `/garmin-coach:coach-plan` | `$coach-plan` |
| "review this block" | specialist sign-off | `/garmin-coach:coach-review` | `$coach-review` |
| "push this week to Garmin" | create and schedule workouts | `/garmin-coach:coach-garmin-sync` | `$coach-garmin-sync` |

In opencode, switch to the `coach` agent (Tab) and just say it; the agent
loads the right skill.

### A typical week

```mermaid
flowchart LR
    A["Once: set me up"] --> B["Plan + review<br/>(automatic)"] --> C["Week 1 on your<br/>Garmin calendar"]
    C --> D{"Training day?"}
    D -- yes --> E["Morning check<br/>GO / MODIFY / REST"] --> F["Train with the<br/>workout on your watch"] --> G["Rate effort on<br/>the watch"]
    D -- no --> H["Rest - nothing to do"]
    G --> I["Check-in day:<br/>weekly check-in"]
    H --> I
    I --> J["Next week pushed<br/>to Garmin"] --> D
    I -. "block finished" .-> K["Next block planned<br/>+ reviewed (automatic)"] --> J
```

| When | You do | The coach does |
|---|---|---|
| **Once** | "set me up as a new athlete" (~20-30 min) | reads your Garmin history, asks what it can't see, builds the plan, reviews it, puts week 1 on your Garmin calendar |
| **Morning of a training day** (~1 min) | "morning check" | compares last night's sleep/HRV/resting HR/Body Battery to *your* normal, says GO / MODIFY / REST, and updates today's workout on Garmin if it changes |
| **During training** | start today's workout on the watch (it's on your Garmin calendar) and follow the steps | nothing. The watch records sets, reps and weight |
| **Right after training** | rate the effort on your watch or in Garmin Connect (perceived effort, 1-10), and fix any set the watch mislabeled | uses it at the next check-in. An effort that's never rated can't guide the plan |
| **Rest days** | nothing (a morning check is optional) | nothing |
| **Check-in day** (you pick it, e.g. Sunday, ~5-10 min) | "weekly check-in", then answer a few questions (missed sessions, pain, sleep) | weekly report, adjusts the plan only if the data supports it, **pushes next week's workouts to Garmin** |
| **End of a block** (every ~3-8 weeks) | nothing extra, it happens inside the weekly check-in | plans the next block, runs the specialist review, pushes week 1 |

### When to ask for what

- **New workouts on Garmin?** You normally never ask. The weekly check-in
  schedules next week, and a morning check updates today if needed. Ask
  ("push this week to Garmin", "move Thursday's session to Friday") only when
  your schedule changes or something is missing on the watch.
- **A review?** It runs automatically before every new block. Ask yourself
  only after you've changed the plan by hand ("I want to add a run on
  Wednesdays") or if you'd like a second opinion on a big change. There's no
  need to request one weekly.
- **Something changed?** Just say it at any time: "my knee hurts on squats",
  "I'm travelling next week, hotel gym only", "I can only train 3 days now",
  "I signed up for a 10k in March". The coach adjusts the plan and the Garmin
  calendar.
- **Missed a check-in?** No problem. The next one covers everything since the
  last one. The coach also reminds you when a check-in is due.

### Using more than one computer

Make `~/coach` a **private** git repository and set `git_sync: true` in
`~/coach/coach.yml`. The coach pulls at the start of each session and saves
and pushes at the end. Don't run sessions on two computers at the same time.

## Local models (opencode)

The coach is built so a model that fits on one consumer GPU can run it. The
coach server does the Garmin fetching, parsing, math, workout building and
verification, and drafts the daily GO / MODIFY / REST and the weekly status.
The model reads compact summaries (a daily check is one tool call returning
about 500 tokens) and spends its effort on judgment and talking to you.

**What to expect on 16 GB of VRAM**

- **Recommended: Qwen3 14B at 4-bit** (`ollama pull qwen3:14b`; the default
  tag is 4-bit, about 9 GB). It calls tools reliably and leaves room on a
  16 GB card for a 32k context. A gpt-oss-20b-class model is an alternative
  if it fits alongside your context. Not yet benchmarked with the coach, so
  treat this as a starting point.
- Daily checks, weekly check-ins and pushing workouts are the flows small
  models handle well. Writing a whole new training block is the hardest
  task: `validate_block` catches mechanical mistakes and the model must fix
  them, but review the plan yourself, or do planning with a bigger model.

**Context window (the most common problem)**

Ollama's default context is 4k on GPUs under 24 GB, and it silently cuts
longer prompts off, which looks like the model ignoring instructions or
failing tool calls. Give it at least 32k:

```sh
OLLAMA_CONTEXT_LENGTH=32768 ollama serve
```

If Ollama runs as a system service (the Linux installer sets one up),
exporting the variable in your shell does nothing: add
`Environment="OLLAMA_CONTEXT_LENGTH=32768"` with `sudo systemctl edit ollama`,
then `sudo systemctl restart ollama`.

Then tell opencode about the model (`~/.config/opencode/opencode.json`,
next to the `mcp` block the installer added):

```json
"provider": {
  "ollama": {
    "npm": "@ai-sdk/openai-compatible",
    "options": { "baseURL": "http://localhost:11434/v1" },
    "models": { "qwen3:14b": { "name": "Qwen3 14B", "limit": { "context": 32768, "output": 8192 } } }
  }
}
```

**Garmin server off by default**

The installer registers the full Garmin server but leaves it disabled: its
~150 tool definitions would take most of a small model's context. The coach
server covers setup, daily, weekly, workouts, HR zones, nutrition and VO2max
by itself. Turn the Garmin server on (`"enabled": true` under `mcp.garmin`)
only with a large context or a hosted model.

## Security and privacy

Short version: the plugin itself sends your data nowhere except Garmin.
But the AI model you pick reads your health data, and the Garmin connection
is unofficial third-party code that holds a full-access login token. Decide
with that in mind.

### Where your data goes

| Part | What it has | Where it goes |
|---|---|---|
| Your coaching folder (`~/coach`) | everything: goals, injuries, plans, daily recovery metrics, workouts, notes | stays on your computer, unless you turn on git sync (then also your git remote) |
| Coach server (this repo) | reads and writes your folder and your Garmin account | talks only to Garmin Connect (and git, if sync is on). No telemetry, no server of ours |
| Garmin login token (`~/.garminconnect`) | full read/write access to your Garmin Connect account | stays on your computer, readable only by your user |
| The AI model | whatever the coach reads during a conversation: recovery metrics, weight, injuries, training history, your answers | **hosted model:** sent to that provider. **Local model:** stays on your computer |

### This repo

- Open source (MIT): you can read every line that runs. The coach server's
  dependencies are pinned in `server/uv.lock` (with hashes) and installed
  with `--frozen`, so an update upstream can't slip new code in.
- The only network traffic is to Garmin Connect, through
  [python-garminconnect](https://github.com/cyberjunky/python-garminconnect)
  (pinned to 0.3.2), plus `git pull`/`push` of your coaching folder if you
  turn on git sync.
- Garmin writes are narrow: the coach creates, schedules, replaces and
  deletes only workouts it created itself (tracked in its database), checks
  each upload against the plan, and removes it again if Garmin stored
  something different. The skills tell the coach to ask before touching
  anything else on your calendar.
- The session hooks only run inside a coaching folder and only do a
  database dump/restore and git there.

### Using a hosted model (Claude, ChatGPT/Codex, or a cloud provider in opencode)

- Your training and health data is part of the conversation, so it goes to
  that provider and is handled under their terms. Before you start, check the
  provider's privacy settings, in particular whether your chats may be used
  to train models and how long they are kept.
- The coach only needs what you choose to tell it. Your name is optional,
  and a medical history isn't required (the safety screen is a few short
  questions; answer only what you're comfortable sharing).
- The model acts through tools that edit files and change your Garmin
  calendar. Claude Code and Codex ask before running tools unless you've
  told them not to; leaving those prompts on is the safe default.
- Text from Garmin (activity names, notes) reaches the model. A malicious
  note could try to steer it ("prompt injection"). The impact is limited to
  what the tools can do, which is why the opencode `coach` agent has no
  shell or web access.

### Using a local model (opencode + Ollama)

- Model inference happens on your machine; the only outside traffic is the
  coach server's calls to Garmin.
- opencode and Ollama are third-party software with their own update and
  sharing features. opencode can upload a session when you share it; turn
  that off with `"share": "disabled"` in `~/.config/opencode/opencode.json`.

### The unofficial Garmin connection

- There is no public Garmin API for this. The coach server and the optional
  [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) server log in
  the way the Garmin Connect website does. Neither is made or endorsed by
  Garmin. Garmin may block or break it at any time, and using it is your
  decision under Garmin's terms.
- **Your password** is entered once into the `garmin-mcp-auth` login tool
  (from Taxuspt/garmin_mcp) and is not stored. What is stored is a login
  token, in two files: `~/.garminconnect/` and `~/.garminconnect_base64`
  (both owner-only). It lasts about 6 months and can do anything your
  account can, so treat it like a password: never commit it or copy it into
  your coaching folder. To revoke it, delete **both**. If you think it
  leaked, also change your Garmin password.
- **The garmin MCP server and its login tool are pinned** to one commit
  of Taxuspt/garmin_mcp (`202913f`, 2026-10-15), in `.mcp.json`, the Codex
  and opencode installers and the setup scripts. That commit was checked
  for what matters here: it only contacts `connect.garmin.com`, runs no
  shell commands, writes its token files owner-only, and pins its own
  dependencies (including the same `garminconnect` 0.3.2 the coach server
  uses). That was a targeted check, not a full audit. Pinning means a later
  change to that repo can't reach your password or token until the pin is
  deliberately moved. A weekly GitHub Action (`upstream-check.yml`) opens an
  issue when there's a newer version, with the diff and an automated scan
  of the new code; it never moves the pin itself.
- It's still the server with about 150 tools, including ones that delete
  activities, so keep it off when you don't need it. opencode does this by
  default, and the coach server covers the everyday flows itself.

### Git sync between computers

`data/coach.sql` is a full text copy of your database, health data included.
Only sync to a **private** repository, and remember that the git host then
stores that data too.

## Updating and removing

| | Claude Code | Codex | opencode |
|---|---|---|---|
| Update | `claude plugin update garmin-coach@garmin-coach` (or re-run the setup command) | re-run the setup command, or `git -C ~/.garmin-coach/plugin pull` | same as Codex |
| Remove | `claude plugin uninstall garmin-coach@garmin-coach` | `uv run --project ~/.garmin-coach/plugin/server coach-codex uninstall` | `... coach-opencode uninstall` |

Removing the plugin never touches your `~/coach` folder.

## How it's built (and why it ports 1:1)

```
garmin-coach-plugin/
├── skills/                  # Agent Skills standard (SKILL.md), read by Claude Code, Codex and opencode
│   ├── coach-core/          # operating manual + references/ + goals/ (loaded by every other skill)
│   ├── coach-setup/ coach-daily/ coach-weekly/ coach-plan/ coach-review/ coach-garmin-sync/
├── server/                  # coach MCP server (Python): the deterministic half
│   └── coach_mcp/           #   server.py (tools), ops.py + garmin_live.py (one-call Garmin tools),
│                            #   session.py (hooks), codex.py / opencode.py (installers)
├── hooks/hooks.json         # session start/end: status line + optional git sync
├── scripts/setup.sh, setup.ps1   # one-command setup
├── .mcp.json                # MCP servers (coach + garmin) for Claude Code
├── .claude-plugin/          # Claude Code manifest + marketplace
├── .codex-plugin/           # Codex manifest
└── .agents/plugins/         # Codex marketplace
```

Portability rules:
- Only the parts every tool supports go in the core: skills, MCP servers and
  session hooks (opencode runs them through a small plugin instead of shell hooks). No Claude-only subagents or slash-command files; the specialist
  roles are reasoning perspectives in a skill reference.
- Skills reference each other by relative path (`../coach-core/...`).
- Everything runs through `uv` and Python: no bash or `python3` dependency,
  so it works the same on Windows.
- Anything that should give the same answer every time is an MCP tool, not a
  prompt: readiness baselines, e1RM/%1RM, load rounding, Garmin workout
  payloads, validated logging. This makes the server reusable as the backend
  of a future app.

Coach MCP tools: `workspace_status` · `init_workspace` · `query` · `log` ·
`update_record` · `upsert_training_block` · `record_metrics` ·
`readiness_report` · `estimate_1rm` · `prescribe_load` · `round_load` ·
`find_garmin_exercise` · `build_strength_workout` · `register_garmin_workout`
· `import_activity` · `training_summary` · `goal_progress`

Workspace layout:

```
~/coach/
├── coach.yml                # settings (units, check-in day, git_sync)
├── AGENTS.md, CLAUDE.md     # always-loaded pointer + your standing rules
├── athlete/                 # profile.md, equipment.yml, schedule.yml, nutrition.md
├── plan/                    # roadmap.yml, blocks/block-NN-*.yml
├── data/coach.db            # sqlite (coach.sql text dump is what git syncs)
└── journal/context.md       # session handover
```

## Development

```sh
git clone https://github.com/fedetic/garmin-coach-plugin.git && cd garmin-coach-plugin
cd server && uv run --group dev pytest -q && cd ..
claude plugin validate .
claude --plugin-dir .        # run Claude Code with your local copy
```
