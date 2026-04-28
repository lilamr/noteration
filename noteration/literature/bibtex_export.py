"""
noteration/literature/bibtex_export.py

Export entri Papis ke format BibTeX.

Mendukung:
  - Export satu entri (@key)         → get_bibtex_string()
  - Export seluruh library           → export_all()
  - Export entri dengan key tertentu → export_keys()
  - Export dari satu note            → export_from_note()
  - Export dari seluruh vault        → export_from_vault()

Perbaikan:
  - entry_type dibaca dari entry._raw["type"] LALU extra_fields["type"]
  - Field abstract ikut diekspor jika ada
  - Author list-of-dict ditulis sebagai "Family, Given and Family2, Given2"
    sesuai format BibTeX standar
  - Trailing comma pada field terakhir dihapus (valid BibTeX tapi rapi)
  - Header file mencantumkan timestamp dan versi
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from noteration.literature.papis_bridge import LiteratureEntry, PapisBridge
from noteration.editor.wiki_links import parse_citations


# ── Tipe BibTeX ───────────────────────────────────────────────────────────

_TYPE_MAP: dict[str, str] = {
    "article":       "article",
    "journal":       "article",
    "book":          "book",
    "inbook":        "inbook",
    "incollection":  "incollection",
    "inproceedings": "inproceedings",
    "conference":    "inproceedings",
    "proceedings":   "proceedings",
    "phdthesis":     "phdthesis",
    "mastersthesis": "mastersthesis",
    "techreport":    "techreport",
    "report":        "techreport",
    "misc":          "misc",
    "online":        "misc",
    "preprint":      "misc",
    "unpublished":   "unpublished",
    "manual":        "manual",
    "booklet":       "booklet",
}

# Field yang sudah ditangani secara eksplisit — tidak perlu ditulis ulang
# dari extra_fields agar tidak duplikat
_HANDLED_FIELDS = frozenset(
    {"type", "title", "author", "year", "journal", "doi", "abstract",
     "tags", "keywords", "ref", "papis_id"}
)


# ── Escaping ──────────────────────────────────────────────────────────────

def _escape_bibtex(value: str) -> str:
    """Escape karakter khusus BibTeX dalam nilai field."""
    return (
        value
        .replace("&",  r"\&")
        .replace("%",  r"\%")
        .replace("_",  r"\_")
        .replace("#",  r"\#")
        .replace("~",  r"\~{}") 
        .replace("^",  r"\^{}")
    )


def _format_author_bibtex(author: Any) -> str:
    """
    Konversi field author ke format BibTeX: "Family, Given and Family2, Given2".
    Mendukung tiga format input yang dihasilkan Papis:
      - str   : sudah dalam format apapun, kembalikan apa adanya
      - list[str]  : gabungkan dengan " and "
      - list[dict] : konversi tiap dict {family, given} → "Family, Given"
    """
    if not author:
        return ""
    if isinstance(author, str):
        # Ganti "; " (format internal Noteration) ke " and " (format BibTeX)
        return re.sub(r"\s*;\s*", " and ", author)
    if isinstance(author, list):
        parts: list[str] = []
        for a in author:
            if isinstance(a, dict):
                family = a.get("family", "").strip()
                given  = a.get("given",  "").strip()
                if family and given:
                    parts.append(f"{family}, {given}")
                elif family:
                    parts.append(family)
                elif given:
                    parts.append(given)
            else:
                parts.append(str(a).strip())
        return " and ".join(p for p in parts if p)
    return str(author)


# ── Core converter ────────────────────────────────────────────────────────

def entry_to_bibtex(
    entry: LiteratureEntry,
    extra_fields: dict[str, Any] | None = None,
) -> str:
    """
    Konversi satu LiteratureEntry ke string BibTeX.

    Urutan prioritas untuk menentukan tipe entri:
      1. entry._raw["type"]    (dari info.yaml)
      2. extra_fields["type"]  (override manual)
      3. "misc"                (fallback)
    """
    # Gabungkan raw dan extra — raw lebih dipercaya
    raw = dict(entry._raw) if entry._raw else {}
    if extra_fields:
        for k, v in extra_fields.items():
            raw.setdefault(k, v)

    # Tentukan tipe BibTeX
    bib_type = "misc"
    for source in (raw.get("type", ""), raw.get("type_", "")):
        if source:
            bib_type = _TYPE_MAP.get(str(source).lower().strip(), "misc")
            break

    # Format author dari raw (mungkin list-of-dict) atau dari entry.author
    raw_author = raw.get("author", entry.author)
    author_str = _format_author_bibtex(raw_author)

    lines: list[str] = [f"@{bib_type}{{{entry.key},"]

    def add(field: str, value: str) -> None:
        v = value.strip() if isinstance(value, str) else str(value).strip()
        if v:
            lines.append(f"  {field} = {{{_escape_bibtex(v)}}},")

    add("title",    entry.title)
    add("author",   author_str)
    add("year",     entry.year)
    add("journal",  entry.journal)
    add("doi",      entry.doi)
    add("abstract", entry.abstract)

    if entry.tags:
        add("keywords", ", ".join(entry.tags))

    # Field tambahan dari raw / extra_fields yang belum ditangani
    for k, v in raw.items():
        if k not in _HANDLED_FIELDS and v is not None:
            add(k, str(v))

    # Hapus trailing comma pada field terakhir untuk BibTeX yang rapi
    if len(lines) > 1 and lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]

    lines.append("}")
    return "\n".join(lines)


# ── BibTeXExporter ────────────────────────────────────────────────────────

class BibTeXExporter:
    """Ekspor library Papis ke file .bib."""

    def __init__(self, bridge: PapisBridge) -> None:
        self._bridge = bridge

    # ── Public API ────────────────────────────────────────────────────

    def export_all(self, output_path: Path) -> int:
        """
        Export seluruh library ke satu file .bib.
        Ekivalen: papis export --all --output all.bib
        Return: jumlah entri yang diekspor.
        """
        entries = self._bridge.all_entries()
        return self._write(entries, output_path)

    def export_keys(self, keys: list[str], output_path: Path) -> int:
        """
        Export hanya entri dengan key tertentu.
        Ekivalen: papis export --all --output out.bib <query>
        """
        key_set = set(keys)
        entries = [e for e in self._bridge.all_entries() if e.key in key_set]
        return self._write(entries, output_path)

    def export_from_note(self, note_path: Path, output_path: Path) -> int:
        """
        Export semua @citation yang digunakan dalam satu file note.
        Ekivalen: papis export --all --output note.bib  (lalu filter manual)
        """
        text = note_path.read_text(encoding="utf-8")
        cited_keys = [c.key for c in parse_citations(text)]
        return self.export_keys(cited_keys, output_path)

    def export_from_vault(self, notes_dir: Path, output_path: Path) -> int:
        """
        Kumpulkan semua @citation dari seluruh vault, lalu export.
        """
        cited_keys: set[str] = set()
        for md_file in notes_dir.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
                for c in parse_citations(text):
                    cited_keys.add(c.key)
            except Exception:
                pass
        return self.export_keys(list(cited_keys), output_path)

    def get_bibtex_string(self, key: str) -> str | None:
        """
        Return BibTeX string untuk satu @key (untuk paste ke clipboard).
        Membaca tipe dari entry._raw["type"] jika tersedia.
        """
        entry = self._bridge.get(key)
        if not entry:
            return None
        return entry_to_bibtex(entry)

    # ── Internal ──────────────────────────────────────────────────────

    def _write(self, entries: list[LiteratureEntry], output_path: Path) -> int:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header = [
            "% Generated by Noteration",
            f"% {len(entries)} entries  —  {ts}",
            "% DO NOT edit manually; regenerate via Tools → Export BibTeX",
            "",
        ]
        body: list[str] = []
        for e in entries:
            body.append(entry_to_bibtex(e))
            body.append("")

        output_path.write_text(
            "\n".join(header + body), encoding="utf-8"
        )
        return len(entries)
