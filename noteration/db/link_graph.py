"""noteration/db/link_graph.py

NetworkX-based note backlink graph.
Stored as JSON in .noteration/link_graph.json.

Features:
  - build_from_vault(): scan entire vault, extract [[wiki-links]] (incremental)
  - backlinks(note): who links to this note?
  - forward_links(note): where does this note link to?
  - orphans(): notes not linked from anywhere
  - most_linked(): most linked notes (hubs)
  - shortest_path(src, dst): shortest path between two notes
  - to_json() / from_json(): serialization for export/visualization
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from noteration.core.repository import NoteRepository

from noteration.editor.wiki_links import parse_wiki_links, resolve_link
from noteration.logger import get_logger

logger = get_logger(__name__)

_GRAPH_FILE = ".noteration/link_graph.json"

_nx: Any = None


def get_nx() -> Any:
    global _nx
    if _nx is None:
        try:
            import networkx as nx  # type: ignore

            _nx = nx
        except ImportError:
            pass
    return _nx


def has_nx() -> bool:
    return get_nx() is not None


class LinkGraph:
    """Directed graph: edge A → B means note A has a [[link to B]].
    If networkx is unavailable, falls back to a simple dict implementation.
    """

    def __init__(self, vault_path: Path, notes: Optional[NoteRepository] = None) -> None:
        self.vault_path = vault_path
        self._graph_path = vault_path / _GRAPH_FILE
        self._notes_dir = vault_path / "notes"
        self.notes = notes
        self._lock = threading.RLock()
        # Internal adjacency dicts for fallback when networkx is missing
        self._adj: dict[str, set[str]] = {}  # A → {B, C, ...}
        self._radj: dict[str, set[str]] = {}  # B → {A, ...}  (reverse)
        self._G = None  # nx.DiGraph if available

        # Incremental tracking: key is relative note ID, value is mtime
        self._file_mtimes: Dict[str, float] = {}

        nx = get_nx()
        if nx:
            self._G = nx.DiGraph()

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_note_id(self, path: Path) -> str:
        """Absolute path -> relative ID (e.g., folder/note)."""
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

    def rebuild(
        self,
        notes_dir: Path | NoteRepository | None = None,
        force: bool = False,
        check_stop: Optional[Callable[[], bool]] = None,
    ) -> int:
        """Scan all .md files, extract [[wiki-links]], and build the graph.
        If not forced, performs an incremental update based on file mtimes.
        Returns: total number of edges (links) in the graph.
        """
        with self._lock:
            # Use provided notes or self.notes or fallback to self._notes_dir
            notes_source = notes_dir or self.notes or self._notes_dir

            if force:
                self._adj.clear()
                self._radj.clear()
                self._file_mtimes.clear()
                if self._G is not None:
                    self._G.clear()

            # Find current files on disk
            if hasattr(notes_source, "list_notes"):
                current_md_files = notes_source.list_notes()
            else:
                current_md_files = list(notes_source.rglob("*.md"))

            current_ids = {self._get_note_id(f) for f in current_md_files}

            # 1. Remove stale nodes (files that no longer exist)
            stale_ids = set(self._adj.keys()) - current_ids
            for stale_id in stale_ids:
                if check_stop and check_stop():
                    return sum(len(dsts) for dsts in self._adj.values())
                self._remove_node(stale_id)

            # 2. Process changed or new files
            for md_file in sorted(current_md_files):
                if check_stop and check_stop():
                    break

                src_id = self._get_note_id(md_file)
                try:
                    mtime = md_file.stat().st_mtime
                except Exception as e:
                    logger.warning(f"Failed to get mtime for {md_file}: {e}")
                    continue

                if not force and self._file_mtimes.get(src_id) == mtime:
                    continue  # Skip unchanged file

                # Update single note incrementally
                self._process_single_note(md_file, src_id, mtime)

            self.save()

            # Return total edge count
            return sum(len(dsts) for dsts in self._adj.values())

    def update_note(self, note_path: Path, save_after: bool = True) -> None:
        """Update the graph for a single changed note (incrementally)."""
        with self._lock:
            src_id = self._get_note_id(note_path)
            try:
                mtime = note_path.stat().st_mtime
            except Exception as e:
                logger.error(f"Failed to get mtime for {note_path}: {e}")
                return

            self._process_single_note(note_path, src_id, mtime)
            if save_after:
                self.save()

    def _process_single_note(self, note_path: Path, src_id: str, mtime: float) -> None:
        """Internal helper to parse a note and update its edges."""
        # Remove old edges from this source
        old_targets = set(self._adj.get(src_id, set()))
        for dst in old_targets:
            self._radj.get(dst, set()).discard(src_id)
        self._adj[src_id] = set()
        if self._G is not None:
            if src_id in self._G:
                self._G.remove_edges_from([(src_id, dst) for dst in old_targets])

        self._ensure_node(src_id)

        # Add new edges
        try:
            text = note_path.read_text(encoding="utf-8")
            for link in parse_wiki_links(text):
                dst_id = self._resolve_target_to_id(link.target)
                if dst_id and dst_id != src_id:
                    self._add_edge(src_id, dst_id)
            self._file_mtimes[src_id] = mtime
        except Exception as e:
            logger.exception(f"Failed to process note {note_path}: {e}")

    def _remove_node(self, node_id: str) -> None:
        """Completely remove a node and all its incident edges."""
        # Remove forward edges
        targets = self._adj.pop(node_id, set())
        for dst in targets:
            self._radj.get(dst, set()).discard(node_id)

        # Remove backward edges
        sources = self._radj.pop(node_id, set())
        for src in sources:
            self._adj.get(src, set()).discard(node_id)

        self._file_mtimes.pop(node_id, None)

        if self._G is not None and node_id in self._G:
            self._G.remove_node(node_id)

    # ── Queries ───────────────────────────────────────────────────────

    def backlinks(self, note_id: str) -> list[str]:
        """Returns notes that link TO the given note."""
        with self._lock:
            return sorted(self._radj.get(note_id, set()))

    def forward_links(self, note_id: str) -> list[str]:
        """Returns notes linked FROM the given note."""
        with self._lock:
            return sorted(self._adj.get(note_id, set()))

    def all_nodes(self) -> list[str]:
        """Return a sorted list of all nodes in the graph."""
        with self._lock:
            return sorted(self._adj.keys())

    def orphans(self) -> list[str]:
        """Returns notes that have no backlinks from anywhere."""
        with self._lock:
            return [n for n in self._adj if not self._radj.get(n)]

    def most_linked(self, top_n: int = 10) -> list[tuple[str, int]]:
        """Top-N notes based on the number of backlinks (in-degree)."""
        with self._lock:
            counts = [(n, len(self._radj.get(n, set()))) for n in self._adj]
            return sorted(counts, key=lambda x: -x[1])[:top_n]

    def shortest_path(self, src: str, dst: str) -> list[str] | None:
        """Calculates the shortest path between two notes.
        Returns None if no path exists or networkx is unavailable.
        """
        with self._lock:
            nx = get_nx()
            if self._G is None or nx is None:
                return self._bfs_path(src, dst)
            try:
                path = nx.shortest_path(self._G, src, dst)
                return path
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return None

    def connected_cluster(self, note_stem: str) -> set[str]:
        """Returns all notes connected (directly or indirectly) to the given note.
        """
        with self._lock:
            nx = get_nx()
            if self._G is None or nx is None:
                return self._reachable(note_stem)
            try:
                # Use undirected projection for cluster detection
                ug = self._G.to_undirected()
                if note_stem not in ug:
                    return {note_stem}
                return set(nx.node_connected_component(ug, note_stem))
            except Exception as e:
                logger.debug(f"Failed to get connected component for {note_stem}: {e}")
                return {note_stem}

    def stats(self) -> dict:
        """Return various statistics about the graph structure."""
        with self._lock:
            n_nodes = len(self._adj)
            n_edges = sum(len(v) for v in self._adj.values())
            orphan_count = len(self.orphans())
            top = self.most_linked(1)
            hub = top[0][0] if top else ""

            extra = {}
            nx = get_nx()
            if self._G is not None and nx is not None and n_nodes > 1:
                try:
                    ug = self._G.to_undirected()
                    comps = list(nx.connected_components(ug))
                    extra["components"] = len(comps)
                    extra["largest_comp"] = max(len(c) for c in comps)
                    if nx.is_weakly_connected(self._G):
                        extra["avg_path_length"] = round(
                            nx.average_shortest_path_length(self._G.to_undirected()), 2
                        )
                except Exception as e:
                    logger.debug(f"Failed to calculate graph stats: {e}")

            return {
                "nodes": n_nodes,
                "edges": n_edges,
                "orphans": orphan_count,
                "hub": hub,
                **extra,
            }

    # ── Serialization ─────────────────────────────────────────────────

    def save(self) -> None:
        """Persist the graph structure to a JSON file."""
        with self._lock:
            self._graph_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "nodes": list(self._adj.keys()),
                "edges": [
                    {"src": src, "dst": dst} for src, dsts in self._adj.items() for dst in dsts
                ],
                "file_mtimes": self._file_mtimes,
            }
            # Atomic write: save to temp then rename
            tmp_path = self._graph_path.with_suffix(".tmp")
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                tmp_path.replace(self._graph_path)
            except Exception as e:
                logger.error(f"Failed to save link graph: {e}")
                if tmp_path.exists():
                    tmp_path.unlink()

    def load(self) -> bool:
        """Load from JSON. Returns True if successful."""
        with self._lock:
            if not self._graph_path.exists():
                return False
            try:
                with open(self._graph_path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load link graph from {self._graph_path}: {e}")
                return False

            self._adj.clear()
            self._radj.clear()
            if self._G is not None:
                self._G.clear()

            self._file_mtimes = data.get("file_mtimes", {})

            for node in data.get("nodes", []):
                self._ensure_node(node)
            for edge in data.get("edges", []):
                self._add_edge(edge["src"], edge["dst"])
            return True

    def to_json(self) -> str:
        """Export graph as a JSON string (for external visualization)."""
        with self._lock:
            nodes = [{"id": n, "backlinks": len(self._radj.get(n, set()))} for n in self._adj]
            edges = [
                {"source": src, "target": dst} for src, dsts in self._adj.items() for dst in dsts
            ]
            return json.dumps({"nodes": nodes, "edges": edges}, indent=2, ensure_ascii=False)

    # ── Internal Helpers ──────────────────────────────────────────────

    def _ensure_node(self, name: str) -> None:
        """Ensure a node exists in the adjacency lists and the graph object."""
        with self._lock:
            self._adj.setdefault(name, set())
            self._radj.setdefault(name, set())
            if self._G is not None and name not in self._G:
                self._G.add_node(name)

    def _add_edge(self, src: str, dst: str) -> None:
        """Add a directed edge from src to dst."""
        with self._lock:
            self._ensure_node(src)
            self._ensure_node(dst)
            self._adj[src].add(dst)
            self._radj[dst].add(src)
            if self._G is not None:
                self._G.add_edge(src, dst)

    def _bfs_path(self, src: str, dst: str) -> list[str] | None:
        """Minimal BFS implementation without NetworkX."""
        with self._lock:
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
        """DFS for all reachable nodes in the undirected version of the graph (without NetworkX)."""
        with self._lock:
            visited: set[str] = set()
            stack = [start]

            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                visited.add(node)

                # Add neighbors from both forward and backward edges to simulate undirected graph
                if node in self._adj:
                    for neighbor in self._adj[node]:
                        if neighbor not in visited:
                            stack.append(neighbor)

                if node in self._radj:
                    for neighbor in self._radj[node]:
                        if neighbor not in visited:
                            stack.append(neighbor)

            return visited
