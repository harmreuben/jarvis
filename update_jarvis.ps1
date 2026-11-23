# Updates JARVIS to the latest version on GitHub WITHOUT touching your settings, contacts, reminders,
# chat history or the installed Python packages. Run it by double-clicking update_jarvis.bat.
# Offline / manual: drag a JARVIS zip onto update_jarvis.bat, or put one (jarvis-main.zip) in Downloads.
param([string]$Zip = "")
$GitHubRepo = "harmreuben/jarvis"
$Branch = "main"
$ErrorActionPreference = "Continue"  # native tools write to stderr; each step checks its own result
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Say($text, $color = "Cyan") { Write-Host $text -ForegroundColor $color }
function Fail($text) {
    Write-Host ""
    Write-Host "UPDATE STOPPED: $text" -ForegroundColor Red
    Write-Host "Nothing in your JARVIS folder was changed." -ForegroundColor Red
    Write-Host ""
    exit 1
}

Say "=============================================="
Say "            JARVIS-MARK5 update"
Say "=============================================="

# JARVIS must not be running while its files are replaced
$running = Get-NetTCPConnection -LocalPort 44444 -State Listen -ErrorAction SilentlyContinue
if ($running) {
    Fail "JARVIS is running. Close the JARVIS window first, then run the update again."
}

$ProgressPreference = "SilentlyContinue"  # makes downloads much faster in Windows PowerShell
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$old = "unknown"
if (Test-Path (Join-Path $Root "VERSION")) { $old = (Get-Content (Join-Path $Root "VERSION") -TotalCount 1).Trim() }
$tmpZip = $null

# --- 1. get the new version: from GitHub, or a zip you provide -----------------------
if (-not $Zip) {
    Say "Checking GitHub ($GitHubRepo) for a new version..."
    try {
        $remote = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 30 -ErrorAction Stop `
                   -Uri "https://raw.githubusercontent.com/$GitHubRepo/$Branch/VERSION").Content.Trim()
        if ($remote -eq $old) {
            Write-Host ""
            Say "JARVIS is already up to date (version $old)." "Green"
            Write-Host ""
            exit 0
        }
        Say "New version $remote available - downloading..."
        $tmpZip = Join-Path $env:TEMP ("jarvis_update_" + [guid]::NewGuid().ToString("N") + ".zip")
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 300 -ErrorAction Stop `
            -Uri "https://github.com/$GitHubRepo/archive/refs/heads/$Branch.zip" -OutFile $tmpZip
        $Zip = $tmpZip
    } catch {
        Say "Couldn't download from GitHub ($($_.Exception.Message)). Looking for a zip in Downloads instead..." "Yellow"
        if ($tmpZip) { Remove-Item -Force $tmpZip -ErrorAction SilentlyContinue; $tmpZip = $null }
        $Zip = ""
    }
}
if (-not $Zip) {
    $downloads = Join-Path $env:USERPROFILE "Downloads"
    $latest = Get-ChildItem -Path $downloads -Filter "jarvis*.zip" -File -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) {
        Fail "No JARVIS zip found in your Downloads folder. Check your internet connection, or download the zip from https://github.com/$GitHubRepo and run the update again."
    }
    $Zip = $latest.FullName
}
if (-not (Test-Path $Zip)) { Fail "The file $Zip doesn't exist." }
Say "Update file: $Zip"

# --- 2. unpack to a temporary folder and check it ----------------------------------
$tmp = Join-Path $env:TEMP ("jarvis_update_" + [guid]::NewGuid().ToString("N"))
try {
    Expand-Archive -Path $Zip -DestinationPath $tmp -Force -ErrorAction Stop
} catch {
    Fail "Could not unpack the zip ($($_.Exception.Message)). Download it again."
}
$src = Get-ChildItem -Path $tmp -Directory | Where-Object { Test-Path (Join-Path $_.FullName "jarvis.py") } | Select-Object -First 1
if (-not $src -and (Test-Path (Join-Path $tmp "jarvis.py"))) { $src = Get-Item $tmp }
if (-not $src -or -not (Test-Path (Join-Path $src.FullName "backend\core\brain.py"))) {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    if ($tmpZip) { Remove-Item -Force $tmpZip -ErrorAction SilentlyContinue }
    Fail "That zip doesn't contain JARVIS."
}

$new = "unknown"
if (Test-Path (Join-Path $src.FullName "VERSION")) { $new = (Get-Content (Join-Path $src.FullName "VERSION") -TotalCount 1).Trim() }
Say "Installed version: $old  ->  new version: $new"

# --- 3. copy the new code over the old (personal files are never in the zip and are protected anyway) ---
Say "`n[1/2] Copying the new files..."
& robocopy $src.FullName $Root /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP `
    /XD venv .git `
    /XF config.json contacts.json reminders.json ChatLog.json jarvis.log jarvis.log.1 jarvis.log.2 | Out-Null
$rc = $LASTEXITCODE
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
if ($tmpZip) { Remove-Item -Force $tmpZip -ErrorAction SilentlyContinue }
if ($rc -ge 8) { Fail "Copying files failed (robocopy code $rc). Close any open JARVIS files and try again." }
Say "Files updated." "Green"

# --- 4. install any new packages (fast: already-installed ones are skipped) -----------
$VenvPy = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Say "`nJARVIS's Python environment is missing - running the full setup instead..." "Yellow"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "setup_windows.ps1")
    exit $LASTEXITCODE
}
Say "`n[2/2] Checking packages..."
& $VenvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Root "requirements-windows-lock.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "PACKAGE INSTALL FAILED (see above). The new JARVIS files are in place, but some new features need these packages." -ForegroundColor Red
    Write-Host "Check your internet connection and run update_jarvis.bat again; it will finish the job." -ForegroundColor Red
    exit 1
}
Say "Packages up to date." "Green"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\fetch_ui_assets.ps1")

Write-Host ""
Say "UPDATE COMPLETE ($new). Your settings, contacts, reminders and chat history were kept." "Green"
Say "Start JARVIS from the desktop icon. If anything seems wrong, run check_setup.bat." "Green"
Write-Host ""
