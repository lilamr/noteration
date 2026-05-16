"""
noteration/literature/papis_bridge.py

Robust interface for Papis libraries.
- Read path: Direct YAML parsing (Fast & Stable).
- Write path: Direct YAML + Papis CLI Wrapper (Consistent metadata).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from noteration.logger import get_logger

logger = get_logger(__name__)

_yaml_mod: Any = None
_HAS_YAML: bool | None = None

def get_yaml() -> Any:
    global _yaml_mod, _HAS_YAML
    if _HAS_YAML is None:
        try:
            import yaml
            _yaml_mod = yaml
            _HAS_YAML = True
        except ImportError:
            _HAS_YAML = False
    return _yaml_mod

def has_yaml() -> bool:
    get_yaml()
    return bool(_HAS_YAML)


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
    Normalize author field to "Name1; Name2" string.
    Supports three formats produced by Papis:
      - plain str        : "Newton, Isaac"
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
                given  = a.get("given",  "")
                combined = f"{family}, {given}".strip(", ")
                parts.append(combined)
            else:
                parts.append(str(a))
        return "; ".join(p for p in parts if p)
    return str(author)


def _parse_tags(raw_tags: Any) -> list[str]:
    """Tags can be a list or a comma-separated string."""
    if not raw_tags:
        return []
    if isinstance(raw_tags, list):
        return [str(t).strip() for t in raw_tags if str(t).strip()]
    return [t.strip() for t in str(raw_tags).split(",") if t.strip()]


def _save_yaml(info_path: Path, data: dict[str, Any]) -> None:
    """Overwrite info.yaml with provided data."""
    yaml = get_yaml()
    if not yaml:
        raise RuntimeError("pyyaml is not installed; cannot save info.yaml")
    
    # Use atomic write pattern
    tmp_path = info_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True,
                      default_flow_style=False, sort_keys=False)
        tmp_path.replace(info_path)
    except Exception as e:
        logger.error(f"Failed to save YAML to {info_path}: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _make_base_key(author: str, year: str, title: str) -> str:
    """
    Create a base key from metadata.
    Format: AuthorYearFirstword (default Papis convention)
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
    Interface to the Papis library within the vault.

    Primary mode: YAML parsing (Fast & Robust).
    Write operations: Direct YAML modification + CLI Wrapper for metadata management.
    """

    def __init__(self, library_path: Path) -> None:
        self.library_path = library_path
        self._entries: list[LiteratureEntry] | None = None
        self._lock = threading.RLock()

    # ── Public Read API ───────────────────────────────────────────────

    def all_entries(self, force_reload: bool = False) -> list[LiteratureEntry]:
        with self._lock:
            if self._entries is None or force_reload:
                self._entries = list(self._load_entries())
            return self._entries

    def search(self, query: str) -> list[LiteratureEntry]:
        """
        Search entries. Supports:
          - free text   : "newton"
          - field:value : "title:principia", "tags:physics", "year:2023"
        Multiple tokens are combined with implicit AND.
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

    # ── Public Write API ──────────────────────────────────────────────

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
        Add a new document to the library.

        Priority:
          1. If from_doi / from_arxiv / from_isbn is provided and Papis CLI is available,
             run `papis add --from ... <id>` (automatically fetches metadata).
          2. Create folder + info.yaml directly from provided arguments.

        Returns: The new LiteratureEntry, or None if failed.
        """
        with self._lock:
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

            # mode 2: manual add from arguments
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
            try:
                _save_yaml(info_path, data)
            except Exception:
                return None

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
            if self._entries is not None:
                self._entries.append(entry)
            return entry

    def update_field(self, key: str, field_name: str, value: Any) -> bool:
        """Modify a single metadata field in info.yaml."""
        with self._lock:
            entry = self.get(key)
            if not entry or not entry.info_path:
                return False
            entry._raw[field_name] = value
            try:
                _save_yaml(entry.info_path, entry._raw)
            except (IOError, PermissionError) as e:
                logger.error(f"Failed to update field '{field_name}' in {entry.info_path}: {e}")
                return False
            except Exception:
                logger.exception(f"Unexpected error updating field '{field_name}' in {entry.info_path}")
                return False
            self._apply_raw_to_entry(entry, entry._raw)
            return True

    def append_tag(self, key: str, tag: str) -> bool:
        """Add a tag to an entry."""
        with self._lock:
            entry = self.get(key)
            if not entry or not entry.info_path:
                return False
            tag = tag.strip()
            if not tag or tag in entry.tags:
                return True   # already exists, not an error
            entry.tags.append(tag)
            entry._raw["tags"] = entry.tags
            try:
                _save_yaml(entry.info_path, entry._raw)
                return True
            except (IOError, PermissionError) as e:
                logger.error(f"Failed to append tag '{tag}' to {entry.info_path}: {e}")
                return False
            except Exception:
                logger.exception(f"Unexpected error appending tag '{tag}' to {entry.info_path}")
                return False

    def remove_tag(self, key: str, tag: str) -> bool:
        """Remove a tag from an entry."""
        with self._lock:
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
            except (IOError, PermissionError) as e:
                logger.error(f"Failed to remove tag '{tag}' from {entry.info_path}: {e}")
                return False
            except Exception:
                logger.exception(f"Unexpected error removing tag '{tag}' from {entry.info_path}")
                return False

    def delete_document(self, key: str) -> bool:
        """Remove document folder from the library."""
        with self._lock:
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
            except (IOError, PermissionError) as e:
                logger.error(f"Failed to delete document folder {folder}: {e}")
                return False
            except Exception:
                logger.exception(f"Unexpected error deleting document folder {folder}")
                return False

    def attach_file(self, key: str, file_path: Path) -> bool:
        """Add a file to an existing document."""
        with self._lock:
            entry = self.get(key)
            if not entry or not entry.info_path:
                return False
            dest = entry.info_path.parent / file_path.name
            try:
                shutil.copy2(file_path, dest)
                if file_path.suffix.lower() == ".pdf":
                    entry.pdf_path = dest
                return True
            except Exception as e:
                logger.error(f"Failed to attach file {file_path}: {e}")
                return False

    # ── Loading ───────────────────────────────────────────────────────

    def _load_entries(self) -> Iterator[LiteratureEntry]:
        if not self.library_path.exists():
            return
        if has_yaml():
            yield from self._load_via_yaml()
        else:
            yield from self._load_directory_only()

    def _load_via_yaml(self) -> Iterator[LiteratureEntry]:
        yaml = get_yaml()
        if not yaml:
            return
        
        info_generator = self.library_path.rglob("info.yaml")
        
        for info_yaml in info_generator:
            entry_dir = info_yaml.parent
            try:
                with open(info_yaml, encoding="utf-8") as f:
                    content = f.read()
                    if not content.strip():
                        data: dict[str, Any] = {}
                    else:
                        data = yaml.safe_load(content) or {}
            except Exception:
                data = {}
            
            try:
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
            except Exception as e:
                logger.debug(f"Skipping invalid literature entry at {info_yaml}: {e}")
                continue

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
        Run `papis add --from <source> <url>` non-interactively.
        """
        try:
            # Prefer sys.executable -m papis if running inside the same venv
            # fallback to system 'papis' if not found
            cmd = [sys.executable, "-m", "papis"]
            if not shutil.which("papis") and not self._check_papis_module():
                 return False

            result = subprocess.run(
                cmd + [
                    "add",
                    "--lib", str(self.library_path),
                    "--from", source, url,
                    "--batch",
                ],
                capture_output=True, timeout=60,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Papis CLI add failed: {e}")
            return False

    @staticmethod
    def _check_papis_module() -> bool:
        try:
            subprocess.run([sys.executable, "-m", "papis", "--version"], 
                           capture_output=True, check=True)
            return True
        except Exception:
            return False

    def _newest_entry(self) -> LiteratureEntry | None:
        """Return the entry with the newest folder."""
        if not self.library_path.exists():
            return None
        dirs = [d for d in self.library_path.iterdir()
                if d.is_dir() and not d.name.startswith(".")]
        if not dirs:
            return None
        newest = max(dirs, key=lambda d: d.stat().st_mtime)
        with self._lock:
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
