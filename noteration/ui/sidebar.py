"""
noteration/ui/sidebar.py
Left QTabWidget containing Notes, PDFs (Papis), Outline, and Citations panels.
"""

from __future__ import annotations

import shutil
import json
from pathlib import Path
from typing import Any, cast, TYPE_CHECKING

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QLineEdit, QHBoxLayout,
    QAbstractItemView, QMessageBox, QFileSystemModel, QTreeWidget,
    QListView, QTabWidget, QTreeWidgetItem, QComboBox, QMenu, QInputDialog,
)
from PySide6.QtCore import (
    Qt, Signal, QSortFilterProxyModel, QModelIndex,
    QAbstractItemModel, QAbstractListModel, QPersistentModelIndex,
)

if TYPE_CHECKING:
    from noteration.config import NoterationConfig


class HeadingItem:
    """Item for HeadingModel hierarchical structure."""
    def __init__(self, level: int, text: str, parent: HeadingItem | None = None) -> None:
        self.level = level
        self.text = text
        self.parent_item = parent
        self.child_items: list[HeadingItem] = []

    def append_child(self, child: HeadingItem) -> None:
        self.child_items.append(child)

    def child(self, row: int) -> HeadingItem | None:
        if 0 <= row < len(self.child_items):
            return self.child_items[row]
        return None

    def child_count(self) -> int:
        return len(self.child_items)

    def row(self) -> int:
        if self.parent_item:
            return self.parent_item.child_items.index(self)
        return 0


class HeadingModel(QAbstractItemModel):
    """Hierarchical model for the note Outline (Headings)."""
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.root_item = HeadingItem(0, "Root")

    def set_headings(self, headings: list[tuple[int, str]]) -> None:
        """Update the hierarchy based on a list of (level, title) tuples."""
        self.beginResetModel()
        self.root_item = HeadingItem(0, "Root")
        stack = [self.root_item]

        for level, text in headings:
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            
            new_item = HeadingItem(level, text, stack[-1])
            stack[-1].append_child(new_item)
            stack.append(new_item)
            
        self.endResetModel()

    def index(self, row: int, column: int, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_item = parent.internalPointer() if parent.isValid() else self.root_item
        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QModelIndex()

    def parent(self, index: QModelIndex | QPersistentModelIndex) -> QModelIndex:  # type: ignore[override]
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent_item

        if parent_item == self.root_item or parent_item is None:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        if parent.column() > 0:
            return 0
        parent_item = parent.internalPointer() if parent.isValid() else self.root_item
        return parent_item.child_count()

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 1

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        item = index.internalPointer()
        if role == Qt.ItemDataRole.DisplayRole:
            prefix = "#" * item.level + " "
            return prefix + item.text
        if role == Qt.ItemDataRole.UserRole:
            return item.text
        return None


class CitationModel(QAbstractListModel):
    """Simple list model for Citations extracted from a note."""
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._keys: list[str] = []

    def set_citations(self, keys: list[str]) -> None:
        self.beginResetModel()
        self._keys = sorted(list(set(keys)))
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self._keys)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        key = self._keys[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"@{key}"
        if role == Qt.ItemDataRole.UserRole:
            return key
        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor("#0F6E56")
        return None


class NotesFilterProxyModel(QSortFilterProxyModel):
    """Proxy model to filter for Markdown files and directories only."""
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex) -> bool:
        model = cast(QFileSystemModel, self.sourceModel())
        idx = model.index(source_row, 0, source_parent)
        
        if model.isDir(idx):
            return True
            
        file_name = model.fileName(idx).lower()
        return file_name.endswith(".md")


class NotesTreeWidget(QTreeWidget):
    """Tree widget for notes that supports manual sorting via drag and drop."""
    note_selected = Signal(Path)
    item_moved = Signal(Path, Path)

    def __init__(self, root_path: Path, vault_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.root_path = root_path
        self.vault_path = vault_path
        self._order_file = vault_path / ".noteration" / "notes_order.json"
        
        self.setHeaderHidden(True)
        self.setIndentation(12)
        self.setAnimated(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        self.itemDoubleClicked.connect(self._on_double_clicked)
        self.populate()

    def populate(self) -> None:
        """Populate the tree based on the notes/ folder structure with persistent ordering."""
        self.clear()
        if not self.root_path.exists():
            return

        order_data = self.load_order()
        if order_data:
            self._apply_order(order_data, self.root_path, self.invisibleRootItem())
            # Check for new items that were manually added and are not in order_data
            self._scan_remaining(self.root_path, self.invisibleRootItem())
        else:
            self._scan_dir(self.root_path, self.invisibleRootItem())

    def _scan_dir(self, path: Path, parent_item: QTreeWidgetItem) -> None:
        """Initial alphabetical scan of the directory structure."""
        entries = sorted(list(path.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
        
        for entry in entries:
            if entry.is_dir():
                item = QTreeWidgetItem(parent_item, [entry.name])
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
                item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon))
                self._scan_dir(entry, item)
            elif entry.suffix.lower() == ".md":
                item = QTreeWidgetItem(parent_item, [entry.name])
                item.setData(0, Qt.ItemDataRole.UserRole, entry)
                item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon))

    def _apply_order(self, order_list: list[dict], current_path: Path, parent_item: QTreeWidgetItem) -> None:
        """Recursively apply the stored JSON ordering to the tree."""
        for entry_info in order_list:
            name = entry_info.get("name")
            if not name:
                continue
            is_dir = entry_info.get("is_dir", False)
            path = current_path / str(name)
            
            if not path.exists():
                continue
                
            item = QTreeWidgetItem(parent_item, [str(name)])
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            
            if is_dir:
                item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon))
                children = entry_info.get("children", [])
                self._apply_order(children, path, item)
            else:
                item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon))

    def _scan_remaining(self, path: Path, parent_item: QTreeWidgetItem) -> None:
        """Scan for items on disk not yet present in the UI."""
        existing_names = set()
        for i in range(parent_item.childCount()):
            existing_names.add(parent_item.child(i).text(0))
            
        for entry in path.iterdir():
            if entry.name not in existing_names:
                if entry.is_dir():
                    item = QTreeWidgetItem(parent_item, [entry.name])
                    item.setData(0, Qt.ItemDataRole.UserRole, entry)
                    item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon))
                    self._scan_dir(entry, item)
                elif entry.suffix.lower() == ".md":
                    item = QTreeWidgetItem(parent_item, [entry.name])
                    item.setData(0, Qt.ItemDataRole.UserRole, entry)
                    item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon))
            elif entry.is_dir():
                # Recursively check the contents of existing folders
                child_item = self.find_item_by_path(entry, parent_item)
                if child_item:
                    self._scan_remaining(entry, child_item)

    def save_order(self) -> None:
        """Persist the current tree structure to a JSON file."""
        data = self._get_item_data(self.invisibleRootItem())
        try:
            self._order_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._order_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving order: {e}")

    def load_order(self) -> list[dict] | None:
        """Load the persisted tree structure from JSON."""
        if not self._order_file.exists():
            return None
        try:
            with open(self._order_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading order: {e}")
            return None

    def _get_item_data(self, parent_item: QTreeWidgetItem) -> list[dict]:
        """Convert tree items to a serializable dictionary structure."""
        items = []
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            path = child.data(0, Qt.ItemDataRole.UserRole)
            item_info = {
                "name": child.text(0),
                "is_dir": path.is_dir(),
            }
            if item_info["is_dir"]:
                item_info["children"] = self._get_item_data(child)
            items.append(item_info)
        return items

    def _on_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(path, Path) and path.is_file():
            self.note_selected.emit(path)

    def find_item_by_path(self, path: Path, parent: QTreeWidgetItem | None = None) -> QTreeWidgetItem | None:
        """Recursively locate a tree item corresponding to a file path."""
        root = parent or self.invisibleRootItem()
        if root.data(0, Qt.ItemDataRole.UserRole) == path:
            return root
        
        for i in range(root.childCount()):
            child = root.child(i)
            res = self.find_item_by_path(path, child)
            if res:
                return res
        return None

    def add_item_to_ui(self, path: Path) -> None:
        """Add new item to the bottom position of its parent in UI if not already present."""
        if self.find_item_by_path(path):
            return

        parent_path = path.parent
        parent_item = self.find_item_by_path(parent_path) or self.invisibleRootItem()

        item = QTreeWidgetItem(parent_item, [path.name])
        item.setData(0, Qt.ItemDataRole.UserRole, path)
        
        if path.is_dir():
            item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon))
        else:
            item.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon))
        
        self.setCurrentItem(item)
        self.scrollToItem(item)
        self.save_order()

    def dropEvent(self, event) -> None:
        """Handle file/folder relocation on disk after a drag-and-drop operation."""
        selected_item = self.currentItem()
        if not selected_item:
            super().dropEvent(event)
            return

        old_path = selected_item.data(0, Qt.ItemDataRole.UserRole)
        
        # Execute the default drop behavior to update the UI
        super().dropEvent(event)
        
        # Calculate the new path based on the drop target
        new_parent_item = selected_item.parent() or self.invisibleRootItem()
        new_parent_path = new_parent_item.data(0, Qt.ItemDataRole.UserRole) or self.root_path
        
        new_path = new_parent_path / old_path.name
        
        if old_path != new_path:
            try:
                if old_path.exists():
                    shutil.move(str(old_path), str(new_path))
                    selected_item.setData(0, Qt.ItemDataRole.UserRole, new_path)
                    self.item_moved.emit(old_path, new_path)
                    # Recursively update paths if a directory was moved
                    if new_path.is_dir():
                        self._update_item_paths(selected_item, new_path)
            except Exception as e:
                QMessageBox.critical(self, "Move Failed", str(e))
                self.populate() # Refresh to sync disk state
        
        self.save_order()

    def _update_item_paths(self, parent_item: QTreeWidgetItem, new_parent_path: Path) -> None:
        """Update UserRole paths for all descendants of a moved directory."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            old_path = child.data(0, Qt.ItemDataRole.UserRole)
            new_path = new_parent_path / old_path.name
            child.setData(0, Qt.ItemDataRole.UserRole, new_path)
            if child.childCount() > 0:
                self._update_item_paths(child, new_path)

    def get_selected_path(self) -> Path:
        item = self.currentItem()
        if not item:
            return self.root_path
        return item.data(0, Qt.ItemDataRole.UserRole)


# ── Panels ─────────────────────────────────────────────────────────────

class NotesPanel(QWidget):
    """Sidebar panel displaying the file tree for notes."""
    note_selected = Signal(Path)
    item_moved = Signal(Path, Path)

    def __init__(self, vault_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.vault_path = vault_path
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = NotesTreeWidget(vault_path / "notes", vault_path)
        self.tree.note_selected.connect(self.note_selected.emit)
        self.tree.item_moved.connect(self.item_moved.emit)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.tree)

    def _show_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        menu = QMenu(self)

        target_dir = self.vault_path / "notes"
        if item:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            target_dir = path if path.is_dir() else path.parent

        act_new_note = menu.addAction("📄 New Note")
        act_new_folder = menu.addAction("📁 New Folder")

        act_rename = None
        act_delete = None
        if item:
            menu.addSeparator()
            act_rename = menu.addAction("✏️ Rename")
            act_delete = menu.addAction("🗑️ Delete")

        chosen = menu.exec(self.tree.mapToGlobal(pos))
        if chosen == act_new_note:
            self._create_new_note(target_dir)
        elif chosen == act_new_folder:
            self._create_new_folder(target_dir)
        elif item and act_rename and chosen == act_rename:
            self._rename_item(item)
        elif item and act_delete and chosen == act_delete:
            self._delete_item(item)

    def _rename_item(self, item: QTreeWidgetItem) -> None:
        old_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not old_path.exists():
            return
        
        is_folder = old_path.is_dir()
        old_name = old_path.stem if not is_folder else old_path.name
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        if ok and new_name.strip():
            new_name = new_name.strip()
            if not is_folder and not new_name.endswith(".md"):
                new_name += ".md"
            
            new_path = old_path.parent / new_name
            try:
                old_path.rename(new_path)
                item.setText(0, new_name)
                item.setData(0, Qt.ItemDataRole.UserRole, new_path)
                self.item_moved.emit(old_path, new_path)
                self.tree.save_order()
            except Exception as e:
                QMessageBox.critical(self, "Rename Failed", str(e))

    def _delete_item(self, item: QTreeWidgetItem) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path.exists():
            return
        
        if QMessageBox.question(self, "Delete", f"Permanently delete '{path.name}'?", 
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                # Remove from the tree UI
                parent = item.parent() or self.tree.invisibleRootItem()
                parent.removeChild(item)
                self.tree.save_order()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _create_new_note(self, parent_dir: Path) -> None:
        name, ok = QInputDialog.getText(self, "New Note", "Note Name:")
        if ok and name.strip():
            path = parent_dir / f"{name.strip()}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {name.strip()}\n\n", encoding="utf-8")
            self.tree.add_item_to_ui(path)
            self.note_selected.emit(path)

    def _create_new_folder(self, parent_dir: Path) -> None:
        name, ok = QInputDialog.getText(self, "New Folder", "Folder Name:")
        if ok and name.strip():
            path = parent_dir / name.strip()
            path.mkdir(parents=True, exist_ok=True)
            self.tree.add_item_to_ui(path)


class PapisPanel(QWidget):
    """Sidebar panel for browsing and filtering Papis literature entries."""
    pdf_selected = Signal(str, str)

    def __init__(self, config: NoterationConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._last_cited_keys: list[str] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Filter row controls
        f_row = QWidget()
        f_lay = QHBoxLayout(f_row)
        f_lay.setContentsMargins(0, 0, 0, 4)
        
        self.combo = QComboBox()
        self.combo.setFixedWidth(85)
        self.combo.addItem("All")
        self.combo.addItem("Linked")
        self.combo.currentTextChanged.connect(lambda _: self._filter())
        f_lay.addWidget(self.combo)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter keywords...")
        self.filter_edit.textChanged.connect(self._filter)
        f_lay.addWidget(self.filter_edit)
        layout.addWidget(f_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(0)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.tree)

    def populate(self) -> None:
        """Scan the Papis library and build the tree UI."""
        self.tree.clear()
        lit_dir = self.config.papis_library
        if not lit_dir.exists():
            return
        
        all_collections = set()
        
        # 1. Direct PDFs in library root
        for pdf_file in sorted(lit_dir.glob("*.pdf")):
            item = QTreeWidgetItem(self.tree, [f"📘 {pdf_file.name}"])
            item.setData(0, Qt.ItemDataRole.UserRole, {"key": pdf_file.stem, "pdf": pdf_file, "collections": []})
        
        # 2. Folder-based entries with info.yaml
        for entry_dir in sorted(lit_dir.iterdir()):
            if not entry_dir.is_dir() or not (entry_dir / "info.yaml").exists():
                continue
            try:
                import yaml  # type: ignore
                with open(entry_dir / "info.yaml") as f:
                    info = yaml.safe_load(f)
                title = info.get("title", entry_dir.name)[:40]
                colls = info.get("collections", [])
                for c in colls:
                    all_collections.add(str(c))
                pdf = list(entry_dir.glob("*.pdf"))
                item = QTreeWidgetItem(self.tree, [f"{'📘' if pdf else '📂'} {title}"])
                item.setData(0, Qt.ItemDataRole.UserRole, {"key": entry_dir.name, "pdf": pdf[0] if pdf else None, "collections": [str(c) for c in colls]})
            except Exception:
                pass

        # Update collection filter dropdown
        curr = self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(["All", "Linked"] + sorted(list(all_collections)))
        if curr in ["All", "Linked"] or curr in all_collections:
            self.combo.setCurrentText(curr)
        self.combo.blockSignals(False)
        self._filter()

    def _filter(self) -> None:
        """Apply current filter/search criteria to tree items."""
        coll_f = self.combo.currentText()
        search_q = self.filter_edit.text().lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if not item:
                continue
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            c_match = True
            if coll_f == "Linked":
                c_match = data.get("key") in self._last_cited_keys
            elif coll_f != "All":
                c_match = coll_f in data.get("collections", [])
            s_match = search_q in item.text(0).lower()
            item.setHidden(not (c_match and s_match))

    def update_cited(self, keys: list[str]) -> None:
        """Signal update for literature entries referenced in the active note."""
        self._last_cited_keys = keys
        if self.combo.currentText() == "Linked":
            self._filter()

    def _on_double_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("pdf"):
            self.pdf_selected.emit(str(data["pdf"]), data.get("key", ""))


class OutlinePanel(QWidget):
    """Sidebar panel displaying a hierarchical heading outline of the active note."""
    heading_clicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.model = HeadingModel(self)
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(10)
        self.tree.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree)

    def update_outline(self, headings: list[tuple[int, str]]) -> None:
        self.model.set_headings(headings)
        self.tree.expandAll()

    def _on_double_click(self, index: QModelIndex) -> None:
        h = index.data(Qt.ItemDataRole.UserRole)
        if h:
            self.heading_clicked.emit(h)


class CitationsPanel(QWidget):
    """Sidebar panel listing all @citations found in the current note."""
    citation_clicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.model = CitationModel(self)
        self.list = QListView()
        self.list.setModel(self.model)
        self.list.setFont(QFont("Monospace", 9))
        self.list.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.list)

    def update_citations(self, keys: list[str]) -> None:
        self.model.set_citations(keys)

    def _on_double_click(self, index: QModelIndex) -> None:
        k = index.data(Qt.ItemDataRole.UserRole)
        if k:
            self.citation_clicked.emit(k)


# ── Main Sidebar ───────────────────────────────────────────────────────

class SidebarWidget(QWidget):
    """
    Main Sidebar container with tabbed panels for navigation and metadata.
    """
    note_selected = Signal(object)
    pdf_selected = Signal(str, str)
    heading_clicked = Signal(str)
    citation_clicked = Signal(str)
    item_moved = Signal(object, object)

    def __init__(self, vault_path: Path, config: NoterationConfig, parent=None) -> None:
        super().__init__(parent)
        self.vault_path = vault_path
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        
        self.notes_panel = NotesPanel(vault_path)
        self.notes_panel.note_selected.connect(self.note_selected.emit)
        self.notes_panel.item_moved.connect(self.item_moved.emit)
        
        self.papis_panel = PapisPanel(config)
        self.papis_panel.pdf_selected.connect(self.pdf_selected.emit)
        
        self.outline_panel = OutlinePanel()
        self.outline_panel.heading_clicked.connect(self.heading_clicked.emit)
        
        self.citations_panel = CitationsPanel()
        self.citations_panel.citation_clicked.connect(self.citation_clicked.emit)

        self.tabs.addTab(self.notes_panel, "Notes")
        self.tabs.addTab(self.papis_panel, "PDFs")
        self.tabs.addTab(self.outline_panel, "Outline")
        self.tabs.addTab(self.citations_panel, "Citations")
        
        layout.addWidget(self.tabs)
        self.papis_panel.populate()

    def update_outline(self, headings: list[tuple[int, str]]) -> None:
        self.outline_panel.update_outline(headings)

    def update_citations(self, keys: list[str]) -> None:
        self.citations_panel.update_citations(keys)

    def update_cited_pdfs(self, keys: list[str]) -> None:
        self.papis_panel.update_cited(keys)

    def add_note(self, path: Path) -> None:
        self.notes_panel.tree.add_item_to_ui(path)

    def refresh(self) -> None:
        self.notes_panel.tree.populate()
        self.papis_panel.populate()
