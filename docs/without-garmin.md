# Use the coach without a Garmin watch

You don't need a Garmin watch. You talk to the coach in the Claude Desktop
app; it builds your plan, adjusts it as you train, and keeps track of how it
goes. If you log your training in a connected app, the coach reads it from
there and writes each week's workouts back into it. Today that app is
**Hevy**; with any other app, or none, the coach works from what you tell it.

> [!TIP]
> There is also a styled version of this guide with copy buttons for the
> commands: download [`without-garmin.html`](without-garmin.html)
> and open it in your browser. It has the same content.

- [What you get](#what-you-get)
- [What works with what](#what-works-with-what)
- [What you need](#what-you-need)
- [Set up (about 15 minutes)](#set-up-about-15-minutes)
- [Your first conversation](#your-first-conversation)
- [A typical week](#a-typical-week)
- [If you use Hevy: how your plan shows up](#if-you-use-hevy-how-your-plan-shows-up)
- [Watches and other apps](#watches-and-other-apps)
- [Privacy](#privacy)
- [If something doesn't work](#if-something-doesnt-work)
- [If your app isn't connected](#if-your-app-isnt-connected)

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
- **Weights worked out for you**, rounded to what you can load. With a
  connected app (Hevy today) the week's workouts land in the app, so there is
  nothing to copy by hand.

It is a coach built from sound training principles, not a doctor. Tell it
about pain and injuries, and see a professional for anything that worries you.

## What works with what

The coach uses two kinds of apps, and both are optional:

- a **watch or ring** for recovery data (sleep, HRV, resting heart rate), and
- a **training log app** where you record your sets.

| | Status | What the coach does with it |
|---|---|---|
| **Garmin** watch | Connected | Reads recovery data and training, puts workouts on the watch (see the [README](../README.md)) |
| **Hevy** (needs Hevy Pro) | Connected | Reads your logged lifts, writes each week's plan into it as routines |
| **Apple Watch, Whoop, Oura, Fitbit** | Not connected | Asks a few quick questions each morning instead (sleep, soreness, pain) |
| **Other training apps** (Strong, Fitbod, JEFIT, a spreadsheet, paper) | Not connected | You log as usual and tell the coach how it went; it writes each week's plan in the chat and in your `plan/` folder to follow or copy |

More apps can be added over time. Nothing is lost by starting without one: the
plan, the weekly check-ins and the morning check all work from conversation.

## What you need

| | |
|---|---|
| **Claude Desktop** with **Cowork** | Mac or Windows. Cowork needs a paid Claude plan. Download: <https://claude.ai/download> |
| **A connected app** (optional) | For Hevy: Hevy Pro, because Hevy only lets Pro accounts use its API. Without one, see [below](#if-your-app-isnt-connected) |
| **Your own computer** | The coach's small helper program runs on it and keeps your data in a folder there, `~/coach` |

## Set up (about 15 minutes)

### 1. Prepare your computer (one command)

Open a terminal, paste the line for your computer and press Enter. It checks
for what the coach needs and installs what's missing: `git`, and `uv`, a small
tool that runs the helper (on a Mac, git comes with Apple's developer tools: a
pop-up appears, finish it and run the command again). Then it asks two
questions:

1. *Do you have a Garmin watch?* Answer **n**.
2. *Do you log your workouts in the Hevy app?* Answer **y** if you do, then
   paste your Hevy key when asked (nothing shows as you type). Answer **n**
   if you use another app or none: you skip the key and nothing else changes.

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
> **Only if you use Hevy: your Hevy key.** In Hevy's web app (hevy.com), open Settings, then
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

1. **Your apps.** Whether you have a Garmin watch and whether you use a
   connected training app. Say which other watch or app you use, if any.
2. **What it can see.** With a connected app it reads your last 12 weeks and
   tells you what it found: how often you train, your main lifts and heaviest
   sets, whether you log effort. Correct anything it got wrong. Without one,
   it asks you for the same things.
3. **You.** Goals and deadlines, injuries, schedule, equipment, how you eat and
   sleep. Short answers are fine; "not sure" is fine.
4. **Your first plan.** A roadmap, the first block in detail, a specialist
   review, and then **week 1 is ready**: in your connected app (Hevy: in a
   folder called *Coach*), or written out in the chat if you have none.

## A typical week

| When | You | The coach |
|---|---|---|
| **Morning of a training day** (1 min) | Say "morning check". Answer: sleep, energy, soreness, any pain | GO, MODIFY or REST, and changes today's workout if needed |
| **Training** | Do the planned workout and log your sets as usual (with Hevy, start it from the routine). RPE too, if you can: it makes the coach noticeably better | Nothing |
| **Rest days** | Nothing | Nothing |
| **Check-in day** (you pick it, e.g. Sunday, 5 to 10 min) | Say "weekly check-in". Answer a few questions: missed sessions, pain, sleep, life | Reads your week (from your connected app, or from what you tell it), reports progress against the plan, changes next week only if the data justifies it, **puts next week's workouts in your app** |
| **End of a block** (every 3 to 8 weeks) | Nothing extra | Plans and reviews the next block inside the weekly check-in |

Just tell it when things change: "my knee hurts on squats", "travelling next
week, hotel gym only", "I can only train three days now". It adjusts the plan
and your workouts.

## If you use Hevy: how your plan shows up

(This section is for the one connected app. Other apps: see
[above](#what-works-with-what).)

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

## Watches and other apps

Only Garmin is connected as a recovery source today. That doesn't hold you
back much:

- **A watch only matters for recovery data and for logging.** If your
  training app has a watch app (Hevy has Apple Watch and Wear OS apps), log
  your sets on your wrist and the coach reads them from the app like any others.
- **Sleep, HRV and resting heart rate from Apple Health, Whoop, Oura or
  Fitbit are not read.** In their place the morning check asks about sleep,
  soreness, pain and stress. The sleep hours you give are saved, and after
  a few weeks the coach compares you with your own normal, the way a watch
  would.
- Your watch still does its own job (heart rate, steps, runs). The coach just
  doesn't see it. Tell it about anything that matters.

## Privacy

- Your coaching folder (`~/coach`) stays on your computer, and so does your
  Hevy key (`~/.hevy/api-key`) if you use Hevy.
- The coach's helper program talks only to the services you connect (Hevy at
  `api.hevyapp.com`, Garmin Connect), plus git if you turn on sync between
  computers. With none connected it talks to nothing. No telemetry, no server
  of ours. It is open source: read every line in this repository.
- The AI model reads what the coach reads: your workouts, weight, injuries and
  your answers. In Claude Desktop that goes to Anthropic, under your plan's
  terms. Check your privacy settings, in particular whether chats may be used
  for training. The coach only needs what you choose to tell it: a name is
  optional and no medical history is required.
- If you use Hevy: the key can read and write your Hevy account. Treat it like
  a password; revoke it in Hevy's Developer settings if you ever think it leaked.
- More detail: [Security and privacy](../README.md#security-and-privacy) in the README.

## If something doesn't work

| Symptom | Try |
|---|---|
| (Hevy) The coach says the key is missing or rejected | Run the setup command from step 1 again; it asks for the key again. Check the key in Hevy's Developer settings, and that the account is Pro |
| Desktop doesn't offer the coach's tools, or "the coach server isn't available" | Run the step 1 command again (it re-prepares `uv` and the helper), restart Claude Desktop, and start a new Cowork task. The helper is a local program, so work in Cowork on your own computer rather than a plain chat or a cloud session |
| "command not found" or "not recognized" after setup | Close the terminal, open a new one, run the command again |
| (Hevy) A routine looks wrong | Tell the coach which one. It re-sends it and reads it back; if Hevy still stores it differently, it tells you exactly what differs |
| (Hevy) "Routine limit" error | The Hevy account isn't Pro. See below |
| You'd rather use the terminal | The same coach runs in Claude Code, Codex and opencode: [README Quick start](../README.md#quick-start-one-command). Answer *no* to Garmin, and *yes* to Hevy if you use it |

## If your app isn't connected

That covers Hevy without Pro, any other training app, and no app at all. The
coach still works. Answer *no* to the Hevy question in setup:

- You get the plan, the weekly check-ins and the morning check, all driven by
  conversation. The coach writes each week's sessions out in the chat (and in
  your `plan/` folder) for you to follow or copy into the app you use.
- After a session, tell it how it went (loads, reps, effort). It uses that the
  same way it would use a connected app's log.
- If you get Hevy Pro later, say "I use Hevy now" and it switches on.

## Status

> [!WARNING]
> The Hevy connection (the only connected training app today) follows Hevy's published API and is tested against a
> simulated Hevy, not yet against many real accounts. Hevy states that its API
> may change. If a routine or a sync misbehaves, tell the coach and
> [open an issue](https://github.com/fedetic/garmin-coach-plugin/issues).
