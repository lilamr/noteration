import pytest

from noteration.search.fts_engine import FTSEngine


@pytest.fixture
def fts_engine(temp_vault):
    return FTSEngine(temp_vault)

def test_fts_init(temp_vault, fts_engine):
    assert (temp_vault / ".noteration" / "search.db").exists()

def test_index_and_search_note(fts_engine):
    fts_engine.index_note("n1", "Test Title", "This is some test content.", 123.45)
    results = fts_engine.search_notes("test")
    assert len(results) == 1
    assert results[0]["note_id"] == "n1"
    assert "Test Title" in results[0]["title"]

def test_index_tags(fts_engine):
    fts_engine.index_tags("n1", ["tag1", "tag2"], source="note")
    assert fts_engine.get_tags_for_note("n1") == ["tag1", "tag2"]
    assert fts_engine.get_notes_with_tag("tag1") == ["n1"]

def test_remove_note(fts_engine):
    fts_engine.index_note("n1", "Title", "Content", 123.45)
    fts_engine.remove_note("n1")
    assert fts_engine.search_notes("Title") == []

def test_needs_update(fts_engine):
    fts_engine.index_note("n1", "Title", "Content", 100.0)
    assert not fts_engine.needs_update("n1", 99.0)
    assert fts_engine.needs_update("n1", 101.0)
