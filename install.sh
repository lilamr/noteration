#!/bin/bash

# Noteration One-Liner Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/lilamr/noteration/main/install.sh | bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==>${NC} Installing Noteration..."

# 1. OS Detection and Early Checks
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo -e "${RED}Error:${NC} This script is for Linux/macOS. For Windows, please use install.ps1"
    exit 1
fi

# Check Python version (3.11+)
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error:${NC} python3 is not installed."
    exit 1
fi

if ! python3 -c 'import sys; exit(0) if sys.version_info >= (3, 11) else exit(1)'; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    echo -e "${RED}Error:${NC} Noteration requires Python 3.11+. Current version is $PYTHON_VERSION."
    exit 1
fi

# Check for venv module
if ! python3 -m venv --help &> /dev/null; then
    echo -e "${RED}Error:${NC} python3-venv is not installed."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo -e "On Ubuntu/Debian, install it with: ${BLUE}sudo apt install python3-venv${NC}"
    fi
    exit 1
fi

# 2. Check Git
if ! command -v git &> /dev/null; then
    echo -e "${RED}Error:${NC} git is not installed. Please install git first."
    exit 1
fi

# 3. Create installation directories
INSTALL_DIR="$HOME/.local/share/noteration"
BIN_DIR="$HOME/.local/bin"
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

echo -e "${BLUE}==>${NC} Creating virtual environment in $INSTALL_DIR..."
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"

echo -e "${BLUE}==>${NC} Installing Noteration and dependencies..."
pip install --upgrade pip --quiet
pip install "noteration[all] @ git+https://github.com/lilamr/noteration.git" --quiet

# 4. Create wrapper script
cat <<EOF > "$BIN_DIR/noteration"
#!/bin/bash
# Wrapper script for Noteration
source "$INSTALL_DIR/venv/bin/activate"
exec noteration "\$@"
EOF
chmod +x "$BIN_DIR/noteration"

# 5. Desktop Integration
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo -e "${BLUE}==>${NC} Creating Linux desktop entry..."
    DESKTOP_DIR="$HOME/.local/share/applications"
    ICON_DIR="$HOME/.local/share/icons"
    mkdir -p "$DESKTOP_DIR"
    mkdir -p "$ICON_DIR"

    # Download icon from GitHub
    curl -sSL "https://raw.githubusercontent.com/lilamr/noteration/main/noteration/assets/images/icon_256.png" -o "$ICON_DIR/noteration.png"

    cat <<EOF > "$DESKTOP_DIR/noteration.desktop"
[Desktop Entry]
Name=Noteration
Comment=Research literature note-taking app
Exec=$BIN_DIR/noteration
Icon=$ICON_DIR/noteration.png
Terminal=false
Type=Application
Categories=Office;Education;Science;
EOF
    
    # Update desktop database if possible
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$DESKTOP_DIR"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${BLUE}==>${NC} Creating macOS App Bundle for Launchpad..."
    APP_NAME="Noteration"
    APP_DIR="$HOME/Applications/$APP_NAME.app"
    CONTENTS_DIR="$APP_DIR/Contents"
    MACOS_DIR="$CONTENTS_DIR/MacOS"
    RESOURCES_DIR="$CONTENTS_DIR/Resources"

    mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

    # Download macOS icon
    echo -e "${BLUE}==>${NC} Downloading app icon..."
    curl -sSL "https://raw.githubusercontent.com/lilamr/noteration/main/noteration/assets/images/icon.icns" -o "$RESOURCES_DIR/icon.icns"

    # Create the launcher inside the app bundle
    cat <<EOF > "$MACOS_DIR/$APP_NAME"
#!/bin/bash
export PATH="$BIN_DIR:\$PATH"
exec "$BIN_DIR/noteration"
EOF
    chmod +x "$MACOS_DIR/$APP_NAME"

    # Create Info.plist with Icon support
    cat <<EOF > "$CONTENTS_DIR/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIconFile</key>
    <string>icon.icns</string>
    <key>CFBundleIdentifier</key>
    <string>com.lilamr.noteration</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>2.0.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
</dict>
</plist>
EOF
    # Refresh the icons cache if possible
    touch "$APP_DIR"
    echo -e "${GREEN}==>${NC} $APP_NAME.app created in ~/Applications and should appear in Launchpad with icon."
fi

echo -e "${GREEN}==>${NC} Noteration installed successfully!"
echo -e "${BLUE}==>${NC} You can run it with: ${GREEN}noteration${NC}"

# 6. Final Path Check and Config Update
SHELL_CONFIG=""
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    SHELL_CONFIG="$HOME/.bashrc"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    SHELL_CONFIG="$HOME/.zshrc"
fi

if [[ -n "$SHELL_CONFIG" && ":$PATH:" != *":$BIN_DIR:"* ]]; then
    [ ! -f "$SHELL_CONFIG" ] && touch "$SHELL_CONFIG"
    if ! grep -q "$BIN_DIR" "$SHELL_CONFIG"; then
        echo -e ""
        echo -e "${RED}Warning:${NC} $BIN_DIR is not in your PATH."
        echo -e "Adding it to $SHELL_CONFIG..."
        echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$SHELL_CONFIG"
        echo -e "Please run ${BLUE}source $SHELL_CONFIG${NC} or restart your terminal."
    fi
fi
