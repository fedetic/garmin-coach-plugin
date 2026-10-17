"""Locating and creating an athlete workspace.

A workspace is a plain folder (ideally its own private git repo) holding one
athlete's data. It is marked by a `coach.yml` file at its root:

    coach.yml            settings (units, check-in day, timezone)
    AGENTS.md / CLAUDE.md  always-loaded pointer + athlete-specific standing rules
    athlete/             profile.md, equipment.yml, schedule.yml, nutrition.md
    plan/                roadmap.yml, blocks/block-NN-<slug>.yml
    data/coach.db        sqlite, schema in data/schema.sql
    journal/context.md   session handover notes
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml

MARKER = "coach.yml"
TEMPLATES = Path(__file__).parent / "data" / "templates"

_active: Path | None = None


class WorkspaceError(RuntimeError):
    pass


def _find_marker(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / MARKER).is_file():
            return p
    return None


def set_active(path: str | os.PathLike) -> Path:
    global _active
    root = _find_marker(Path(path).expanduser().resolve())
    if root is None:
        raise WorkspaceError(f"No {MARKER} found at or above {path}. Run the coach-setup skill first.")
    _active = root
    return root


def resolve(path: str | None = None) -> Path:
    """Explicit path > previously activated > $COACH_WORKSPACE > cwd walk-up."""
    if path:
        return set_active(path)
    if _active is not None:
        return _active
    env = os.environ.get("COACH_WORKSPACE")
    if env:
        return set_active(env)
    found = _find_marker(Path.cwd())
    if found is None:
        raise WorkspaceError(
            "No active workspace. Call workspace_status with the absolute path of the "
            "athlete's coach folder (the session's working directory)."
        )
    return set_active(found)


def settings(root: Path) -> dict:
    return yaml.safe_load((root / MARKER).read_text()) or {}


def init(path: str, athlete_name: str = "", units: str = "kg", timezone: str = "",
         checkin_day: str = "Sunday") -> tuple[Path, list[str]]:
    """Copy templates into `path` without overwriting anything that exists."""
    root = Path(path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    created = []
    for src in sorted(TEMPLATES.rglob("*")):
        if src.is_dir():
            continue
        dest = root / src.relative_to(TEMPLATES)
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        created.append(str(dest.relative_to(root)))
    cfg = settings(root)
    cfg.update({k: v for k, v in {
        "athlete": athlete_name, "units": units, "timezone": timezone, "weekly_checkin_day": checkin_day,
    }.items() if v})
    (root / MARKER).write_text(yaml.safe_dump(cfg, sort_keys=False))
    (root / "plan" / "blocks").mkdir(parents=True, exist_ok=True)
    set_active(root)
    return root, created


def inventory(root: Path) -> dict:
    """Which workspace files exist and whether they still hold template placeholders."""
    out = {}
    for rel in ["athlete/profile.md", "athlete/equipment.yml", "athlete/schedule.yml",
                "athlete/nutrition.md", "plan/roadmap.yml", "journal/context.md"]:
        p = root / rel
        if not p.exists():
            out[rel] = "missing"
        elif "TODO" in p.read_text():
            out[rel] = "incomplete (has TODO placeholders)"
        else:
            out[rel] = "ok"
    out["plan/blocks"] = sorted(f.name for f in (root / "plan" / "blocks").glob("*.yml")) \
        if (root / "plan" / "blocks").exists() else []
    return out
