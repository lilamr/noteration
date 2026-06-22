from pathlib import Path

from PySide6.QtWidgets import QTabWidget

from noteration.config import NoterationConfig
from noteration.core.session_state import SessionStateStore
from noteration.ui.editor_tab import EditorTab
from noteration.ui.literature_tab import LiteratureTab
from noteration.ui.main_window import MainWindow
from noteration.ui.pdf_viewer_tab import PdfViewerTab
from noteration.ui.sync_tab import SyncTab
from noteration.ui.tab_base import NoterationTab
from noteration.vault_manager import VaultManager


class _DummySessionTab(NoterationTab):
    def __init__(self, state: dict, parent=None) -> None:
        super().__init__(parent)
        self._state = state

    def session_state(self) -> dict:
        return self._state


def _make_minimal_main_window(temp_vault: Path, qtbot) -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window.tabs = QTabWidget()
    window.tabs_split = QTabWidget()
    window.config = NoterationConfig(temp_vault)
    window._session_store = SessionStateStore(temp_vault)
    window._active_tab_widget = window.tabs
    qtbot.addWidget(window.tabs)
    qtbot.addWidget(window.tabs_split)
    return window


def test_session_state_methods_use_relative_paths(temp_vault: Path) -> None:
    note_path = temp_vault / "notes" / "note.md"
    pdf_path = temp_vault / "attachments" / "paper.pdf"

    editor_tab = EditorTab.__new__(EditorTab)
    editor_tab.file_path = note_path
    editor_tab.vault_path = temp_vault

    pdf_tab = PdfViewerTab.__new__(PdfViewerTab)
    pdf_tab.pdf_path = pdf_path
    pdf_tab.papis_key = "paper-key"
    pdf_tab.vault_path = temp_vault

    assert EditorTab.session_state(editor_tab) == {
        "type": "editor",
        "path": "notes/note.md",
    }
    assert PdfViewerTab.session_state(pdf_tab) == {
        "type": "pdf",
        "path": "attachments/paper.pdf",
        "papis_key": "paper-key",
    }
    assert LiteratureTab.session_state(LiteratureTab.__new__(LiteratureTab)) == {"type": "literature"}
    assert SyncTab.session_state(SyncTab.__new__(SyncTab)) == {"type": "sync"}


def test_save_session_writes_session_json_not_config(temp_vault: Path, qtbot) -> None:
    window = _make_minimal_main_window(temp_vault, qtbot)
    window.tabs.addTab(_DummySessionTab({"type": "editor", "path": "notes/a.md"}), "main")
    window.tabs_split.addTab(_DummySessionTab({"type": "pdf", "path": "attachments/a.pdf"}), "split")
    window._active_tab_widget = window.tabs_split

    window._save_session()

    session_path = temp_vault / ".noteration" / "session.json"
    assert session_path.exists()
    assert SessionStateStore(temp_vault).load() == {
        "open_tabs": [
            {"type": "editor", "path": "notes/a.md", "pane": "main"},
            {"type": "pdf", "path": "attachments/a.pdf", "pane": "split"},
        ],
        "active_pane": "split",
    }
    assert window.config.get("session", "open_tabs") is None
    assert window.config.get("session", "active_pane") is None


def test_restore_session_opens_saved_editor_tabs_in_panes(temp_vault: Path, qtbot) -> None:
    note_1 = temp_vault / "notes" / "note1.md"
    note_2 = temp_vault / "notes" / "note2.md"
    note_1.write_text("# Note 1\n", encoding="utf-8")
    note_2.write_text("# Note 2\n", encoding="utf-8")
    SessionStateStore(temp_vault).save(
        [
            {"type": "editor", "path": "notes/note1.md", "pane": "main"},
            {"type": "editor", "path": "notes/note2.md", "pane": "split"},
        ],
        "split",
    )

    config = NoterationConfig(temp_vault)
    config.set("general", "restore_last_session", False)

    window = MainWindow(temp_vault)
    qtbot.addWidget(window)
    window.config.set("general", "restore_last_session", False)
    try:
        window.config.set("general", "restore_last_session", True)
        window._restore_session()

        assert window.tabs.count() == 1
        assert window.tabs_split.count() == 1
        assert not window.tabs_split.isHidden()
        assert window.tabs.tabText(0) == "note1.md"
        assert window.tabs_split.tabText(0) == "note2.md"
        assert window._active_tab_widget is window.tabs_split
    finally:
        window.close()


def test_restore_session_skips_missing_files(temp_vault: Path, qtbot) -> None:
    config = NoterationConfig(temp_vault)
    config.set("general", "restore_last_session", False)
    SessionStateStore(temp_vault).save(
        [{"type": "editor", "path": "notes/missing.md", "pane": "main"}],
        "main",
    )

    window = MainWindow(temp_vault)
    qtbot.addWidget(window)
    window.config.set("general", "restore_last_session", False)
    try:
        window.config.set("general", "restore_last_session", True)
        window._restore_session()

        assert window.tabs.count() == 0
        assert window.tabs_split.count() == 0
        assert window._active_tab_widget is window.tabs
    finally:
        window.close()


def test_restore_session_disabled_returns_without_opening_tabs(temp_vault: Path, qtbot) -> None:
    note_path = temp_vault / "notes" / "note.md"
    note_path.write_text("# Note\n", encoding="utf-8")
    config = NoterationConfig(temp_vault)
    config.set("general", "restore_last_session", False)
    SessionStateStore(temp_vault).save(
        [{"type": "editor", "path": "notes/note.md", "pane": "main"}],
        "main",
    )

    window = MainWindow(temp_vault)
    qtbot.addWidget(window)
    window.config.set("general", "restore_last_session", False)
    try:
        window._restore_session()

        assert window.tabs.count() == 0
        assert window.tabs_split.count() == 0
    finally:
        window.close()


def test_close_event_saves_session_before_shutdown(temp_vault: Path, qtbot) -> None:
    note_path = temp_vault / "notes" / "note.md"
    note_path.write_text("# Note\n", encoding="utf-8")

    window = MainWindow(temp_vault)
    qtbot.addWidget(window)
    window._open_note(note_path)

    window.close()

    vault = VaultManager(temp_vault)
    try:
        assert SessionStateStore(temp_vault).load() == {
            "open_tabs": [{"type": "editor", "path": "notes/note.md", "pane": "main"}],
            "active_pane": "main",
        }
        assert vault.config.get("session", "open_tabs") is None
        assert vault.config.get("session", "active_pane") is None
    finally:
        vault.shutdown()


def test_config_drops_legacy_session_section(temp_vault: Path) -> None:
    config_path = temp_vault / ".noteration" / "config.toml"
    config_path.write_text(
        "[general]\n"
        "restore_last_session = true\n\n"
        "[session]\n"
        'open_tabs = [{ type = "editor", path = "notes/old.md", pane = "main" }]\n'
        'active_pane = "main"\n',
        encoding="utf-8",
    )

    config = NoterationConfig(temp_vault)
    assert config.get("session", "open_tabs") is None
    config.save()

    assert "[session]" not in config_path.read_text(encoding="utf-8")
