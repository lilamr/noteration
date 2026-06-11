from unittest.mock import patch

from noteration.controllers.index_controller import IndexController
from noteration.controllers.library_controller import LibraryController
from noteration.controllers.sync_controller import SyncController
from noteration.core.vault_core import VaultCore


def _wait_for_thread(controller, attr_name):
    thread = getattr(controller, attr_name, None)
    if thread and thread.isRunning():
        thread.requestInterruption()
        thread.quit()
        thread.wait(10000)
    setattr(controller, attr_name, None)


def test_index_controller_lifecycle(qtbot, temp_vault):
    """Test that IndexController can start and shutdown gracefully."""
    core = VaultCore(temp_vault)
    controller = IndexController(core.pdf_index, core.graph, core.fts, core.papis, core.notes)

    # 1. Trigger background tasks
    controller.scan_pdfs()
    controller.build_graph()

    # 2. Test shutdown
    controller.shutdown()

    # Verify threads are cleaned up
    assert controller._scan_thread is None
    assert controller._graph_thread is None


def test_sync_controller_lifecycle(qtbot, temp_vault):
    """Test that SyncController handles background status checks and shutdown."""
    core = VaultCore(temp_vault)
    controller = SyncController(core)

    # 1. Request status (creates a thread)
    controller.request_status()

    # 2. Immediate shutdown using patch to force a blocking wait
    with patch.object(
        controller, "_safe_stop_thread", side_effect=lambda attr: _wait_for_thread(controller, attr)
    ):
        controller.shutdown()

    assert controller._status_thread is None


def test_library_controller_lifecycle(qtbot, temp_vault):
    """Test that LibraryController handles background loading and shutdown."""
    core = VaultCore(temp_vault)
    controller = LibraryController(core.papis)

    # 1. Start loading literature
    controller.load_entries()

    # 2. Shutdown using patch to force a blocking wait
    with patch.object(
        controller, "_safe_stop_thread", side_effect=lambda attr: _wait_for_thread(controller, attr)
    ):
        controller.shutdown()

    assert controller._load_thread is None


def test_controller_signals(qtbot, temp_vault):
    """Verify that controllers emit basic signals (using IndexController as example)."""
    core = VaultCore(temp_vault)
    controller = IndexController(core.pdf_index, core.graph, core.fts, core.papis, core.notes)

    # Create some content to index
    note_path = temp_vault / "notes" / "test.md"
    note_path.write_text("# Test Note", encoding="utf-8")

    with qtbot.waitSignal(controller.indexing_finished, timeout=5000):
        controller.scan_pdfs()

    with qtbot.waitSignal(controller.graph_updated, timeout=5000):
        controller.build_graph()

    # Test shutdown
    controller.shutdown()
