<p align="center">
  <img src="noteration/assets/icon_256.png" width="96" alt="Noteration icon"/>
</p>

<h1 align="center">Noteration: Note-Literature-Synchronization</h1>

<p align="center">
  <strong>Research Literature Note-Taking App</strong><br>
  Markdown editor · PDF viewer · Papis · GitHub sync
</p>

<p align="center">
  <a href="https://github.com/lilamr/noteration/releases/tag/v1.2.0"><img src="https://img.shields.io/github/v/release/lilamr/noteration?label=version&color=4CAF50" alt="Release"/></a>
  <a href="https://github.com/lilamr/noteration/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License"/></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python"/></a>
  <a href="https://github.com/lilamr/noteration/actions"><img src="https://img.shields.io/github/actions/workflow/status/lilamr/noteration/ci.yml?label=CI" alt="CI"/></a>
</p>

---

## About

Noteration is a desktop application for managing literature notes in an integrated way. It combines all the tools you need in a single interface:

```
noteration/
├── 📄  Markdown notes with [[wiki-link]] and @citation
├── 📘  Integrated PDF viewer with non-destructive annotations
├── 📚  Literature browser via Papis
├── 🔍  Global vault search
├── 🕸️  Interactive backlink graph between notes
└── ☁️  Synchronization via GitHub
```

---

## Key Features

| Feature | Description |
|-------|------------|
| **Markdown Editor** | Syntax highlighting, line numbers, view/edit modes, auto-indent |
| **Focus Mode** | Distraction-free writing with Vim keybindings and centered layout |
| **Wiki-link** | `[[note-name]]` with `Ctrl+Click` navigation and autocomplete |
| **Citation** | `@citation-key` with autocomplete from Papis library |
| **Global Search** | Search across all notes, literature, and PDF annotations simultaneously |
| **PDF Viewer** | Render via QtPDF or PyMuPDF, highlight & JSON annotations |
| **Backlink Graph** | Visualization of note network, interactive |
| **Papis Bridge** | Browse, import, and export BibTeX from Papis library |
| **Git Sync** | Manual commit, pull, push; visual conflict resolution |
| **Dark Mode** | Light / Dark / System — automatically follows OS theme |

---

## Installation

Choose the quickest way to get Noteration running on your system.

### 🐧 Linux & 🍎 macOS (One-liner)

Open your terminal and run:
```bash
curl -fsSL https://raw.githubusercontent.com/lilamr/noteration/main/install.sh | bash
```
*On macOS, this will create a **Noteration.app** in your Applications folder and add it to your Launchpad.*

### 🪟 Windows (One-liner)

Open PowerShell and run:
```powershell
irm https://raw.githubusercontent.com/lilamr/noteration/main/install.ps1 | iex
```
*This will create a desktop shortcut and a Start Menu entry for easy access.*

---

### Manual Installation (Development)

If you want to contribute or prefer manual setup:

#### 1. Prerequisites
- Python 3.11 or higher
- Git

#### 2. Clone and Setup
```bash
git clone https://github.com/lilamr/noteration.git
cd noteration

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate

# Install with all features
pip install -e ".[all]"
```

#### 3. Optional Dependencies
| Feature | Command |
|-------|----------|
| Papis literature management | `pip install -e ".[papis]"` |
| PyMuPDF PDF renderer | `pip install -e ".[pymupdf]"` |
| Fuzzy search | `pip install -e ".[search]"` |
| Backlink graph (NetworkX) | `pip install -e ".[graph]"` |
| File watcher (live reload) | `pip install -e ".[watch]"` |
| Markdown preview | `pip install -e ".[markdown]"` |


---

## Running the Application

```bash
# Via entry point (after pip install -e .)
noteration

# Or directly as a module
python -m noteration
```

On first run, a **Select Vault** dialog will appear to choose or create a new research vault.

---

## Uninstallation

If you need to remove Noteration, follow the steps for your operating system:

### 🐧 Linux
```bash
# Remove installation directory and venv
rm -rf ~/.local/share/noteration

# Remove wrapper script
rm ~/.local/bin/noteration

# Remove desktop entry and icon
rm ~/.local/share/applications/noteration.desktop
rm ~/.local/share/icons/noteration.png
```

### 🍎 macOS
```bash
# Remove App Bundle
rm -rf ~/Applications/Noteration.app

# Remove installation directory and binary
rm -rf ~/.local/share/noteration
rm ~/.local/bin/noteration
```

### 🪟 Windows (PowerShell)
```powershell
# Remove installation directory
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\noteration"

# Remove shortcuts
Remove-Item "$env:USERPROFILE\Desktop\Noteration.lnk" -ErrorAction SilentlyContinue
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Noteration.lnk" -ErrorAction SilentlyContinue
```

> [!NOTE]
> These steps remove the application itself. Your **Vault data** (notes, literature, annotations and config) is stored separately and will not be deleted.

---

## Vault Structure

```
~/noteration-vault/
├── .noteration/
│   ├── config.toml          # Main configuration
│   ├── db.sqlite            # Cache & link graph
│   └── link_graph.json      # Backlink graph (JSON)
├── notes/                   # Markdown files
│   ├── index.md
│   └── research-topic.md
├── literature/              # Managed by Papis
├── annotations/             # PDF annotations (JSON, synced via Git)
└── attachments/             # Images and attachments
```

> [!TIP]
> **Git Synchronization:** Noteration automatically ignores large binary files (PDFs) and internal caches (`db.sqlite`, `link_graph.json`) to prevent merge conflicts and repository bloat. Only your notes, metadata, and annotations are synchronized.

---

## Configuration (`config.toml`)

```toml
[general]
autosave          = true
autosave_interval = 30           # seconds

[editor]
tab_width         = 2
font_family       = "Consolas"
font_size         = 12
show_line_numbers = true
auto_indent       = true

[pdf]
renderer              = "qtpdf"   # or "pymupdf"
default_highlight_color = "#FFEB3B"

[papis]
library_path = "~/noteration/literature"

[sync]
remote        = "origin"
branch        = ""               # empty = auto-detect active branch

[ui]
theme           = "system"       # dark / light / system
sidebar_visible = true
```

---

## Project Structure

```
noteration/ (repository root)
├── noteration/ (package)
│   ├── assets/              # Icons and static assets
│   ├── docs/                # User guides and documentation
│   ├── app.py               # Bootstrap & QApplication
│   ├── config.py            # TOML Configuration
│   ├── db/                  # Link graph & layout engine
│   ├── dialogs/             # Dialogs (vault, note, settings, conflict)
│   ├── editor/              # Find/Replace, syntax highlight, wiki-link
│   ├── literature/          # Papis bridge & BibTeX export
│   ├── pdf/                 # PDF reader & annotations
│   ├── search/              # Global vault search
│   ├── sync/                # Git engine
│   └── ui/                  # Main window, tabs, sidebar, graph
├── tests/                   # Pytest test suite
└── pyproject.toml
```

---

## Contribution

Contributions are welcome! Check [Issues](https://github.com/lilamr/noteration/issues) for a list of things to work on, or open a new issue to report a bug or suggest a feature.

```bash
# Setup development environment
pip install -e ".[all,dev]"

# Run tests
pytest -v
mypy .

# Linting
ruff check .
```

---

## Author

Created by **[lilamr](https://github.com/lilamr)**. 

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/R6R11Z1NDP)

---

## License

[MIT License](LICENSE) — free to use, modify, and distribute.

---

<p align="center">
  Built with PySide6 · PyMuPDF · GitPython · NetworkX · Papis
</p>
