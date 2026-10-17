#!/usr/bin/env bash
# Session hooks for garmin-coach (Claude Code and Codex both run hooks/hooks.json).
#   start: optional git pull + rebuild data/coach.db from data/coach.sql, then
#          print a one-line status (what check-in is due) into the session.
#   end:   optional dump data/coach.db -> data/coach.sql, commit, push.
# Silent outside a coach workspace (no coach.yml at or above the project dir).
# Never fails the hook: problems are printed so the session can see them.
set -u

find_ws() {
  local d="${CLAUDE_PROJECT_DIR:-$PWD}"
  while [ "$d" != "/" ]; do
    [ -f "$d/coach.yml" ] && { echo "$d"; return; }
    d="$(dirname "$d")"
  done
}
WS="$(find_ws)"
[ -z "$WS" ] && exit 0
cd "$WS" || exit 0

git_sync=$(grep -E '^git_sync:\s*true' coach.yml >/dev/null && echo 1 || echo 0)
is_repo() { git rev-parse --is-inside-work-tree >/dev/null 2>&1; }
has_remote() { git remote get-url origin >/dev/null 2>&1; }

py() { python3 - "$@"; }

restore_db() {  # rebuild coach.db from coach.sql when the sql changed (e.g. after a pull)
  [ -f data/coach.sql ] || return 0
  local h; h=$(sha256sum data/coach.sql | cut -d' ' -f1)
  if [ ! -f data/coach.db ] || [ "$(cat data/.restored 2>/dev/null)" != "$h" ]; then
    py <<'EOF' && echo "$h" > data/.restored && echo "[coach] database rebuilt from data/coach.sql"
import sqlite3, os
tmp = "data/coach.db.tmp"
if os.path.exists(tmp): os.remove(tmp)
con = sqlite3.connect(tmp); con.executescript(open("data/coach.sql").read()); con.close()
os.replace(tmp, "data/coach.db")
EOF
  fi
}

dump_db() {
  [ -f data/coach.db ] || return 0
  py <<'EOF'
import sqlite3
con = sqlite3.connect("data/coach.db")
with open("data/coach.sql", "w") as f:
    for line in con.iterdump():
        f.write(line + "\n")
EOF
  sha256sum data/coach.sql | cut -d' ' -f1 > data/.restored
}

status() {
  py <<'EOF'
import sqlite3, datetime, os, re
if not os.path.exists("data/coach.db"):
    print("[coach] workspace found but no database yet - run the coach-setup skill"); raise SystemExit
con = sqlite3.connect("data/coach.db")
today = datetime.date.today()
def last(kind):
    r = con.execute("SELECT max(date) FROM checkins WHERE kind=?", (kind,)).fetchone()[0]
    return datetime.date.fromisoformat(r[:10]) if r else None
d, w = last("daily"), last("weekly")
cfg = open("coach.yml").read()
m = re.search(r"weekly_checkin_day:\s*(\w+)", cfg)
day = m.group(1) if m else "Sunday"
due = []
if d != today: due.append("daily check")
if w is None or (today - w).days >= 7 or (today.strftime("%A") == day and (today - w).days >= 5):
    due.append("weekly check-in")
blk = con.execute("SELECT id, name FROM training_blocks WHERE status='active'").fetchone()
print("[coach] garmin-coach workspace: load the coach-core skill before coaching."
      + (f" Active block: {blk[0]} ({blk[1]})." if blk else " No active block.")
      + (f" Due: {', '.join(due)}." if due else " Nothing due."))
EOF
}

case "${1:-}" in
  start)
    if [ "$git_sync" = 1 ] && is_repo && has_remote; then
      if git pull --rebase --autostash --quiet; then
        echo "[coach] pulled latest ($(git log -1 --format='%h %cr'))"
      else
        git rebase --abort >/dev/null 2>&1
        echo "[coach] WARNING: git pull conflicted (likely data/coach.sql edited on two devices)."
        echo "[coach] Resolve the text conflict in data/coach.sql before logging anything new."
      fi
    fi
    restore_db
    status
    ;;
  end)
    dump_db
    if [ "$git_sync" = 1 ] && is_repo; then
      git add -A
      git diff --cached --quiet || git commit --quiet -m "coach: $(hostname) $(date '+%Y-%m-%d %H:%M')"
      has_remote && { git push --quiet origin HEAD 2>&1 || echo "[coach] WARNING: push failed"; }
    fi
    ;;
esac
exit 0
