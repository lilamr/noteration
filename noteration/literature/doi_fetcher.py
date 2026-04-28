"""
noteration/literature/doi_fetcher.py

Fetch metadata jurnal dari DOI via Crossref API dan arXiv API.
Tidak membutuhkan library eksternal — hanya stdlib.

API publik:
  fetch_doi(doi)    → dict metadata atau None
  fetch_arxiv(url)  → dict metadata atau None
  fetch_isbn(isbn)  → dict metadata atau None
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


_CROSSREF_URL = "https://api.crossref.org/works/{doi}"
_ARXIV_API    = "https://export.arxiv.org/api/query?id_list={arxiv_id}"
_OPENLIBRARY_API = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"

# User-Agent yang sopan untuk Crossref polite pool
_USER_AGENT = (
    "Noteration/1.0 (Open-source research note-taking; "
    "https://github.com/noteration/noteration)"
)

_TYPE_MAP = {
    "journal-article":  "article",
    "book":             "book",
    "book-chapter":     "inbook",
    "proceedings-article": "inproceedings",
    "posted-content":   "misc",   # preprint
    "report":           "techreport",
    "dissertation":     "phdthesis",
    "dataset":          "misc",
    "monograph":        "book",
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Hapus tag HTML/XML dari teks (untuk abstract Crossref)."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _get_json(url: str, timeout: int = 10) -> dict | None:
    req = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError, TimeoutError):
        return None


# ── Crossref ──────────────────────────────────────────────────────────────

def fetch_doi(doi: str) -> dict[str, Any] | None:
    """
    Fetch metadata dari Crossref untuk DOI yang diberikan.
    DOI boleh dengan atau tanpa prefix https://doi.org/.

    Return dict dengan keys:
      title, author, year, journal, doi, abstract, publisher,
      volume, issue, page, type (BibTeX), tags (kosong)
    atau None jika gagal.
    """
    # Normalisasi DOI
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:", "", doi, flags=re.IGNORECASE)

    data = _get_json(_CROSSREF_URL.format(doi=urllib.parse.quote(doi, safe="")))
    if not data or "message" not in data:
        return None

    work = data["message"]
    return _parse_crossref(work)


def _parse_crossref(work: dict) -> dict[str, Any]:
    # Title
    title = (work.get("title") or [""])[0]

    # Author: list of {family, given}
    authors = work.get("author", [])
    author_str = "; ".join(
        f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
        for a in authors
        if a.get("family") or a.get("given")
    )

    # Year: published > published-print > published-online > issued
    year = ""
    for date_key in ("published", "published-print", "published-online", "issued"):
        parts = work.get(date_key, {}).get("date-parts", [[]])
        if parts and parts[0]:
            year = str(parts[0][0])
            break

    # Journal / container
    journal = (work.get("container-title") or [""])[0]

    # DOI
    doi = work.get("DOI", "")

    # Abstract (hapus tag XML Crossref)
    abstract = _strip_html(work.get("abstract", ""))

    # BibTeX type
    bib_type = _TYPE_MAP.get(work.get("type", ""), "misc")

    return {
        "title":     title,
        "author":    author_str,
        "year":      year,
        "journal":   journal,
        "doi":       doi,
        "abstract":  abstract,
        "publisher": work.get("publisher", ""),
        "volume":    str(work.get("volume", "")),
        "issue":     str(work.get("issue", "")),
        "page":      work.get("page", ""),
        "type":      bib_type,
        "tags":      [],
    }


# ── arXiv ─────────────────────────────────────────────────────────────────

def fetch_arxiv(url_or_id: str) -> dict[str, Any] | None:
    """
    Fetch metadata dari arXiv untuk URL atau ID yang diberikan.
    Contoh input: "https://arxiv.org/abs/2404.14339" atau "2404.14339"

    Return dict dengan keys yang sama dengan fetch_doi, atau None.
    """
    arxiv_id = _extract_arxiv_id(url_or_id)
    if not arxiv_id:
        return None

    data = _get_xml(_ARXIV_API.format(arxiv_id=arxiv_id))
    if not data:
        return None

    return _parse_arxiv(data, arxiv_id)


def _extract_arxiv_id(text: str) -> str:
    """Ekstrak arXiv ID dari berbagai format input."""
    text = text.strip()
    # Format: https://arxiv.org/abs/2404.14339 atau arxiv.org/pdf/2404.14339
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]+(?:v\d+)?)", text,
                  re.IGNORECASE)
    if m:
        return m.group(1)
    # Format: 2404.14339 atau 2404.14339v2
    m = re.match(r"^([0-9]{4}\.[0-9]+(?:v\d+)?)$", text)
    if m:
        return m.group(1)
    # Format lama: hep-th/0001001
    m = re.match(r"^([a-z\-]+/[0-9]{7})$", text)
    if m:
        return m.group(1)
    return ""


def _get_xml(url: str, timeout: int = 10) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def _parse_arxiv(xml: str, arxiv_id: str) -> dict[str, Any] | None:
    """Parse Atom feed arXiv menjadi dict metadata."""
    def _tag(tag: str) -> str:
        m = re.search(rf"<{tag}[^>]*>(.+?)</{tag}>", xml, re.DOTALL)
        return m.group(1).strip() if m else ""

    title = re.sub(r"\s+", " ", _tag("title")).strip()
    if not title or title == "Error":
        return None

    # Authors dari <author><name>...</name></author>
    author_names = re.findall(r"<author>\s*<name>(.+?)</name>", xml)
    # Konversi "Firstname Lastname" → "Lastname, Firstname"
    def _invert(name: str) -> str:
        parts = name.strip().split()
        if len(parts) >= 2:
            return f"{parts[-1]}, {' '.join(parts[:-1])}"
        return name
    author_str = "; ".join(_invert(a) for a in author_names)

    # Tahun dari <published>2024-04-22T...</published>
    published = _tag("published")
    year = published[:4] if published else ""

    abstract = re.sub(r"\s+", " ", _tag("summary")).strip()
    doi_tag  = re.search(r"<arxiv:doi[^>]*>(.+?)</arxiv:doi>", xml)
    doi      = doi_tag.group(1).strip() if doi_tag else ""

    return {
        "title":     title,
        "author":    author_str,
        "year":      year,
        "journal":   "arXiv",
        "doi":       doi,
        "abstract":  abstract,
        "publisher": "arXiv",
        "volume":    "",
        "issue":     "",
        "page":      "",
        "type":      "misc",
        "tags":      ["preprint", "arxiv"],
        "eprint":    arxiv_id,
    }


# ── OpenLibrary (ISBN) ────────────────────────────────────────────────────

def fetch_isbn(isbn: str) -> dict[str, Any] | None:
    """
    Fetch metadata dari OpenLibrary untuk ISBN yang diberikan.
    Mendukung ISBN-10 atau ISBN-13.
    """
    isbn = re.sub(r"[^0-9X]", "", isbn.strip().upper())
    if not isbn:
        return None

    data = _get_json(_OPENLIBRARY_API.format(isbn=isbn))
    if not data or f"ISBN:{isbn}" not in data:
        return None

    book = data[f"ISBN:{isbn}"]
    return _parse_openlibrary(book, isbn)


def _parse_openlibrary(book: dict, isbn: str) -> dict[str, Any]:
    # Title
    title = book.get("title", "")
    subtitle = book.get("subtitle", "")
    if subtitle:
        title = f"{title}: {subtitle}"

    # Authors
    authors = book.get("authors", [])
    # OpenLibrary format: {"name": "Isaac Newton", "url": "..."}
    # Konversi ke "Lastname, Firstname"
    def _invert(name: str) -> str:
        parts = name.strip().split()
        if len(parts) >= 2:
            return f"{parts[-1]}, {' '.join(parts[:-1])}"
        return name
    author_str = "; ".join(_invert(a.get("name", "")) for a in authors)

    # Year
    publish_date = book.get("publish_date", "")
    year_match = re.search(r"\b(1\d|2\d)\d{2}\b", publish_date)
    year = year_match.group(0) if year_match else ""

    # Publisher
    publishers = book.get("publishers", [])
    pub_str = publishers[0].get("name", "") if publishers else ""

    return {
        "title":     title,
        "author":    author_str,
        "year":      year,
        "journal":   "",
        "doi":       "",
        "isbn":      isbn,
        "abstract":  book.get("notes", ""),
        "publisher": pub_str,
        "volume":    "",
        "issue":     "",
        "page":      str(book.get("number_of_pages", "")),
        "type":      "book",
        "tags":      ["book"],
    }
