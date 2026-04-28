"""
noteration/ui/sidebar.py
QDockWidget kiri berisi panel Notes, PDFs (Papis), Outline, dan Citations.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLabel, QLineEdit, QHBoxLayout, QFrame,
    QAbstractItemView, QMessageBox,
)
from PySide6.QtCore import Qt, Signal

from noteration.config import NoterationConfig


class NotesTreeWidget(QTreeWidget):
    """Tree widget khusus untuk catatan dengan dukungan Drag-and-Drop."""
    item_moved = Signal(object, object)  # Path src, Path dest

    def __init__(self, root_notes: Path, parent=None) -> None:
        super().__init__(parent)
        self.root_notes = root_notes
        self.setHeaderHidden(True)
        self.setIndentation(12)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setStyleSheet("font-size: 12px;")

    def dropEvent(self, event) -> None:
        src_item = self.currentItem()
        if not src_item:
            super().dropEvent(event)
            return

        src_data = src_item.data(0, Qt.ItemDataRole.UserRole)
        if not src_data or "path" not in src_data:
            super().dropEvent(event)
            return

        src_path = Path(src_data["path"])
        
        # Cari target drop
        target_item = self.itemAt(event.position().toPoint())
        if target_item:
            target_data = target_item.data(0, Qt.ItemDataRole.UserRole)
            if target_data and target_data.get("type") == "folder":
                target_dir = Path(target_data["path"])
            else:
                # Jika drop di atas file, pindahkan ke folder yang sama dengan file tersebut
                target_dir = Path(target_data["path"]).parent
        else:
            # Jika drop di area kosong, pindahkan ke root notes
            target_dir = self.root_notes

        dest_path = target_dir / src_path.name

        # Validasi
        if src_path == dest_path:
            event.ignore()
            return

        # Cegah pindah folder ke dirinya sendiri atau subfoldernya
        # Python 3.9+ support is_relative_to
        try:
            if src_path.is_dir() and target_dir.is_relative_to(src_path):
                QMessageBox.warning(self, "Operasi Ilegal", "Tidak bisa memindahkan folder ke dalam dirinya sendiri.")
                event.ignore()
                return
        except AttributeError:
            # Fallback for older python if needed
            if src_path.is_dir() and str(target_dir).startswith(str(src_path)):
                QMessageBox.warning(self, "Operasi Ilegal", "Tidak bisa memindahkan folder ke dalam dirinya sendiri.")
                event.ignore()
                return

        if dest_path.exists():
            reply = QMessageBox.question(
                self, "Konflik Nama",
                f"'{src_path.name}' sudah ada di tujuan. Timpa?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        try:
            shutil.move(str(src_path), str(dest_path))
            self.item_moved.emit(src_path, dest_path)
            event.accept()
        except Exception as e:
            QMessageBox.critical(self, "Gagal Memindahkan", f"Terjadi kesalahan saat memindahkan file:\n{e}")
            event.ignore()


class _ClickableHeader(QWidget):
    """Header widget dengan proper mousePressEvent override."""
    def __init__(self, callback, parent=None) -> None:
        super().__init__(parent)
        self._callback = callback
    def mousePressEvent(self, event) -> None:
        self._callback()
        super().mousePressEvent(event)


class CollapsibleSection(QWidget):
    """Header yang bisa di-collapse/expand dengan konten di bawahnya."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self._collapsed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        self._header = _ClickableHeader(self._toggle)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet(
            "QWidget { background: palette(window); padding: 4px 8px; }"
            "QWidget:hover { background: palette(mid); }"
        )
        h_layout = QHBoxLayout(self._header)
        h_layout.setContentsMargins(4, 3, 4, 3)

        self._arrow = QLabel("▾")
        self._arrow.setFixedWidth(12)
        self._arrow.setStyleSheet("font-size: 9px; color: gray;")

        self._title_label = QLabel(title.upper())
        self._title_label.setStyleSheet(
            "font-size: 10px; font-weight: 600; letter-spacing: 0.5px; color: gray;"
        )

        h_layout.addWidget(self._arrow)
        h_layout.addWidget(self._title_label)
        h_layout.addStretch()

        layout.addWidget(self._header)

        # Content container
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        layout.addWidget(self._content)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: palette(mid);")
        layout.addWidget(line)

    def add_widget(self, widget: QWidget) -> None:
        self._content_layout.addWidget(widget)

    def _toggle(self, _event=None) -> None:
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._arrow.setText("▸" if self._collapsed else "▾")


class SidebarWidget(QWidget):
    note_selected = Signal(object)
    pdf_selected = Signal(str, str)
    heading_clicked = Signal(str)
    citation_clicked = Signal(str)
    item_moved = Signal(object, object)

    def __init__(self, vault_path: Path, config: NoterationConfig, parent=None) -> None:
        super().__init__(parent)
        self.vault_path = vault_path
        self.config = config
        self._last_cited_keys: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._setup_notes_section(layout)
        self._setup_pdfs_section(layout)
        self._setup_outline_section(layout)
        self._setup_citations_section(layout)
        layout.addStretch()

        self._populate_notes()
        self._populate_pdfs()

    # ------------------------------------------------------------------
    # NOTES section
    # ------------------------------------------------------------------

    def _setup_notes_section(self, parent_layout: QVBoxLayout) -> None:
        sec = CollapsibleSection("Notes")

        self._notes_tree = NotesTreeWidget(self.vault_path / "notes")
        self._notes_tree.setMaximumHeight(500)
        self._notes_tree.itemDoubleClicked.connect(self._on_note_double_clicked)
        self._notes_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._notes_tree.customContextMenuRequested.connect(self._show_notes_context_menu)
        self._notes_tree.item_moved.connect(self._on_item_moved)

        sec.add_widget(self._notes_tree)
        parent_layout.addWidget(sec)

    def _on_item_moved(self, src: Path, dest: Path) -> None:
        self.item_moved.emit(src, dest)
        self._populate_notes()

    def _populate_notes(self) -> None:
        self._notes_tree.clear()
        notes_dir = self.vault_path / "notes"
        if not notes_dir.exists():
            notes_dir.mkdir(parents=True, exist_ok=True)
        self._add_tree_items(self._notes_tree.invisibleRootItem(), notes_dir, notes_dir)
        # Auto-expand root level
        for i in range(self._notes_tree.topLevelItemCount()):
            item = self._notes_tree.topLevelItem(i)
            if item:
                item.setExpanded(True)

    def _add_tree_items(self, parent: QTreeWidgetItem, directory: Path, root_notes: Path) -> None:
        # Folder dulu (hidden folders starting with . ignored)
        for d in sorted(directory.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                folder_item = QTreeWidgetItem(parent, [f"📁 {d.name}"])
                folder_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "path": d})
                folder_item.setData(0, Qt.ItemDataRole.UserRole + 1, d.relative_to(root_notes))
                self._add_tree_items(folder_item, d, root_notes)

        # Markdown files
        for f in sorted(directory.glob("*.md")):
            rel_path = f.relative_to(root_notes)
            item = QTreeWidgetItem(parent, [f"📄 {f.name}"])
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "file", "path": f})
            item.setData(0, Qt.ItemDataRole.UserRole + 1, rel_path)

    def _on_note_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "file":
            self.note_selected.emit(data["path"])

    def _show_notes_context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        item = self._notes_tree.itemAt(pos)
        menu = QMenu(self)

        # Determine target directory
        target_dir = self.vault_path / "notes"
        if item:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "folder":
                target_dir = data["path"]

        act_new_note = menu.addAction("📄 New Note")
        act_new_folder = menu.addAction("📁 New Folder")

        act_rename = None
        act_delete = None
        if item:
            menu.addSeparator()
            act_rename = menu.addAction("✏️ Rename")
            act_delete = menu.addAction("🗑️ Hapus")

        chosen = menu.exec(self._notes_tree.mapToGlobal(pos))
        if chosen == act_new_note:
            self._create_new_note(target_dir)
        elif chosen == act_new_folder:
            self._create_new_folder(target_dir)
        elif chosen == act_rename and item:
            self._rename_item(item)
        elif chosen == act_delete and item:
            self._delete_item(item)

    def _rename_item(self, item: QTreeWidgetItem) -> None:
        """Rename file atau folder."""
        from PySide6.QtWidgets import QInputDialog
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or "path" not in data:
            return

        old_path = Path(data["path"])
        if not old_path.exists():
            QMessageBox.warning(self, "Path Tidak Ada", f"'{old_path}' tidak ditemukan.")
            return

        is_folder = data.get("type") == "folder"
        type_str = "Folder" if is_folder else "Note"

        # Pre-fill dengan nama lama (tanpa ekstensi untuk note)
        old_name = old_path.stem if not is_folder else old_path.name

        new_name, ok = QInputDialog.getText(
            self, f"Rename {type_str}",
            f"Nama baru untuk '{old_name}':",
            text=old_name
        )

        if not ok or not new_name.strip():
            return

        new_name = new_name.strip()

        # Untuk note, pastikan ada ekstensi .md
        if not is_folder:
            if not new_name.endswith(".md"):
                new_name += ".md"

        new_path = old_path.parent / new_name

        # Cek konflik nama
        if new_path.exists() and new_path != old_path:
            QMessageBox.warning(
                self, "Nama Sudah Ada",
                f"'{new_name}' sudah ada di folder ini."
            )
            return

        try:
            old_path.rename(new_path)
            # Jika ini adalah note (file .md), emit note_selected untuk refresh editor jika perlu
            if not is_folder:
                self.note_selected.emit(new_path)
            # Refresh tree
            self._populate_notes()
            # Emit item_moved signal agar main window bisa update path di tab yang terbuka
            if hasattr(self, 'item_moved'):
                self.item_moved.emit(old_path, new_path)
        except Exception as e:
            QMessageBox.critical(
                self, "Gagal Rename",
                f"Terjadi kesalahan saat me-rename:\n{e}"
            )

    def _delete_item(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        path = data.get("path")
        if not path or not path.exists():
            return

        is_folder = data.get("type") == "folder"
        type_str = "folder" if is_folder else "note"

        reply = QMessageBox.question(
            self, f"Hapus {type_str}",
            f"Apakah Anda yakin ingin menghapus {type_str} '{path.name}'?\n"
            "Tindakan ini tidak dapat dibatalkan.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if is_folder:
                    shutil.rmtree(path)
                else:
                    path.unlink()
                self._populate_notes()
            except Exception as e:
                QMessageBox.critical(self, "Gagal Menghapus", f"Terjadi kesalahan:\n{e}")

    def _create_new_note(self, parent_dir: Path) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Note", "Note name (e.g. folder/note):")
        if ok and name.strip():
            note_path = parent_dir / f"{name.strip()}.md"
            if not note_path.exists():
                note_path.parent.mkdir(parents=True, exist_ok=True)
                note_path.write_text(f"# {Path(name.strip()).name}\n\n")
                self._populate_notes()
                self.note_selected.emit(note_path)

    def _create_new_folder(self, parent_dir: Path) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            folder_path = parent_dir / name.strip()
            if not folder_path.exists():
                folder_path.mkdir(parents=True, exist_ok=True)
                self._populate_notes()

    # ------------------------------------------------------------------
    # PDFs (Papis) section
    # ------------------------------------------------------------------

    def _setup_pdfs_section(self, parent_layout: QVBoxLayout) -> None:
        sec = CollapsibleSection("PDFs (Papis)")

        # Filter row
        filter_row = QWidget()
        f_lay = QHBoxLayout(filter_row)
        f_lay.setContentsMargins(6, 3, 6, 3)
        f_lay.setSpacing(4)

        from PySide6.QtWidgets import QComboBox
        self._pdf_collection_combo = QComboBox()
        self._pdf_collection_combo.setFixedWidth(80)
        self._pdf_collection_combo.addItem("Semua")
        self._pdf_collection_combo.addItem("Linked")
        self._pdf_collection_combo.currentTextChanged.connect(lambda _: self._filter_pdfs(self._pdf_filter.text()))
        f_lay.addWidget(self._pdf_collection_combo)

        self._pdf_filter: QLineEdit = QLineEdit()
        self._pdf_filter.setPlaceholderText("Filter...")
        self._pdf_filter.setStyleSheet("font-size: 11px;")
        self._pdf_filter.textChanged.connect(self._filter_pdfs)
        f_lay.addWidget(self._pdf_filter)

        self._pdf_tree = QTreeWidget()
        self._pdf_tree.setHeaderHidden(True)
        self._pdf_tree.setIndentation(0)
        self._pdf_tree.setMaximumHeight(160)
        self._pdf_tree.setStyleSheet("font-size: 12px;")
        self._pdf_tree.itemDoubleClicked.connect(self._on_pdf_double_clicked)

        sec.add_widget(filter_row)
        sec.add_widget(self._pdf_tree)
        parent_layout.addWidget(sec)

    def _populate_pdfs(self) -> None:
        self._pdf_tree.clear()
        lit_dir = self.config.papis_library
        if not lit_dir.exists():
            return

        all_collections = set()

        #Cara 1: Langsung file PDF di root literature/ (tanpa folder Papis)
        for pdf_file in sorted(lit_dir.glob("*.pdf")):
            key = pdf_file.stem
            item = QTreeWidgetItem(self._pdf_tree, [f"📘 {pdf_file.name}"])
            item.setData(0, Qt.ItemDataRole.UserRole, {
                "key": key,
                "pdf": pdf_file,
                "title": key,
                "collections": [],
            })
            item.setToolTip(0, key)

        # Cara 2: Folder Papis (dengan info.yaml)
        for entry_dir in sorted(lit_dir.iterdir()):
            if not entry_dir.is_dir():
                continue
            info_yaml = entry_dir / "info.yaml"
            if not info_yaml.exists():
                continue

            title = entry_dir.name
            collections = []
            try:
                import yaml  # type: ignore
                with open(info_yaml) as f:
                    info = yaml.safe_load(f)
                title = info.get("title", entry_dir.name)[:40]
                collections = info.get("collections", [])
                for col in collections:
                    all_collections.add(str(col))
            except Exception:
                pass

            pdf_files = list(entry_dir.glob("*.pdf"))
            icon = "📘" if pdf_files else "📂"
            display_text = title if title else entry_dir.name

            # Get collections for tooltip
            coll_str = f" [{', '.join(collections)}]" if collections else ""
            
            item = QTreeWidgetItem(self._pdf_tree, [f"{icon} {display_text}"])
            item.setData(0, Qt.ItemDataRole.UserRole, {
                "key": entry_dir.name,
                "pdf": pdf_files[0] if pdf_files else None,
                "title": title,
                "collections": [str(c) for c in collections],
            })
            item.setToolTip(0, f"{title}{coll_str}")

        # Update collection dropdown
        current = self._pdf_collection_combo.currentText()
        self._pdf_collection_combo.blockSignals(True)
        self._pdf_collection_combo.clear()
        self._pdf_collection_combo.addItem("Semua")
        self._pdf_collection_combo.addItem("Linked")
        for col in sorted(all_collections):
            self._pdf_collection_combo.addItem(col)
        if current == "Linked" or current in all_collections:
            self._pdf_collection_combo.setCurrentText(current)
        self._pdf_collection_combo.blockSignals(False)

        # Re-apply current filter
        self._filter_pdfs(self._pdf_filter.text())

    def _filter_pdfs(self, text: str) -> None:
        coll_filter = self._pdf_collection_combo.currentText()
        search_q = text.lower()

        for i in range(self._pdf_tree.topLevelItemCount()):
            item = self._pdf_tree.topLevelItem(i)
            if not item:
                continue
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            
            # Collection / Linked match
            coll_match = True
            if coll_filter == "Linked":
                key = data.get("key")
                coll_match = key in self._last_cited_keys
            elif coll_filter != "Semua":
                item_colls = data.get("collections", [])
                coll_match = coll_filter in item_colls
            
            # Search match
            search_match = search_q in item.text(0).lower()
            
            item.setHidden(not (coll_match and search_match))

    def update_cited_pdfs(self, keys: list[str]) -> None:
        """Update daftar key yang dikutip dan refresh filter jika mode 'Linked' aktif."""
        self._last_cited_keys = keys
        if self._pdf_collection_combo.currentText() == "Linked":
            self._filter_pdfs(self._pdf_filter.text())

    def _on_pdf_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("pdf"):
            pdf_path = data["pdf"]
            pdf_str = str(pdf_path) if pdf_path else ""
            key_str = data.get("key", "")
            self.pdf_selected.emit(pdf_str, key_str)

    # ------------------------------------------------------------------
    # OUTLINE section
    # ------------------------------------------------------------------

    def _setup_outline_section(self, parent_layout: QVBoxLayout) -> None:
        sec = CollapsibleSection("Outline")

        self._outline_tree = QTreeWidget()
        self._outline_tree.setHeaderHidden(True)
        self._outline_tree.setIndentation(10)
        self._outline_tree.setMaximumHeight(130)
        self._outline_tree.setStyleSheet("font-size: 11px;")

        self._outline_tree.itemDoubleClicked.connect(self._on_outline_double_click)

        sec.add_widget(self._outline_tree)
        parent_layout.addWidget(sec)

    def update_outline(self, headings: list[tuple[int, str]]) -> None:
        """
        Diisi dari EditorTab saat konten berubah.
        headings: list of (level, text) misal [(1, 'Pendahuluan'), (2, 'Latar Belakang')]
        """
        self._outline_tree.clear()
        stack: list[QTreeWidgetItem] = []

        for level, text in headings:
            prefix = "#" * level + " "
            item = QTreeWidgetItem([prefix + text])
            item.setData(0, Qt.ItemDataRole.UserRole, text)

            if not stack or level == 1:
                self._outline_tree.addTopLevelItem(item)
                stack = [item]
            else:
                # Cari parent yang levelnya lebih kecil
                while len(stack) >= level:
                    stack.pop()
                if stack:
                    stack[-1].addChild(item)
                else:
                    self._outline_tree.addTopLevelItem(item)
                stack.append(item)

        self._outline_tree.expandAll()

    def _on_outline_double_click(self, item, column) -> None:
        heading = item.data(0, Qt.ItemDataRole.UserRole)
        if heading:
            self.heading_clicked.emit(heading)

    # ------------------------------------------------------------------
    # CITATIONS section
    # ------------------------------------------------------------------

    def _setup_citations_section(self, parent_layout: QVBoxLayout) -> None:
        sec = CollapsibleSection("Citations")

        self._citations_tree = QTreeWidget()
        self._citations_tree.setHeaderHidden(True)
        self._citations_tree.setIndentation(0)
        self._citations_tree.setMaximumHeight(100)
        self._citations_tree.setStyleSheet(
            "font-size: 11px; font-family: monospace; color: #0F6E56;"
        )
        self._citations_tree.itemDoubleClicked.connect(self._on_citation_double_click)

        sec.add_widget(self._citations_tree)
        parent_layout.addWidget(sec)

    def update_citations(self, keys: list[str]) -> None:
        """Diisi dari EditorTab saat @citation ditemukan."""
        self._citations_tree.clear()
        for key in sorted(set(keys)):
            item = QTreeWidgetItem(self._citations_tree, [f"@{key}"])
            item.setData(0, Qt.ItemDataRole.UserRole, key)

    def _on_citation_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.citation_clicked.emit(key)

    # ------------------------------------------------------------------
    # Public refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        self._populate_notes()
        self._populate_pdfs()
