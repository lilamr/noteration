# Noteration One-Liner Installer for Windows
# Usage: irm https://raw.githubusercontent.com/lilamr/noteration/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Header ($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Success ($msg) { Write-Host "==> $msg" -ForegroundColor Green }
function Write-Error-Msg ($msg) { Write-Host "Error: $msg" -ForegroundColor Red }
function Write-Yellow ($msg) { Write-Host $msg -ForegroundColor Yellow }

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

# 3. Detect latest release tag
Write-Header "Checking latest release..."
try {
    $releaseInfo = Invoke-RestMethod -Uri "https://api.github.com/repos/lilamr/noteration/releases/latest" -ErrorAction Stop
    $latestTag = $releaseInfo.tag_name
    $version = $latestTag.TrimStart('v')
    $installRef = $latestTag
    Write-Success "Latest release: $latestTag"
} catch {
    Write-Yellow "Warning: Could not detect latest release. Falling back to main branch."
    $installRef = "main"
    $version = "dev"
}

# 4. Setup Directories
$installDir = Join-Path $env:LOCALAPPDATA "noteration"
$binDir = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"
if (!(Test-Path $installDir)) { New-Item -ItemType Directory -Path $installDir | Out-Null }

# 5. Create Virtual Environment
Write-Header "Creating virtual environment in $installDir..."
& $pythonExe -m venv (Join-Path $installDir "venv") --clear

$venvDir = Join-Path $installDir "venv"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"

# 6. Install Noteration
Write-Header "Installing Noteration $version..."
& $venvPip install --upgrade pip --quiet
& $venvPip install "noteration[all] @ git+https://github.com/lilamr/noteration.git@$installRef" --quiet

# Log version locally
Set-Content -Path (Join-Path $installDir "VERSION") -Value $version

# 7. Create Wrapper Batch Files
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
    return $wrapperPath
}

Create-Wrapper "noteration" $true | Out-Null
Create-Wrapper "ntr" $false | Out-Null
Create-Wrapper "ntr-api" $false | Out-Null

# 8. Create Shortcuts
Write-Header "Creating shortcuts..."
try {
    $WshShell = New-Object -ComObject WScript.Shell
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

    Create-Lnk $desktopPath (Join-Path $installDir "noteration.bat") $iconPath
    Create-Lnk $startMenuPath (Join-Path $installDir "noteration.bat") $iconPath
} catch {
    Write-Yellow "Warning: Could not create shortcuts automatically."
}

Write-Success "Noteration $version installed successfully!"
Write-Host "You can now run Noteration from your Desktop, Start Menu, or by typing 'noteration' in CMD/PowerShell."
