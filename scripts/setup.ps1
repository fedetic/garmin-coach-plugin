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
# pinned to a reviewed commit: the login tool sees your password, the server your token
$GarminMcp = "git+https://github.com/Taxuspt/garmin_mcp@202913fde53c9d15890d661fc9748dc6d0d5af52"

function Step($n, $t) { Write-Host "`n[$n] $t" -ForegroundColor White }
function Ok($t) { Write-Host "  + $t" -ForegroundColor Green }
function Fail($t) { Write-Host "  x $t" -ForegroundColor Red; throw "setup stopped" }
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
  # registry PATH plus the folders installers use, in case PATH isn't updated yet
  $extra = @((Join-Path $HOME ".local\bin"),
             (Join-Path $env:ProgramFiles "Git\cmd"),
             (Join-Path $env:LOCALAPPDATA "Programs\Git\cmd")) | Where-Object { Test-Path $_ }
  $env:Path = (@([Environment]::GetEnvironmentVariable("Path", "Machine"),
                 [Environment]::GetEnvironmentVariable("Path", "User")) + $extra) -join ";"
}

# Git for Windows straight from its GitHub release, installed for this user only
# (no admin needed). Used when winget is missing or fails.
function Install-GitDirect {
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "64-bit" }
    $rel = Invoke-RestMethod "https://api.github.com/repos/git-for-windows/git/releases/latest" -UseBasicParsing
    $asset = $rel.assets | Where-Object { $_.name -match "^Git-[\d.]+-$arch\.exe$" } | Select-Object -First 1
    if (-not $asset) { return $false }
    $exe = Join-Path $env:TEMP $asset.name
    Write-Host "  downloading $($asset.name) ..."
    # the progress bar makes downloads many times slower in Windows PowerShell 5.1
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest $asset.browser_download_url -OutFile $exe -UseBasicParsing
    Start-Process $exe -Wait -ArgumentList "/VERYSILENT", "/NORESTART", "/NOCANCEL", "/SP-", "/CURRENTUSER"
    Remove-Item $exe -ErrorAction SilentlyContinue
    return $true
  } catch { Write-Host "  direct download failed: $($_.Exception.Message)"; return $false }
}

Step "1/6" "git"
Refresh-Path
if (Has git) { Ok "git found" }
else {
  if (Has winget) {
    # user scope first (no admin prompt); machine scope if the package has no user installer
    winget install --id Git.Git -e --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
    if (-not (Has git)) {
      winget install --id Git.Git -e --source winget --silent --accept-package-agreements --accept-source-agreements
      Refresh-Path
    }
  }
  if (-not (Has git)) {
    Write-Host "  winget unavailable or failed - installing Git for Windows directly"
    if (Install-GitDirect) { Refresh-Path }
  }
  if (Has git) { Ok "git installed" }
  else { Fail "could not install git. Install Git for Windows from https://git-scm.com/downloads/win, then open a new PowerShell and run this setup again." }
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
  # fetch Python and the server's packages now, so the first session doesn't time out on them
  $ServerDir = Get-ChildItem (Join-Path $HOME ".claude\plugins\cache\garmin-coach\garmin-coach\*\server") -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime | Select-Object -Last 1
  if ($ServerDir) {
    uv sync --quiet --frozen --project $ServerDir.FullName
    if ($LASTEXITCODE -eq 0) { Ok "coach server ready" }
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
