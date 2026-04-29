from noteration.editor.wiki_links import (
    parse_wiki_links, parse_citations, extract_headings, resolve_link
)

def test_parse_wiki_links():
    text = "See [[Main Note]] and [[note-2|Alias]] as well as [[note-3#Heading 1]]"
    links = parse_wiki_links(text)
    
    assert len(links) == 3
    assert links[0].target == "Main Note"
    assert links[1].target == "note-2"
    assert links[1].alias == "Alias"
    assert links[2].target == "note-3"
    assert links[2].heading == "Heading 1"

def test_parse_citations():
    text = "As cited by @newton1687 and @darwin1859."
    cites = parse_citations(text)
    
    assert len(cites) == 2
    assert cites[0].key == "newton1687"
    assert cites[1].key == "darwin1859"

def test_extract_headings():
    text = "# Title\n## Section 1\n```\n# Not a heading\n```\n### Subsection"
    headings = extract_headings(text)
    
    assert len(headings) == 3
    assert headings[0] == (1, "Title")
    assert headings[1] == (2, "Section 1")
    assert headings[2] == (3, "Subsection")

def test_resolve_link(temp_vault):
    note_path = temp_vault / "notes" / "research.md"
    note_path.write_text("# Research", encoding="utf-8")
    
    # Direct match
    assert resolve_link("research", temp_vault) == note_path
    # Case-insensitive
    assert resolve_link("RESEARCH", temp_vault) == note_path
    # Nested match (if it existed)
    sub_dir = temp_vault / "notes" / "drafts"
    sub_dir.mkdir()
    sub_note = sub_dir / "idea.md"
    sub_note.write_text("# Idea", encoding="utf-8")
    
    assert resolve_link("drafts/idea", temp_vault) == sub_note
    assert resolve_link("idea", temp_vault) == sub_note
