#!/usr/bin/env bash
# Install garmin-coach into OpenAI Codex without the plugin marketplace:
#   - symlinks every skill into ~/.agents/skills/ (Codex's user skill folder)
#   - registers the coach + garmin MCP servers in ~/.codex/config.toml
# Same skills, same MCP servers as the Claude Code plugin - nothing is forked.
# Re-runnable; pass --uninstall to remove.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="${CODEX_SKILLS_DIR:-$HOME/.agents/skills}"
CONFIG="${CODEX_HOME:-$HOME/.codex}/config.toml"
VENV="${CODEX_HOME:-$HOME/.codex}/garmin-coach/venv"
BEGIN="# >>> garmin-coach >>>"
END="# <<< garmin-coach <<<"

strip_block() {
  [ -f "$CONFIG" ] || return 0
  python3 - "$CONFIG" "$BEGIN" "$END" <<'EOF'
import sys, re
path, b, e = sys.argv[1:]
s = open(path).read()
s = re.sub(re.escape(b) + r".*?" + re.escape(e) + r"\n?", "", s, flags=re.S)
open(path, "w").write(s)
EOF
}

if [ "${1:-}" = "--uninstall" ]; then
  for d in "$ROOT"/skills/*/; do rm -f "$SKILLS_DIR/$(basename "$d")"; done
  strip_block
  echo "garmin-coach removed from Codex (venv left at $VENV)"
  exit 0
fi

command -v uv >/dev/null || { echo "uv is required: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }

mkdir -p "$SKILLS_DIR" "$(dirname "$CONFIG")"
for d in "$ROOT"/skills/*/; do
  ln -sfn "${d%/}" "$SKILLS_DIR/$(basename "$d")"
done
echo "linked $(ls -d "$ROOT"/skills/*/ | wc -l) skills into $SKILLS_DIR"

if grep -qE '^\[mcp_servers\.(coach|garmin)\]' "$CONFIG" 2>/dev/null && ! grep -q "$BEGIN" "$CONFIG"; then
  echo "WARNING: $CONFIG already defines [mcp_servers.coach] or [mcp_servers.garmin] outside this"
  echo "installer's block. Remove or rename them, then re-run."
  exit 1
fi
strip_block
cat >> "$CONFIG" <<EOF
$BEGIN
[mcp_servers.coach]
command = "uv"
args = ["run", "--quiet", "--frozen", "--project", "$ROOT/server", "coach-mcp"]
env = { UV_PROJECT_ENVIRONMENT = "$VENV" }

[mcp_servers.garmin]
command = "uvx"
args = ["--python", "3.12", "--from", "git+https://github.com/Taxuspt/garmin_mcp", "garmin-mcp"]
startup_timeout_sec = 120
$END
EOF
echo "registered MCP servers 'coach' and 'garmin' in $CONFIG"

# warm the coach server's environment so the first session starts fast
UV_PROJECT_ENVIRONMENT="$VENV" uv sync --quiet --frozen --project "$ROOT/server" && echo "coach server environment ready"

[ -f "$HOME/.garminconnect/garmin_tokens.json" ] || {
  echo
  echo "Next: log in to Garmin Connect once (tokens stay in ~/.garminconnect/):"
  echo "  uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth"
}
echo
echo "Then: mkdir ~/coach && cd ~/coach && codex   ->  \"\$coach-setup\" or \"set me up as a new athlete\""
