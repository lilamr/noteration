# Noteration One-Liner Installer for Windows
# Usage: irm https://raw.githubusercontent.com/lilamr/noteration/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Header ($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Success ($msg) { Write-Host "==> $msg" -ForegroundColor Green }
function Write-Error-Msg ($msg) { Write-Host "Error: $msg" -ForegroundColor Red }

Write-Header "Installing Noteration for Windows..."

# 1. Check Python version (3.11+)
$pythonExe = "python"
if (!(Get-Command "python" -ErrorAction SilentlyContinue)) {
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $pythonExe = "py"
    } else {
        Write-Error-Msg "Python is not installed. Please install Python 3.11+ from python.org or Microsoft Store."
        exit 1
    }
}

$version = & $pythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([float]$version -lt 3.11) {
    Write-Error-Msg "Noteration requires Python 3.11+. Current version is $version."
    exit 1
}

# 2. Check Git
if (!(Get-Command "git" -ErrorAction SilentlyContinue)) {
    Write-Error-Msg "Git is not installed. Please install Git for Windows first."
    exit 1
}

# 3. Setup Directories
$installDir = Join-Path $env:LOCALAPPDATA "noteration"
$binDir = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps" # Often already in PATH
if (!(Test-Path $installDir)) { New-Item -ItemType Directory -Path $installDir | Out-Null }

# 4. Create Virtual Environment
Write-Header "Creating virtual environment in $installDir..."
& $pythonExe -m venv (Join-Path $installDir "venv")

$venvPython = Join-Path $installDir "venv\Scripts\python.exe"
$venvPip = Join-Path $installDir "venv\Scripts\pip.exe"

# 5. Install Noteration
Write-Header "Installing Noteration and dependencies..."
& $venvPip install --upgrade pip --quiet
& $venvPip install "noteration[all] @ git+https://github.com/lilamr/noteration.git" --quiet

# 6. Create Wrapper Batch File
$wrapperPath = Join-Path $installDir "noteration.bat"
@"
@echo off
setlocal
set PATH=$installDir\venv\Scripts;%PATH%
start "" "noteration.exe" %*
"@ | Out-File -FilePath $wrapperPath -Encoding ascii

# 7. Create Shortcuts (Desktop & Start Menu)
Write-Header "Creating shortcuts..."
$WshShell = New-Object -ComObject WScript.Shell

# Download Icon for Windows
$iconPath = Join-Path $installDir "icon.ico"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/lilamr/noteration/main/noteration/assets/icon.ico" -OutFile $iconPath -ErrorAction SilentlyContinue

function Create-Lnk ($path, $target, $icon) {
    $Shortcut = $WshShell.CreateShortcut($path)
    $Shortcut.TargetPath = $target
    $Shortcut.WorkingDirectory = $installDir
    if (Test-Path $icon) { $Shortcut.IconLocation = $icon }
    $Shortcut.Save()
}

$desktopPath = [System.IO.Path]::Combine([Environment]::GetFolderPath("Desktop"), "Noteration.lnk")
$startMenuPath = [System.IO.Path]::Combine([Environment]::GetFolderPath("Programs"), "Noteration.lnk")

Create-Lnk $desktopPath $wrapperPath $iconPath
Create-Lnk $startMenuPath $wrapperPath $iconPath

Write-Success "Noteration installed successfully!"
Write-Host "You can now run Noteration from your Desktop, Start Menu, or by typing 'noteration' in CMD/PowerShell (if path is updated)."
Write-Host ""
Write-Host "Note: If 'noteration' command is not found, please restart your terminal."
