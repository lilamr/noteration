"""noteration/literature/doi_fetcher.py

Fetch journal metadata from DOI via Crossref API and arXiv API.
Does not require external libraries — uses standard library only.

Public API:
  fetch_doi(doi)    → metadata dict or None
  fetch_arxiv(url)  → metadata dict or None
  fetch_isbn(isbn)  → metadata dict or None
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any


_CROSSREF_URL = "https://api.crossref.org/works/{doi}"
_ARXIV_API = "https://export.arxiv.org/api/query?id_list={arxiv_id}"
_OPENLIBRARY_API = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"

# Polite User-Agent for Crossref pool
_USER_AGENT = (
    "Noteration/1.0 (Open-source research note-taking; https://github.com/noteration/noteration)"
)

_TYPE_MAP = {
    "journal-article": "article",
    "book": "book",
    "book-chapter": "inbook",
    "proceedings-article": "inproceedings",
    "posted-content": "misc",  # preprint
    "report": "techreport",
    "dissertation": "phdthesis",
    "dataset": "misc",
    "monograph": "book",
}


# ── Helpers ───────────────────────────────────────────────────────────────


def _strip_html(text: str) -> str:
    """Remove HTML/XML tags from text (for Crossref abstracts)."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _get_json(url: str, timeout: int = 10) -> dict | None:
    if not url.startswith(("http://", "https://")):
        return None
    req = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec S310
            return json.load(resp)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        OSError,
        TimeoutError,
    ):
        return None


# ── Crossref ──────────────────────────────────────────────────────────────


def fetch_doi(doi: str) -> dict[str, Any] | None:
    """Fetch metadata from Crossref for the given DOI.
    DOI can be with or without the https://doi.org/ prefix.

    Returns dict with keys:
      title, author, year, journal, doi, abstract, publisher,
      volume, issue, page, type (BibTeX), tags (empty)
    or None if failed.
    """
    # Normalize DOI
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

    # Abstract (remove Crossref XML tags)
    abstract = _strip_html(work.get("abstract", ""))

    # BibTeX type
    bib_type = _TYPE_MAP.get(work.get("type", ""), "misc")

    return {
        "title": title,
        "author": author_str,
        "year": year,
        "journal": journal,
        "doi": doi,
        "abstract": abstract,
        "publisher": work.get("publisher", ""),
        "volume": str(work.get("volume", "")),
        "issue": str(work.get("issue", "")),
        "page": work.get("page", ""),
        "type": bib_type,
        "tags": [],
    }


# ── arXiv ─────────────────────────────────────────────────────────────────


def fetch_arxiv(url_or_id: str) -> dict[str, Any] | None:
    """Fetch metadata from arXiv for the given URL or ID.
    Example input: "https://arxiv.org/abs/2404.14339" or "2404.14339"

    Returns dict with same keys as fetch_doi, or None.
    """
    arxiv_id = _extract_arxiv_id(url_or_id)
    if not arxiv_id:
        return None

    data = _get_xml(_ARXIV_API.format(arxiv_id=arxiv_id))
    if not data:
        return None

    return _parse_arxiv(data, arxiv_id)


def _extract_arxiv_id(text: str) -> str:
    """Extract arXiv ID from various input formats."""
    text = text.strip()
    # Format: https://arxiv.org/abs/2404.14339 or arxiv.org/pdf/2404.14339
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]+(?:v\d+)?)", text, re.IGNORECASE)
    if m:
        return m.group(1)
    # Format: 2404.14339 or 2404.14339v2
    m = re.match(r"^([0-9]{4}\.[0-9]+(?:v\d+)?)$", text)
    if m:
        return m.group(1)
    # Old format: hep-th/0001001
    m = re.match(r"^([a-z\-]+/[0-9]{7})$", text)
    if m:
        return m.group(1)
    return ""


def _get_xml(url: str, timeout: int = 10) -> str | None:
    if not url.startswith(("http://", "https://")):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec S310
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def _parse_arxiv(xml_str: str, arxiv_id: str) -> dict[str, Any] | None:
    """Parse arXiv Atom feed into metadata dict using ElementTree."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None

    # Atom namespace and arXiv namespace
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

    entry = root.find("atom:entry", ns)
    if entry is None:
        return None

    # Title
    title_node = entry.find("atom:title", ns)
    title = title_node.text.strip() if title_node is not None and title_node.text else ""
    title = re.sub(r"\s+", " ", title)
    if not title or title == "Error":
        return None

    # Authors
    author_nodes = entry.findall("atom:author", ns)
    author_names = []
    for auth in author_nodes:
        name_node = auth.find("atom:name", ns)
        if name_node is not None and name_node.text:
            author_names.append(name_node.text.strip())

    # Convert "Firstname Lastname" → "Lastname, Firstname"
    def _invert(name: str) -> str:
        parts = name.strip().split()
        if len(parts) >= 2:
            return f"{parts[-1]}, {' '.join(parts[:-1])}"
        return name

    author_str = "; ".join(_invert(a) for a in author_names)

    # Year from <published>2024-04-22T...</published>
    pub_node = entry.find("atom:published", ns)
    published = pub_node.text if pub_node is not None and pub_node.text else ""
    year = published[:4] if published else ""

    # Abstract
    sum_node = entry.find("atom:summary", ns)
    abstract = sum_node.text.strip() if sum_node is not None and sum_node.text else ""
    abstract = re.sub(r"\s+", " ", abstract)

    # DOI
    doi_node = entry.find("arxiv:doi", ns)
    doi = doi_node.text.strip() if doi_node is not None and doi_node.text else ""

    return {
        "title": title,
        "author": author_str,
        "year": year,
        "journal": "arXiv",
        "doi": doi,
        "abstract": abstract,
        "publisher": "arXiv",
        "volume": "",
        "issue": "",
        "page": "",
        "type": "misc",
        "tags": ["preprint", "arxiv"],
        "eprint": arxiv_id,
    }


# ── OpenLibrary (ISBN) ────────────────────────────────────────────────────


def fetch_isbn(isbn: str) -> dict[str, Any] | None:
    """Fetch metadata from OpenLibrary for the given ISBN.
    Supports ISBN-10 or ISBN-13.
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
    # Convert to "Lastname, Firstname"
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
        "title": title,
        "author": author_str,
        "year": year,
        "journal": "",
        "doi": "",
        "isbn": isbn,
        "abstract": book.get("notes", ""),
        "publisher": pub_str,
        "volume": "",
        "issue": "",
        "page": str(book.get("number_of_pages", "")),
        "type": "book",
        "tags": ["book"],
    }
