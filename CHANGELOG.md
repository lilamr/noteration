# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
