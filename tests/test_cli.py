import pytest
from click.testing import CliRunner

from noteration.cli.main import cli


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_cli_info(cli_runner, temp_vault):
    result = cli_runner.invoke(cli, ["--vault", str(temp_vault), "info"])
    assert result.exit_code == 0
    assert f"Vault Path: {temp_vault}" in result.output


def test_cli_note_new_and_list(cli_runner, temp_vault):
    # Create note
    result = cli_runner.invoke(cli, ["--vault", str(temp_vault), "note", "new", "test-note"])
    assert result.exit_code == 0
    assert "Created note" in result.output
    assert (temp_vault / "notes" / "test-note.md").exists()

    # List notes
    result = cli_runner.invoke(cli, ["--vault", str(temp_vault), "note", "list"])
    assert result.exit_code == 0
    assert "test-note" in result.output


def test_cli_note_show(cli_runner, temp_vault):
    note_path = temp_vault / "notes" / "hello.md"
    note_path.write_text("# Hello World\nSome content", encoding="utf-8")

    result = cli_runner.invoke(cli, ["--vault", str(temp_vault), "note", "show", "hello"])
    assert result.exit_code == 0
    assert "Hello World" in result.output


def test_cli_note_delete(cli_runner, temp_vault):
    note_path = temp_vault / "notes" / "delete-me.md"
    note_path.write_text("content", encoding="utf-8")

    # Delete with confirmation flag
    result = cli_runner.invoke(
        cli, ["--vault", str(temp_vault), "note", "delete", "delete-me", "--confirm"]
    )
    assert result.exit_code == 0
    assert not note_path.exists()


def test_cli_search(cli_runner, temp_vault):
    # Search requires FTS which might need some setup or just run on empty vault
    result = cli_runner.invoke(cli, ["--vault", str(temp_vault), "search", "anything"])
    # If FTS is initialized, it should return 0 but "No results found"
    assert result.exit_code == 0
    assert "No results found" in result.output


def test_cli_tags_list(cli_runner, temp_vault):
    note_path = temp_vault / "notes" / "tagged.md"
    note_path.write_text("# Title\n#mytag", encoding="utf-8")

    # We might need to index first if the CLI doesn't do it automatically on query
    # But usually VaultCore initializes FTS which might do a quick scan if enabled
    result = cli_runner.invoke(cli, ["--vault", str(temp_vault), "tags", "list"])
    assert result.exit_code == 0


def test_cli_graph_stats(cli_runner, temp_vault):
    result = cli_runner.invoke(cli, ["--vault", str(temp_vault), "graph", "stats"])
    assert result.exit_code == 0
    assert "Total notes" in result.output
