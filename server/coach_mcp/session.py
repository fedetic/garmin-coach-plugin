"""Session hooks (Claude Code and Codex both run hooks/hooks.json):

    coach-session start   optional git pull, rebuild data/coach.db from data/coach.sql
                          when the dump changed, print a one-line status into the session
    coach-session end     dump data/coach.db -> data/coach.sql, optional commit + push

Silent outside a coach workspace. Never exits non-zero: problems are printed so
the session can see them. Pure Python + git, so it runs the same on Windows.
"""
from __future__ import annotations

import hashlib
import os
import socket
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

from .workspace import MARKER


def _find_ws() -> Path | None:
    start = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    for p in [start, *start.parents]:
        if (p / MARKER).is_file():
            return p
    return None


def _git(ws: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ws, capture_output=True, text=True)


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _restore(ws: Path) -> None:
    sql, db, marker = ws / "data/coach.sql", ws / "data/coach.db", ws / "data/.restored"
    if not sql.exists():
        return
    h = _hash(sql)
    if db.exists() and marker.exists() and marker.read_text().strip() == h:
        return
    tmp = db.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(sql.read_text(encoding="utf-8"))
    con.close()
    os.replace(tmp, db)
    marker.write_text(h)
    print("[coach] database rebuilt from data/coach.sql")


def _dump(ws: Path) -> None:
    db, sql = ws / "data/coach.db", ws / "data/coach.sql"
    if not db.exists():
        return
    con = sqlite3.connect(db)
    with open(sql, "w", encoding="utf-8", newline="\n") as f:
        for line in con.iterdump():
            f.write(line + "\n")
    con.close()
    (ws / "data/.restored").write_text(_hash(sql))


def _status(ws: Path, cfg: dict) -> None:
    db = ws / "data/coach.db"
    if not db.exists():
        print("[coach] garmin-coach workspace found but no database yet - run the coach-setup skill")
        return
    con = sqlite3.connect(db)
    today = date.today()

    def last(kind):
        r = con.execute("SELECT max(date) FROM checkins WHERE kind=?", (kind,)).fetchone()[0]
        return date.fromisoformat(r[:10]) if r else None

    d, w = last("daily"), last("weekly")
    day = cfg.get("weekly_checkin_day", "Sunday")
    due = []
    if d != today:
        due.append("daily check")
    if w is None or (today - w).days >= 7 or (today.strftime("%A") == day and (today - w).days >= 5):
        due.append("weekly check-in")
    blk = con.execute("SELECT id, name FROM training_blocks WHERE status='active'").fetchone()
    con.close()
    print("[coach] garmin-coach workspace: load the coach-core skill before coaching."
          + (f" Active block: {blk[0]} ({blk[1]})." if blk else " No active block.")
          + (f" Due: {', '.join(due)}." if due else " Nothing due."))


def start(ws: Path, cfg: dict) -> None:
    if cfg.get("git_sync") and _git(ws, "rev-parse", "--is-inside-work-tree").returncode == 0 \
            and _git(ws, "remote", "get-url", "origin").returncode == 0:
        if _git(ws, "pull", "--rebase", "--autostash", "--quiet").returncode == 0:
            print(f"[coach] pulled latest ({_git(ws, 'log', '-1', '--format=%h %cr').stdout.strip()})")
        else:
            _git(ws, "rebase", "--abort")
            print("[coach] WARNING: git pull conflicted (likely data/coach.sql edited on two devices). "
                  "Resolve the text conflict in data/coach.sql before logging anything new.")
    _restore(ws)
    _status(ws, cfg)


def end(ws: Path, cfg: dict) -> None:
    _dump(ws)
    if cfg.get("git_sync") and _git(ws, "rev-parse", "--is-inside-work-tree").returncode == 0:
        _git(ws, "add", "-A")
        if _git(ws, "diff", "--cached", "--quiet").returncode != 0:
            _git(ws, "commit", "--quiet", "-m",
                 f"coach: {socket.gethostname()} {datetime.now():%Y-%m-%d %H:%M}")
        if _git(ws, "remote", "get-url", "origin").returncode == 0 \
                and _git(ws, "push", "--quiet", "origin", "HEAD").returncode != 0:
            print("[coach] WARNING: git push failed")


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        ws = _find_ws()
        if ws is None:
            return
        cfg = yaml.safe_load((ws / MARKER).read_text()) or {}
        {"start": start, "end": end}.get(action, lambda *_: print("usage: coach-session start|end"))(ws, cfg)
    except Exception as e:  # a hook must never break the session
        print(f"[coach] hook error: {e}")


if __name__ == "__main__":
    main()
