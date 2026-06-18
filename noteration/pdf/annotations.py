"""noteration/pdf/annotations.py
Non-destructive PDF annotation model + CRUD to JSON files.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from noteration.logger import get_logger

logger = get_logger(__name__)

AnnotationType = Literal["highlight", "image", "comment", "bookmark"]


@dataclass
class Annotation:
    id: str
    type: AnnotationType
    page: int  # page (0-indexed)
    color: str = "#FFEB3B"  # highlight color
    note: str = ""  # text note
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    linked_notes: list[str] = field(default_factory=list)

    # Only for highlight: rect coordinates [x0, y0, x1, y1] in PDF points
    rect: list[float] | None = None
    quads: list[list[float]] | None = None  # list of [x0,y0, x1,y1, x2,y2, x3,y3]
    text_content: str = ""  # highlighted text
    image_path: str = ""  # path to captured image (if any)

    # Only for comment: position [x, y]
    position: list[float] | None = None

    def __post_init__(self) -> None:
        """Initialize created_at if not set."""
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class DocumentAnnotations:
    """All annotations for a single PDF document."""

    papis_key: str
    pdf_hash: str
    pdf_path_relative: str
    annotations: list[Annotation] = field(default_factory=list)
    last_page: int = 0
    reading_progress: float = 0.0

    # ------------------------------------------------------------------
    # CRUD Operations
    # ------------------------------------------------------------------

    def add(self, annotation: Annotation) -> None:
        """Add an annotation to the document."""
        self.annotations.append(annotation)

    def remove(self, ann_id: str) -> bool:
        """Remove an annotation by its ID."""
        original = len(self.annotations)
        self.annotations = [a for a in self.annotations if a.id != ann_id]
        return len(self.annotations) < original

    def get(self, ann_id: str) -> Annotation | None:
        """Get an annotation by its ID."""
        for a in self.annotations:
            if a.id == ann_id:
                return a
        return None

    def update(self, ann_id: str, **kwargs) -> bool:
        """Update annotation attributes by ID."""
        ann = self.get(ann_id)
        if ann is None:
            return False
        for k, v in kwargs.items():
            if hasattr(ann, k):
                setattr(ann, k, v)
        return True

    def for_page(self, page: int) -> list[Annotation]:
        """Get all annotations for a specific page."""
        return [a for a in self.annotations if a.page == page]

    def compile_to_markdown(self, vault_path: Path) -> str:
        """Format all annotations into a Markdown document."""
        if not self.annotations:
            return ""

        lines = [f"# Annotations for {self.papis_key}\n"]

        # Sort by page then by vertical position if possible
        sorted_anns = sorted(self.annotations, key=lambda a: (a.page, a.rect[1] if a.rect else 0))

        current_page = -1
        for ann in sorted_anns:
            if ann.page != current_page:
                current_page = ann.page
                lines.append(f"\n## Page {current_page + 1}\n")

            if ann.type == "highlight":
                if ann.text_content:
                    lines.append(f"> {ann.text_content.strip()}\n")
                if ann.note:
                    lines.append(f"{ann.note}\n")
            elif ann.type == "comment":
                lines.append(f"**Note:** {ann.note}\n")
            elif ann.type == "image":
                if ann.image_path:
                    # Convert absolute path to relative path
                    try:
                        img_path = Path(ann.image_path)
                        # Assume relative to vault root
                        rel_path = img_path.relative_to(vault_path)
                        lines.append(f"> ![]({rel_path.as_posix()})\n")
                    except ValueError:
                        # Fallback if path is not relative to vault
                        lines.append(f"> ![]({ann.image_path})\n")

            if ann.tags:
                lines.append(f"Tags: {' '.join(['#' + t for t in ann.tags])}\n")

            lines.append("")  # Spacer

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize DocumentAnnotations to a dictionary."""
        return {
            "papis_key": self.papis_key,
            "pdf_hash": self.pdf_hash,
            "pdf_path_relative": self.pdf_path_relative,
            "annotations": [asdict(a) for a in self.annotations],
            "last_page": self.last_page,
            "reading_progress": self.reading_progress,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentAnnotations":
        """Deserialize DocumentAnnotations from a dictionary."""
        anns = [Annotation(**a) for a in data.get("annotations", [])]
        return cls(
            papis_key=data["papis_key"],
            pdf_hash=data.get("pdf_hash", ""),
            pdf_path_relative=data.get("pdf_path_relative", ""),
            annotations=anns,
            last_page=data.get("last_page", 0),
            reading_progress=data.get("reading_progress", 0.0),
        )


class AnnotationStore:
    """Load and save DocumentAnnotations from/to:
    vault/annotations/<papis_key>.json
    """

    def __init__(self, vault_path: Path, on_changed: Callable[[], None] | None = None) -> None:
        """Initialize the annotation store."""
        self.vault_path = vault_path
        self.on_changed = on_changed
        self._annotations_dir = vault_path / "annotations"
        self._annotations_dir.mkdir(parents=True, exist_ok=True)
        self._images_dir = self._annotations_dir / "images"
        self._images_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, DocumentAnnotations] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _json_path(self, papis_key: str) -> Path:
        """Return the path to the annotation JSON file for a given papis key."""
        return self._annotations_dir / f"{papis_key}.json"

    def load(self, papis_key: str, force_reload: bool = False) -> DocumentAnnotations:
        """Load annotations for a document."""
        with self._lock:
            if papis_key in self._cache and not force_reload:
                return self._cache[papis_key]

            json_path = self._json_path(papis_key)
            if json_path.exists():
                with open(json_path) as f:
                    data = json.load(f)
                doc = DocumentAnnotations.from_dict(data)
            else:
                doc = DocumentAnnotations(
                    papis_key=papis_key,
                    pdf_hash="",
                    pdf_path_relative="",
                )

            self._cache[papis_key] = doc
            return doc

    def save(self, papis_key: str) -> None:
        """Save annotations for a document to JSON."""
        with self._lock:
            if papis_key not in self._cache:
                return
            doc = self._cache[papis_key]
            json_path = self._json_path(papis_key)
            # Atomic write: save to temp then rename
            tmp_path = json_path.with_suffix(".tmp")
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)
                tmp_path.replace(json_path)

                if self.on_changed:
                    self.on_changed()
            except Exception as e:
                logger.error(f"Failed to save annotations for {papis_key}: {e}")
                if tmp_path.exists():
                    tmp_path.unlink()

    def save_all(self) -> None:
        """Save all cached annotations to JSON."""
        with self._lock:
            for key in list(self._cache.keys()):
                self.save(key)

    def remove_annotation(self, papis_key: str, ann_id: str) -> bool:
        """Remove an annotation from a document."""
        with self._lock:
            doc = self.load(papis_key)
            if doc.remove(ann_id):
                self.save(papis_key)
                return True
            return False

    def update_annotation(self, papis_key: str, ann_id: str, **kwargs) -> bool:
        """Update an annotation by its ID."""
        with self._lock:
            doc = self.load(papis_key)
            if doc.update(ann_id, **kwargs):
                self.save(papis_key)
                return True
            return False

    def add_annotation(self, papis_key: str, annotation: Annotation) -> None:
        """Add an annotation to a document."""
        with self._lock:
            doc = self.load(papis_key)
            doc.add(annotation)
            self.save(papis_key)

    def update_metadata(self, papis_key: str, last_page: int, reading_progress: float) -> None:
        """Update document reading metadata."""
        with self._lock:
            doc = self.load(papis_key)
            doc.last_page = last_page
            doc.reading_progress = reading_progress
            self.save(papis_key)

    # ------------------------------------------------------------------
    # Helper: create new highlight
    # ------------------------------------------------------------------

    def new_highlight(
        self,
        papis_key: str,
        page: int,
        rect: list[float],
        text_content: str,
        color: str = "#FFEB3B",
        note: str = "",
        tags: list[str] | None = None,
        image_path: str = "",
        type_: AnnotationType = "highlight",
        quads: list[list[float]] | None = None,
    ) -> Annotation:
        """Create a new highlight annotation."""
        with self._lock:
            ann = Annotation(
                id=f"ann-{uuid.uuid4().hex[:8]}",
                type=type_,
                page=page,
                rect=rect,
                quads=quads,
                text_content=text_content,
                image_path=image_path,
                color=color,
                note=note,
                tags=tags or [],
            )
            doc = self.load(papis_key)
            doc.add(ann)
            self.save(papis_key)
            return ann

    def new_comment(
        self,
        papis_key: str,
        page: int,
        position: list[float],
        note: str,
        tags: list[str] | None = None,
    ) -> Annotation:
        """Create a new comment annotation."""
        with self._lock:
            ann = Annotation(
                id=f"ann-{uuid.uuid4().hex[:8]}",
                type="comment",
                page=page,
                position=position,
                note=note,
                tags=tags or [],
            )
            doc = self.load(papis_key)
            doc.add(ann)
            self.save(papis_key)
            return ann

    # ------------------------------------------------------------------
    # Image Helpers
    # ------------------------------------------------------------------

    @property
    def images_dir(self) -> Path:
        """Return the directory path for annotation images."""
        return self._images_dir

    def save_image(self, papis_key: str, ann_id: str, image_bytes: bytes) -> str:
        """Save an annotation image to disk."""
        with self._lock:
            filename = f"{papis_key}_{ann_id}.png"
            image_path = self._images_dir / filename
            with open(image_path, "wb") as f:
                f.write(image_bytes)
            return str(image_path)


# ------------------------------------------------------------------
# Utility: Hash file
# ------------------------------------------------------------------


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file for cross-device verification."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return f"sha256:{sha256.hexdigest()}"
