"""
noteration/ui/backlink_panel.py

Panel backlink yang bisa ditaruh di sidebar atau sebagai dock widget.
Menampilkan:
  - Daftar note yang menautkan KE note aktif (backlinks)
  - Daftar note yang ditautkan DARI note aktif (forward links)
  - Orphan notes (tidak ada backlink)
  - Statistik graf
"""

from __future__ import annotations


from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTabWidget, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from noteration.db.link_graph import LinkGraph


class BacklinkPanel(QWidget):
    """
    Panel backlink (bisa dipakai sebagai dock atau embedded widget).

    Signals
    -------
    note_requested(stem: str)  — user mengklik note di daftar
    """

    note_requested = Signal(str)   # stem nama file note
    rebuild_requested = Signal()   # user mengklik tombol bangun ulang

    def __init__(self, graph: LinkGraph, parent=None) -> None:
        super().__init__(parent)
        self._graph       = graph
        self._current_note: str = ""
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet(
            "QFrame{background:palette(window);"
            "border-bottom:0.5px solid palette(mid);}")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 4, 8, 4)
        title = QLabel("Backlinks")
        title.setStyleSheet("font-weight:600;font-size:12px;")
        hl.addWidget(title)
        hl.addStretch()
        self._badge = QLabel("0")
        self._badge.setStyleSheet(
            "font-size:10px;background:#E3F2FD;color:#0D47A1;"
            "padding:1px 6px;border-radius:8px;")
        hl.addWidget(self._badge)
        root.addWidget(header)

        # Tabs: Backlinks | Forward | Orphans | Stats
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet(
            "QTabBar::tab{padding:4px 10px;font-size:11px;}"
            "QTabBar::tab:selected{font-weight:600;}")

        self._back_list    = self._make_note_list()
        self._forward_list = self._make_note_list()
        self._orphan_list  = self._make_note_list()
        self._stats_widget = self._make_stats_widget()

        self._tabs.addTab(self._back_list,    "← In")
        self._tabs.addTab(self._forward_list, "→ Out")
        self._tabs.addTab(self._orphan_list,  "◎ Orphan")
        self._tabs.addTab(self._stats_widget, "📊 Stats")
        root.addWidget(self._tabs)

    def _make_note_list(self) -> QListWidget:
        lst = QListWidget()
        lst.setStyleSheet(
            "QListWidget{font-size:12px;font-family:'Consolas',monospace;}"
            "QListWidget::item:hover{background:palette(mid);}"
            "QListWidget::item:selected{background:#BBDEFB;color:#0D47A1;}")
        lst.itemDoubleClicked.connect(self._on_item_double_clicked)
        return lst

    def _make_stats_widget(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self._stat_labels: dict[str, QLabel] = {}
        for key, label in [
            ("nodes",        "Total note"),
            ("edges",        "Total link"),
            ("orphans",      "Orphan"),
            ("hub",          "Hub (paling terhubung)"),
            ("components",   "Komponen terpisah"),
            ("largest_comp", "Komponen terbesar"),
        ]:
            row = QHBoxLayout()
            lbl_k = QLabel(label + ":")
            lbl_k.setStyleSheet("color:gray;font-size:11px;")
            lbl_k.setFixedWidth(160)
            lbl_v = QLabel("—")
            lbl_v.setStyleSheet("font-size:12px;font-weight:600;")
            row.addWidget(lbl_k)
            row.addWidget(lbl_v)
            row.addStretch()
            self._stat_labels[key] = lbl_v
            lay.addLayout(row)

        lay.addStretch()

        btn_rebuild = QPushButton("↺  Bangun Ulang Graf")
        btn_rebuild.clicked.connect(self._rebuild_graph)
        lay.addWidget(btn_rebuild)

        return w

    # ── Public API ────────────────────────────────────────────────────

    def set_current_note(self, note_stem: str) -> None:
        """Panggil saat pengguna berpindah ke note berbeda."""
        if note_stem == self._current_note:
            return
        self._current_note = note_stem
        self._refresh_note_lists()

    def refresh_all(self) -> None:
        """Refresh seluruh panel (setelah rebuild graf)."""
        self._refresh_note_lists()
        self._refresh_stats()
        self._refresh_orphans()

        # Update badge jika ada note aktif
        if self._current_note:
            count = len(self._graph.backlinks(self._current_note))
            self._badge.setText(str(count))

    # ── Refresh helpers ───────────────────────────────────────────────

    def _refresh_note_lists(self) -> None:
        note_id = self._current_note

        # Backlinks
        self._back_list.clear()
        backs = self._graph.backlinks(note_id)
        for nid in backs:
            item = QListWidgetItem(f"📄 {nid}")
            item.setData(Qt.ItemDataRole.UserRole, nid)
            item.setToolTip(f"[[{nid}]] menautkan ke sini")
            self._back_list.addItem(item)

        # Forward links
        self._forward_list.clear()
        for nid in self._graph.forward_links(note_id):
            item = QListWidgetItem(f"📄 {nid}")
            item.setData(Qt.ItemDataRole.UserRole, nid)
            self._forward_list.addItem(item)

        self._badge.setText(str(len(backs)))
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        stats = self._graph.stats()
        for key, lbl in self._stat_labels.items():
            val = stats.get(key)
            if val is None:
                lbl.setText("—")
            elif isinstance(val, float):
                lbl.setText(f"{val:.2f}")
            else:
                lbl.setText(str(val))

    def _refresh_orphans(self) -> None:
        self._orphan_list.clear()
        for nid in self._graph.orphans():
            item = QListWidgetItem(f"◎ {nid}")
            item.setData(Qt.ItemDataRole.UserRole, nid)
            item.setForeground(QColor("#9E9E9E"))
            self._orphan_list.addItem(item)

    def _rebuild_graph(self) -> None:
        self._badge.setText("↺")
        self.rebuild_requested.emit()

    # ── Click handler ─────────────────────────────────────────────────

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        stem = item.data(Qt.ItemDataRole.UserRole)
        if stem:
            self.note_requested.emit(stem)
