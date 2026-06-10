from noteration.dialogs.vault_picker import VaultPickerDialog
from noteration.ui.main_window import MainWindow


def test_vault_picker_init(qtbot):
    """Test that VaultPickerDialog initializes correctly."""
    dlg = VaultPickerDialog()
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == "Noteration — Select Vault"


def test_main_window_init(qtbot, temp_vault):
    """Test that MainWindow initializes with a vault."""
    window = MainWindow(temp_vault)
    qtbot.addWidget(window)
    assert temp_vault.name in window.windowTitle()
    assert window.tabs.count() == 0
    window.close()


def test_editor_tab_word_count(qtbot, temp_vault):
    """Test word count logic in EditorTab."""
    from noteration.ui.editor_tab import EditorTab
    from noteration.vault_manager import VaultManager

    vault = VaultManager(temp_vault)
    note_path = temp_vault / "notes" / "test.md"
    note_path.write_text(
        "---\ntitle: test\n---\n# Hello\nThis is a test.\n```python\nprint(1)\n```",
        encoding="utf-8",
    )

    tab = EditorTab(note_path, vault)
    qtbot.addWidget(tab)

    # "Hello", "This", "is", "a", "test" = 5 words
    # Frontmatter and code block should be excluded
    assert tab.word_count() == 5
    tab.shutdown()
    vault.shutdown()


def test_split_view_behavior(qtbot, temp_vault):
    """Test split view creation, tab movement, and splitter adjustment."""
    window = MainWindow(temp_vault)
    qtbot.addWidget(window)

    # 1. Initially, tabs_split should be hidden, and both tabs and tabs_split empty
    assert window.tabs.count() == 0
    assert window.tabs_split.count() == 0
    assert window.tabs_split.isHidden()

    # 2. Open two notes
    note_path_1 = temp_vault / "notes" / "note1.md"
    note_path_1.parent.mkdir(parents=True, exist_ok=True)
    note_path_1.write_text("# Note 1\nContent 1", encoding="utf-8")

    note_path_2 = temp_vault / "notes" / "note2.md"
    note_path_2.write_text("# Note 2\nContent 2", encoding="utf-8")

    window._open_note(note_path_1)
    window._open_note(note_path_2)

    assert window.tabs.count() == 2
    assert window.tabs_split.count() == 0

    # 3. Move the second tab (note2.md) to the split view
    # Index of note2 is 1 (since note1 was opened first)
    window._move_tab(window.tabs, window.tabs_split, 1)

    # Verify split view is visible and tabs are partitioned
    assert window.tabs.count() == 1
    assert window.tabs_split.count() == 1
    assert not window.tabs_split.isHidden()
    assert window.tabs.tabText(0) == "note1.md"
    assert window.tabs_split.tabText(0) == "note2.md"

    # 4. Move the tab back to the main view
    window._move_tab(window.tabs_split, window.tabs, 0)

    # Verify split view hides and tabs are merged
    assert window.tabs.count() == 2
    assert window.tabs_split.isHidden()

    window.close()
