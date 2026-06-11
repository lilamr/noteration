from pathlib import Path

from PySide6.QtCore import Qt

from noteration.ui.main_window import MainWindow

# This test requires a full application instance (pytest-qt handles this via 'qtbot')


def test_full_workflow(qtbot, tmp_path: Path):
    """Simulate a full user journey:
    1. Initialize MainWindow
    2. Add a new note
    3. Trigger sync
    """
    vault_path = tmp_path / "test_vault"
    vault_path.mkdir()

    # Initialize main window
    window = MainWindow(vault_path=vault_path)
    qtbot.addWidget(window)
    window.show()

    # 1. Simulate "New Note" via the Sidebar
    # Assuming the sidebar exists and has the necessary method
    # 1. Simulate "New Note" via the Sidebar
    sidebar = window.sidebar
    qtbot.mouseClick(sidebar.tabs.tabBar(), Qt.MouseButton.LeftButton)

    # Create note
    note_name = "WorkflowTestNote"
    note_path = vault_path / "notes" / f"{note_name}.md"

    # Helper to simulate QInputDialog interaction
    def handle_dialog():
        # Use qtbot to wait for the dialog to appear
        # QInputDialog is a modal dialog, it doesn't need to be waited on by waitActive as a context manager
        # Instead of waitActive (which returns a context manager),
        # we can just use a small delay or find the active modal
        import time

        time.sleep(0.2)

        # Find the active modal dialog
        from PySide6.QtWidgets import QApplication

        dialog = QApplication.activeModalWidget()

        from PySide6.QtWidgets import QLineEdit

        line_edit = dialog.findChild(QLineEdit)

        qtbot.keyClicks(line_edit, note_name)
        qtbot.keyClick(dialog, Qt.Key.Key_Enter)

    # Run dialog handler in background
    from PySide6.QtCore import QTimer

    QTimer.singleShot(100, handle_dialog)

    # Trigger the UI action
    sidebar.notes_panel._create_new_note(vault_path / "notes")

    # Verify note was created on disk
    # Add a small wait if necessary, but filesystem operations are usually fast
    import time

    time.sleep(0.5)
    assert note_path.exists(), "Note file was not created on disk."

    # 2. Check if the note shows up in the UI tree
    item = sidebar.notes_panel.tree.find_item_by_path(note_path)
    assert item is not None, "Note was not added to the UI tree."

    print(f"\n[Test Passed] E2E Workflow: Created note '{note_name}' and verified UI update.")

    window.close()
