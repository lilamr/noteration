"""
noteration/dialogs/conflict_dialog.py

Dialog resolusi konflik Git dengan tampilan 3-panel:
  - Kiri: "Milik saya" (our)
  - Kanan: "Dari remote" (their)
  - Bawah: Editor resolusi (bisa edit manual atau pilih salah satu)
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QSplitter, QFrame, QTabWidget, QWidget,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from noteration.sync.git_engine import ConflictInfo


class ConflictEditorPanel(QWidget):
    """
    Panel 3-panel untuk satu file konflik:
    Atas: our vs their (read-only)
    Bawah: editor resolusi (editable)
    """

    def __init__(self, conflict: ConflictInfo, parent=None) -> None:
        super().__init__(parent)
        self._conflict = conflict
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Toolbar aksi cepat
        tb = QHBoxLayout()
        tb.setContentsMargins(8, 4, 8, 4)

        lbl = QLabel(f"📄 {self._conflict.path}")
        lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        tb.addWidget(lbl)
        tb.addStretch()

        btn_ours = QPushButton("Ambil semua milik saya ↓")
        btn_ours.clicked.connect(self._use_ours)
        btn_ours.setStyleSheet(
            "background: #E3F2FD; color: #0D47A1; border: 1px solid #BBDEFB;")
        tb.addWidget(btn_ours)

        btn_theirs = QPushButton("Ambil semua dari remote ↓")
        btn_theirs.clicked.connect(self._use_theirs)
        btn_theirs.setStyleSheet(
            "background: #FFF3E0; color: #E65100; border: 1px solid #FFE0B2;")
        tb.addWidget(btn_theirs)

        btn_both = QPushButton("Gabung keduanya ↓")
        btn_both.clicked.connect(self._use_both)
        tb.addWidget(btn_both)

        tb_frame = QFrame()
        tb_frame.setLayout(tb)
        tb_frame.setStyleSheet(
            "QFrame { background: palette(window); border-bottom: 1px solid palette(mid); }"
        )
        root.addWidget(tb_frame)

        # Splitter: atas (our vs their) + bawah (resolved)
        vsplitter = QSplitter(Qt.Orientation.Vertical)

        # Atas: side-by-side our vs their
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        our_panel = self._make_panel(
            "Milik saya (local)",
            self._conflict.our_content,
            "#E3F2FD",
        )
        their_panel = self._make_panel(
            "Dari remote",
            self._conflict.their_content,
            "#FFF3E0",
        )
        top_splitter.addWidget(our_panel)
        top_splitter.addWidget(their_panel)
        vsplitter.addWidget(top_splitter)

        # Bawah: resolved
        bot_frame = QFrame()
        bot_layout = QVBoxLayout(bot_frame)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        bot_header = QLabel("✏  Resolusi (edit di bawah ini):")
        bot_header.setStyleSheet(
            "padding: 4px 8px; background: #E8F5E9; color: #2E7D32;"
            "border-bottom: 1px solid #C8E6C9; font-weight: bold;"
        )
        bot_layout.addWidget(bot_header)

        self._resolved_editor = QPlainTextEdit()
        self._resolved_editor.setPlainText(self._conflict.our_content)
        font = QFont("Consolas", 11)
        font.setFixedPitch(True)
        self._resolved_editor.setFont(font)
        bot_layout.addWidget(self._resolved_editor)
        vsplitter.addWidget(bot_frame)

        vsplitter.setSizes([300, 200])
        root.addWidget(vsplitter)

    def _make_panel(self, title: str, content: str, bg: str) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel(title)
        header.setStyleSheet(
            f"padding: 4px 8px; background: {bg}; font-weight: bold;"
            "border-bottom: 1px solid #ccc;"
        )
        layout.addWidget(header)

        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(content)
        font = QFont("Consolas", 11)
        font.setFixedPitch(True)
        editor.setFont(font)
        editor.setStyleSheet(f"background: {bg}; border: none;")
        layout.addWidget(editor)
        return frame

    def _use_ours(self) -> None:
        self._resolved_editor.setPlainText(self._conflict.our_content)

    def _use_theirs(self) -> None:
        self._resolved_editor.setPlainText(self._conflict.their_content)

    def _use_both(self) -> None:
        combined = (
            f"# === Milik saya ===\n"
            f"{self._conflict.our_content}\n\n"
            f"# === Dari remote ===\n"
            f"{self._conflict.their_content}"
        )
        self._resolved_editor.setPlainText(combined)

    def resolved_content(self) -> str:
        return self._resolved_editor.toPlainText()

    @property
    def path(self) -> str:
        return self._conflict.path


class ConflictResolutionDialog(QDialog):
    """
    Dialog utama yang menampilkan semua konflik dalam satu QTabWidget.
    Tombol 'Terapkan Resolusi' memanggil GitRepo.resolve_conflict()
    untuk setiap file, lalu menutup dialog.
    """

    resolutions_applied = Signal(dict)  # {path: resolved_content}

    def __init__(
        self,
        conflicts: list[ConflictInfo],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            f"Resolusi Konflik Git — {len(conflicts)} file")
        self.resize(1000, 680)
        self._panels: list[ConflictEditorPanel] = []
        self._setup_ui(conflicts)

    def _setup_ui(self, conflicts: list[ConflictInfo]) -> None:
        root = QVBoxLayout(self)

        # Penjelasan
        info = QLabel(
            f"⚠  {len(conflicts)} file konflik ditemukan saat sinkronisasi.\n"
            "Untuk setiap file, pilih versi yang ingin dipertahankan "
            "atau edit resolusi secara manual, lalu klik 'Terapkan Resolusi'."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background: #FFF8E1; border: 1px solid #FFE082;"
            "padding: 10px; border-radius: 4px; color: #5D4037;"
        )
        root.addWidget(info)

        # Tab per file konflik
        self._tabs = QTabWidget()
        for conflict in conflicts:
            panel = ConflictEditorPanel(conflict, self)
            self._panels.append(panel)
            label = Path(conflict.path).name
            self._tabs.addTab(panel, f"⚠ {label}")
        root.addWidget(self._tabs)

        # Tombol bawah
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Batal (batalkan sync)")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_apply = QPushButton("✓ Terapkan Resolusi")
        btn_apply.setDefault(True)
        btn_apply.setStyleSheet(
            "background: #2E7D32; color: white; padding: 6px 16px;"
            "border-radius: 4px; font-weight: bold;"
        )
        btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(btn_apply)

        root.addLayout(btn_row)

    def _apply(self) -> None:
        resolutions = {
            panel.path: panel.resolved_content()
            for panel in self._panels
        }
        self.resolutions_applied.emit(resolutions)
        self.accept()

    def get_resolutions(self) -> dict[str, str]:
        return {
            panel.path: panel.resolved_content()
            for panel in self._panels
        }
