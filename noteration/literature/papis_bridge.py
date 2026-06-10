"""noteration/literature/papis_bridge.py

Robust interface for Papis libraries.
- Read path: Direct YAML parsing (Fast & Stable) + SQLite Cache.
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
from typing import Any, Callable, Iterator, Optional

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
    key: str
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
    if not author:
        return ""
    if isinstance(author, str):
        return author
    if isinstance(author, list):
        parts: list[str] = []
        for a in author:
            if isinstance(a, dict):
                family = a.get("family", "")
                given = a.get("given", "")
                combined = f"{family}, {given}".strip(", ")
                parts.append(combined)
            else:
                parts.append(str(a))
        return "; ".join(p for p in parts if p)
    return str(author)


def _parse_tags(raw_tags: Any) -> list[str]:
    if not raw_tags:
        return []
    if isinstance(raw_tags, list):
        return [str(t).strip() for t in raw_tags if str(t).strip()]
    return [t.strip() for t in str(raw_tags).split(",") if t.strip()]


def _save_yaml(info_path: Path, data: dict[str, Any]) -> None:
    yaml = get_yaml()
    if not yaml:
        raise RuntimeError("pyyaml is not installed; cannot save info.yaml")

    tmp_path = info_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        tmp_path.replace(info_path)
    except Exception as e:
        logger.error(f"Failed to save YAML to {info_path}: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _make_base_key(author: str, year: str, title: str) -> str:
    first_author = author.split(";")[0].split(",")[0].strip()
    first_author = re.sub(r"[^A-Za-z]", "", first_author)[:20]
    yr = re.sub(r"[^0-9]", "", str(year))[:4]
    
    title_clean = re.sub(r"[^A-Za-z0-9\s]", "", title)
    words = title_clean.split()
    first_word = words[0][:15] if words else ""
    
    key = f"{first_author}{yr}{first_word}"
    return key if key.strip() else "untitled"


# ── PapisBridge ───────────────────────────────────────────────────────────


class PapisBridge:
    def __init__(self, library_path: Path) -> None:
        self.library_path = library_path
        self._entries: list[LiteratureEntry] | None = None
        self._lock = threading.RLock()

    def all_entries(
        self, force_reload: bool = False, fts_engine: Optional[Any] = None
    ) -> list[LiteratureEntry]:
        with self._lock:
            if self._entries is None or force_reload:
                if fts_engine:
                    self._entries = self._load_with_cache(fts_engine)
                else:
                    self._entries = list(self._load_entries())
            return list(self._entries)

    def _load_with_cache(self, fts_engine: Any) -> list[LiteratureEntry]:
        cached_data = fts_engine.get_all_literature_cache()
        cache_map = {item["key"]: item for item in cached_data}

        final_entries: list[LiteratureEntry] = []
        found_keys: set[str] = set()

        if self.library_path.exists():
            for info_yaml in self.library_path.rglob("info.yaml"):
                entry_key = info_yaml.parent.name
                found_keys.add(entry_key)

                try:
                    mtime = info_yaml.stat().st_mtime
                    cached = cache_map.get(entry_key)

                    if cached and cached["mtime"] >= mtime:
                        entry = self._entry_from_cache(cached)
                        final_entries.append(entry)
                    else:
                        maybe_entry = self._parse_info_yaml(info_yaml)
                        if maybe_entry:
                            self._upsert_to_cache(fts_engine, maybe_entry, mtime)
                            final_entries.append(maybe_entry)
                except Exception as e:
                    logger.error(f"Failed to sync literature entry {entry_key}: {e}")

        stale_keys = set(cache_map.keys()) - found_keys
        for key in stale_keys:
            fts_engine.remove_literature_cache(key)

        return final_entries

    def _entry_from_cache(self, cached: dict) -> LiteratureEntry:
        entry_dir = self.library_path / cached["key"]
        pdf_files = list(entry_dir.glob("*.pdf"))
        return LiteratureEntry(
            key=cached["key"],
            title=cached["title"],
            author=cached["author"],
            year=cached["year"],
            journal=cached["journal"],
            publisher=cached["publisher"],
            doi=cached["doi"],
            isbn=cached["isbn"],
            volume=cached["volume"],
            issue=cached["issue"],
            page=cached["page"],
            abstract=cached["abstract"],
            tags=cached["tags"],
            collections=cached["collections"],
            pdf_path=pdf_files[0] if pdf_files else None,
            info_path=self.library_path / cached["key"] / "info.yaml",
            _raw={},
        )

    def _upsert_to_cache(self, fts_engine: Any, entry: LiteratureEntry, mtime: float) -> None:
        data = {
            "key": entry.key,
            "title": entry.title,
            "author": entry.author,
            "year": entry.year,
            "journal": entry.journal,
            "publisher": entry.publisher,
            "doi": entry.doi,
            "isbn": entry.isbn,
            "volume": entry.volume,
            "issue": entry.issue,
            "page": entry.page,
            "abstract": entry.abstract,
            "tags": entry.tags,
            "collections": entry.collections,
            "mtime": mtime,
        }
        fts_engine.upsert_literature_cache(data)

    def _parse_info_yaml(self, info_yaml: Path) -> LiteratureEntry | None:
        yaml = get_yaml()
        if not yaml:
            return None
        entry_dir = info_yaml.parent
        try:
            with open(info_yaml, encoding="utf-8") as f:
                data = yaml.safe_load(f.read()) or {}
            collections = data.get("collections", [])
            pdf_files = list(entry_dir.glob("*.pdf"))
            return LiteratureEntry(
                key=entry_dir.name,
                title=data.get("title", entry_dir.name),
                author=_format_author(data.get("author", "")),
                year=str(data.get("year", "")),
                journal=data.get("journal", ""),
                publisher=str(data.get("publisher", "")),
                doi=data.get("doi", ""),
                isbn=str(data.get("isbn", "")),
                volume=str(data.get("volume", "")),
                issue=str(data.get("issue", "")),
                page=str(data.get("page", "")),
                abstract=data.get("abstract", ""),
                tags=_parse_tags(data.get("tags", [])),
                collections=[str(c) for c in collections if c]
                if isinstance(collections, list)
                else [],
                pdf_path=pdf_files[0] if pdf_files else None,
                info_path=info_yaml,
                _raw=data,
            )
        except Exception as e:
            logger.error(f"Failed to parse {info_yaml}: {e}")
            return None

    def search(self, query: str) -> list[LiteratureEntry]:
        tokens = query.strip().split()
        with self._lock:
            results = self.all_entries()
            for token in tokens:
                if ":" in token:
                    fname, _, value = token.partition(":")
                    results = [
                        e for e in results if self._match_field(e, fname.lower(), value.lower())
                    ]
                else:
                    q = token.lower()
                    results = [e for e in results if self._match_any(e, q)]
            return results

    def get(self, key: str) -> LiteratureEntry | None:
        with self._lock:
            for e in self.all_entries():
                if e.key == key:
                    return e
            return None

    def get_by_ref(self, ref: str) -> LiteratureEntry | None:
        with self._lock:
            for e in self.all_entries():
                if e._raw.get("ref") == ref:
                    return e
            return None

    def _ensure_raw_loaded(self, entry: LiteratureEntry) -> None:
        if not entry._raw and entry.info_path and entry.info_path.exists():
            yaml = get_yaml()
            if yaml:
                try:
                    with open(entry.info_path, encoding="utf-8") as f:
                        entry._raw = yaml.safe_load(f.read()) or {}
                except Exception as e:
                    logger.error(f"Failed to reload raw data from {entry.info_path}: {e}")

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
        from_doi: str = "",
        from_arxiv: str = "",
        from_isbn: str = "",
        fts_engine: Optional[Any] = None,
        track_changes_callback: Optional[Callable[[Path], None]] = None,
    ) -> LiteratureEntry | None:
        with self._lock:
            entry: LiteratureEntry | None = None

            # mode 1: automation
            has_automation = any([from_doi, from_arxiv, from_isbn])
            if has_automation and self._papis_cli_available():
                source = "doi" if from_doi else "arxiv" if from_arxiv else "isbn"
                url = from_doi or from_arxiv or from_isbn
                success, ref_key, is_duplicate = self._run_papis_add_from(source, url, pdf_path)
                if success:
                    self._entries = None
                    if ref_key:
                        entry = self.get(ref_key) or self.get_by_ref(ref_key)
                    if not entry and not is_duplicate:
                        entry = self._newest_entry()
                    
                    if entry:
                        if is_duplicate:
                            logger.info(f"Duplicate entry found: @{entry.key}, skipping rename.")
                            return entry
                        
                        # Apply metadata overrides
                        for field, val in [
                            ("title", title),
                            ("author", author),
                            ("year", year),
                            ("journal", journal),
                            ("publisher", publisher),
                            ("doi", doi),
                        ]:
                            if val:
                                self.update_field(
                                    entry.key,
                                    field,
                                    val,
                                    fts_engine=fts_engine,
                                    track_changes_callback=track_changes_callback,
                                )
                        
                        # Re-fetch entry to get updated metadata for naming
                        entry = self.get(entry.key)
                        if entry:
                            # Rename to standard format if it's currently a hash/uuid
                            # Using 'papis rename' is the standard way to handle this
                            if len(entry.key) > 20: # Heuristic for hash
                                # 1. Generate desired key and set it as 'ref' to help Papis
                                desired_key = _make_base_key(entry.author, entry.year, entry.title)
                                self.update_field(entry.key, "ref", desired_key)
                                
                                logger.info(f"Normalizing folder name for entry @{entry.key}...")
                                try:
                                    # 2. Use papis rename with --doc-folder to target it directly
                                    # We use {doc[ref]} template which Papis 0.15+ supports reliably
                                    if self._run_papis_rename(entry.key, "{doc[ref]}"):
                                        # After papis rename, the folder name changes. 
                                        # We need to find the new key.
                                        self._entries = None
                                        new_entry = self._newest_entry()
                                        if new_entry:
                                            entry = new_entry
                                            logger.info(f"Folder successfully renamed to @{entry.key}")
                                except Exception as e:
                                    logger.error(f"Failed to rename imported folder {entry.key} via papis: {e}")
                        
                        return entry

            # mode 2: manual add
            key = self._unique_key(_make_base_key(author, year, title))
            entry_dir = self.library_path / key
            entry_dir.mkdir(parents=True, exist_ok=True)
            data: dict[str, Any] = {
                "ref": key,
                "title": title,
                "author": author,
                "year": year,
                "journal": journal,
                "publisher": publisher,
                "doi": doi,
                "isbn": isbn,
                "volume": volume,
                "issue": issue,
                "page": page,
                "abstract": abstract,
            }
            if tags:
                data["tags"] = tags
            if collections:
                data["collections"] = collections
            info_path = entry_dir / "info.yaml"
            _save_yaml(info_path, data)

            pdf_dest: Path | None = None
            if pdf_path and pdf_path.exists():
                pdf_dest = entry_dir / f"{key}.pdf"
                shutil.copy2(pdf_path, pdf_dest)
                data["files"] = [f"{key}.pdf"]
                _save_yaml(info_path, data)

            entry = LiteratureEntry(
                key=key,
                title=title,
                author=author,
                year=year,
                journal=journal,
                publisher=publisher,
                doi=doi,
                isbn=isbn,
                volume=volume,
                issue=issue,
                page=page,
                abstract=abstract,
                tags=tags or [],
                collections=collections or [],
                pdf_path=pdf_dest,
                info_path=info_path,
                _raw=data,
            )
            if self._entries is not None:
                self._entries.append(entry)
            if fts_engine:
                self._upsert_to_cache(fts_engine, entry, info_path.stat().st_mtime)
                fts_engine.index_tags(key, tags or [], source="literature")
            if track_changes_callback:
                track_changes_callback(info_path)
            return entry

    def update_field(
        self,
        key: str,
        field_name: str,
        value: Any,
        fts_engine: Optional[Any] = None,
        track_changes_callback: Optional[Callable[[Path], None]] = None,
    ) -> bool:
        with self._lock:
            entry = self.get(key)
            if not entry or not entry.info_path:
                return False
            self._ensure_raw_loaded(entry)
            entry._raw[field_name] = value
            _save_yaml(entry.info_path, entry._raw)
            if fts_engine:
                self._upsert_to_cache(fts_engine, entry, entry.info_path.stat().st_mtime)
                if field_name == "tags":
                    fts_engine.index_tags(key, value, source="literature")
            if track_changes_callback:
                track_changes_callback(entry.info_path)
            self._apply_raw_to_entry(entry, entry._raw)
            return True

    def append_tag(
        self,
        key: str,
        tag: str,
        fts_engine: Optional[Any] = None,
        track_changes_callback: Optional[Callable[[Path], None]] = None,
    ) -> bool:
        with self._lock:
            entry = self.get(key)
            if not entry or not entry.info_path:
                return False
            tag = tag.strip()
            if not tag or tag in entry.tags:
                return True
            self._ensure_raw_loaded(entry)
            entry.tags.append(tag)
            entry._raw["tags"] = entry.tags
            _save_yaml(entry.info_path, entry._raw)
            if fts_engine:
                self._upsert_to_cache(fts_engine, entry, entry.info_path.stat().st_mtime)
                fts_engine.index_tags(key, entry.tags, source="literature")
            if track_changes_callback:
                track_changes_callback(entry.info_path)
            return True

    def remove_tag(
        self,
        key: str,
        tag: str,
        fts_engine: Optional[Any] = None,
        track_changes_callback: Optional[Callable[[Path], None]] = None,
    ) -> bool:
        with self._lock:
            entry = self.get(key)
            if not entry or not entry.info_path:
                return False
            tag = tag.strip()
            if tag not in entry.tags:
                return True
            self._ensure_raw_loaded(entry)
            entry.tags.remove(tag)
            entry._raw["tags"] = entry.tags
            _save_yaml(entry.info_path, entry._raw)
            if fts_engine:
                self._upsert_to_cache(fts_engine, entry, entry.info_path.stat().st_mtime)
                fts_engine.index_tags(key, entry.tags, source="literature")
            if track_changes_callback:
                track_changes_callback(entry.info_path)
            return True

    def append_collection(
        self,
        key: str,
        collection: str,
        track_changes_callback: Optional[Callable[[Path], None]] = None,
    ) -> bool:
        with self._lock:
            entry = self.get(key)
            if not entry or not entry.info_path:
                return False
            if collection in entry.collections:
                return True
            self._ensure_raw_loaded(entry)
            entry.collections.append(collection)
            entry._raw["collections"] = entry.collections
            _save_yaml(entry.info_path, entry._raw)
            if track_changes_callback:
                track_changes_callback(entry.info_path)
            return True

    def remove_collection(
        self,
        key: str,
        collection: str,
        track_changes_callback: Optional[Callable[[Path], None]] = None,
    ) -> bool:
        with self._lock:
            entry = self.get(key)
            if not entry or not entry.info_path:
                return False
            if collection not in entry.collections:
                return True
            self._ensure_raw_loaded(entry)
            entry.collections.remove(collection)
            entry._raw["collections"] = entry.collections
            _save_yaml(entry.info_path, entry._raw)
            if track_changes_callback:
                track_changes_callback(entry.info_path)
            return True

    def attach_file(
        self,
        key: str,
        file_path: Path,
    ) -> bool:
        with self._lock:
            entry = self.get(key)
            if not entry or not entry.info_path or not file_path.exists():
                return False
            
            self._ensure_raw_loaded(entry)
            entry_dir = entry.info_path.parent
            dest_name = file_path.name
            dest_path = entry_dir / dest_name
            
            try:
                # If there was an old file, we might want to keep it or replace it.
                # Papis usually allows multiple files, but our UI expects one primary pdf.
                shutil.copy2(file_path, dest_path)
                
                # Update info.yaml
                files = entry._raw.get("files", [])
                if not isinstance(files, list):
                    files = [files] if files else []
                if dest_name not in files:
                    files.append(dest_name)
                entry._raw["files"] = files
                _save_yaml(entry.info_path, entry._raw)
                
                # Update object
                entry.pdf_path = dest_path
                return True
            except Exception as e:
                logger.error(f"Failed to attach file to {key}: {e}")
                return False

    def delete_document(
        self,
        key: str,
        fts_engine: Optional[Any] = None,
        track_changes_callback: Optional[Callable[[Path], None]] = None,
    ) -> bool:
        with self._lock:
            entry = self.get(key)
            if not entry or not entry.info_path:
                return False
            folder = entry.info_path.parent
            shutil.rmtree(folder)
            if self._entries is not None:
                self._entries = [e for e in self._entries if e.key != key]
            if fts_engine:
                fts_engine.remove_literature_cache(key)
            if track_changes_callback:
                track_changes_callback(folder)
            return True

    def _unique_key(self, base_key: str) -> str:
        key, n = base_key, 1
        while (self.library_path / key).exists():
            key = f"{base_key}_{n}"
            n += 1
        return key

    def _papis_cli_available(self) -> bool:
        return shutil.which("papis") is not None

    def _run_papis_add_from(
        self, source: str, url: str, pdf_path: Path | None = None
    ) -> tuple[bool, str, bool]:
        try:
            papis_bin = shutil.which("papis")
            cmd = [papis_bin] if papis_bin else [sys.executable, "-m", "papis"]
            cmd += [
                "--lib",
                str(self.library_path),
                "add",
                "--from",
                source,
                url,
                "--batch",
                "--no-download-files",
                "--folder-name",
                "{author}{year}{title}",
            ]
            if pdf_path and pdf_path.exists():
                cmd.append(str(pdf_path))
            result = subprocess.run(cmd, capture_output=True, timeout=60, encoding="utf-8")
            out = (result.stdout or "") + (result.stderr or "")
            is_dup = "already in your library" in out or "Duplication Warning" in out
            ref = re.search(r"ref:\s*(\S+)", out)
            return result.returncode == 0, ref.group(1) if ref else "", is_dup
        except Exception:
            return False, "", False

    def _run_papis_rename(self, key: str, folder_format: str) -> bool:
        try:
            papis_bin = shutil.which("papis")
            cmd = [papis_bin] if papis_bin else [sys.executable, "-m", "papis"]
            entry_path = self.library_path / key
            cmd += [
                "--lib",
                str(self.library_path),
                "rename",
                "--batch",
                "--folder-name",
                folder_format,
                "--doc-folder",
                str(entry_path),
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30, encoding="utf-8")
            if result.returncode != 0:
                logger.error(f"Papis rename failed for {key}: {result.stderr}")
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error running papis rename for {key}: {e}")
            return False

    def _newest_entry(self) -> LiteratureEntry | None:
        if not self.library_path.exists():
            return None
        dirs = [d for d in self.library_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        if not dirs:
            return None
        newest = max(dirs, key=lambda d: d.stat().st_mtime)
        for e in self._load_via_yaml():
            if e.key == newest.name:
                return e
        return None

    @staticmethod
    def _apply_raw_to_entry(entry: LiteratureEntry, raw: dict[str, Any]) -> None:
        entry.title = str(raw.get("title", entry.title))
        entry.author = _format_author(raw.get("author", entry.author))
        entry.year = str(raw.get("year", entry.year))
        entry.journal = str(raw.get("journal", entry.journal))
        entry.publisher = str(raw.get("publisher", entry.publisher))
        entry.doi = str(raw.get("doi", entry.doi))
        entry.isbn = str(raw.get("isbn", entry.isbn))
        entry.volume = str(raw.get("volume", entry.volume))
        entry.issue = str(raw.get("issue", entry.issue))
        entry.page = str(raw.get("page", entry.page))
        entry.abstract = str(raw.get("abstract", entry.abstract))
        entry.tags = _parse_tags(raw.get("tags", entry.tags))

    def _match_field(self, entry: LiteratureEntry, fname: str, value: str) -> bool:
        mapping = {
            "title": entry.title,
            "author": entry.author,
            "year": entry.year,
            "journal": entry.journal,
            "doi": entry.doi,
            "key": entry.key,
            "ref": entry.key,
            "tags": ",".join(entry.tags),
            "tag": ",".join(entry.tags),
        }
        return value in mapping.get(fname, "").lower()

    def _match_any(self, entry: LiteratureEntry, q: str) -> bool:
        return any(
            q in v.lower() for v in [entry.key, entry.title, entry.author, entry.year] + entry.tags
        )

    def _load_entries(self) -> Iterator[LiteratureEntry]:
        if self.library_path.exists():
            if has_yaml():
                yield from self._load_via_yaml()
            else:
                yield from self._load_directory_only()

    def _load_via_yaml(self) -> Iterator[LiteratureEntry]:
        for info_yaml in self.library_path.rglob("info.yaml"):
            entry = self._parse_info_yaml(info_yaml)
            if entry:
                yield entry

    def _load_directory_only(self) -> Iterator[LiteratureEntry]:
        for d in sorted(self.library_path.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                pdf_files = list(d.glob("*.pdf"))
                yield LiteratureEntry(
                    key=d.name, title=d.name, pdf_path=pdf_files[0] if pdf_files else None
                )
