"""
Updater module for Noteration.
Handles version checking and self-updating.
"""

from __future__ import annotations

import sys
import subprocess
import platform
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from noteration import __version__

# URL to check for latest version (directly from pyproject.toml on main branch)
REMOTE_PYPROJECT_URL = "https://raw.githubusercontent.com/lilamr/noteration/main/pyproject.toml"

class CheckUpdateThread(QThread):
    """Thread to check for updates without blocking the UI."""
    finished = Signal(bool, str)  # (is_update_available, latest_version)
    error = Signal(str)

    def run(self) -> None:
        try:
            import urllib.request
            import re

            with urllib.request.urlopen(REMOTE_PYPROJECT_URL, timeout=10) as response:
                content = response.read().decode('utf-8')
                
                # Simple regex to find version in pyproject.toml
                match = re.search(r'version\s*=\s*"([^"]+)"', content)
                if match:
                    remote_version = match.group(1)
                    is_newer = self._is_newer(remote_version, __version__)
                    self.finished.emit(is_newer, remote_version)
                else:
                    self.error.emit("Could not parse version from remote repository.")
        except Exception as e:
            self.error.emit(str(e))

    def _is_newer(self, remote: str, local: str) -> bool:
        """Simple semantic version comparison."""
        try:
            r_parts = [int(p) for p in remote.split('.')]
            l_parts = [int(p) for p in local.split('.')]
            return r_parts > l_parts
        except (ValueError, AttributeError):
            return remote != local

def run_update_process() -> bool:
    """
    Executes the update command.
    Returns True if update was initiated.
    """
    repo_url = "git+https://github.com/lilamr/noteration.git"
    install_cmd = [
        sys.executable, "-m", "pip", "install", "--upgrade",
        f"noteration[all] @ {repo_url}"
    ]

    try:
        if platform.system() == "Windows":
            return _run_windows_update(install_cmd)
        else:
            # Linux/macOS can usually update in-place
            subprocess.Popen(install_cmd)
            return True
    except Exception:
        return False

def _run_windows_update(install_cmd: list[str]) -> bool:
    """Windows-specific update logic to handle file locking."""
    # Create a temporary batch file that waits for the app to exit, 
    # then runs the update, then restarts the app.
    
    app_path = sys.executable
    if app_path.endswith("python.exe") or app_path.endswith("pythonw.exe"):
        # We are likely in a venv, we want the noteration.exe wrapper if possible, 
        # but pip upgrade will handle the scripts too.
        pass

    with tempfile.NamedTemporaryFile(delete=False, suffix=".bat", mode='w') as f:
        f.write("@echo off\n")
        f.write("echo Waiting for Noteration to close...\n")
        f.write("timeout /t 2 /nobreak > nul\n")
        f.write("echo Updating Noteration...\n")
        f.write(f"{' '.join(install_cmd)}\n")
        f.write("echo Update complete. Restarting...\n")
        # Find the noteration.exe in the same venv Scripts folder
        noteration_exe = Path(sys.executable).parent / "noteration.exe"
        if noteration_exe.exists():
            f.write(f"start \"\" \"{noteration_exe}\"\n")
        else:
            f.write(f"start \"\" \"{sys.executable}\" -m noteration\n")
        f.write("del \"%~f0\"\n")
        batch_path = f.name

    subprocess.Popen(["cmd.exe", "/c", "start", "/min", batch_path], shell=True)
    return True
