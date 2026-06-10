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

# Robust Python version check
& $pythonExe -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    $currentVer = & $pythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    Write-Error-Msg "Noteration requires Python 3.11+. Current version is $currentVer."
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
& $pythonExe -m venv (Join-Path $installDir "venv") --clear

$venvDir = Join-Path $installDir "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"
$noterationExe = Join-Path $venvDir "Scripts\noteration.exe"

# 5. Install Noteration
Write-Header "Installing Noteration and dependencies..."
& $venvPip install --upgrade pip --quiet
& $venvPip install "noteration[all] @ git+https://github.com/lilamr/noteration.git" --quiet

# 6. Create Wrapper Batch Files
Write-Header "Creating wrapper scripts..."

function Create-Wrapper ($cmdName, $isGui) {
    $wrapperPath = Join-Path $installDir "$cmdName.bat"
    $exePath = Join-Path $venvDir "Scripts\$cmdName.exe"
    
    if ($isGui) {
        $batchContent = @"
@echo off
setlocal
set "PATH=$venvDir\Scripts;%PATH%"
start "" "$exePath" %*
"@
    } else {
        $batchContent = @"
@echo off
setlocal
set "PATH=$venvDir\Scripts;%PATH%"
"$exePath" %*
"@
    }
    $batchContent | Out-File -FilePath $wrapperPath -Encoding ascii

    if (Test-Path $binDir) {
        Copy-Item $wrapperPath (Join-Path $binDir "$cmdName.bat") -Force
    }
    return $wrapperPath
}

$noterationWrapper = Create-Wrapper "noteration" $true
$ntrWrapper = Create-Wrapper "ntr" $false
$ntrApiWrapper = Create-Wrapper "ntr-api" $false

# 8. Create Shortcuts (Desktop & Start Menu)
Write-Header "Creating shortcuts..."
try {
    $WshShell = New-Object -ComObject WScript.Shell

    # Download Icon for Windows
    $iconPath = Join-Path $installDir "icon.ico"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/lilamr/noteration/main/noteration/assets/images/icon.ico" -OutFile $iconPath -ErrorAction SilentlyContinue

    function Create-Lnk ($path, $target, $icon) {
        $Shortcut = $WshShell.CreateShortcut($path)
        $Shortcut.TargetPath = $target
        $Shortcut.WorkingDirectory = $installDir
        if (Test-Path $icon) { $Shortcut.IconLocation = $icon }
        $Shortcut.Save()
    }

    $desktopPath = [System.IO.Path]::Combine([Environment]::GetFolderPath("Desktop"), "Noteration.lnk")
    $startMenuPath = [System.IO.Path]::Combine([Environment]::GetFolderPath("Programs"), "Noteration.lnk")

    Create-Lnk $desktopPath $noterationWrapper $iconPath
    Create-Lnk $startMenuPath $noterationWrapper $iconPath
} catch {
    Write-Host "Warning: Could not create shortcuts automatically. You can still run Noteration by typing 'noteration' in the terminal."
}

Write-Success "Noteration installed successfully!"
Write-Host "You can now run Noteration from your Desktop, Start Menu, or by typing 'noteration' in CMD/PowerShell."
Write-Host ""
Write-Host "Note: If 'noteration' command is not found, please restart your terminal."
