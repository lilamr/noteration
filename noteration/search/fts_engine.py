"""noteration/search/fts_engine.py
SQLite FTS5 Full-Text Search engine for Noteration.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List

from noteration.logger import get_logger

logger = get_logger(__name__)


class FTSEngine:
    """Manages an SQLite FTS5 database for fast text searching across notes.
    Stored in .noteration/search.db within the vault.
    """

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._db_path = vault_path / ".noteration" / "search.db"
        self._lock = threading.RLock()
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for a thread-safe connection with automatic commit/rollback."""
        conn = self._get_conn()
        with self._lock:
            try:
                yield conn
                conn.commit()
            except sqlite3.Error as e:
                conn.rollback()
                raise e

    def _init_db(self) -> None:
        """Initialize the FTS5 table if it doesn't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            # Create FTS5 table for notes
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    note_id UNINDEXED,
                    title,
                    content,
                    tokenize='unicode61 remove_diacritics 1'
                )
            """)
            # Table to track mtimes for incremental updates
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_metadata (
                    note_id TEXT PRIMARY KEY,
                    mtime REAL
                )
            """)

            # Cache for Papis literature metadata to avoid O(N) YAML parsing
            conn.execute("""
                CREATE TABLE IF NOT EXISTS literature_cache (
                    key TEXT PRIMARY KEY,
                    title TEXT,
                    author TEXT,
                    year TEXT,
                    journal TEXT,
                    publisher TEXT,
                    doi TEXT,
                    isbn TEXT,
                    volume TEXT,
                    issue TEXT,
                    page TEXT,
                    abstract TEXT,
                    tags TEXT,
                    collections TEXT,
                    mtime REAL
                )
            """)

            # Tags table for both notes and literature
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id_ref TEXT,
                    tag TEXT,
                    source TEXT,
                    PRIMARY KEY(id_ref, tag, source)
                )
            """)

    def index_note(self, note_id: str, title: str, content: str, mtime: float) -> None:
        """Add or update a note in the search index."""
        with self.connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO file_metadata (note_id, mtime) VALUES (?, ?)",
                (note_id, mtime),
            )
            conn.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
            conn.execute(
                "INSERT INTO notes_fts (note_id, title, content) VALUES (?, ?, ?)",
                (note_id, title, content),
            )

    def remove_note(self, note_id: str) -> None:
        """Remove a note from the search index."""
        with self.connection() as conn:
            conn.execute("DELETE FROM file_metadata WHERE note_id = ?", (note_id,))
            conn.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
            conn.execute("DELETE FROM tags WHERE id_ref = ? AND source = 'note'", (note_id,))

    def index_tags(self, id_ref: str, tags: List[str], source: str = "note") -> None:
        """Update tags for a note or literature entry."""
        with self.connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id_ref TEXT,
                    tag TEXT,
                    source TEXT,
                    PRIMARY KEY(id_ref, tag, source)
                )
            """)
            conn.execute("DELETE FROM tags WHERE id_ref = ? AND source = ?", (id_ref, source))
            for tag in tags:
                conn.execute(
                    "INSERT INTO tags (id_ref, tag, source) VALUES (?, ?, ?)", (id_ref, tag, source)
                )

    def get_all_tags(self) -> List[tuple[str, str]]:
        """Return all unique (tag, source) pairs in the vault."""
        conn = self._get_conn()
        with self._lock:
            try:
                cursor = conn.execute("SELECT DISTINCT tag, source FROM tags ORDER BY tag, source")
                return [(row[0], row[1]) for row in cursor.fetchall()]
            except sqlite3.Error:
                return []

    def get_notes_with_tag(self, tag: str) -> List[str]:
        """Return note_ids that have the given tag."""
        conn = self._get_conn()
        with self._lock:
            try:
                cursor = conn.execute(
                    "SELECT id_ref FROM tags WHERE tag = ? AND source = 'note'", (tag,)
                )
                return [row[0] for row in cursor.fetchall()]
            except sqlite3.Error:
                return []

    def get_literature_with_tag(self, tag: str) -> List[str]:
        """Return literature keys that have the given tag."""
        conn = self._get_conn()
        with self._lock:
            try:
                cursor = conn.execute(
                    "SELECT id_ref FROM tags WHERE tag = ? AND source = 'literature'", (tag,)
                )
                return [row[0] for row in cursor.fetchall()]
            except sqlite3.Error:
                return []

    def get_tags_for_note(self, note_id: str) -> List[str]:
        """Return all tags for a specific note."""
        conn = self._get_conn()
        with self._lock:
            try:
                cursor = conn.execute(
                    "SELECT tag FROM tags WHERE id_ref = ? AND source = 'note' ORDER BY tag",
                    (note_id,),
                )
                return [row[0] for row in cursor.fetchall()]
            except sqlite3.Error:
                return []

    def needs_update(self, note_id: str, mtime: float) -> bool:
        """Check if a note needs to be re-indexed based on its mtime."""
        conn = self._get_conn()
        with self._lock:
            try:
                cursor = conn.execute(
                    "SELECT mtime FROM file_metadata WHERE note_id = ?", (note_id,)
                )
                row = cursor.fetchone()
                if row is None:
                    return True
                return row[0] < mtime
            except sqlite3.Error:
                return True

    def search_notes(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search for notes using FTS5 MATCH.
        Returns a list of dicts with note_id, title, and snippet.
        """
        query_text = query.strip()
        if not query_text:
            return []

        conn = self._get_conn()
        with self._lock:
            # First, attempt the raw query as provided by the user.
            try:
                return self._do_search(conn, query_text, limit)
            except sqlite3.OperationalError:
                # If the raw query contains FTS5 syntax errors, attempt to treat
                # it as a simple literal phrase search.
                # To do this safely in FTS5, we escape double quotes within the phrase.
                # This is a fallback to ensure we at least return results for literal matches.
                sanitized = query_text.replace('"', '""')
                safe_query = f'"{sanitized}"'
                try:
                    return self._do_search(conn, safe_query, limit)
                except sqlite3.OperationalError as e:
                    logger.error(f"FTS search failed: {e}")
                    return []

    def _do_search(
        self, conn: sqlite3.Connection, fts_query: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Helper to execute the FTS search query."""
        # Note: We use literal '2' for the content column index in snippet()
        # to satisfy security linters (S608). Index 2 corresponds to 'content'
        # in our schema: (0: note_id, 1: title, 2: content).
        cursor = conn.execute(
            """
            SELECT 
                note_id, 
                title, 
                snippet(notes_fts, 2, '**', '**', '...', 32) as snippet,
                rank
            FROM notes_fts 
            WHERE notes_fts MATCH ? 
            ORDER BY rank 
            LIMIT ?
            """,
            (fts_query, limit),
        )
        return [
            {
                "note_id": row["note_id"],
                "title": row["title"],
                "snippet": row["snippet"],
                "score": -row["rank"],
            }
            for row in cursor.fetchall()
        ]

    def clear(self) -> None:
        """Clear the entire index."""
        with self.connection() as conn:
            conn.execute("DELETE FROM file_metadata")
            conn.execute("DELETE FROM notes_fts")
            conn.execute("DELETE FROM tags")

    def close(self) -> None:
        """Close the thread-local connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ── Literature Metadata Cache ─────────────────────────────────────

    def upsert_literature_cache(self, entry_data: Dict[str, Any]) -> None:
        """Add or update a literature entry in the cache."""
        import json

        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO literature_cache (
                    key, title, author, year, journal, publisher,
                    doi, isbn, volume, issue, page, abstract,
                    tags, collections, mtime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry_data["key"],
                    entry_data["title"],
                    entry_data["author"],
                    entry_data["year"],
                    entry_data["journal"],
                    entry_data["publisher"],
                    entry_data["doi"],
                    entry_data["isbn"],
                    entry_data["volume"],
                    entry_data["issue"],
                    entry_data["page"],
                    entry_data["abstract"],
                    json.dumps(entry_data["tags"]),
                    json.dumps(entry_data["collections"]),
                    entry_data["mtime"],
                ),
            )

    def get_all_literature_cache(self) -> List[Dict[str, Any]]:
        """Retrieve all cached literature metadata."""
        import json

        conn = self._get_conn()
        with self._lock:
            try:
                cursor = conn.execute("SELECT * FROM literature_cache")
                results = []
                for row in cursor.fetchall():
                    data = dict(row)
                    data["tags"] = json.loads(data["tags"])
                    data["collections"] = json.loads(data["collections"])
                    results.append(data)
                return results
            except (sqlite3.Error, json.JSONDecodeError):
                return []

    def remove_literature_cache(self, key: str) -> None:
        """Remove a specific entry from the literature cache."""
        with self.connection() as conn:
            conn.execute("DELETE FROM literature_cache WHERE key = ?", (key,))
