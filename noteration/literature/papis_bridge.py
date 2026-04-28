"""
noteration/literature/papis_bridge.py

Wrapper untuk Papis Python API.
Fallback ke YAML parsing langsung jika papis tidak terinstall.

Perbaikan:
  - Inisialisasi library via path (bukan nama), sesuai papis.config API
  - Format author robust: string, list-of-dict, list-of-string
  - Pencarian mendukung sintaks field:value (title:principia, tags:fisika)
  - Operasi write: add_document, update_field, append_tag, remove_tag, attach_file
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

try:
    import papis.api          # type: ignore
    import papis.config       # type: ignore
    _HAS_PAPIS = True
except ImportError:
    _HAS_PAPIS = False

try:
    import yaml               # type: ignore
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ── Data model ────────────────────────────────────────────────────────────

@dataclass
class LiteratureEntry:
    key: str                              # folder name / papis ref
    title: str = ""
    author: str = ""
    year: str = ""
    journal: str = ""
    publisher: str = ""
    doi: str = ""
    isbn: str = ""
    volume: str = ""
    issue: str = ""
    page: str = ""
    abstract: str = ""
    tags: list[str] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)
    pdf_path: Path | None = None
    info_path: Path | None = None
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)


# ── Helpers ───────────────────────────────────────────────────────────────

def _format_author(author: Any) -> str:
    """
    Normalkan field author ke string "Nama1; Nama2".
    Mendukung tiga format yang dihasilkan Papis:
      - str biasa        : "Newton, Isaac"
      - list[str]        : ["Isaac Newton", "Carl Gauss"]
      - list[dict]       : [{"family": "Newton", "given": "Isaac"}, ...]
    """
    if not author:
        return ""
    if isinstance(author, str):
        return author
    if isinstance(author, list):
        parts: list[str] = []
        for a in author:
            if isinstance(a, dict):
                family = a.get("family", "")
                given  = a.get("given", "")
                combined = f"{family}, {given}".strip(", ")
                parts.append(combined)
            else:
                parts.append(str(a))
        return "; ".join(p for p in parts if p)
    return str(author)


def _parse_tags(raw_tags: Any) -> list[str]:
    """Tag bisa berupa list atau string dipisah koma."""
    if not raw_tags:
        return []
    if isinstance(raw_tags, list):
        return [str(t).strip() for t in raw_tags if str(t).strip()]
    return [t.strip() for t in str(raw_tags).split(",") if t.strip()]


def _save_yaml(info_path: Path, data: dict[str, Any]) -> None:
    """Tulis ulang info.yaml dengan data yang diberikan."""
    if not _HAS_YAML:
        raise RuntimeError("pyyaml tidak terinstall; tidak bisa menyimpan info.yaml")
    with open(info_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True,
                  default_flow_style=False, sort_keys=False)


def _make_base_key(author: str, year: str, title: str) -> str:
    """
    Buat base key dari metadata.
    Format: AuthorYearFirstword  (konvensi Papis default)
    """
    first_author = author.split(";")[0].split(",")[0].strip()
    first_author = re.sub(r"[^A-Za-z]", "", first_author)[:20]
    yr = re.sub(r"[^0-9]", "", year)[:4]
    first_word = (re.sub(r"[^A-Za-z0-9]", "", title.split()[0])[:15]
                  if title.strip() else "")
    return f"{first_author}{yr}{first_word}" or "untitled"


# ── PapisBridge ───────────────────────────────────────────────────────────

class PapisBridge:
    """
    Interface ke library Papis di dalam vault.

    Prioritas backend:
      1. Papis Python API   (jika papis terinstall)
      2. YAML parsing       (jika pyyaml terinstall)
      3. Directory listing  (minimal, read-only)

    Operasi write (add, update, tag) selalu memanipulasi info.yaml
    secara langsung sehingga berfungsi tanpa bergantung pada CLI Papis.
    """

    def __init__(self, library_path: Path) -> None:
        self.library_path = library_path
        self._entries: list[LiteratureEntry] | None = None
        self._papis_ok = False

        if _HAS_PAPIS and library_path.exists():
            self._papis_ok = self._init_papis_lib(library_path)

    # ── Inisialisasi Papis API ────────────────────────────────────────

    @staticmethod
    def _init_papis_lib(library_path: Path) -> bool:
        """
        Daftarkan library_path ke papis.config menggunakan nama folder
        sebagai nama library dan path absolut sebagai "dir".
        Mengembalikan True jika berhasil.
        """
        try:
            lib_name = library_path.name
            cfg = papis.config.get_configuration()
            if not cfg.has_section(lib_name):
                cfg.add_section(lib_name)
            papis.config.set("dir", str(library_path.resolve()), section=lib_name)
            papis.config.set_lib_from_name(lib_name)
            return True
        except Exception:
            return False

    # ── Public read API ───────────────────────────────────────────────

    def all_entries(self, force_reload: bool = False) -> list[LiteratureEntry]:
        if self._entries is None or force_reload:
            self._entries = list(self._load_entries())
        return self._entries

    def search(self, query: str) -> list[LiteratureEntry]:
        """
        Cari entri.  Mendukung:
          - teks bebas  : "newton"
          - field:value : "title:principia", "tags:fisika", "year:2023"
        Beberapa token digabung sebagai AND implisit.
        """
        tokens = query.strip().split()
        results = self.all_entries()
        for token in tokens:
            if ":" in token:
                fname, _, value = token.partition(":")
                results = [e for e in results
                           if self._match_field(e, fname.lower(), value.lower())]
            else:
                q = token.lower()
                results = [e for e in results if self._match_any(e, q)]
        return results

    def get(self, key: str) -> LiteratureEntry | None:
        for e in self.all_entries():
            if e.key == key:
                return e
        return None

    # ── Public write API ──────────────────────────────────────────────

    def add_document(
        self,
        pdf_path: Path | None = None,
        *,
        title: str = "",
        author: str = "",
        year: str = "",
        journal: str = "",
        publisher: str = "",
        doi: str = "",
        isbn: str = "",
        volume: str = "",
        issue: str = "",
        page: str = "",
        abstract: str = "",
        tags: list[str] | None = None,
        collections: list[str] | None = None,
        extra_fields: dict[str, Any] | None = None,
        from_doi: str = "",
        from_arxiv: str = "",
        from_isbn: str = "",
    ) -> LiteratureEntry | None:
        """
        Tambah dokumen baru ke library.

        Prioritas:
          1. Jika from_doi / from_arxiv / from_isbn diisi dan papis CLI tersedia,
             jalankan `papis add --from ... <id>` (otomatis fetch metadata).
          2. Buat folder + info.yaml secara langsung dari argumen yang diberikan
             (ekivalen `papis add file.pdf --set author "..." --set title "..."`).

        Return: LiteratureEntry yang baru, atau None jika gagal.
        """
        # mode 1: fetch via CLI
        if (from_doi or from_arxiv or from_isbn) and self._papis_cli_available():
            if from_doi:
                source, url = "doi", from_doi
            elif from_arxiv:
                source, url = "arxiv", from_arxiv
            else:
                source, url = "isbn", from_isbn

            if self._run_papis_add_from(source, url):
                self._entries = None          # invalidate cache
                return self._newest_entry()

        # mode 2: tambah manual dari argumen
        base_key = _make_base_key(author, year, title)
        key = self._unique_key(base_key)

        self.library_path.mkdir(parents=True, exist_ok=True)
        entry_dir = self.library_path / key
        entry_dir.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "ref": key, "title": title, "author": author, "year": year,
        }
        if journal:
            data["journal"] = journal
        if publisher:
            data["publisher"] = publisher
        if doi:
            data["doi"] = doi
        if isbn:
            data["isbn"] = isbn
        if volume:
            data["volume"] = volume
        if issue:
            data["issue"] = issue
        if page:
            data["page"] = page
        if abstract:
            data["abstract"] = abstract
        if tags:
            data["tags"] = tags
        if collections:
            data["collections"] = collections

        info_path = entry_dir / "info.yaml"
        _save_yaml(info_path, data)

        pdf_dest: Path | None = None
        if pdf_path and pdf_path.exists():
            pdf_dest = entry_dir / pdf_path.name
            shutil.copy2(pdf_path, pdf_dest)

        entry = LiteratureEntry(
            key=key, title=title, author=author, year=year,
            journal=journal, publisher=publisher,
            doi=doi, isbn=isbn,
            volume=volume, issue=issue, page=page,
            abstract=abstract,
            tags=tags or [],
            collections=collections or [],
            pdf_path=pdf_dest, info_path=info_path, _raw=data,
        )
        # Pastikan cache menyimpan object yang SAMA (bukan salinan)
        if self._entries is None:
            self._entries = []
        self._entries.append(entry)
        return entry

    def update_field(self, key: str, field_name: str, value: Any) -> bool:
        """
        Ubah satu field metadata di info.yaml.
        Ekivalen: `papis update --set <field> <value> <key>`
        """
        entry = self.get(key)
        if not entry or not entry.info_path:
            return False
        entry._raw[field_name] = value
        try:
            _save_yaml(entry.info_path, entry._raw)
        except Exception:
            return False
        self._apply_raw_to_entry(entry, entry._raw)
        return True

    def append_tag(self, key: str, tag: str) -> bool:
        """
        Tambah tag ke entri.
        Ekivalen: `papis tag --append <tag> <key>`
        """
        entry = self.get(key)
        if not entry or not entry.info_path:
            return False
        tag = tag.strip()
        if not tag or tag in entry.tags:
            return True   # sudah ada, bukan error
        entry.tags.append(tag)
        entry._raw["tags"] = entry.tags
        try:
            _save_yaml(entry.info_path, entry._raw)
            return True
        except Exception:
            return False

    def remove_tag(self, key: str, tag: str) -> bool:
        """Hapus satu tag dari entri."""
        entry = self.get(key)
        if not entry or not entry.info_path:
            return False
        tag = tag.strip()
        if tag not in entry.tags:
            return True
        entry.tags.remove(tag)
        entry._raw["tags"] = entry.tags
        try:
            _save_yaml(entry.info_path, entry._raw)
            return True
        except Exception:
            return False

    def delete_document(self, key: str) -> bool:
        """Hapus folder dokumen dari library."""
        entry = self.get(key)
        if not entry or not entry.info_path:
            return False
        folder = entry.info_path.parent
        if not folder.exists():
            return False
        try:
            shutil.rmtree(folder)
            if self._entries is not None:
                self._entries = [e for e in self._entries if e.key != key]
            return True
        except Exception:
            return False

    def attach_file(self, key: str, file_path: Path) -> bool:
        """
        Tambah file ke dokumen yang sudah ada.
        Ekivalen: `papis addto --files <file> <key>`
        """
        entry = self.get(key)
        if not entry or not entry.info_path:
            return False
        dest = entry.info_path.parent / file_path.name
        try:
            shutil.copy2(file_path, dest)
            if file_path.suffix.lower() == ".pdf":
                entry.pdf_path = dest   # update selalu, termasuk jika sudah ada
            return True
        except Exception:
            return False

    # ── Loading ───────────────────────────────────────────────────────

    def _load_entries(self) -> Iterator[LiteratureEntry]:
        if not self.library_path.exists():
            return
        # Always try yaml loading for reliability
        if _HAS_YAML:
            yield from self._load_via_yaml()
        elif self._papis_ok:
            yield from self._load_via_papis()
        else:
            yield from self._load_directory_only()

    def _load_via_papis(self) -> Iterator[LiteratureEntry]:
        try:
            docs = papis.api.get_all_documents_in_lib()
            for doc in docs:
                pdf_files = [Path(f) for f in doc.get_files()
                             if str(f).endswith(".pdf")]
                folder = doc.get_main_folder()
                info_p = Path(folder) / "info.yaml" if folder else None
                raw    = dict(doc) if hasattr(doc, "__iter__") else {}
                yield LiteratureEntry(
                    key      = doc.get_main_folder_name() or doc.get("ref", ""),
                    title    = doc.get("title", ""),
                    author   = _format_author(doc.get("author", "")),
                    year     = str(doc.get("year", "")),
                    journal  = doc.get("journal", ""),
                    doi      = doc.get("doi", ""),
                    abstract = doc.get("abstract", ""),
                    tags     = _parse_tags(doc.get("tags", [])),
                    pdf_path = pdf_files[0] if pdf_files else None,
                    info_path= info_p,
                    _raw     = raw,
                )
        except Exception:
            yield from self._load_via_yaml()

    def _load_via_yaml(self) -> Iterator[LiteratureEntry]:
        for info_yaml in sorted(self.library_path.rglob("info.yaml")):
            entry_dir = info_yaml.parent
            try:
                with open(info_yaml, encoding="utf-8") as f:
                    data: dict[str, Any] = yaml.safe_load(f) or {}
            except Exception:
                data = {}
            
            # Parse collections (list format)
            collections_raw = data.get("collections", [])
            if isinstance(collections_raw, list):
                collections = [str(c) for c in collections_raw if c]
            else:
                collections = []
            
            pdf_files = list(entry_dir.glob("*.pdf"))
            yield LiteratureEntry(
                key      = entry_dir.name,
                title    = data.get("title", entry_dir.name),
                author   = _format_author(data.get("author", "")),
                year     = str(data.get("year", "")),
                journal  = data.get("journal", ""),
                publisher = str(data.get("publisher", "")),
                doi     = data.get("doi", ""),
                isbn    = str(data.get("isbn", "")),
                volume  = str(data.get("volume", "")),
                issue   = str(data.get("issue", "")),
                page    = str(data.get("page", "")),
                abstract = data.get("abstract", ""),
                tags     = _parse_tags(data.get("tags", [])),
                collections = collections,
                pdf_path = pdf_files[0] if pdf_files else None,
                info_path= info_yaml,
                _raw     = data,
            )

    def _load_directory_only(self) -> Iterator[LiteratureEntry]:
        for d in sorted(self.library_path.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                pdf_files = list(d.glob("*.pdf"))
                yield LiteratureEntry(
                    key     = d.name,
                    title   = d.name,
                    pdf_path= pdf_files[0] if pdf_files else None,
                )

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _match_field(entry: LiteratureEntry, fname: str, value: str) -> bool:
        mapping: dict[str, str] = {
            "title":   entry.title,
            "author":  entry.author,
            "year":    entry.year,
            "journal": entry.journal,
            "doi":     entry.doi,
            "key":     entry.key,
            "ref":     entry.key,
            "tags":    ",".join(entry.tags),
            "tag":     ",".join(entry.tags),
        }
        return value in mapping.get(fname, "").lower()

    @staticmethod
    def _match_any(entry: LiteratureEntry, q: str) -> bool:
        return (
            q in entry.key.lower()
            or q in entry.title.lower()
            or q in entry.author.lower()
            or q in entry.year.lower()
            or any(q in t.lower() for t in entry.tags)
        )

    def _unique_key(self, base_key: str) -> str:
        key, n = base_key, 1
        while (self.library_path / key).exists():
            key = f"{base_key}_{n}"
            n += 1
        return key

    @staticmethod
    def _papis_cli_available() -> bool:
        return shutil.which("papis") is not None

    def _run_papis_add_from(self, source: str, url: str) -> bool:
        """
        Jalankan `papis add --from <source> <url>` secara non-interaktif.
        Library path diteruskan via --lib.
        """
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "papis", "add",
                    "--lib", str(self.library_path),
                    "--from", source, url,
                    "--batch",
                ],
                capture_output=True, timeout=60,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _newest_entry(self) -> LiteratureEntry | None:
        """Kembalikan entri dengan folder paling baru (setelah papis add)."""
        if not self.library_path.exists():
            return None
        dirs = [d for d in self.library_path.iterdir()
                if d.is_dir() and not d.name.startswith(".")]
        if not dirs:
            return None
        newest = max(dirs, key=lambda d: d.stat().st_mtime)
        if _HAS_YAML:
            for e in self._load_via_yaml():
                if e.key == newest.name:
                    return e
        return None

    @staticmethod
    def _apply_raw_to_entry(entry: LiteratureEntry, raw: dict[str, Any]) -> None:
        entry.title    = str(raw.get("title",    entry.title))
        entry.author   = _format_author(raw.get("author", entry.author))
        entry.year     = str(raw.get("year",     entry.year))
        entry.journal  = str(raw.get("journal",  entry.journal))
        entry.publisher = str(raw.get("publisher", entry.publisher))
        entry.doi      = str(raw.get("doi",      entry.doi))
        entry.isbn     = str(raw.get("isbn",     entry.isbn))
        entry.volume   = str(raw.get("volume",   entry.volume))
        entry.issue    = str(raw.get("issue",    entry.issue))
        entry.page    = str(raw.get("page",    entry.page))
        entry.abstract = str(raw.get("abstract", entry.abstract))
        entry.tags     = _parse_tags(raw.get("tags", entry.tags))
