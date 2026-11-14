# garmin-coach one-command setup for Windows (PowerShell).
#
#   irm https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.ps1 | iex
#   $env:COACH_TOOL="codex"; irm https://raw.githubusercontent.com/fedetic/garmin-coach-plugin/main/scripts/setup.ps1 | iex
#   $env:COACH_TOOL="opencode"; irm ... | iex   # opencode (e.g. with a local model)
#   $env:COACH_TOOL="desktop"; irm ... | iex    # Claude Desktop (Cowork): prepare this computer, add the plugin in the app
#   $env:COACH_GARMIN="no"; irm ... | iex       # no Garmin watch: skip the Garmin login, don't ask
#   $env:COACH_HEVY="yes"; irm ... | iex        # log lifts in Hevy: connect it, don't ask
#
# Safe to run again: every step checks first and skips what is already done.
# Continue, not Stop: Windows PowerShell 5.1 turns any stderr output of a native
# command into a terminating error under Stop. Failures are checked explicitly.
$ErrorActionPreference = "Continue"

$Tool = if ($env:COACH_TOOL -in @("codex", "opencode", "desktop")) { $env:COACH_TOOL } else { "claude" }
$Garmin = if ($env:COACH_GARMIN -in @("yes", "no")) { $env:COACH_GARMIN } else { "ask" }
$Hevy = if ($env:COACH_HEVY -in @("yes", "no")) { $env:COACH_HEVY } else { "ask" }
$Repo = "https://github.com/fedetic/garmin-coach-plugin.git"
$PluginDir = Join-Path $HOME ".garmin-coach\plugin"     # Codex and opencode
$Workspace = Join-Path $HOME "coach"
$NodeDir = Join-Path $env:LOCALAPPDATA "Programs\nodejs"   # only used if setup installs Node.js
$Launch = $Tool                                             # what to type to start the AI tool
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
             (Join-Path $env:LOCALAPPDATA "Programs\Git\cmd"),
             $NodeDir, (Join-Path $env:APPDATA "npm")) | Where-Object { Test-Path $_ }
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

function Ask($q) {
  $a = Read-Host "  $q [Y/n]"
  return ($a.Trim() -eq "" -or $a.Trim() -match "^(y|yes)$")
}

# Node.js LTS as a portable zip in the user's folder: no admin, no winget needed.
# npm then puts global commands (codex, opencode) in that same folder.
function Install-Node {
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $ProgressPreference = "SilentlyContinue"
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }
    # assigned first: Invoke-RestMethod sends a JSON array down the pipe as one object
    $releases = Invoke-RestMethod "https://nodejs.org/dist/index.json" -UseBasicParsing
    $lts = $releases | Where-Object { $_.lts -and $_.files -contains "win-$arch-zip" } | Select-Object -First 1
    $name = "node-$($lts.version)-win-$arch"
    $zip = Join-Path $env:TEMP "$name.zip"
    Write-Host "  downloading Node.js $($lts.version) ..."
    Invoke-WebRequest "https://nodejs.org/dist/$($lts.version)/$name.zip" -OutFile $zip -UseBasicParsing
    $tmp = Join-Path $env:TEMP "node-extract"
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    if (Has tar) { tar -xf $zip -C $tmp } else { Expand-Archive $zip $tmp -Force }
    Remove-Item $NodeDir -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path (Split-Path $NodeDir) | Out-Null
    Move-Item (Join-Path $tmp $name) $NodeDir
    Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
    # on the user's PATH for new windows too
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($userPath -split ";") -notcontains $NodeDir) {
      [Environment]::SetEnvironmentVariable("Path", (@($userPath, $NodeDir) | Where-Object { $_ }) -join ";", "User")
    }
    return (Test-Path (Join-Path $NodeDir "node.exe"))
  } catch { Write-Host "  Node.js download failed: $($_.Exception.Message)"; return $false }
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
} elseif ($Tool -eq "desktop") {
  # the app itself is installed and signed in by the person; this script only prepares the computer
  Write-Host "  Claude Desktop is installed from https://claude.ai/download (a paid Claude plan is needed for Cowork)."
  Ok "nothing to install here for Claude Desktop"
} else {
  $Pkg = if ($Tool -eq "codex") { "@openai/codex" } else { "opencode-ai" }
  if (Has $Tool) { Ok "$Tool found" }
  else {
    Write-Host "  $Tool is not installed. Setup can install it for you:"
    if (-not (Has node)) { Write-Host "   - Node.js LTS, for your user only (no admin needed)" }
    Write-Host "   - $Tool (npm install -g $Pkg)"
    if (-not (Ask "Install now?")) { Fail "install $Tool yourself (npm install -g $Pkg), then run this setup again." }
    if (-not (Has node)) {
      if (Install-Node) { Refresh-Path; Ok "Node.js installed" } else { Fail "could not install Node.js. Install the LTS version from https://nodejs.org, then run this setup again." }
    }
    npm.cmd install -g $Pkg    # npm.cmd: npm.ps1 is blocked until scripts are allowed
    Refresh-Path
    if (Has $Tool) { Ok "$Tool installed" } else { Fail "$Tool install failed (see message above)." }
  }
  # npm installs commands as PowerShell scripts, which Windows blocks by default
  if ((Get-Command $Tool -All | Where-Object CommandType -eq ExternalScript) -and
      (Get-ExecutionPolicy) -in @("Restricted", "AllSigned", "Undefined")) {
    Write-Host "  Windows blocks running '$Tool' from PowerShell until scripts are allowed for your user:"
    Write-Host "    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned"
    Write-Host "  (scripts made on this computer may run; downloaded scripts must be signed)"
    if (Ask "Allow it?") {
      try { Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force -ErrorAction Stop } catch { }
    }
    if ((Get-ExecutionPolicy) -in @("Restricted", "AllSigned", "Undefined")) {
      $Launch = "$Tool.cmd"
      Ok "scripts stay blocked - start it with '$Launch' instead of '$Tool'"
    } else { Ok "scripts allowed for your user" }
  }
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
  if ($Tool -eq "desktop") {
    uv sync --quiet --frozen --project (Join-Path $PluginDir "server")
    if ($LASTEXITCODE -eq 0) { Ok "coach server ready (you add the plugin inside Claude Desktop, see below)" }
  } else {
    uv run --quiet --frozen --project (Join-Path $PluginDir "server") "coach-$Tool" install
    if ($LASTEXITCODE -ne 0) { Fail "$Tool registration failed (see message above)" }
  }
}

Step "5/6" "Your data sources (Garmin watch, Hevy app)"
if ($Garmin -eq "ask") { $Garmin = if (Ask "Do you have a Garmin watch that syncs to Garmin Connect?") { "yes" } else { "no" } }
if ($Garmin -eq "no") {
  Ok "no Garmin: the coach will ask a few quick questions instead of reading recovery data"
} elseif (Get-ChildItem (Join-Path $HOME ".garminconnect\*.json") -ErrorAction SilentlyContinue) {
  Ok "Garmin: already logged in (tokens in $HOME\.garminconnect)"
} else {
  Write-Host "  Log in with your Garmin Connect email and password (and MFA code if you use one)."
  Write-Host "  Your password is not stored, only a login token in .garminconnect on this computer."
  uvx --python 3.12 --from $GarminMcp garmin-mcp-auth
}
if ($Hevy -eq "ask") {
  $a = (Read-Host "  Do you log your workouts in the Hevy app? (needs Hevy Pro) [y/N]").Trim()
  $Hevy = if ($a -match "^(y|yes)$") { "yes" } else { "no" }
}
if ($Hevy -eq "yes") {
  if ((Test-Path (Join-Path $HOME ".hevy\api-key")) -and (Get-Item (Join-Path $HOME ".hevy\api-key")).Length -gt 0) {
    Ok "Hevy: key already saved ($HOME\.hevy\api-key)"
  } else {
    Write-Host "  Create an API key in Hevy: Settings > Developer (https://hevy.com/settings?developer)."
    Write-Host "  It is saved only on this computer. Nothing shows as you type."
    $HevyServer = if ($Tool -eq "claude") {
      Get-ChildItem (Join-Path $HOME ".claude\plugins\cache\garmin-coach\garmin-coach\*\server") -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime | Select-Object -Last 1 -ExpandProperty FullName
    } else { Join-Path $PluginDir "server" }
    if ($HevyServer) { uv run --quiet --frozen --project $HevyServer coach-hevy-auth }
    else { uvx --from "git+https://github.com/fedetic/garmin-coach-plugin#subdirectory=server" coach-hevy-auth }
    if ($LASTEXITCODE -ne 0) { Write-Host "  Hevy key not saved. Run this step again later; the coach will tell you how." }
  }
}

Step "6/6" "Your coaching folder"
New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
Ok "$Workspace (your data lives here, not in the plugin)"

Write-Host ""
if ($Tool -eq "desktop") {
  Write-Host "This computer is ready. Two things left, in Claude Desktop:" -ForegroundColor Green
  Write-Host ""
  Write-Host "  1. Cowork > Plugins > Add marketplace > enter:  fedetic/garmin-coach-plugin"
  Write-Host "     then install 'garmin-coach'."
  Write-Host "  2. Start a Cowork task, choose the folder ~\coach, and type:  set me up as a new athlete"
  Write-Host ""
  Write-Host "Full walkthrough: docs/claude-desktop-hevy.md in the repository."
} else {
  Write-Host "All set. Start coaching:" -ForegroundColor Green
  Write-Host ""
  Write-Host "    cd ~\coach"
  Write-Host "    $Launch"
  Write-Host ""
  Write-Host "Then type:   set me up as a new athlete"
}
if ($Tool -eq "claude") { Write-Host "(First time? Claude Code asks you to log in - a Claude Pro or Max plan is needed.)" }
if ($Tool -eq "opencode") { Write-Host "(In opencode, press Tab to switch to the 'coach' agent. Local model? See 'Local models' in the README.)" }
