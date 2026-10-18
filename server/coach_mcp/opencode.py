"""Install garmin-coach into opencode (any OS), aimed at local models:

    coach-opencode install [--with-garmin]   skills, MCP servers, `coach` agent, session plugin
    coach-opencode uninstall

- Skills: linked into ~/.agents/skills (opencode reads it; shared with the Codex install).
- MCP: `coach` enabled; `garmin` registered but disabled unless --with-garmin, because its
  ~150 tool schemas would fill a small model's context. The coach server talks to Garmin itself.
- Agent: ~/.config/opencode/agents/coach.md, a primary agent with only the tools coaching needs.
- Plugin: ~/.config/opencode/plugins/garmin-coach.js runs `coach-session start` when a session
  is created and `coach-session end` when it goes idle (opencode has no shell hooks).

Same skills and server as the Claude Code plugin; nothing is forked.
Respects $OPENCODE_CONFIG_DIR and $CODEX_SKILLS_DIR.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .codex import BEGIN, GARMIN_MCP, PLUGIN_ROOT, SERVER, _link, _unlink
from .codex import _paths as codex_paths

AGENT = """---
description: Adaptive training coach on your Garmin data (daily check, weekly check-in, plans, workouts)
mode: primary
temperature: 0.3
permission:
  bash: deny
  webfetch: deny
  websearch: deny
  task: deny
  todowrite: deny
---
You are garmin-coach, an adaptive training coach for one athlete, working in their coach
workspace (the folder with coach.yml).

Before any coaching, load the `coach-core` skill, then the skill for the task: coach-daily
(morning check), coach-weekly (weekly check-in), coach-plan, coach-review, coach-garmin-sync,
coach-setup (no coach.yml yet).

Prefer the coach server's one-call tools: garmin_history (setup), garmin_daily_snapshot (daily),
garmin_sync_since (weekly), push_week (workouts to Garmin), validate_block (check a block yml),
garmin_lookup (HR zones, nutrition, VO2max trend). They return drafts (proposed_call,
proposed status/risk): confirm or override them with a reason.

Never invent numbers: report missing data as missing. Keep daily answers short.
"""

PLUGIN = """// garmin-coach session hooks for opencode (written by coach-opencode install).
// Pull + rebuild the database at session start; dump + commit/push after each reply.
// Silent outside a coach workspace. Uses child_process, not Bun's $ (which can hang here).
import { execFile } from "node:child_process";

const SERVER = %s;

export const GarminCoach = async ({ directory }) => {
  const run = (action) =>
    new Promise((resolve) =>
      execFile("uv", ["run", "--quiet", "--frozen", "--project", SERVER, "coach-session", action],
               { cwd: directory, timeout: 60000, windowsHide: true }, () => resolve()));
  return {
    event: async ({ event }) => {
      if (event.type === "session.created") await run("start");
      if (event.type === "session.idle") await run("end");
    },
  };
};
"""


def _dirs() -> tuple[Path, Path]:
    cfg = Path(os.environ.get("OPENCODE_CONFIG_DIR") or Path.home() / ".config" / "opencode")
    skills = Path(os.environ.get("CODEX_SKILLS_DIR") or Path.home() / ".agents" / "skills")
    return cfg, skills


def _servers(with_garmin: bool) -> dict:
    return {
        "coach": {"type": "local", "enabled": True, "timeout": 60000,
                  "command": ["uv", "run", "--quiet", "--frozen", "--project", SERVER.as_posix(), "coach-mcp"]},
        "garmin": {"type": "local", "enabled": with_garmin, "timeout": 120000,
                   "command": ["uvx", "--python", "3.12", "--from", GARMIN_MCP, "garmin-mcp"]},
    }


def _ours(entry: dict) -> bool:
    return any(SERVER.as_posix() in str(a) or GARMIN_MCP in str(a) for a in entry.get("command") or [])


def _config_file(cfg_dir: Path) -> Path:
    for name in ("opencode.json", "opencode.jsonc"):
        if (cfg_dir / name).exists():
            return cfg_dir / name
    return cfg_dir / "opencode.json"


def _load(path: Path) -> dict | None:
    """The config as a dict, or None if it isn't plain JSON (comments) - we never rewrite those."""
    if not path.exists():
        return {"$schema": "https://opencode.ai/config.json"}
    try:
        return json.loads(path.read_text() or "{}")
    except json.JSONDecodeError:
        return None


def install(with_garmin: bool = False) -> None:
    cfg_dir, skills_dir = _dirs()
    skills_dir.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in (PLUGIN_ROOT / "skills").iterdir() if (p / "SKILL.md").exists())
    for n in names:
        _link(PLUGIN_ROOT / "skills" / n, skills_dir / n)
    print(f"linked {len(names)} skills into {skills_dir}")

    for sub, name, text in (("agents", "coach.md", AGENT),
                            ("plugins", "garmin-coach.js", PLUGIN % json.dumps(SERVER.as_posix()))):
        (cfg_dir / sub).mkdir(parents=True, exist_ok=True)
        (cfg_dir / sub / name).write_text(text)
    print(f"wrote the `coach` agent and the session plugin into {cfg_dir}")

    path = _config_file(cfg_dir)
    conf = _load(path)
    servers = _servers(with_garmin)
    if conf is None:
        print(f"{path} has comments, so it was left untouched. Add this under its \"mcp\" key:\n"
              + json.dumps(servers, indent=2))
        return
    mcp = conf.setdefault("mcp", {})
    clash = [k for k in servers if k in mcp and not _ours(mcp[k])]
    if clash:
        sys.exit(f"{path} already has MCP server(s) {clash} that aren't garmin-coach's; "
                 "rename them, then run this again.")
    mcp.update(servers)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(conf, indent=2) + "\n")
    print(f"registered MCP servers in {path}: coach (on), garmin ({'on' if with_garmin else 'off'})")
    if not with_garmin:
        print("  garmin is off to keep small models' context free; the coach server talks to Garmin "
              "itself. Turn it on with --with-garmin, or set mcp.garmin.enabled in that file.")


def uninstall() -> None:
    cfg_dir, skills_dir = _dirs()
    codex_config, _ = codex_paths()
    if codex_config.exists() and BEGIN in codex_config.read_text():
        print(f"kept the skills in {skills_dir}: the Codex install uses them too")
    else:
        for p in (PLUGIN_ROOT / "skills").iterdir():
            d = skills_dir / p.name
            if d.is_symlink() or d.exists():
                _unlink(d)
    for f in (cfg_dir / "agents" / "coach.md", cfg_dir / "plugins" / "garmin-coach.js"):
        f.unlink(missing_ok=True)
    path = _config_file(cfg_dir)
    conf = _load(path)
    if conf and isinstance(conf.get("mcp"), dict):
        for k in [k for k, v in conf["mcp"].items() if isinstance(v, dict) and _ours(v)]:
            del conf["mcp"][k]
        path.write_text(json.dumps(conf, indent=2) + "\n")
    elif conf is None:
        print(f"{path} has comments: remove the `coach` and `garmin` entries under \"mcp\" yourself.")
    print("garmin-coach removed from opencode")


def main() -> None:
    args = sys.argv[1:]
    action = args[0] if args else "install"
    if action == "install":
        install(with_garmin="--with-garmin" in args)
    elif action == "uninstall":
        uninstall()
    else:
        sys.exit("usage: coach-opencode install [--with-garmin] | uninstall")


if __name__ == "__main__":
    main()
