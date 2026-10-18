#!/usr/bin/env bash
# garmin-coach one-command setup for macOS, Linux and WSL.
#
#   curl -fsSL https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.sh | bash
#   ... | bash -s -- --codex        # use OpenAI Codex instead of Claude Code
#   ... | bash -s -- --opencode     # use opencode (e.g. with a local model)
#
# Safe to run again: every step checks first and skips what is already done.
set -euo pipefail

TOOL=claude
for a in "$@"; do
  [ "$a" = "--codex" ] && TOOL=codex
  [ "$a" = "--opencode" ] && TOOL=opencode
done
REPO="https://github.com/fedetic/garmin-coach-plugin.git"
PLUGIN_DIR="$HOME/.garmin-coach/plugin"          # Codex and opencode
WORKSPACE="$HOME/coach"
# pinned to a reviewed commit: the login tool sees your password, the server your token
GARMIN_MCP="git+https://github.com/Taxuspt/garmin_mcp@202913fde53c9d15890d661fc9748dc6d0d5af52"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

step() { printf '\n\033[1m[%s] %s\033[0m\n' "$1" "$2"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
die()  { printf '  \033[31m✗ %s\033[0m\n' "$1"; exit 1; }
tty_in() { if [ -r /dev/tty ]; then "$@" </dev/tty; else "$@"; fi; }   # interactive even under curl | bash

step 1/6 "git"
if command -v git >/dev/null; then ok "git found"
elif [ "$(uname)" = Darwin ]; then
  xcode-select --install 2>/dev/null || true
  die "macOS is installing developer tools (includes git). Finish that window, then run this setup again."
else
  die "git is missing. Install it (Ubuntu/Debian: sudo apt install git), then run this setup again."
fi

step 2/6 "uv (runs the coach and Garmin servers; installs Python by itself)"
if command -v uv >/dev/null; then ok "uv found"
else curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null && ok "uv installed"; fi
command -v uv >/dev/null || die "uv not on PATH - open a new terminal and run this setup again."

step 3/6 "AI tool: $TOOL"
if [ "$TOOL" = claude ]; then
  if command -v claude >/dev/null; then ok "Claude Code found"
  else curl -fsSL https://claude.ai/install.sh | bash && ok "Claude Code installed"; fi
  command -v claude >/dev/null || die "claude not on PATH - open a new terminal and run this setup again."
elif [ "$TOOL" = codex ]; then
  command -v codex >/dev/null && ok "Codex found" || die \
    "Codex is not installed. Install it (https://developers.openai.com/codex/cli, e.g. npm install -g @openai/codex), then run this setup again with --codex."
else
  command -v opencode >/dev/null && ok "opencode found" || die \
    "opencode is not installed. Install it (https://opencode.ai, e.g. npm install -g opencode-ai), then run this setup again with --opencode."
fi

step 4/6 "garmin-coach plugin"
if [ "$TOOL" = claude ]; then
  claude plugin marketplace add fedetic/garmin-coach-plugin >/dev/null 2>&1 \
    || claude plugin marketplace update garmin-coach >/dev/null 2>&1 || true
  if claude plugin list 2>/dev/null | grep -q "garmin-coach@garmin-coach"; then
    claude plugin update garmin-coach@garmin-coach >/dev/null 2>&1 || true
    ok "plugin already installed (updated to latest)"
  else
    claude plugin install garmin-coach@garmin-coach >/dev/null || die "plugin install failed - run: claude plugin install garmin-coach@garmin-coach"
    ok "plugin installed in Claude Code"
  fi
  # fetch Python and the server's packages now, so the first session doesn't time out on them
  SERVER_DIR=$(ls -dt "$HOME"/.claude/plugins/cache/garmin-coach/garmin-coach/*/server 2>/dev/null | head -1 || true)
  if [ -n "$SERVER_DIR" ] && uv sync --quiet --frozen --project "$SERVER_DIR"; then ok "coach server ready"; fi
else
  if [ -d "$PLUGIN_DIR/.git" ]; then git -C "$PLUGIN_DIR" pull --quiet && ok "plugin updated"
  else git clone --quiet "$REPO" "$PLUGIN_DIR" && ok "plugin downloaded to $PLUGIN_DIR"; fi
  uv run --quiet --frozen --project "$PLUGIN_DIR/server" coach-$TOOL install | sed 's/^/  /'
fi

step 5/6 "Garmin Connect login"
if ls "$HOME/.garminconnect/"*.json >/dev/null 2>&1; then ok "already logged in (tokens in ~/.garminconnect)"
else
  echo "  Log in with your Garmin Connect email and password (and MFA code if you use one)."
  echo "  Your password is not stored, only a login token in ~/.garminconnect on this computer."
  tty_in uvx --python 3.12 --from "$GARMIN_MCP" garmin-mcp-auth
fi

step 6/6 "Your coaching folder"
mkdir -p "$WORKSPACE" && ok "$WORKSPACE (your data lives here, not in the plugin)"

cat <<EOF

All set. Start coaching:

    cd ~/coach
    $TOOL

Then type:   set me up as a new athlete
EOF
if [ "$TOOL" = claude ]; then echo "(First time? Claude Code asks you to log in - a Claude Pro or Max plan is needed.)"; fi
if [ "$TOOL" = opencode ]; then echo "(In opencode, press Tab to switch to the 'coach' agent. Local model? See 'Local models' in the README.)"; fi
