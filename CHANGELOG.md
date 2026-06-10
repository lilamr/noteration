# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-06-03

### Added
- **Command Line Interface (ntr)**: A robust CLI for vault management, full-text search, note creation/deletion, literature management (DOI/arXiv fetching), graph analysis, and synchronization.
- **REST API (ntr-api)**: A FastAPI-based HTTP interface allowing external tools to interact with the vault (CRUD notes, search, stats).
- **API Security**: Implemented API Key authentication for the REST API.
- **GUI API Control**: Added a new "API" tab in Settings to manage the server lifecycle, port, and authentication keys directly from the GUI.
- **Advanced CLI Export**: Integrated Pandoc-based document export directly into the CLI (`ntr export`).
- **New User Guides**: Added comprehensive `user_guide_cli.md` and `user_guide_api.md` in the `docs/` folder.
- **Architectural Decoupling**: Refactored the core logic into `VaultCore` (Pure Python), separating business rules from the PySide6 GUI.
- **SQLite FTS5 Search**: Replaced regex-based search with a high-performance Full-Text Search engine using SQLite FTS5.
- **Tags System**: Implemented a first-class `#tag` system with automatic extraction from Markdown and a dedicated "Tags" sidebar panel.
- **Navigation History**: Added support for `Alt+Left` (Back) and `Alt+Right` (Forward) navigation between recently opened notes.
- **Robust LaTeX Rendering**: Integrated `pymdownx.arithmatex` for reliable math rendering, preserving complex formulas and double backslashes.
- **Advanced Markdown Features**: Enabled tasklists, highlights, strikethrough, and superscript extensions.
- **Smart Re-encryption**: Optimized synchronization for encrypted vaults to prevent unnecessary Git modifications by only re-encrypting modified files.
- **Thread Safety**: Improved shutdown logic in background controllers to resolve application crashes on exit.
- **Encrypted Vault Indexing**: Resolved PDF indexing issues in encrypted vaults by ensuring correct path initialization for the literature bridge.
- **Transparent Vault Encryption**: Implemented "at-rest" encryption using the **age** format, natively integrated for seamless security, including a session-based secure decryption workflow and the ability to permanently disable encryption.
- **CSL Style Selection**: Added the ability to choose citation styles (APA, IEEE, MLA, etc.) directly in the Settings dialog.
- **Document Export Integration**: Unified document export menus in the File menu and Preview context menu.
- **Split View**: Implemented vertical split view in the main window, allowing side-by-side editing and reading. Use the tab context menu to move tabs between panes.
- **PDF Annotation Toggle**: Added a dedicated button and shortcut (`Ctrl+Alt+A`) to show/hide the annotation panel for a cleaner reading experience.
- **Detailed Sync Logs**: The Synchronization tab now lists specific changed and untracked files in its log.

## [1.2.0] - 2026-05-16

### Added
- **Thread Safety**: Implemented global `RLock` across all data engines (`LinkGraph`, `PdfIndex`, `AnnotationStore`, `NoterationConfig`) to prevent race conditions during background operations.
- **Data Integrity**: Added Atomic Write pattern ("Write-to-Temp-then-Rename") for all JSON and TOML storage to prevent file corruption.
- **Advanced Memory Management**: Replaced static PDF caching with a Cost-Based LRU Cache (250MB limit), automatically managing RAM usage for high-resolution renders.
- **Robust Shutdown**: Improved shutdown orchestration with a blocking wait mechanism and early-exit support for long-running background tasks.
- **Structured Logging**: Enhanced observability with detailed tracebacks in logs and visual error notifications in the UI status bar and dialogs.

### Changed
- **Architecture**: Decoupled `VaultManager` into specialized controllers (`IndexController`, `SyncController`, `LibraryController`) for better maintainability.
- **Papis Integration**: Standardized the Papis interface to use direct YAML parsing for reads and a robust CLI wrapper for writes, removing unstable Python API dependencies.
- **PDF Viewer**: Explicit resource release on tab closure to prevent file handle leaks.

## [1.1.2] - 2026-05-10

### Fixed
- **Stability**: Fixed a critical crash caused by premature destruction of background threads (`QThread`) using robust validity checks and explicit reference clearing.
- **Git Sync**: Resolved a Segmentation Fault when handling large conflict files by implementing a memory safety limit (128KB) for file previews.
- **Git Sync**: Fixed an infinite rebase loop on `.noteration/*.log` files by implementing automatic conflict resolution for log files and better `.gitignore` enforcement.
- **Git Sync**: Automatically untracks accidentally committed log files and metadata from Git to maintain a clean vault state.
- **UI Performance**: Refactored the Sync tab to use non-blocking background status refreshes, preventing interface freezes during network operations.

### Added
- **Git Sync**: Enhanced status reporting with clear "Ahead" and "Behind" indicators and color-coded feedback for better visibility into remote changes.

### Removed
- Git auto-sync feature.

## [1.1.1] - 2026-05-06

### Fixed
- **Git Sync**: Resolved repository state detection issues after manual initialization.
- **Git Sync**: Improved robustness when syncing with new/empty remotes by automatically pushing local changes.
- **Git Sync**: Fixed branch mismatch by dynamically detecting and prioritizing the active local branch (e.g., `master`) over hardcoded defaults.
- **UI Performance**: Eliminated application lag by removing synchronous network calls from the status bar update logic.
- **Shortcuts**: Resolved "Ambiguous shortcut overload" warning for `Ctrl+N` and `Ctrl+S` by consolidating global actions.
- **UX**: New notes created from the sidebar now open automatically in the editor.
- **Git Status**: Refined status detection to correctly ignore internal metadata in the `.noteration/` folder.
- **Config**: Fixed a shared state bug where default settings could be accidentally modified across vault instances.

### Changed
- **Default Settings**: `Auto Sync` is now disabled by default to improve performance and give users more control over network activity.
- Updated documentation and example configurations to reflect new branch auto-detection and default settings.

## [1.1.0] - 2026-05-04

### Added
- **Focus Mode**: A distraction-free writing environment (F11) with:
    - Fullscreen view and hidden UI elements (MenuBar, StatusBar, Toolbar, Sidebars).
    - Centered editor with dynamic width (50% of the screen).
    - Integrated Vim keybindings (Normal, Insert, Visual mode).
    - Vim-style command field for saving (`:w`) and exiting (`:q`).
- **Research Briefing**: New "Research and Writing" help entry (F2) synthesizing academic writing strategies.
- **Global Shortcuts**: Enhanced `Ctrl+N` (New Note) and `Ctrl+S` (Save) to work globally, including in Focus Mode.

### Changed
- Refactored Help Dialog to be reusable for different documentation files.
- Version increment to v1.1.0.

## [1.0.0] - 2026-04-30

### Added
- **Markdown Editor**: Full-featured editor with syntax highlighting, line numbers, and auto-indent.
- **Wiki-links**: Support for `[[note-name]]` with `Ctrl+Click` navigation and autocompletion.
- **Citations**: Integration with Papis library for `@citation-key` autocompletion.
- **PDF Viewer**: Integrated PDF reader supporting both QtPDF and PyMuPDF backends.
- **Annotations**: Non-destructive, JSON-based PDF highlighting and annotations.
- **Papis Bridge**: Browser and management for research literature via Papis.
- **Git Engine**: Automated vault synchronization with remote repositories, including conflict resolution UI.
- **Backlink Graph**: Interactive visualization of relationships between notes using NetworkX.
- **Global Search**: Unified search across notes, literature metadata, and PDF annotations.
- **Vault Management**: Robust vault-centric architecture for portable knowledge bases.
- **Multi-platform Support**: Native installation scripts for Linux, macOS, and Windows.
- **Theming**: Support for Light, Dark, and System-adaptive themes.
- **Test Suite**: Comprehensive testing infrastructure using pytest and pytest-qt.

[1.0.0]: https://github.com/lilamr/noteration/releases/tag/v1.0.0
