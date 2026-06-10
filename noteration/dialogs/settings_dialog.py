"""Provide the settings dialog for the Noteration application.

This module contains the `SettingsDialog` and its sub-tabs for configuring
various aspects of the application, such as the editor, PDF viewer, Papis,
sync settings, security, API, and appearance.
"""

from __future__ import annotations


from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QPushButton,
    QDialogButtonBox,
    QGroupBox,
    QFileDialog,
    QColorDialog,
    QFrame,
    QFontComboBox,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QColor

from noteration.config import NoterationConfig


class _Section(QGroupBox):
    """Represent a thin GroupBox used as a visual separator within a tab.
    """

    def __init__(self, title: str, parent=None) -> None:
        """Initialize the section group box."""
        super().__init__(title, parent)
        self.setStyleSheet(
            "QGroupBox { font-weight: 600; border: 0.5px solid palette(mid);"
            "border-radius: 6px; margin-top: 8px; padding-top: 6px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
        )


class _EditorTab(QWidget):
    """Represent the editor settings tab.
    """

    def __init__(self, config: NoterationConfig) -> None:
        """Initialize the editor settings tab."""
        super().__init__()
        self._config = config
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        # Font
        font_grp = _Section("Editor Font")
        fl = QFormLayout(font_grp)
        fl.setSpacing(8)

        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentFont(QFont(config.get("editor", "font_family", "Consolas")))
        fl.addRow("Font:", self._font_combo)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 32)
        self._font_size.setValue(int(config.get("editor", "font_size", 12)))
        fl.addRow("Size:", self._font_size)

        self._tab_width = QSpinBox()
        self._tab_width.setRange(1, 8)
        self._tab_width.setValue(int(config.get("editor", "tab_width", 2)))
        fl.addRow("Tab width:", self._tab_width)

        lay.addWidget(font_grp)

        # Behavior
        behav_grp = _Section("Behavior")
        bl = QFormLayout(behav_grp)
        bl.setSpacing(8)

        self._line_numbers = QCheckBox("Show line numbers")
        self._line_numbers.setChecked(bool(config.get("editor", "show_line_numbers", True)))
        bl.addRow(self._line_numbers)

        self._auto_indent = QCheckBox("Auto indent")
        self._auto_indent.setChecked(bool(config.get("editor", "auto_indent", True)))
        bl.addRow(self._auto_indent)

        self._autosave = QCheckBox("Auto save")
        self._autosave.setChecked(bool(config.get("general", "autosave", True)))
        bl.addRow(self._autosave)

        self._autosave_interval = QSpinBox()
        self._autosave_interval.setRange(5, 600)
        self._autosave_interval.setSuffix(" seconds")
        self._autosave_interval.setValue(int(config.get("general", "autosave_interval", 30)))
        bl.addRow("Autosave interval:", self._autosave_interval)

        lay.addWidget(behav_grp)
        lay.addStretch()

    def apply(self) -> None:
        """Apply editor settings to the configuration."""
        self._config.set("editor", "font_family", self._font_combo.currentFont().family())
        self._config.set("editor", "font_size", self._font_size.value())
        self._config.set("editor", "tab_width", self._tab_width.value())
        self._config.set("editor", "show_line_numbers", self._line_numbers.isChecked())
        self._config.set("editor", "auto_indent", self._auto_indent.isChecked())
        self._config.set("general", "autosave", self._autosave.isChecked())
        self._config.set("general", "autosave_interval", self._autosave_interval.value())


class _PdfTab(QWidget):
    """Represent the PDF viewer settings tab.
    """

    def __init__(self, config: NoterationConfig) -> None:
        """Initialize the PDF settings tab."""
        super().__init__()
        self._config = config
        self._hl_color = config.get("pdf", "default_highlight_color", "#FFEB3B")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        grp = _Section("PDF Viewer")
        fl = QFormLayout(grp)
        fl.setSpacing(8)

        self._renderer = QComboBox()
        self._renderer.addItems(["qtpdf", "pymupdf"])
        renderer = config.get("pdf", "renderer", "qtpdf")
        self._renderer.setCurrentText(renderer)
        fl.addRow("Renderer:", self._renderer)

        # Highlight color picker
        hl_row = QHBoxLayout()
        self._hl_btn = QPushButton()
        self._hl_btn.setFixedSize(28, 28)
        self._hl_btn.clicked.connect(self._pick_color)
        self._update_hl_btn()
        hl_row.addWidget(self._hl_btn)
        hl_row.addWidget(QLabel(self._hl_color))
        self._hl_label = hl_row.itemAt(1).widget()  # type: ignore[union-attr]
        hl_row.addStretch()
        fl.addRow("Highlight color:", hl_row)

        lay.addWidget(grp)
        lay.addStretch()

    def _pick_color(self) -> None:
        """Open a color dialog to pick a highlight color."""
        color = QColorDialog.getColor(QColor(self._hl_color), self, "Select Highlight Color")
        if color.isValid():
            self._hl_color = color.name()
            self._update_hl_btn()
            if self._hl_label:
                self._hl_label.setText(self._hl_color)  # type: ignore[union-attr]

    def _update_hl_btn(self) -> None:
        """Update the appearance of the color picker button."""
        self._hl_btn.setStyleSheet(
            f"background:{self._hl_color};border:1px solid #999;border-radius:3px;"
        )

    def apply(self) -> None:
        """Apply PDF settings to the configuration."""
        self._config.set("pdf", "renderer", self._renderer.currentText())
        self._config.set("pdf", "default_highlight_color", self._hl_color)


class _PapisTab(QWidget):
    """Represent the Papis library settings tab.
    """

    def __init__(self, config: NoterationConfig) -> None:
        """Initialize the Papis settings tab."""
        super().__init__()
        self._config = config

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        grp = _Section("Papis Library")
        fl = QFormLayout(grp)
        fl.setSpacing(8)

        path_row = QHBoxLayout()
        self._lib_path = QLineEdit(str(config.papis_library))
        path_row.addWidget(self._lib_path)
        btn_browse = QPushButton("…")
        btn_browse.setFixedWidth(28)
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(btn_browse)
        fl.addRow("Library path:", path_row)

        info = QLabel(
            "Path to the Papis library directory.\n"
            "Each sub-folder contains info.yaml and PDF files."
        )
        info.setStyleSheet("color: gray; font-size: 11px;")
        info.setWordWrap(True)
        fl.addRow(info)

        # CSL Style
        fl.addRow(QLabel(""))  # Spacer
        self._csl_style = QComboBox()
        # Common academic styles
        styles = [
            ("apa", "APA (7th edition)"),
            ("ieee", "IEEE"),
            ("modern-language-association", "MLA (9th edition)"),
            ("chicago-author-date", "Chicago (Author-Date)"),
            ("nature", "Nature"),
            ("science", "Science"),
            ("elsevier-with-titles", "Elsevier"),
        ]
        for val, label in styles:
            self._csl_style.addItem(label, val)

        current_style = config.get("literature", "citation_style", "apa")
        idx = self._csl_style.findData(current_style)
        if idx >= 0:
            self._csl_style.setCurrentIndex(idx)

        fl.addRow("Citation style:", self._csl_style)

        lay.addWidget(grp)
        lay.addStretch()

    def _browse(self) -> None:
        """Open a directory browser dialog to select the Papis library."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Papis Library Directory", str(self._config.papis_library)
        )
        if path:
            self._lib_path.setText(path)

    def apply(self) -> None:
        """Apply Papis settings to the configuration."""
        self._config.set("papis", "library_path", self._lib_path.text().strip())
        self._config.set("literature", "citation_style", self._csl_style.currentData())


class _SyncTab(QWidget):
    """Represent the Git synchronization settings tab.
    """

    def __init__(self, config: NoterationConfig) -> None:
        """Initialize the synchronization settings tab."""
        super().__init__()
        self._config = config

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        grp = _Section("Git Synchronization")
        fl = QFormLayout(grp)
        fl.setSpacing(8)

        self._remote = QLineEdit(config.get("sync", "remote", "origin"))
        fl.addRow("Remote:", self._remote)

        self._branch = QLineEdit(config.get("sync", "branch", ""))
        fl.addRow("Branch:", self._branch)

        self._strategy = QComboBox()
        self._strategy.addItems(["rebase", "merge", "stash"])
        self._strategy.setCurrentText(config.get("sync", "strategy", "rebase"))
        fl.addRow("Pull strategy:", self._strategy)

        lay.addWidget(grp)

        tip = QLabel(
            "💡 Tip: Use SSH keys or a GitHub personal access token\n"
            "for synchronization without password prompts."
        )
        tip.setStyleSheet(
            "background:#E8F5E9;border:0.5px solid #A5D6A7;"
            "border-radius:4px;padding:8px;color:#2E7D32;font-size:11px;"
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)
        lay.addStretch()

    def apply(self) -> None:
        """Apply synchronization settings to the configuration."""
        self._config.set("sync", "remote", self._remote.text().strip())
        self._branch_text = self._branch.text().strip()
        self._config.set("sync", "branch", self._branch_text)
        self._config.set("sync", "strategy", self._strategy.currentText())


class _UITab(QWidget):
    """Represent the user interface settings tab.
    """

    theme_preview_requested = Signal(str)

    def __init__(self, config: NoterationConfig) -> None:
        """Initialize the UI settings tab."""
        super().__init__()
        self._config = config

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        # Theme
        theme_grp = _Section("Appearance Theme")
        tl = QFormLayout(theme_grp)
        tl.setSpacing(8)

        self._theme = QComboBox()
        self._theme.addItems(["system", "light", "dark"])
        self._theme.setCurrentText(config.get("ui", "theme", "system"))
        self._theme.currentTextChanged.connect(lambda t: self.theme_preview_requested.emit(t))
        tl.addRow("Theme:", self._theme)

        # Preview swatches
        swatch_row = QHBoxLayout()
        for label, colors in [
            ("Light", ["#F5F5F5", "#1A1A1A", "#1565C0"]),
            ("Dark", ["#1E1E1E", "#E0E0E0", "#1976D2"]),
        ]:
            sw = QFrame()
            sw.setFixedSize(64, 36)
            sw.setStyleSheet(f"background:{colors[0]};border:1px solid #999;border-radius:4px;")
            sw_lay = QHBoxLayout(sw)
            sw_lay.setContentsMargins(4, 4, 4, 4)
            for c in colors[1:]:
                dot = QFrame()
                dot.setFixedSize(10, 10)
                dot.setStyleSheet(f"background:{c};border-radius:5px;border:none;")
                sw_lay.addWidget(dot)
            swatch_row.addWidget(QLabel(label))
            swatch_row.addWidget(sw)
        swatch_row.addStretch()
        tl.addRow("Preview:", swatch_row)

        lay.addWidget(theme_grp)

        # Layout
        layout_grp = _Section("Layout")
        ll = QFormLayout(layout_grp)
        ll.setSpacing(8)

        self._sidebar_visible = QCheckBox("Show sidebar on startup")
        self._sidebar_visible.setChecked(bool(config.get("ui", "sidebar_visible", True)))
        ll.addRow(self._sidebar_visible)

        lay.addWidget(layout_grp)
        lay.addStretch()

    def apply(self) -> None:
        """Apply UI settings to the configuration."""
        self._config.set("ui", "theme", self._theme.currentText())
        self._config.set("ui", "sidebar_visible", self._sidebar_visible.isChecked())

    @property
    def selected_theme(self) -> str:
        """Return the currently selected theme."""
        return self._theme.currentText()


class _SecurityTab(QWidget):
    """Represent the security settings tab.
    """

    decrypt_requested = Signal()

    def __init__(self, config: NoterationConfig) -> None:
        """Initialize the security settings tab."""
        super().__init__()
        self._config = config
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        grp = _Section("Encryption")
        fl = QFormLayout(grp)
        fl.setSpacing(12)

        is_enc = config.get("security", "encryption_enabled", False)

        status_label = QLabel(
            "Vault is currently ENCRYPTED" if is_enc else "Vault is NOT encrypted"
        )
        status_label.setStyleSheet(
            "font-weight: bold; color: #2E7D32;"
            if not is_enc
            else "font-weight: bold; color: #C62828;"
        )
        fl.addRow("Status:", status_label)

        if is_enc:
            self._decrypt_btn = QPushButton("Permanently Decrypt Vault")
            self._decrypt_btn.setStyleSheet(
                "background-color: #C62828; color: white; padding: 8px;"
            )
            self._decrypt_btn.clicked.connect(self.decrypt_requested)

            warning = QLabel(
                "⚠️ Warning: This will permanently remove encryption from all files in this vault.\n"
                "After decryption, anyone with access to your computer can read your notes and PDFs."
            )
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #C62828; font-size: 11px;")

            fl.addRow(self._decrypt_btn)
            fl.addRow(warning)
        else:
            info = QLabel(
                "To enable encryption, please use the 'New Vault' or 'Import Vault' wizard.\n"
                "Note: Enabling encryption on an existing plaintext vault is not yet supported via settings."
            )
            info.setWordWrap(True)
            info.setStyleSheet("color: gray; font-size: 11px;")
            fl.addRow(info)

        lay.addWidget(grp)
        lay.addStretch()


class _ApiTab(QWidget):
    """Represent the REST API settings tab.
    """

    def __init__(self, config: NoterationConfig) -> None:
        """Initialize the API settings tab."""
        super().__init__()
        self._config = config
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        grp = _Section("REST API Server")
        fl = QFormLayout(grp)
        fl.setSpacing(8)

        self._enabled = QCheckBox("Enable API Server on startup")
        self._enabled.setChecked(bool(config.get("api", "enabled", False)))
        fl.addRow(self._enabled)

        self._host = QLineEdit(config.get("api", "host", "127.0.0.1"))
        fl.addRow("Host:", self._host)

        self._port = QSpinBox()
        self._port.setRange(1024, 65535)
        self._port.setValue(int(config.get("api", "port", 8765)))
        fl.addRow("Port:", self._port)

        self._api_key = QLineEdit(config.get("api", "api_key", ""))
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)

        btn_toggle = QPushButton("👁")
        btn_toggle.setFixedWidth(28)
        btn_toggle.setCheckable(True)
        btn_toggle.toggled.connect(self._toggle_visibility)

        key_layout = QHBoxLayout()
        key_layout.addWidget(self._api_key)
        key_layout.addWidget(btn_toggle)
        fl.addRow("API Key:", key_layout)

        btn_gen = QPushButton("Generate Random Key")
        btn_gen.clicked.connect(self._generate_key)
        fl.addRow("", btn_gen)

        lay.addWidget(grp)

        info = QLabel(
            "The API allows external tools to access your vault.\n"
            "By default, it is restricted to 127.0.0.1 (local access only)."
        )
        info.setStyleSheet("color: gray; font-size: 11px;")
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addStretch()

    def _generate_key(self) -> None:
        """Generate a random API key."""
        import secrets

        self._api_key.setText(secrets.token_urlsafe(32))

    def _toggle_visibility(self, checked: bool) -> None:
        """Toggle the visibility of the API key."""
        if checked:
            self._api_key.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self._api_key.setEchoMode(QLineEdit.EchoMode.Password)

    def apply(self) -> None:
        """Apply API settings to the configuration."""
        self._config.set("api", "enabled", self._enabled.isChecked())
        self._config.set("api", "host", self._host.text().strip())
        self._config.set("api", "port", self._port.value())
        self._config.set("api", "api_key", self._api_key.text().strip())


class SettingsDialog(QDialog):
    """Display the main settings dialog containing all configuration tabs.

    Emits `settings_applied` signal when OK is pressed.
    """

    settings_applied = Signal()
    theme_changed = Signal(str)  # for live preview
    decrypt_requested = Signal()

    def __init__(self, config: NoterationConfig, parent=None) -> None:
        """Initialize the settings dialog."""
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Noteration Settings")
        self.resize(560, 480)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI for the settings dialog."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._editor_tab = _EditorTab(self._config)
        self._pdf_tab = _PdfTab(self._config)
        self._papis_tab = _PapisTab(self._config)
        self._sync_tab = _SyncTab(self._config)
        self._ui_tab = _UITab(self._config)
        self._security_tab = _SecurityTab(self._config)
        self._api_tab = _ApiTab(self._config)

        self._ui_tab.theme_preview_requested.connect(self.theme_changed)
        self._security_tab.decrypt_requested.connect(self.decrypt_requested)

        self._tabs.addTab(self._editor_tab, "✏  Editor")
        self._tabs.addTab(self._pdf_tab, "📄  PDF")
        self._tabs.addTab(self._papis_tab, "📚  Papis")
        self._tabs.addTab(self._sync_tab, "☁  Sync")
        self._tabs.addTab(self._security_tab, "🔒  Security")
        self._tabs.addTab(self._api_tab, "🌐  API")
        self._tabs.addTab(self._ui_tab, "🎨  Appearance")
        root.addWidget(self._tabs)

        # Separator + buttons
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: palette(mid);")
        root.addWidget(sep)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        btn_box.setContentsMargins(12, 8, 12, 12)
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        btn_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_all)
        root.addWidget(btn_box)

    def _apply_all(self) -> None:
        """Apply all tab settings to the configuration."""
        for tab in [
            self._editor_tab,
            self._pdf_tab,
            self._papis_tab,
            self._sync_tab,
            self._api_tab,
            self._ui_tab,
        ]:
            if hasattr(tab, "apply"):
                tab.apply()
        self._config.save()
        self.settings_applied.emit()

    def _on_ok(self) -> None:
        """Apply settings and accept the dialog."""
        self._apply_all()
        self.accept()

    @property
    def selected_theme(self) -> str:
        """Return the currently selected theme."""
        return self._ui_tab.selected_theme
