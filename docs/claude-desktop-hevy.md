# Your own coach in Claude Desktop, with your workouts in Hevy

No Garmin needed. You talk to the coach in the Claude Desktop app; it builds
your plan, adjusts it as you train, and writes each week's workouts into your
**Hevy** app as routines you start with one tap. Lifting is logged in Hevy as
you always do, and the coach reads it back to see how the week went.

> [!TIP]
> There is also a styled version of this guide with copy buttons for the
> commands: download [`claude-desktop-hevy.html`](claude-desktop-hevy.html)
> and open it in your browser. It has the same content.

- [What you get](#what-you-get)
- [What you need](#what-you-need)
- [Set up (about 15 minutes)](#set-up-about-15-minutes)
- [Your first conversation](#your-first-conversation)
- [A typical week](#a-typical-week)
- [How your plan shows up in Hevy](#how-your-plan-shows-up-in-hevy)
- [Apple Watch and other watches](#apple-watch-and-other-watches)
- [Privacy](#privacy)
- [If something doesn't work](#if-something-doesnt-work)
- [Without Hevy Pro, or without Hevy](#without-hevy-pro-or-without-hevy)

## What you get

A personal coach, not a workout generator:

- **A plan built around you.** Goals turned into numbers (a 100 kg bench, a
  first pull-up, 8 kg lighter), a roadmap of training blocks, and sessions
  that fit the days, time and equipment you really have, down to the plates
  in your garage.
- **A plan that adapts.** Every week it looks at what you actually lifted,
  compares it to what was planned, and changes next week only when the
  evidence says so: progress, hold, deload, or work around a sore shoulder.
- **A morning check.** A one-minute "should I train today?": how you slept and
  feel, any pain, then GO, MODIFY (lighter or shorter) or REST, with the
  specific change.
- **Specialist review** of every block before it starts (programming,
  recovery, injury risk, nutrition), and calorie and protein targets per block.
- **Your workouts in Hevy**, with the weights worked out and rounded to what
  you can load. Nothing to copy by hand.

It is a coach built from sound training principles, not a doctor. Tell it
about pain and injuries, and see a professional for anything that worries you.

## What you need

| | |
|---|---|
| **Claude Desktop** with **Cowork** | Mac or Windows. Cowork needs a paid Claude plan. Download: <https://claude.ai/download> |
| **Hevy Pro** | Hevy only lets Pro accounts use its API. Without it, see [below](#without-hevy-pro-or-without-hevy) |
| **Your own computer** | The coach's small helper program runs on it and keeps your data in a folder there, `~/coach` |

## Set up (about 15 minutes)

### 1. Prepare your computer (one command)

Open a terminal, paste the line for your computer and press Enter. It checks
for what the coach needs and installs what's missing: `git`, and `uv`, a small
tool that runs the helper (on a Mac, git comes with Apple's developer tools: a
pop-up appears, finish it and run the command again). Then it asks two
questions:

1. *Do you have a Garmin watch?* Answer **n**.
2. *Do you log your workouts in the Hevy app?* Answer **y**, then paste your
   Hevy key when asked (next step; nothing shows as you type).

| Mac | Windows |
|---|---|
| Press `Cmd + Space`, type **Terminal**, Enter | Press the Windows key, type **PowerShell**, Enter (not "as administrator") |

Mac:
```sh
curl -fsSL https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.sh | bash -s -- --desktop
```

Windows:
```powershell
$env:COACH_TOOL="desktop"; irm https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.ps1 | iex
```

> [!IMPORTANT]
> **Your Hevy key.** In Hevy's web app (hevy.com), open Settings, then
> **Developer**, and create an API key ([hevy.com/settings?developer](https://hevy.com/settings?developer)).
> The setup command asks for it once and saves it only on your computer, in
> `~/.hevy/api-key`, readable only by you. Never paste the key into the chat:
> the coach never needs you to.

The command is safe to run again if it stops halfway.

### 2. Add the coach to Claude Desktop

In Claude Desktop, open **Cowork**, go to **Plugins** (under Customize), choose
**Add marketplace**, and enter:

```
fedetic/garmin-coach-plugin
```

Then install **garmin-coach**. (Screen names change between versions; Anthropic's
guide is [Install plugins](https://claude.com/docs/cowork/guide/plugins).)

The plugin also lists a *garmin* connector. You don't use it. If Desktop shows
it as failed or asks you to connect, ignore it or switch it off.

### 3. Open your coaching folder

Start a new Cowork task and, when it asks for a folder, choose **`coach`** in
your home folder (the setup command created it). Your goals, plan and history
live there as plain files, so you can read them yourself and nothing is locked
inside the plugin.

### 4. Say hello

Type:

```
set me up as a new athlete
```

## Your first conversation

About 20 to 30 minutes, once. The coach asks one topic at a time:

1. **Your apps.** "Do you have a Garmin watch?" (no) and "Do you log in Hevy?"
   (yes). If you wear another watch, say which.
2. **What it can see.** It reads your last 12 weeks from Hevy and tells you
   what it found: how often you train, your main lifts and heaviest sets,
   whether you log effort. Correct anything it got wrong.
3. **You.** Goals and deadlines, injuries, schedule, equipment, how you eat and
   sleep. Short answers are fine; "not sure" is fine.
4. **Your first plan.** A roadmap, the first block in detail, a specialist
   review, and then **week 1 appears in Hevy** in a folder called *Coach*.

## A typical week

| When | You | The coach |
|---|---|---|
| **Morning of a training day** (1 min) | Say "morning check". Answer: sleep, energy, soreness, any pain | GO, MODIFY or REST, and changes today's routine in Hevy if needed |
| **Training** | Open the routine in Hevy and start it from there. Log your sets as usual (RPE too, if you can: it makes the coach noticeably better) | Nothing |
| **Rest days** | Nothing | Nothing |
| **Check-in day** (you pick it, e.g. Sunday, 5 to 10 min) | Say "weekly check-in". Answer a few questions: missed sessions, pain, sleep, life | Reads your Hevy week, reports progress against the plan, changes next week only if the data justifies it, **updates your Hevy routines for the week** |
| **End of a block** (every 3 to 8 weeks) | Nothing extra | Plans and reviews the next block inside the weekly check-in |

Just tell it when things change: "my knee hurts on squats", "travelling next
week, hotel gym only", "I can only train three days now". It adjusts the plan
and your routines.

## How your plan shows up in Hevy

Hevy has no calendar, so the coach works with what Hevy does have:

- **One routine per planned session**, in a folder called **Coach**, named like
  `Mon - Bench heavy (wk3)`. The routine's note says the planned day.
- **The same routine is updated each week** with that week's weights, sets and
  reps. Your library doesn't fill up with old weeks, and your logged history
  is never touched.
- **Start the workout from the routine.** That is how the coach knows a session
  was the planned one. A workout you log from scratch on the planned day
  still counts; one on another day shows up as "unplanned".
- **Edit the plan by telling the coach**, not in the routine: the next weekly
  update overwrites hand edits. ("Make Thursday's accessory work lighter" works.)
- **Strength only.** Hevy routines hold lifting. A run or a bike ride in your
  plan stays in the plan and in the check-in; do it with whatever you
  normally use and tell the coach how it went.
- **Exercises.** The coach picks from your Hevy exercise list, including your
  custom ones, and asks when two are close ("Pull Up" or "Pull Up (Assisted)").
- **Hevy's API can't delete routines.** If the coach ever stores a routine
  wrongly it tells you which one to check; deleting a routine yourself in
  Hevy is always fine, and the next update recreates it.

## Apple Watch and other watches

Only Garmin is connected as a recovery source today. That doesn't hold you
back much:

- **Hevy has its own Apple Watch app.** Log your sets on your wrist and the
  coach reads them from Hevy like any others.
- **Sleep, HRV and resting heart rate from Apple Health, Whoop, Oura or
  Fitbit are not read.** In their place the morning check asks about sleep,
  soreness, pain and stress. The sleep hours you give are saved, and after
  a few weeks the coach compares you with your own normal, the way a watch
  would.
- Your watch still does its own job (heart rate, steps, runs). The coach just
  doesn't see it. Tell it about anything that matters.

## Privacy

- Your coaching folder (`~/coach`) and your Hevy key (`~/.hevy/api-key`) stay on
  your computer.
- The coach's helper program talks to one place only: Hevy
  (`api.hevyapp.com`), plus git if you turn on sync between computers. No
  telemetry, no server of ours. It is open source: read
  every line in this repository.
- The AI model reads what the coach reads: your workouts, weight, injuries and
  your answers. In Claude Desktop that goes to Anthropic, under your plan's
  terms. Check your privacy settings, in particular whether chats may be used
  for training. The coach only needs what you choose to tell it: a name is
  optional and no medical history is required.
- The Hevy key can read and write your Hevy account. Treat it like a password;
  revoke it in Hevy's Developer settings if you ever think it leaked.
- More detail: [Security and privacy](../README.md#security-and-privacy) in the README.

## If something doesn't work

| Symptom | Try |
|---|---|
| The coach says the Hevy key is missing or rejected | Run the setup command from step 1 again; it asks for the key again. Check the key in Hevy's Developer settings, and that the account is Pro |
| Desktop doesn't offer the coach's tools, or "the coach server isn't available" | Run the step 1 command again (it re-prepares `uv` and the helper), restart Claude Desktop, and start a new Cowork task. The helper is a local program, so work in Cowork on your own computer rather than a plain chat or a cloud session |
| "command not found" or "not recognized" after setup | Close the terminal, open a new one, run the command again |
| A routine in Hevy looks wrong | Tell the coach which one. It re-sends it and reads it back; if Hevy still stores it differently, it tells you exactly what differs |
| "Routine limit" error | The Hevy account isn't Pro. See below |
| You'd rather use the terminal | The same coach runs in Claude Code, Codex and opencode: [README Quick start](../README.md#quick-start-one-command). Answer *no* to Garmin and *yes* to Hevy |

## Without Hevy Pro, or without Hevy

The coach still works. Answer *no* to the Hevy question in setup:

- You get the plan, the weekly check-ins and the morning check, all driven by
  conversation. The coach writes each week's sessions out in the chat (and in
  your `plan/` folder) for you to follow or copy into the app you use.
- After a session, tell it how it went (loads, reps, effort). It uses that the
  same way it would use Hevy's log.
- If you get Hevy Pro later, say "I use Hevy now" and it switches on.

## Status

> [!WARNING]
> The Hevy connection follows Hevy's published API and is tested against a
> simulated Hevy, not yet against many real accounts. Hevy states that its API
> may change. If a routine or a sync misbehaves, tell the coach and
> [open an issue](https://github.com/fedetic/garmin-coach-plugin/issues).
