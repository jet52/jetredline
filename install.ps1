#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SkillName = "jetredline"
$InstallDir = Join-Path $HOME ".claude\skills\$SkillName"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Installing $SkillName skill..."

# Create target directory
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# Copy skill files
$SourceDir = Join-Path $ScriptDir "skills\jetredline"
Copy-Item -Path "$SourceDir\*" -Destination $InstallDir -Recurse -Force

Write-Host "Installed to $InstallDir"

# --- Python virtual environment ---
Write-Host ""
Write-Host "Setting up Python virtual environment..."

$VenvDir = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "Using uv to create venv..."
    & uv venv $VenvDir --clear
    & uv pip install -r "$InstallDir\requirements.txt" --python $VenvPython
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    Write-Host "Using python3 to create venv..."
    & python3 -m venv $VenvDir --clear
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r "$InstallDir\requirements.txt"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "Using python to create venv..."
    & python -m venv $VenvDir --clear
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r "$InstallDir\requirements.txt"
} else {
    Write-Host "ERROR: Neither uv nor python found. Cannot create virtual environment." -ForegroundColor Red
    Write-Host "  Install Python 3 from https://www.python.org/ or uv from https://docs.astral.sh/uv/"
    exit 1
}

Write-Host "Python packages installed."

# --- Node.js dependencies ---
Write-Host ""
Write-Host "Installing Node.js dependencies..."

if (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location $InstallDir
    & npm install
    Pop-Location
    Write-Host "Node packages installed."
} else {
    Write-Host "ERROR: npm not found. Cannot install Node.js dependencies." -ForegroundColor Red
    Write-Host "  Install Node.js from https://nodejs.org/"
    exit 1
}

Write-Host ""
Write-Host "Done."
