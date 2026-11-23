# JARVIS-MARK5 installer for Windows 10/11 (64-bit).
# Run it by double-clicking setup_windows.bat. Safe to run again: it repairs/updates the install.
$ErrorActionPreference = "Continue"  # native tools (py, pip) write to stderr; every step checks $LASTEXITCODE instead
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Say($text, $color = "Cyan") { Write-Host $text -ForegroundColor $color }
function Fail($text) {
    Write-Host ""
    Write-Host "SETUP STOPPED: $text" -ForegroundColor Red
    Write-Host ""
    exit 1
}

Say "=============================================="
Say "        JARVIS-MARK5 setup for Windows"
Say "=============================================="

# --- 1. Basic checks ---------------------------------------------------------
if (-not [Environment]::Is64BitOperatingSystem) { Fail "JARVIS needs 64-bit Windows." }

$longPaths = 0
try { $longPaths = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled } catch { }
if ($longPaths -ne 1 -and $Root.Length -gt 100) {
    Fail "This folder's path is too long for Windows ($($Root.Length) characters). Move the JARVIS-MARK5 folder somewhere shorter, for example C:\Users\$env:USERNAME\JARVIS-MARK5, and run setup again."
}
if ($Root -match "OneDrive") {
    Say "Note: this folder is inside OneDrive. That works, but OneDrive will sync about 2 GB of packages. A folder outside OneDrive is better." "Yellow"
}

# --- 2. Python 3.12 ------------------------------------------------------------
function Find-Python312 {
    $candidates = @()
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $exe = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $exe) { $candidates += $exe.Trim() }
        } catch { }
    }
    $candidates += "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    $candidates += "$env:ProgramFiles\Python312\python.exe"
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) {
            $v = (& $c -c "import sys, struct; print('%d.%d %d' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P') * 8))" 2>$null)
            if ($v -and $v.Trim() -eq "3.12 64") { return $c }
        }
    }
    return $null
}

Say "`n[1/5] Checking for Python 3.12..."
$Python = Find-Python312
if (-not $Python) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Fail "Python 3.12 is not installed and winget is not available. Install Python 3.12 (64-bit) from https://www.python.org/downloads/windows/ , then run setup again."
    }
    Say "Python 3.12 not found - installing it with winget (this takes a minute)..." "Yellow"
    & winget install --exact --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    $Python = Find-Python312
    if (-not $Python) {
        Fail "Python 3.12 could not be installed automatically. Install Python 3.12 (64-bit) from https://www.python.org/downloads/windows/ , then run setup again."
    }
}
Say "Using Python: $Python" "Green"

# --- 3. Virtual environment + packages -------------------------------------------
$VenvPy = Join-Path $Root "venv\Scripts\python.exe"
Say "`n[2/5] Preparing the JARVIS Python environment..."
if (Test-Path $VenvPy) {
    $ok = (& $VenvPy -c "import sys; print(sys.version_info[:2] == (3, 12))" 2>$null)
    if (-not $ok -or $ok.Trim() -ne "True") {
        Say "Existing environment is broken or the wrong version - rebuilding it." "Yellow"
        Remove-Item -Recurse -Force (Join-Path $Root "venv")
    }
}
if (-not (Test-Path $VenvPy)) {
    & $Python -m venv (Join-Path $Root "venv")
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the Python environment." }
}

Say "`n[3/5] Installing packages (about 1-2 GB download the first time; this can take 5-15 minutes)..."
& $VenvPy -m pip install --upgrade pip --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Fail "Could not update pip. Check your internet connection and run setup again." }
& $VenvPy -m pip install --disable-pip-version-check -r (Join-Path $Root "requirements-windows-lock.txt")
if ($LASTEXITCODE -ne 0) { Fail "Package installation failed (see the messages above). Check your internet connection and run setup again - it continues where it stopped." }
& $VenvPy -m pip check
if ($LASTEXITCODE -ne 0) { Fail "Installed packages are inconsistent (see above). Run setup again." }
Say "Packages installed." "Green"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\fetch_ui_assets.ps1")

# --- 4. Settings -------------------------------------------------------------------
Say "`n[4/5] Settings"
$hasGemini = (& $VenvPy -c "from backend.core import config; print('yes' if config.load().get('GEMINI_API_KEY') else 'no')")
$hasGroq = (& $VenvPy -c "from backend.core import config; print('yes' if config.load().get('GROQ_API') else 'no')")
$hasGemini = ($hasGemini -and $hasGemini.Trim() -eq "yes")
$hasGroq = ($hasGroq -and $hasGroq.Trim() -eq "yes")
$askKey = $true
if ($hasGemini -or $hasGroq) {
    $saved = @(); if ($hasGemini) { $saved += "Gemini" }; if ($hasGroq) { $saved += "Groq" }
    $answer = Read-Host "AI key(s) already saved: $($saved -join ', '). Add or replace a key? (y/N)"
    $askKey = ($answer -match "^[yY]")
}
if ($askKey) {
    Say "JARVIS needs a free AI key. Recommended: Google Gemini (fast, can also see your screen and camera)." "Yellow"
    Say "  1. Sign in at https://aistudio.google.com/apikey  2. Click 'Create API key'  3. Copy it." "Yellow"
    Start-Process "https://aistudio.google.com/apikey"
    $gem = (Read-Host "Paste your Gemini API key (or press Enter to use Groq instead)").Trim()
    if ($gem) { $env:JARVIS_SETUP_GEMINI = $gem }
    $groqPrompt = "Optional: paste a Groq API key too, as a backup (or press Enter to skip)"
    if (-not $gem) {
        Say "Groq: sign in at https://console.groq.com/keys, click 'Create API Key' and copy it." "Yellow"
        Start-Process "https://console.groq.com/keys"
        $groqPrompt = "Paste your Groq API key"
    }
    $groq = (Read-Host $groqPrompt).Trim()
    while (-not $gem -and -not $groq -and -not $hasGemini -and -not $hasGroq) {
        $groq = (Read-Host "JARVIS needs at least one key. Paste a Groq or Gemini key").Trim()
        if ($groq -match "^AIza") { $env:JARVIS_SETUP_GEMINI = $groq; $gem = $groq; $groq = "" }
    }
    if ($groq -match "^AIza") { $env:JARVIS_SETUP_GEMINI = $groq; $groq = "" }  # a Gemini key pasted in the Groq box
    if ($groq) { $env:JARVIS_SETUP_KEY = $groq }
}
$name = (Read-Host "What should JARVIS call you? (Enter = Sir)").Trim()
if (-not $name) { $name = "Sir" }
$env:JARVIS_SETUP_NAME = $name
& $VenvPy -c "import os; from backend.core import config; u = {'USER_NAME': os.environ['JARVIS_SETUP_NAME']}; k = os.environ.get('JARVIS_SETUP_KEY'); g = os.environ.get('JARVIS_SETUP_GEMINI'); u.update({'GROQ_API': k} if k else {}); u.update({'GEMINI_API_KEY': g} if g else {}); config.save(u); print('Settings saved to config\\config.json')"
if ($LASTEXITCODE -ne 0) { Fail "Could not save settings." }
Remove-Item Env:\JARVIS_SETUP_KEY -ErrorAction SilentlyContinue
Remove-Item Env:\JARVIS_SETUP_GEMINI -ErrorAction SilentlyContinue

# --- 5. Self-test + shortcut ----------------------------------------------------------
Say "`n[5/5] Testing everything..."
& $VenvPy (Join-Path $Root "check_setup.py")
$checkResult = $LASTEXITCODE

try {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut((Join-Path $desktop "JARVIS.lnk"))
    $lnk.TargetPath = Join-Path $Root "run_jarvis.bat"
    $lnk.WorkingDirectory = $Root
    $lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,22"
    $lnk.Description = "Start JARVIS"
    $lnk.Save()
    Say "Desktop shortcut 'JARVIS' created." "Green"
} catch {
    Say "Could not create a desktop shortcut (start JARVIS with run_jarvis.bat instead)." "Yellow"
}

Write-Host ""
if ($checkResult -eq 0) {
    Say "SETUP COMPLETE. Start JARVIS with the 'JARVIS' icon on your desktop (or run_jarvis.bat)." "Green"
} else {
    Say "Setup finished, but the self-test reported a problem (see FAILED lines above). Fix it, then run check_setup.bat to test again." "Yellow"
}
Write-Host ""
