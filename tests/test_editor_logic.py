from noteration.editor.wiki_links import parse_wiki_links, parse_citations, extract_headings

def test_parse_wiki_links():
    text = "Lihat [[Catatan Utama]] dan [[note-2|Alias]] serta [[note-3#Heading 1]]"
    links = parse_wiki_links(text)
    
    assert len(links) == 3
    assert links[0].target == "Catatan Utama"
    assert links[0].alias is None
    
    assert links[1].target == "note-2"
    assert links[1].alias == "Alias"
    
    assert links[2].target == "note-3"
    assert links[2].heading == "Heading 1"

def test_parse_citations():
    text = "Sesuai dengan @Smith2023 dan @Doe:2024."
    cites = parse_citations(text)
    
    assert len(cites) == 2
    assert cites[0].key == "Smith2023"
    assert cites[1].key == "Doe:2024"

def test_extract_headings():
    text = """
# Judul 1
Beberapa teks.
## Subjudul A
Teks lagi.
```python
# Ini komentar, bukan heading
```
### Subjudul B
    """
    headings = extract_headings(text)
    
    assert len(headings) == 3
    assert headings[0] == (1, "Judul 1")
    assert headings[1] == (2, "Subjudul A")
    assert headings[2] == (3, "Subjudul B")
