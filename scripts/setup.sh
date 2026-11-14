#!/usr/bin/env bash
# garmin-coach one-command setup for macOS, Linux and WSL.
#
#   curl -fsSL https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.sh | bash
#   ... | bash -s -- --codex        # use OpenAI Codex instead of Claude Code
#   ... | bash -s -- --opencode     # use opencode (e.g. with a local model)
#   ... | bash -s -- --desktop      # Claude Desktop (Cowork): prepare this computer, add the plugin in the app
#   ... | bash -s -- --no-garmin    # no Garmin watch: skip the Garmin login, don't ask
#   ... | bash -s -- --hevy         # log lifts in Hevy: connect it, don't ask
#
# Safe to run again: every step checks first and skips what is already done.
set -euo pipefail

TOOL=claude
GARMIN=ask      # ask | yes | no
HEVY=ask
for a in "$@"; do
  [ "$a" = "--codex" ] && TOOL=codex
  [ "$a" = "--opencode" ] && TOOL=opencode
  [ "$a" = "--desktop" ] && TOOL=desktop
  [ "$a" = "--no-garmin" ] && GARMIN=no
  [ "$a" = "--hevy" ] && HEVY=yes
done
REPO="https://github.com/fedetic/garmin-coach-plugin.git"
PLUGIN_DIR="$HOME/.garmin-coach/plugin"          # Codex and opencode
WORKSPACE="$HOME/coach"
# pinned to a reviewed commit: the login tool sees your password, the server your token
GARMIN_MCP="git+https://github.com/Taxuspt/garmin_mcp@202913fde53c9d15890d661fc9748dc6d0d5af52"
# cryptography 49+ ships no Intel-Mac wheels; without this uv compiles it from source (needs Rust)
GARMIN_MCP_WITH="cryptography<49; sys_platform == 'darwin' and platform_machine == 'x86_64'"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

step() { printf '\n\033[1m[%s] %s\033[0m\n' "$1" "$2"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
die()  { printf '  \033[31m✗ %s\033[0m\n' "$1"; exit 1; }
tty_in() { if [ -r /dev/tty ]; then "$@" </dev/tty; else "$@"; fi; }   # interactive even under curl | bash
# yes/no question; $2 is the answer when there is no keyboard to ask (curl | bash in a script)
ask() {
  local a=""
  if (exec </dev/tty) 2>/dev/null; then printf '  %s ' "$1" >/dev/tty; read -r a </dev/tty || a=""
  else a="$2"; fi
  a=${a:-$2}
  case "$a" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

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
elif [ "$TOOL" = desktop ]; then
  # the app itself is installed and signed in by the person; this script only prepares the computer
  if [ -d /Applications/Claude.app ] || [ -d "$HOME/Applications/Claude.app" ]; then ok "Claude Desktop found"
  else echo "  Claude Desktop not found in Applications. Download it from https://claude.ai/download (a paid Claude plan is needed for Cowork)."; fi
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
  if [ "$TOOL" = desktop ]; then
    uv sync --quiet --frozen --project "$PLUGIN_DIR/server" && ok "coach server ready (you add the plugin inside Claude Desktop, see below)"
  else
    uv run --quiet --frozen --project "$PLUGIN_DIR/server" coach-$TOOL install | sed 's/^/  /'
  fi
fi

step 5/6 "Your data sources (Garmin watch, Hevy app)"
if [ "$GARMIN" = ask ]; then ask "Do you have a Garmin watch that syncs to Garmin Connect? [Y/n]" y && GARMIN=yes || GARMIN=no; fi
if [ "$GARMIN" = no ]; then ok "no Garmin: the coach will ask a few quick questions instead of reading recovery data"
elif ls "$HOME/.garminconnect/"*.json >/dev/null 2>&1; then ok "Garmin: already logged in (tokens in ~/.garminconnect)"
else
  echo "  Log in with your Garmin Connect email and password (and MFA code if you use one)."
  echo "  Your password is not stored, only a login token in ~/.garminconnect on this computer."
  tty_in uvx --python 3.12 --with "$GARMIN_MCP_WITH" --from "$GARMIN_MCP" garmin-mcp-auth
fi
if [ "$HEVY" = ask ]; then ask "Do you log your workouts in the Hevy app? (needs Hevy Pro) [y/N]" n && HEVY=yes || HEVY=no; fi
if [ "$HEVY" = yes ]; then
  if [ -s "$HOME/.hevy/api-key" ]; then ok "Hevy: key already saved (~/.hevy/api-key)"
  else
    echo "  Create an API key in Hevy: Settings > Developer (https://hevy.com/settings?developer)."
    echo "  It is saved only on this computer, readable only by you. Nothing shows as you type."
    if [ "$TOOL" = claude ]; then HEVY_SERVER=$(ls -dt "$HOME"/.claude/plugins/cache/garmin-coach/garmin-coach/*/server 2>/dev/null | head -1 || true)
    else HEVY_SERVER="$PLUGIN_DIR/server"; fi
    if [ -n "${HEVY_SERVER:-}" ]; then tty_in uv run --quiet --frozen --project "$HEVY_SERVER" coach-hevy-auth
    else tty_in uvx --from "git+https://github.com/fedetic/garmin-coach-plugin#subdirectory=server" coach-hevy-auth; fi \
      || echo "  Hevy key not saved. Run this step again later; the coach will tell you how."
  fi
fi

step 6/6 "Your coaching folder"
mkdir -p "$WORKSPACE" && ok "$WORKSPACE (your data lives here, not in the plugin)"

if [ "$TOOL" = desktop ]; then
cat <<EOF

This computer is ready. Two things left, in Claude Desktop:

  1. Cowork > Plugins > Add marketplace > enter:  fedetic/garmin-coach-plugin
     then install "garmin-coach".
  2. Start a Cowork task, choose the folder ~/coach, and type:  set me up as a new athlete

Full walkthrough: docs/claude-desktop-hevy.md in the repository.
EOF
else
cat <<EOF

All set. Start coaching:

    cd ~/coach
    $TOOL

Then type:   set me up as a new athlete
EOF
fi
if [ "$TOOL" = claude ]; then echo "(First time? Claude Code asks you to log in - a Claude Pro or Max plan is needed.)"; fi
if [ "$TOOL" = opencode ]; then echo "(In opencode, press Tab to switch to the 'coach' agent. Local model? See 'Local models' in the README.)"; fi
