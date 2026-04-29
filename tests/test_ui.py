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

def test_editor_tab_word_count(qtbot, temp_vault):
    """Test word count logic in EditorTab."""
    from noteration.ui.editor_tab import EditorTab
    from noteration.vault_manager import VaultManager
    
    vault = VaultManager(temp_vault)
    note_path = temp_vault / "notes" / "test.md"
    note_path.write_text("---\ntitle: test\n---\n# Hello\nThis is a test.\n```python\nprint(1)\n```", encoding="utf-8")
    
    tab = EditorTab(note_path, vault)
    qtbot.addWidget(tab)
    
    # "Hello", "This", "is", "a", "test" = 5 words
    # Frontmatter and code block should be excluded
    assert tab.word_count() == 5
