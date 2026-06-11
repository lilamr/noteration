"""Pydantic models for Noteration API responses and requests."""

from typing import List, Optional

from pydantic import BaseModel


class NoteResponse(BaseModel):
    """Represents a note's metadata for API responses."""

    note_id: str
    title: str
    path: str
    word_count: int
    modified_at: float
    tags: List[str]


class SearchResult(BaseModel):
    """Represents a single search result item."""

    type: str
    id: str
    title: str
    snippet: str
    score: float


class LiteratureResponse(BaseModel):
    """Represents a literature entry's metadata for API responses."""

    key: str
    title: str
    author: str
    year: str
    doi: str
    tags: List[str]


class NoteCreate(BaseModel):
    """Represents the data required to create a new note."""

    note_id: str
    content: str = ""


class NoteUpdate(BaseModel):
    """Represents the data required to update an existing note."""

    content: str


class GraphStats(BaseModel):
    """Represents statistics about the note graph."""

    nodes: int
    links: int
    orphans: int
    hub: Optional[str] = None


class SyncStatus(BaseModel):
    """Represents the current git synchronization status."""

    branch: str
    remotes: List[str]
    is_dirty: bool
    ahead: int
    behind: int
