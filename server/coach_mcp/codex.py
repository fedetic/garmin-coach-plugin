"""Install garmin-coach into OpenAI Codex (any OS):

    coach-codex install      link skills into ~/.agents/skills, register MCP servers in ~/.codex/config.toml
    coach-codex uninstall

Same skills and MCP servers as the Claude Code plugin; nothing is forked.
Respects $CODEX_HOME and $CODEX_SKILLS_DIR.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SERVER = PLUGIN_ROOT / "server"
BEGIN, END = "# >>> garmin-coach >>>", "# <<< garmin-coach <<<"
GARMIN_MCP = "git+https://github.com/Taxuspt/garmin_mcp"


def _paths() -> tuple[Path, Path]:
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    skills = Path(os.environ.get("CODEX_SKILLS_DIR") or Path.home() / ".agents" / "skills")
    return codex_home / "config.toml", skills


def _strip(text: str) -> str:
    return re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", "", text, flags=re.S)


def _link(src: Path, dest: Path) -> None:
    if dest.is_symlink() or dest.exists():
        _unlink(dest)
    try:
        dest.symlink_to(src, target_is_directory=True)
    except OSError:
        if os.name == "nt":  # symlinks need Developer Mode on Windows; junctions don't
            subprocess.run(["cmd", "/c", "mklink", "/J", str(dest), str(src)], check=True, capture_output=True)
        else:
            raise


def _unlink(dest: Path) -> None:
    if dest.is_symlink():
        os.unlink(dest)
    elif os.name == "nt" and os.path.realpath(dest) != os.path.abspath(dest):
        os.rmdir(dest)  # junction: removes the link only, never the target
    elif dest.is_dir():
        shutil.rmtree(dest)


def install() -> None:
    config, skills_dir = _paths()
    skills_dir.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in (PLUGIN_ROOT / "skills").iterdir() if (p / "SKILL.md").exists())
    for n in names:
        _link(PLUGIN_ROOT / "skills" / n, skills_dir / n)
    print(f"linked {len(names)} skills into {skills_dir}")

    config.parent.mkdir(parents=True, exist_ok=True)
    text = config.read_text() if config.exists() else ""
    if re.search(r"^\[mcp_servers\.(coach|garmin)\]", _strip(text), re.M):
        sys.exit(f"{config} already defines [mcp_servers.coach] or [mcp_servers.garmin]; "
                 "remove or rename them, then run this again.")
    q = json.dumps  # TOML basic strings accept JSON string escapes
    block = "\n".join([
        BEGIN,
        "[mcp_servers.coach]",
        'command = "uv"',
        f'args = ["run", "--quiet", "--frozen", "--project", {q(SERVER.as_posix())}, "coach-mcp"]',
        "",
        "[mcp_servers.garmin]",
        'command = "uvx"',
        f'args = ["--python", "3.12", "--from", {q(GARMIN_MCP)}, "garmin-mcp"]',
        "startup_timeout_sec = 120",
        END, "",
    ])
    text = _strip(text)
    config.write_text(text + ("\n" if text and not text.endswith("\n") else "") + block)
    print(f"registered MCP servers 'coach' and 'garmin' in {config}")


def uninstall() -> None:
    config, skills_dir = _paths()
    for p in (PLUGIN_ROOT / "skills").iterdir():
        d = skills_dir / p.name
        if d.is_symlink() or d.exists():
            _unlink(d)
    if config.exists():
        config.write_text(_strip(config.read_text()))
    print("garmin-coach removed from Codex")


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "install"
    {"install": install, "uninstall": uninstall}.get(action, lambda: sys.exit("usage: coach-codex install|uninstall"))()


if __name__ == "__main__":
    main()
