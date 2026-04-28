"""
noteration/ui/theme.py

Mesin tema untuk Phase 5:
  - ThemeMode: light | dark | system
  - apply_theme(app, mode): terapkan QPalette + stylesheet
  - get_effective_mode(): deteksi tema OS (Windows/macOS/Linux)
  - watch_system_theme(callback): notifikasi jika tema OS berubah
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt, QObject, Signal, QTimer


class ThemeMode(str, Enum):
    LIGHT  = "light"
    DARK   = "dark"
    SYSTEM = "system"


# ── Palette definitions ───────────────────────────────────────────────────

_LIGHT_COLORS = {
    QPalette.ColorRole.Window:          "#F5F5F5",
    QPalette.ColorRole.WindowText:      "#1A1A1A",
    QPalette.ColorRole.Base:            "#FFFFFF",
    QPalette.ColorRole.AlternateBase:   "#F0F0F0",
    QPalette.ColorRole.Text:            "#1A1A1A",
    QPalette.ColorRole.BrightText:      "#FFFFFF",
    QPalette.ColorRole.Button:          "#E8E8E8",
    QPalette.ColorRole.ButtonText:      "#1A1A1A",
    QPalette.ColorRole.Highlight:       "#1565C0",
    QPalette.ColorRole.HighlightedText: "#FFFFFF",
    QPalette.ColorRole.Link:            "#185FA5",
    QPalette.ColorRole.Mid:             "#C8C8C8",
    QPalette.ColorRole.Midlight:        "#DCDCDC",
    QPalette.ColorRole.Dark:            "#AAAAAA",
    QPalette.ColorRole.Shadow:          "#888888",
    QPalette.ColorRole.ToolTipBase:     "#FFFDE7",
    QPalette.ColorRole.ToolTipText:     "#1A1A1A",
    QPalette.ColorRole.PlaceholderText: "#9E9E9E",
}

_DARK_COLORS = {
    QPalette.ColorRole.Window:          "#1E1E1E",
    QPalette.ColorRole.WindowText:      "#E0E0E0",
    QPalette.ColorRole.Base:            "#252525",
    QPalette.ColorRole.AlternateBase:   "#2C2C2C",
    QPalette.ColorRole.Text:            "#E0E0E0",
    QPalette.ColorRole.BrightText:      "#FFFFFF",
    QPalette.ColorRole.Button:          "#2D2D2D",
    QPalette.ColorRole.ButtonText:      "#E0E0E0",
    QPalette.ColorRole.Highlight:       "#1976D2",
    QPalette.ColorRole.HighlightedText: "#FFFFFF",
    QPalette.ColorRole.Link:            "#64B5F6",
    QPalette.ColorRole.Mid:             "#3C3C3C",
    QPalette.ColorRole.Midlight:        "#333333",
    QPalette.ColorRole.Dark:            "#111111",
    QPalette.ColorRole.Shadow:          "#0A0A0A",
    QPalette.ColorRole.ToolTipBase:     "#263238",
    QPalette.ColorRole.ToolTipText:     "#E0E0E0",
    QPalette.ColorRole.PlaceholderText: "#616161",
}

# Editor-specific stylesheet additions
_LIGHT_QSS = """
QPlainTextEdit, QTextEdit {
    background: #FFFFFF;
    color: #1A1A1A;
    border: 1px solid #DCDCDC;
    selection-background-color: #BBDEFB;
}
QToolBar { border-bottom: 1px solid #C8C8C8; spacing: 4px; }
QTabBar::tab {
    padding: 5px 12px;
    border: 1px solid #C8C8C8;
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    background: #EEEEEE;
}
QTabBar::tab:selected { background: #FFFFFF; border-bottom: 1px solid #FFFFFF; }
QTabBar::tab:hover:!selected { background: #E0E0E0; }
QSplitter::handle { background: #DCDCDC; }
QScrollBar:vertical { width: 10px; background: #F0F0F0; }
QScrollBar::handle:vertical { background: #BDBDBD; min-height: 24px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #9E9E9E; }
QGroupBox {
    font-weight: 600;
    border: 1px solid #DCDCDC;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 6px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; }

/* Styles from User Screenshot/CSS */
QLineEdit, QSpinBox {
    background: #FFFFFF;
    border: 1px solid #AAAAAA;
    padding: 3px 5px;
    border-radius: 2px;
    font-size: 11px;
}
QComboBox {
    background: #D6D6D6;
    color: #333333;
    border: 1px solid #AAAAAA;
    padding: 2px 5px;
    border-radius: 2px;
    font-size: 11px;
}
QComboBox:hover {
    background: #CECECE;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #000000;
    selection-background-color: #0078D7;
    selection-color: #FFFFFF;
    outline: 0px;
    border: 1px solid #AAAAAA;
}
QDockWidget > QWidget {
    background-color: #E9E9E9;
    border: 1px solid #BDBDBD;
}
QDockWidget::title {
    background-color: #D6D6D6;
    padding: 6px 10px;
    font-weight: bold;
    color: #333333;
}
"""

_DARK_QSS = """
QPlainTextEdit, QTextEdit {
    background: #252525;
    color: #E0E0E0;
    border: 1px solid #3C3C3C;
    selection-background-color: #1565C0;
}
QToolBar { border-bottom: 1px solid #3C3C3C; spacing: 4px; background: #1E1E1E; }
QTabBar::tab {
    padding: 5px 12px;
    border: 1px solid #3C3C3C;
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    background: #2C2C2C;
    color: #BDBDBD;
}
QTabBar::tab:selected { background: #252525; color: #E0E0E0; }
QTabBar::tab:hover:!selected { background: #333333; }
QSplitter::handle { background: #3C3C3C; }
QMenuBar { background: #1E1E1E; color: #E0E0E0; }
QMenuBar::item:selected { background: #333333; }
QMenu { background: #2C2C2C; color: #E0E0E0; border: 1px solid #3C3C3C; }
QMenu::item:selected { background: #1976D2; }
QScrollBar:vertical { width: 10px; background: #2C2C2C; }
QScrollBar::handle:vertical { background: #555; min-height: 24px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #777; }
QGroupBox {
    font-weight: 600;
    border: 1px solid #3C3C3C;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 6px;
    color: #E0E0E0;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #BDBDBD; }
QPushButton {
    background: #2D2D2D;
    color: #E0E0E0;
    border: 1px solid #3C3C3C;
    padding: 4px 10px;
    border-radius: 4px;
}
QPushButton:hover { background: #3A3A3A; }
QPushButton:pressed { background: #252525; }
QLineEdit, QSpinBox, QComboBox {
    background: #2D2D2D;
    color: #E0E0E0;
    border: 1px solid #3C3C3C;
    padding: 3px 6px;
    border-radius: 4px;
}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {
    background: #3A3A3A;
}
QLineEdit:focus, QSpinBox:focus { border-color: #1976D2; }
QComboBox QAbstractItemView {
    background-color: #2D2D2D;
    color: #E0E0E0;
    selection-background-color: #1976D2;
    selection-color: #FFFFFF;
    outline: 0px;
    border: 1px solid #3C3C3C;
}
QListWidget, QTableWidget, QTreeWidget {
    background: #252525;
    color: #E0E0E0;
    border: 1px solid #3C3C3C;
    alternate-background-color: #2C2C2C;
}
QHeaderView::section {
    background: #2D2D2D;
    color: #BDBDBD;
    border: none;
    padding: 4px 6px;
    border-bottom: 1px solid #3C3C3C;
}
QDockWidget { color: #E0E0E0; }
QDockWidget::title { background: #2C2C2C; padding: 4px; }
QStatusBar { background: #1E1E1E; color: #9E9E9E; border-top: 1px solid #3C3C3C; }
"""


# ── System theme detection ────────────────────────────────────────────────

def _system_is_dark() -> bool:
    """Deteksi tema OS. Return True jika dark mode aktif."""
    try:
        # Qt 6.5+ punya styleHints().colorScheme()
        app = QApplication.instance()
        if app and hasattr(app, 'styleHints'):
            scheme = app.styleHints().colorScheme()  # type: ignore[attr-defined]
            return scheme == Qt.ColorScheme.Dark  # type: ignore[attr-defined]
    except Exception:
        pass

    # Fallback: cek palette
    app = QApplication.instance()
    if app and hasattr(app, 'palette'):
        bg = app.palette().color(QPalette.ColorRole.Window)  # type: ignore[attr-defined]
        return bg.lightness() < 128

    return False


# ── Apply ─────────────────────────────────────────────────────────────────

# Syntax highlighting palettes
_SYNTAX_LIGHT = {
    "heading":    "#1a1a2e",
    "bold_italic":"#111111",
    "italic":     "#444444",
    "image":      ("#c77700", "#FFF8E1"), # (fg, bg)
    "link":       "#185FA5",
    "wiki":       ("#534AB7", "#EEEDFE"),
    "citation":   ("#0F6E56", "#E1F5EE"),
    "code":       ("#1D9E75", "#F0FFF8"),
    "quote":      ("#777777", "#F0F0F0"),
    "list":       "#BA7517",
    "escape":     "#c0392b",
    "code_block": ("#888888", "#F5F5F5"),
}

_SYNTAX_DARK = {
    "heading":    "#BBDEFB",
    "bold_italic":"#FFFFFF",
    "italic":     "#BDBDBD",
    "image":      ("#FFB74D", "#3E2723"),
    "link":       "#64B5F6",
    "wiki":       ("#9575CD", "#311B92"),
    "citation":   ("#4DB6AC", "#004D40"),
    "code":       ("#81C784", "#1B5E20"),
    "quote":      ("#9E9E9E", "#2C2C2C"),
    "list":       "#FFD54F",
    "escape":     "#EF5350",
    "code_block": ("#B0BEC5", "#2D2D2D"),
}


def get_syntax_palette(effective_mode: ThemeMode) -> dict:
    return _SYNTAX_DARK if effective_mode == ThemeMode.DARK else _SYNTAX_LIGHT


def apply_theme(app: QApplication, mode: ThemeMode | str) -> None:
    """Terapkan tema ke seluruh aplikasi."""
    mode = ThemeMode(mode)

    if mode == ThemeMode.SYSTEM:
        effective = ThemeMode.DARK if _system_is_dark() else ThemeMode.LIGHT
    else:
        effective = mode

    colors = _DARK_COLORS if effective == ThemeMode.DARK else _LIGHT_COLORS
    qss    = _DARK_QSS    if effective == ThemeMode.DARK else _LIGHT_QSS

    palette = QPalette()
    for role, hex_color in colors.items():
        color = QColor(hex_color)
        palette.setColor(role, color)
        # Set untuk semua group (Active, Inactive, Disabled)
        palette.setColor(QPalette.ColorGroup.Active,   role, color)
        palette.setColor(QPalette.ColorGroup.Inactive, role, color)
        # Disabled sedikit lebih pucat
        disabled = QColor(hex_color)
        disabled.setAlpha(120)
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)

    app.setPalette(palette)
    app.setStyleSheet(qss)


def get_effective_mode(config_mode: str) -> ThemeMode:
    mode = ThemeMode(config_mode) if config_mode in ThemeMode._value2member_map_ \
           else ThemeMode.SYSTEM
    if mode == ThemeMode.SYSTEM:
        return ThemeMode.DARK if _system_is_dark() else ThemeMode.LIGHT
    return mode


# ── Watcher ───────────────────────────────────────────────────────────────

class SystemThemeWatcher(QObject):
    """
    Polling-based watcher: setiap 5 detik cek apakah tema OS berubah.
    Emit theme_changed(ThemeMode) jika ya.
    (Qt 6.5+ punya signal nativeColorSchemeChanged, tapi ini lebih portable)
    """

    theme_changed = Signal(object)   # ThemeMode

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last: bool | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(5_000)
        self._timer.timeout.connect(self._check)

    def start(self) -> None:
        self._last = _system_is_dark()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _check(self) -> None:
        current = _system_is_dark()
        if current != self._last:
            self._last = current
            self.theme_changed.emit(
                ThemeMode.DARK if current else ThemeMode.LIGHT)
