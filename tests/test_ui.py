from noteration.dialogs.vault_picker import VaultPickerDialog
from noteration.ui.main_window import MainWindow

def test_vault_picker_init(qtbot):
    """Test that VaultPickerDialog initializes correctly."""
    dlg = VaultPickerDialog()
    qtbot.add_widget(dlg)
    
    assert dlg.windowTitle() == "Noteration — Pilih Vault"
    # Button is enabled only if there is a selected item
    if dlg._list.count() == 0:
        assert not dlg._btn_open.isEnabled()
    else:
        assert dlg._btn_open.isEnabled()

def test_main_window_init(qtbot, temp_vault):
    """Test that MainWindow initializes correctly with a vault."""
    # Ensure structure is there
    for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
        (temp_vault / sub).mkdir(parents=True, exist_ok=True)
        
    window = MainWindow(temp_vault)
    qtbot.add_widget(window)
    
    assert "Noteration" in window.windowTitle()
    assert window.vault_path == temp_vault
    assert window.tabs.count() == 0  # No tabs at start

def test_main_window_open_note(qtbot, temp_vault):
    """Test opening a note in MainWindow."""
    note_path = temp_vault / "notes" / "test-note.md"
    note_path.write_text("# Test Note", encoding="utf-8")
    
    window = MainWindow(temp_vault)
    qtbot.add_widget(window)
    
    window._open_note(note_path)
    assert window.tabs.count() == 1
    assert window.tabs.tabText(0) == "test-note.md"
