"""
Settings dialog with tabs for editor, PDF, Papis, sync, and appearance.
"""

from __future__ import annotations


from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QLabel, QLineEdit, QSpinBox, QCheckBox,
    QComboBox, QPushButton, QDialogButtonBox, QGroupBox,
    QFileDialog, QColorDialog, QFrame, QFontComboBox,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QColor

from noteration.config import NoterationConfig


class _Section(QGroupBox):
    """Thin GroupBox as a visual separator within a tab."""
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(title, parent)
        self.setStyleSheet(
            "QGroupBox { font-weight: 600; border: 0.5px solid palette(mid);"
            "border-radius: 6px; margin-top: 8px; padding-top: 6px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
        )


class _EditorTab(QWidget):
    def __init__(self, config: NoterationConfig) -> None:
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
        self._font_combo.setCurrentFont(
            QFont(config.get("editor", "font_family", "Consolas")))
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
        self._line_numbers.setChecked(
            bool(config.get("editor", "show_line_numbers", True)))
        bl.addRow(self._line_numbers)

        self._auto_indent = QCheckBox("Auto indent")
        self._auto_indent.setChecked(
            bool(config.get("editor", "auto_indent", True)))
        bl.addRow(self._auto_indent)

        self._autosave = QCheckBox("Auto save")
        self._autosave.setChecked(
            bool(config.get("general", "autosave", True)))
        bl.addRow(self._autosave)

        self._autosave_interval = QSpinBox()
        self._autosave_interval.setRange(5, 600)
        self._autosave_interval.setSuffix(" seconds")
        self._autosave_interval.setValue(
            int(config.get("general", "autosave_interval", 30)))
        bl.addRow("Autosave interval:", self._autosave_interval)

        lay.addWidget(behav_grp)
        lay.addStretch()

    def apply(self) -> None:
        self._config.set("editor", "font_family",
                         self._font_combo.currentFont().family())
        self._config.set("editor", "font_size",    self._font_size.value())
        self._config.set("editor", "tab_width",    self._tab_width.value())
        self._config.set("editor", "show_line_numbers",
                         self._line_numbers.isChecked())
        self._config.set("editor", "auto_indent",  self._auto_indent.isChecked())
        self._config.set("general", "autosave",    self._autosave.isChecked())
        self._config.set("general", "autosave_interval",
                         self._autosave_interval.value())


class _PdfTab(QWidget):
    def __init__(self, config: NoterationConfig) -> None:
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
        color = QColorDialog.getColor(QColor(self._hl_color), self, "Select Highlight Color")
        if color.isValid():
            self._hl_color = color.name()
            self._update_hl_btn()
            if self._hl_label:
                self._hl_label.setText(self._hl_color)  # type: ignore[union-attr]

    def _update_hl_btn(self) -> None:
        self._hl_btn.setStyleSheet(
            f"background:{self._hl_color};border:1px solid #999;border-radius:3px;")

    def apply(self) -> None:
        self._config.set("pdf", "renderer", self._renderer.currentText())
        self._config.set("pdf", "default_highlight_color", self._hl_color)


class _PapisTab(QWidget):
    def __init__(self, config: NoterationConfig) -> None:
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

        lay.addWidget(grp)
        lay.addStretch()

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Papis Library Directory",
            str(self._config.papis_library))
        if path:
            self._lib_path.setText(path)

    def apply(self) -> None:
        self._config.set("papis", "library_path", self._lib_path.text().strip())


class _SyncTab(QWidget):
    def __init__(self, config: NoterationConfig) -> None:
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
            "border-radius:4px;padding:8px;color:#2E7D32;font-size:11px;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        lay.addStretch()

    def apply(self) -> None:
        self._config.set("sync", "remote",        self._remote.text().strip())
        self._branch_text = self._branch.text().strip()
        self._config.set("sync", "branch",        self._branch_text)
        self._config.set("sync", "strategy",      self._strategy.currentText())


class _UITab(QWidget):
    theme_preview_requested = Signal(str)

    def __init__(self, config: NoterationConfig) -> None:
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
        self._theme.currentTextChanged.connect(
            lambda t: self.theme_preview_requested.emit(t))
        tl.addRow("Theme:", self._theme)

        # Preview swatches
        swatch_row = QHBoxLayout()
        for label, colors in [
            ("Light", ["#F5F5F5", "#1A1A1A", "#1565C0"]),
            ("Dark",  ["#1E1E1E", "#E0E0E0", "#1976D2"]),
        ]:
            sw = QFrame()
            sw.setFixedSize(64, 36)
            sw.setStyleSheet(
                f"background:{colors[0]};border:1px solid #999;border-radius:4px;")
            sw_lay = QHBoxLayout(sw)
            sw_lay.setContentsMargins(4, 4, 4, 4)
            for c in colors[1:]:
                dot = QFrame()
                dot.setFixedSize(10, 10)
                dot.setStyleSheet(
                    f"background:{c};border-radius:5px;border:none;")
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
        self._sidebar_visible.setChecked(
            bool(config.get("ui", "sidebar_visible", True)))
        ll.addRow(self._sidebar_visible)

        lay.addWidget(layout_grp)
        lay.addStretch()

    def apply(self) -> None:
        self._config.set("ui", "theme",           self._theme.currentText())
        self._config.set("ui", "sidebar_visible",
                         self._sidebar_visible.isChecked())

    @property
    def selected_theme(self) -> str:
        return self._theme.currentText()


class SettingsDialog(QDialog):
    """
    Complete settings dialog.
    Emits settings_applied when OK is pressed.
    """

    settings_applied = Signal()
    theme_changed    = Signal(str)   # for live preview

    def __init__(self, config: NoterationConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Noteration Settings")
        self.resize(560, 480)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._editor_tab = _EditorTab(self._config)
        self._pdf_tab    = _PdfTab(self._config)
        self._papis_tab  = _PapisTab(self._config)
        self._sync_tab   = _SyncTab(self._config)
        self._ui_tab     = _UITab(self._config)

        self._ui_tab.theme_preview_requested.connect(self.theme_changed)

        self._tabs.addTab(self._editor_tab, "✏  Editor")
        self._tabs.addTab(self._pdf_tab,    "📄  PDF")
        self._tabs.addTab(self._papis_tab,  "📚  Papis")
        self._tabs.addTab(self._sync_tab,   "☁  Sync")
        self._tabs.addTab(self._ui_tab,     "🎨  Appearance")
        root.addWidget(self._tabs)

        # Separator + buttons
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: palette(mid);")
        root.addWidget(sep)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        btn_box.setContentsMargins(12, 8, 12, 12)
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        btn_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply_all)
        root.addWidget(btn_box)

    def _apply_all(self) -> None:
        for tab in [
            self._editor_tab, self._pdf_tab,
            self._papis_tab, self._sync_tab, self._ui_tab,
        ]:
            if hasattr(tab, 'apply'):
                tab.apply()
        self._config.save()
        self.settings_applied.emit()

    def _on_ok(self) -> None:
        self._apply_all()
        self.accept()

    @property
    def selected_theme(self) -> str:
        return self._ui_tab.selected_theme
