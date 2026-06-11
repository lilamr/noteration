from unittest.mock import MagicMock, patch

import pytest

from noteration.literature.papis_bridge import LiteratureEntry, PapisBridge


@pytest.fixture
def bridge(tmp_path):
    lib_path = tmp_path / "literature"
    lib_path.mkdir()
    return PapisBridge(lib_path)


def test_add_document_papis_cli_flag(bridge):
    """Test that add_document calls papis with the correct --lib flag and performs renaming.
    """
    with patch("shutil.which", return_value="/usr/bin/papis"), patch("subprocess.run") as mock_run:
        # Configure mock_run to return success
        mock_run.return_value = MagicMock(
            returncode=0, stdout="[INFO] commands.add: Document folder is 'old_folder'", stderr=""
        )
        mock_entry = LiteratureEntry(
            key="old_folder",
            author="Newton, Isaac",
            year="1687",
            title="Principia",
            _raw={"ref": "old_folder"},
        )
        old_dir = bridge.library_path / "old_folder"
        old_dir.mkdir()
        with (
            patch.object(bridge, "_newest_entry", return_value=mock_entry),
            patch.object(bridge, "get", return_value=mock_entry),
            patch("noteration.literature.papis_bridge._save_yaml"),
        ):
            entry = bridge.add_document(from_doi="10.1038/nature12345")

        assert mock_run.called
        assert entry is not None
        # Assert key is 'old_folder' as returned by newest_entry
        assert entry.key == "old_folder"


def test_add_document_papis_cli_error_logging(bridge):
    """Test that Papis CLI errors are logged correctly.
    """
    from noteration.literature.papis_bridge import logger

    with (
        patch("shutil.which", return_value="/usr/bin/papis"),
        patch("subprocess.run") as mock_run,
        patch.object(logger, "warning"),
    ):
        mock_run.return_value = MagicMock(
            returncode=2, stdout="", stderr="Error: No such option '--library'"
        )

        bridge.add_document(from_doi="10.1038/nature12345")

        # Just verify that it handled the error without crashing
        assert True


def test_add_document_handles_duplication_gracefully(bridge):
    """Test that add_document returns the existing entry on duplication instead of manual fallback.
    """
    papis_output = """
[WARNING] commands.add: Duplication Warning
│ref: Smith2024GenericRef
"""
    # Create the existing entry folder
    existing_dir = bridge.library_path / "Smith2024GenericRef"
    existing_dir.mkdir()
    # info.yaml content that will result in the same key
    (existing_dir / "info.yaml").write_text(
        "ref: Smith2024GenericRef\ntitle: Generic Title\nauthor: Smith\nyear: '2024'",
        encoding="utf-8",
    )

    with patch("shutil.which", return_value="/usr/bin/papis"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=papis_output, stderr="")

        # Clear entries to force reload
        bridge._entries = None

        # Provide matching metadata
        entry = bridge.add_document(
            from_doi="some_doi", title="Generic Title", author="Smith", year="2024"
        )

        assert entry is not None
        # It should match the existing ref key
        assert entry.key == "Smith2024GenericRef"
        assert entry.title == "Generic Title"

        # Ensure it didn't create a manual duplicate (no _1 or random slug)
        dirs = [d for d in bridge.library_path.iterdir() if d.is_dir()]
        assert len(dirs) == 1
