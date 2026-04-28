"""
noteration/pdf/pdf_index.py

Index metadata PDF di vault: hash SHA-256, path relatif, papis_key.
Disimpan di .noteration/pdf_index.json.

Digunakan saat sinkronisasi cross-device agar anotasi bisa
dipasangkan ke file PDF yang path-nya berbeda antar mesin.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

from noteration.pdf.annotations import hash_pdf


_INDEX_FILE = ".noteration/pdf_index.json"


class PdfIndex:
    """
    Menyimpan peta:  sha256_hash  →  { papis_key, path_relative, indexed_at }

    Saat membuka PDF baru:
      1. Hitung hash-nya
      2. Cek apakah sudah ada di index
      3. Jika belum, tambahkan
      4. Return papis_key yang terdaftar
    """

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._index_path = vault_path / _INDEX_FILE
        self._data: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._index_path.exists():
            try:
                with open(self._index_path) as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}

    def save(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._index_path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def register(self, pdf_path: Path, papis_key: str) -> str:
        """
        Daftarkan PDF ke index.
        Return: hash string.
        """
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
        """Temukan entri berdasarkan hash."""
        return self._data.get(pdf_hash)

    def lookup_by_key(self, papis_key: str) -> list[dict]:
        """Temukan semua entri untuk papis_key tertentu."""
        return [v for v in self._data.values() if v.get("papis_key") == papis_key]

    def find_or_register(self, pdf_path: Path, papis_key: str) -> str:
        """
        Jika PDF sudah ada di index (by path), kembalikan hash-nya.
        Jika belum, daftarkan dulu.
        """
        # Cari berdasarkan path relatif
        rel = str(pdf_path.relative_to(self.vault_path)) if pdf_path.is_relative_to(self.vault_path) else str(pdf_path)
        for h, v in self._data.items():
            if v.get("path_relative") == rel:
                return h

        return self.register(pdf_path, papis_key)

    def resolve_pdf_path(self, papis_key: str) -> Path | None:
        """
        Temukan path PDF lokal berdasarkan papis_key.
        Cross-device: path mungkin berbeda, tapi hash sama.
        """
        entries = self.lookup_by_key(papis_key)
        for entry in entries:
            rel = entry.get("path_relative", "")
            candidate = self.vault_path / rel
            if candidate.exists():
                return candidate
        return None

    def scan_vault(self, literature_dir: Path | None = None) -> int:
        """
        Scan seluruh direktori literature dan daftarkan semua PDF yang belum ada di index.
        Return: jumlah PDF baru yang didaftarkan.
        """
        lit_dir = literature_dir or (self.vault_path / "literature")
        if not lit_dir.exists():
            return 0

        count = 0
        for pdf_path in lit_dir.rglob("*.pdf"):
            papis_key = pdf_path.parent.name   # gunakan nama folder sebagai key
            rel = str(pdf_path.relative_to(self.vault_path))

            already_indexed = any(
                v.get("path_relative") == rel for v in self._data.values()
            )
            if not already_indexed:
                self.register(pdf_path, papis_key)
                count += 1

        return count

    @property
    def all_entries(self) -> dict[str, dict]:
        return dict(self._data)

    def __len__(self) -> int:
        return len(self._data)
