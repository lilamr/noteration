#!/bin/bash

# Noteration One-Liner Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/lilamr/noteration/main/install.sh | bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO="lilamr/noteration"

echo -e "${BLUE}==>${NC} Installing Noteration..."

# ── OS check ────────────────────────────────────────────────
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo -e "${RED}Error:${NC} This script is for Linux/macOS. For Windows, please use install.ps1"
    exit 1
fi

# ── Python check ────────────────────────────────────────────
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error:${NC} python3 is not installed."
    exit 1
fi

if ! python3 -c 'import sys; exit(0) if sys.version_info >= (3, 11) else exit(1)'; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    echo -e "${RED}Error:${NC} Noteration requires Python 3.11+. Current version is $PYTHON_VERSION."
    exit 1
fi

if ! python3 -m venv --help &> /dev/null; then
    echo -e "${RED}Error:${NC} python3-venv is not installed."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo -e "On Ubuntu/Debian: ${BLUE}sudo apt install python3-venv${NC}"
    fi
    exit 1
fi

if ! command -v git &> /dev/null; then
    echo -e "${RED}Error:${NC} git is not installed. Please install git first."
    exit 1
fi

# ── Detect latest release tag from GitHub API ───────────────
echo -e "${BLUE}==>${NC} Checking latest release..."

if command -v curl &> /dev/null; then
    LATEST_TAG=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
        | grep '"tag_name"' \
        | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/')
elif command -v wget &> /dev/null; then
    LATEST_TAG=$(wget -qO- "https://api.github.com/repos/${REPO}/releases/latest" \
        | grep '"tag_name"' \
        | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/')
else
    echo -e "${RED}Error:${NC} curl or wget is required."
    exit 1
fi

# Fallback jika GitHub API gagal (rate limit, dll)
if [[ -z "$LATEST_TAG" ]]; then
    echo -e "${YELLOW}Warning:${NC} Could not detect latest release. Falling back to main branch."
    INSTALL_REF="main"
    VERSION="dev"
else
    INSTALL_REF="$LATEST_TAG"
    VERSION="${LATEST_TAG#v}"
    echo -e "${GREEN}==>${NC} Latest release: ${LATEST_TAG}"
fi

# ── Installation ────────────────────────────────────────────
INSTALL_DIR="$HOME/.local/share/noteration"
BIN_DIR="$HOME/.local/bin"
mkdir -p "$INSTALL_DIR" "$BIN_DIR"

echo -e "${BLUE}==>${NC} Creating virtual environment in $INSTALL_DIR..."
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"

echo -e "${BLUE}==>${NC} Installing Noteration ${VERSION}..."
pip install --upgrade pip --quiet
pip install "noteration[all] @ git+https://github.com/${REPO}.git @${INSTALL_REF}" --quiet

# Simpan versi yang terinstall untuk referensi
echo "$VERSION" > "$INSTALL_DIR/VERSION"

# ── Wrapper scripts ─────────────────────────────────────────
echo -e "${BLUE}==>${NC} Creating wrapper scripts in $BIN_DIR..."
for cmd in noteration ntr ntr-api; do
    cat <<EOF > "$BIN_DIR/$cmd"
#!/bin/bash
source "$INSTALL_DIR/venv/bin/activate"
exec $cmd "\$@"
EOF
    chmod +x "$BIN_DIR/$cmd"
done

# ── Desktop integration ─────────────────────────────────────
ICON_URL="https://raw.githubusercontent.com/${REPO}/main/noteration/assets/images"

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo -e "${BLUE}==>${NC} Creating Linux desktop entry..."
    DESKTOP_DIR="$HOME/.local/share/applications"
    ICON_DIR="$HOME/.local/share/icons"
    mkdir -p "$DESKTOP_DIR" "$ICON_DIR"

    curl -sSL "${ICON_URL}/icon_256.png" -o "$ICON_DIR/noteration.png"

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

    command -v update-desktop-database &> /dev/null && \
        update-desktop-database "$DESKTOP_DIR"

elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${BLUE}==>${NC} Creating macOS App Bundle..."
    APP_NAME="Noteration"
    APP_DIR="$HOME/Applications/$APP_NAME.app"
    MACOS_DIR="$APP_DIR/Contents/MacOS"
    RESOURCES_DIR="$APP_DIR/Contents/Resources"
    mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

    curl -sSL "${ICON_URL}/icon.icns" -o "$RESOURCES_DIR/icon.icns"

    cat <<EOF > "$MACOS_DIR/$APP_NAME"
#!/bin/bash
export PATH="$BIN_DIR:\$PATH"
exec "$BIN_DIR/noteration"
EOF
    chmod +x "$MACOS_DIR/$APP_NAME"

    # Versi dinamis dari tag, bukan hardcoded
    cat <<EOF > "$APP_DIR/Contents/Info.plist"
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
    <string>${VERSION}</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
</dict>
</plist>
EOF
    touch "$APP_DIR"
    # Remove quarantine attribute to avoid Gatekeeper issues for unsigned apps
    xattr -cr "$APP_DIR" 2>/dev/null || true
    echo -e "${GREEN}==>${NC} $APP_NAME.app created in ~/Applications."
fi

# ── PATH check ───────────────────────────────────────────────
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    SHELL_CONFIG="$HOME/.bashrc"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    SHELL_CONFIG="$HOME/.zshrc"
fi

if [[ -n "$SHELL_CONFIG" && ":$PATH:" != *":$BIN_DIR:"* ]]; then
    [ ! -f "$SHELL_CONFIG" ] && touch "$SHELL_CONFIG"
    if ! grep -q "$BIN_DIR" "$SHELL_CONFIG"; then
        echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$SHELL_CONFIG"
        echo -e "${YELLOW}==>${NC} Added $BIN_DIR to PATH in $SHELL_CONFIG"
        echo -e "    Run: ${BLUE}source $SHELL_CONFIG${NC} or restart your terminal."
    fi
fi

echo ""
echo -e "${GREEN}✓${NC} Noteration ${VERSION} installed successfully!"
echo -e "${BLUE}==>${NC} Run it with: ${GREEN}noteration${NC}"
