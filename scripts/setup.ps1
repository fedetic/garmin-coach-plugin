# garmin-coach one-command setup for Windows (PowerShell).
#
#   irm https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.ps1 | iex
#   $env:COACH_TOOL="codex"; irm https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.ps1 | iex
#   $env:COACH_TOOL="opencode"; irm ... | iex   # opencode (e.g. with a local model)
#
# Safe to run again: every step checks first and skips what is already done.
# Continue, not Stop: Windows PowerShell 5.1 turns any stderr output of a native
# command into a terminating error under Stop. Failures are checked explicitly.
$ErrorActionPreference = "Continue"

$Tool = if ($env:COACH_TOOL -in @("codex", "opencode")) { $env:COACH_TOOL } else { "claude" }
$Repo = "https://github.com/fedetic/garmin-coach-plugin.git"
$PluginDir = Join-Path $HOME ".garmin-coach\plugin"     # Codex and opencode
$Workspace = Join-Path $HOME "coach"
$GarminMcp = "git+https://github.com/Taxuspt/garmin_mcp"

function Step($n, $t) { Write-Host "`n[$n] $t" -ForegroundColor White }
function Ok($t) { Write-Host "  + $t" -ForegroundColor Green }
function Fail($t) { Write-Host "  x $t" -ForegroundColor Red; throw "setup stopped" }
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User") + ";" + (Join-Path $HOME ".local\bin")
}

Step "1/6" "git"
if (Has git) { Ok "git found" }
else {
  if (-not (Has winget)) { Fail "git is missing. Install Git for Windows from https://git-scm.com/downloads/win, then run this setup again." }
  winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
  Refresh-Path
  if (Has git) { Ok "git installed" } else { Fail "git installed but not visible yet - close this window, open a new PowerShell and run setup again." }
}

Step "2/6" "uv (runs the coach and Garmin servers; installs Python by itself)"
if (Has uv) { Ok "uv found" }
else {
  powershell -ExecutionPolicy ByPass -NoProfile -c "irm https://astral.sh/uv/install.ps1 | iex" | Out-Null
  Refresh-Path
  if (Has uv) { Ok "uv installed" } else { Fail "uv not on PATH - open a new PowerShell and run setup again." }
}

Step "3/6" "AI tool: $Tool"
if ($Tool -eq "claude") {
  if (Has claude) { Ok "Claude Code found" }
  else {
    # child process, so an `exit` inside the installer can't end this script
    powershell -ExecutionPolicy ByPass -NoProfile -c "irm https://claude.ai/install.ps1 | iex"
    Refresh-Path
    if (Has claude) { Ok "Claude Code installed" } else { Fail "claude not on PATH - open a new PowerShell and run setup again." }
  }
} elseif ($Tool -eq "codex") {
  if (Has codex) { Ok "Codex found" }
  else { Fail "Codex is not installed. Install it (https://developers.openai.com/codex/cli), then run this setup again." }
} else {
  if (Has opencode) { Ok "opencode found" }
  else { Fail "opencode is not installed. Install it (https://opencode.ai, e.g. npm install -g opencode-ai), then run this setup again." }
}

Step "4/6" "garmin-coach plugin"
if ($Tool -eq "claude") {
  claude plugin marketplace add fedetic/garmin-coach-plugin *> $null
  if ($LASTEXITCODE -ne 0) { claude plugin marketplace update garmin-coach *> $null }
  if ((claude plugin list 2>$null) -match "garmin-coach@garmin-coach") {
    claude plugin update garmin-coach@garmin-coach *> $null
    Ok "plugin already installed (updated to latest)"
  } else {
    claude plugin install garmin-coach@garmin-coach | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok "plugin installed in Claude Code" } else { Fail "plugin install failed - run: claude plugin install garmin-coach@garmin-coach" }
  }
} else {
  if (Test-Path (Join-Path $PluginDir ".git")) { git -C $PluginDir pull --quiet; Ok "plugin updated" }
  else {
    git clone --quiet $Repo $PluginDir
    if ($LASTEXITCODE -ne 0) { Fail "could not download the plugin from $Repo" }
    Ok "plugin downloaded to $PluginDir"
  }
  uv run --quiet --frozen --project (Join-Path $PluginDir "server") "coach-$Tool" install
  if ($LASTEXITCODE -ne 0) { Fail "$Tool registration failed (see message above)" }
}

Step "5/6" "Garmin Connect login"
if (Get-ChildItem (Join-Path $HOME ".garminconnect\*.json") -ErrorAction SilentlyContinue) {
  Ok "already logged in (tokens in $HOME\.garminconnect)"
} else {
  Write-Host "  Log in with your Garmin Connect email and password (and MFA code if you use one)."
  Write-Host "  Your password is not stored, only a login token in .garminconnect on this computer."
  uvx --python 3.12 --from $GarminMcp garmin-mcp-auth
}

Step "6/6" "Your coaching folder"
New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
Ok "$Workspace (your data lives here, not in the plugin)"

Write-Host ""
Write-Host "All set. Start coaching:" -ForegroundColor Green
Write-Host ""
Write-Host "    cd ~\coach"
Write-Host "    $Tool"
Write-Host ""
Write-Host "Then type:   set me up as a new athlete"
if ($Tool -eq "claude") { Write-Host "(First time? Claude Code asks you to log in - a Claude Pro or Max plan is needed.)" }
if ($Tool -eq "opencode") { Write-Host "(In opencode, press Tab to switch to the 'coach' agent. Local model? See 'Local models' in the README.)" }
