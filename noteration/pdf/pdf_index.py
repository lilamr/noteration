"""
noteration/pdf/pdf_index.py

PDF metadata index in vault: SHA-256 hash, relative path, papis_key.
Stored in .noteration/pdf_index.json.

Used during cross-device synchronization so annotations can be 
matched to PDF files that may have different paths across machines.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from datetime import datetime, timezone

from noteration.pdf.annotations import hash_pdf


_INDEX_FILE = ".noteration/pdf_index.json"


class PdfIndex:
    """
    Stores a map: sha256_hash  →  { papis_key, path_relative, indexed_at }

    When opening a new PDF:
      1. Calculate its hash
      2. Check if it's already in the index
      3. If not, add it
      4. Return the registered papis_key
    """
    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._index_path = vault_path / _INDEX_FILE
        self._data: dict[str, dict] = {}
        self._lock = threading.RLock()

    def load(self) -> bool:
        """Load from JSON. Returns True if successful."""
        with self._lock:
            if not self._index_path.exists():
                return False
            try:
                with open(self._index_path, encoding="utf-8") as f:
                    self._data = json.load(f)
                return True
            except Exception:
                return False


    def save(self) -> None:
        with self._lock:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write: save to temp then rename
            tmp_path = self._index_path.with_suffix(".tmp")
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                tmp_path.replace(self._index_path)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to save PDF index: {e}")
                if tmp_path.exists():
                    tmp_path.unlink()

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def register(self, pdf_path: Path, papis_key: str) -> str:
        """
        Register PDF to index.
        Returns: hash string.
        """
        with self._lock:
            pdf_hash = hash_pdf(pdf_path)
            rel = str(pdf_path.relative_to(self.vault_path)) if pdf_path.is_relative_to(self.vault_path) else str(pdf_path)

            self._data[pdf_hash] = {
                "papis_key": papis_key,
                "path_relative": rel,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.save()
            return pdf_hash

    def lookup_by_hash(self, pdf_hash: str) -> dict | None:
        """Find entry by hash."""
        with self._lock:
            return self._data.get(pdf_hash)

    def lookup_by_key(self, papis_key: str) -> list[dict]:
        """Find all entries for a specific papis_key."""
        with self._lock:
            return [v for v in self._data.values() if v.get("papis_key") == papis_key]

    def find_or_register(self, pdf_path: Path, papis_key: str) -> str:
        """
        If PDF already exists in index (by path), return its hash.
        Otherwise, register it first.
        """
        with self._lock:
            # Search by relative path
            rel = str(pdf_path.relative_to(self.vault_path)) if pdf_path.is_relative_to(self.vault_path) else str(pdf_path)
            for h, v in self._data.items():
                if v.get("path_relative") == rel:
                    return h

            return self.register(pdf_path, papis_key)

    def resolve_pdf_path(self, papis_key: str) -> Path | None:
        """
        Find local PDF path based on papis_key.
        Cross-device: paths may differ, but the hash is the same.
        """
        with self._lock:
            entries = self.lookup_by_key(papis_key)
            for entry in entries:
                rel = entry.get("path_relative", "")
                candidate = self.vault_path / rel
                if candidate.exists():
                    return candidate
            return None

    def scan_vault(self, literature_dir: Path | None = None, check_stop=None) -> int:
        """
        Scan the entire literature directory and register all PDFs not yet in the index.
        Returns: number of new PDFs registered.
        """
        with self._lock:
            lit_dir = literature_dir or (self.vault_path / "literature")
            if not lit_dir.exists():
                return 0

            count = 0
            for pdf_path in lit_dir.rglob("*.pdf"):
                if check_stop and check_stop():
                    break
                
                try:
                    papis_key = pdf_path.parent.name   # use folder name as key
                    rel = str(pdf_path.relative_to(self.vault_path))

                    already_indexed = any(
                        v.get("path_relative") == rel for v in self._data.values()
                    )
                    if not already_indexed:
                        self.register(pdf_path, papis_key)
                        count += 1
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).debug(f"Skipping PDF during scan ({pdf_path}): {e}")
                    continue

            return count

    @property
    def all_entries(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._data)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
