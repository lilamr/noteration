import pytest

from noteration.db.link_graph import LinkGraph


@pytest.fixture
def link_graph(temp_vault):
    # Setup some dummy notes
    (temp_vault / "notes").mkdir(exist_ok=True)
    (temp_vault / "notes" / "n1.md").write_text("[[n2]]")
    (temp_vault / "notes" / "n2.md").write_text("content")
    
    return LinkGraph(temp_vault)

def test_link_graph_init(link_graph):
    assert link_graph.vault_path is not None

def test_rebuild_graph(link_graph):
    # The rebuild might take time, we trigger it explicitly
    edge_count = link_graph.rebuild(force=True)
    assert edge_count >= 1
    
def test_links(link_graph):
    link_graph.rebuild(force=True)
    assert "n2" in link_graph.forward_links("n1")
    assert "n1" in link_graph.backlinks("n2")

def test_shortest_path(temp_vault, link_graph):
    # Setup a longer path
    (temp_vault / "notes" / "n3.md").write_text("[[n1]]")
    
    link_graph.rebuild(force=True)
    path = link_graph.shortest_path("n3", "n2")
    assert path == ["n3", "n1", "n2"]
