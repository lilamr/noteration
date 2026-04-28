"""
noteration/db/link_graph.py

Graf backlink antar note berbasis NetworkX.
Disimpan sebagai JSON di .noteration/link_graph.json.

Fitur:
  - build_from_vault(): scan seluruh vault, ekstrak [[wiki-link]]
  - backlinks(note): siapa yang menautkan ke note ini?
  - forward_links(note): note ini menautkan ke mana?
  - orphans(): note yang tidak ditautkan dari mana pun
  - most_linked(): note paling banyak ditautkan (hub)
  - shortest_path(src, dst): jalur terpendek antara dua note
  - to_json() / from_json(): serialisasi untuk export/visualisasi
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    import networkx as nx        # type: ignore
    _HAS_NX = True
except ImportError:
    _HAS_NX = False

from noteration.editor.wiki_links import parse_wiki_links, resolve_link


_GRAPH_FILE = ".noteration/link_graph.json"


class LinkGraph:
    """
    Graf terarah: tepi A → B berarti note A memiliki [[link ke B]].
    Jika networkx tidak tersedia, fall back ke implementasi dict sederhana.
    """

    def __init__(self, vault_path: Path) -> None:
        self.vault_path  = vault_path
        self._graph_path = vault_path / _GRAPH_FILE
        self._notes_dir  = vault_path / "notes"
        # Internal: dict adjacency saat nx tidak ada
        self._adj:  dict[str, set[str]] = {}   # A → {B, C, ...}
        self._radj: dict[str, set[str]] = {}   # B → {A, ...}  (reverse)
        self._G = None  # nx.DiGraph jika tersedia

        if _HAS_NX:
            self._G = nx.DiGraph()

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_note_id(self, path: Path) -> str:
        """Absolute path -> relative ID (e.g. folder/note)."""
        try:
            rel = path.relative_to(self._notes_dir)
            return str(rel.with_suffix(""))
        except ValueError:
            return path.stem

    def _resolve_target_to_id(self, target: str) -> str | None:
        """Resolve [[target]] to its relative note_id."""
        path = resolve_link(target, self.vault_path)
        if path:
            return self._get_note_id(path)
        return None

    # ── Build ─────────────────────────────────────────────────────────

    def build_from_vault(self, notes_dir: Path | None = None) -> int:
        """
        Scan semua file .md, ekstrak [[wiki-link]], bangun graf.
        Return: jumlah tepi (link) yang ditemukan.
        """
        nd = notes_dir or self._notes_dir
        self._adj.clear()
        self._radj.clear()
        if self._G is not None:
            self._G.clear()

        edge_count = 0
        for md_file in sorted(nd.rglob("*.md")):
            src = self._get_note_id(md_file)
            self._ensure_node(src)
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            for link in parse_wiki_links(text):
                dst = self._resolve_target_to_id(link.target)
                if dst and dst != src:
                    self._add_edge(src, dst)
                    edge_count += 1

        self.save()
        return edge_count

    def update_note(self, note_path: Path) -> None:
        """Update graf untuk satu note yang berubah (incremental)."""
        src = self._get_note_id(note_path)

        # Hapus tepi lama dari src
        old_targets = set(self._adj.get(src, set()))
        for dst in old_targets:
            self._radj.get(dst, set()).discard(src)
        self._adj[src] = set()
        if self._G is not None:
            if src in self._G:
                self._G.remove_edges_from(
                    [(src, dst) for dst in old_targets])

        # Tambah tepi baru
        try:
            text = note_path.read_text(encoding="utf-8")
            for link in parse_wiki_links(text):
                dst = self._resolve_target_to_id(link.target)  # type: ignore[assignment]
                if dst and dst != src:
                    self._add_edge(src, dst)
        except Exception:
            pass

        self.save()

    # ── Queries ───────────────────────────────────────────────────────

    def backlinks(self, note_id: str) -> list[str]:
        """Note mana yang menautkan KE note ini."""
        return sorted(self._radj.get(note_id, set()))

    def forward_links(self, note_id: str) -> list[str]:
        """Note mana yang ditautkan DARI note ini."""
        return sorted(self._adj.get(note_id, set()))

    def all_nodes(self) -> list[str]:
        return sorted(self._adj.keys())

    def orphans(self) -> list[str]:
        """Note yang tidak memiliki backlink dari mana pun."""
        return [
            n for n in self._adj
            if not self._radj.get(n)
        ]

    def most_linked(self, top_n: int = 10) -> list[tuple[str, int]]:
        """Top-N note berdasarkan jumlah backlink (in-degree)."""
        counts = [
            (n, len(self._radj.get(n, set())))
            for n in self._adj
        ]
        return sorted(counts, key=lambda x: -x[1])[:top_n]

    def shortest_path(self, src: str, dst: str) -> list[str] | None:
        """
        Jalur terpendek antara dua note.
        Return None jika tidak ada jalur atau networkx tidak tersedia.
        """
        if self._G is None:
            return self._bfs_path(src, dst)
        try:
            path = nx.shortest_path(self._G, src, dst)
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def connected_cluster(self, note_stem: str) -> set[str]:
        """
        Semua note yang terhubung (langsung atau tidak) ke note ini.
        """
        if self._G is None:
            return self._reachable(note_stem)
        try:
            # Pakai undirected projection untuk cluster
            ug = self._G.to_undirected()
            if note_stem not in ug:
                return {note_stem}
            return set(nx.node_connected_component(ug, note_stem))
        except Exception:
            return {note_stem}

    def stats(self) -> dict:
        n_nodes = len(self._adj)
        n_edges = sum(len(v) for v in self._adj.values())
        orphan_count = len(self.orphans())
        top = self.most_linked(1)
        hub = top[0][0] if top else ""

        extra = {}
        if self._G is not None and n_nodes > 1:
            try:
                ug = self._G.to_undirected()
                comps = list(nx.connected_components(ug))
                extra["components"]   = len(comps)
                extra["largest_comp"] = max(len(c) for c in comps)
                if nx.is_weakly_connected(self._G):
                    extra["avg_path_length"] = round(
                        nx.average_shortest_path_length(
                            self._G.to_undirected()), 2)
            except Exception:
                pass

        return {
            "nodes":        n_nodes,
            "edges":        n_edges,
            "orphans":      orphan_count,
            "hub":          hub,
            **extra,
        }

    # ── Serialization ─────────────────────────────────────────────────

    def save(self) -> None:
        self._graph_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": list(self._adj.keys()),
            "edges": [
                {"src": src, "dst": dst}
                for src, dsts in self._adj.items()
                for dst in dsts
            ],
        }
        with open(self._graph_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self) -> bool:
        """Load dari JSON. Return True jika berhasil."""
        if not self._graph_path.exists():
            return False
        try:
            with open(self._graph_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return False

        self._adj.clear()
        self._radj.clear()
        if self._G is not None:
            self._G.clear()

        for node in data.get("nodes", []):
            self._ensure_node(node)
        for edge in data.get("edges", []):
            self._add_edge(edge["src"], edge["dst"])
        return True

    def to_json(self) -> str:
        """Export graf sebagai JSON string (untuk visualisasi eksternal)."""
        nodes = [{"id": n, "backlinks": len(self._radj.get(n, set()))}
                 for n in self._adj]
        edges = [
            {"source": src, "target": dst}
            for src, dsts in self._adj.items()
            for dst in dsts
        ]
        return json.dumps({"nodes": nodes, "edges": edges},
                          indent=2, ensure_ascii=False)

    # ── Internal helpers ──────────────────────────────────────────────

    def _ensure_node(self, name: str) -> None:
        self._adj.setdefault(name, set())
        self._radj.setdefault(name, set())
        if self._G is not None and name not in self._G:
            self._G.add_node(name)

    def _add_edge(self, src: str, dst: str) -> None:
        self._ensure_node(src)
        self._ensure_node(dst)
        self._adj[src].add(dst)
        self._radj[dst].add(src)
        if self._G is not None:
            self._G.add_edge(src, dst)

    def _bfs_path(self, src: str, dst: str) -> list[str] | None:
        """BFS minimal tanpa networkx."""
        if src == dst:
            return [src]
        visited = {src}
        queue: list[list[str]] = [[src]]
        while queue:
            path = queue.pop(0)
            node = path[-1]
            for neighbor in self._adj.get(node, set()):
                if neighbor == dst:
                    return path + [dst]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return None

    def _reachable(self, start: str) -> set[str]:
        """DFS untuk semua node yang dapat dicapai (tanpa networkx)."""
        visited: set[str] = set()
        stack = [start]
        # Gabungkan forward dan backward edges
        combined: dict[str, set[str]] = {}
        for n in self._adj:
            combined.setdefault(n, set()).update(self._adj[n])
            combined.setdefault(n, set()).update(self._radj.get(n, set()))
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            stack.extend(combined.get(node, set()) - visited)
        return visited
