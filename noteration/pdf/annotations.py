"""
noteration/pdf/annotations.py
Model anotasi PDF non-destructive + CRUD ke file JSON.
"""

from __future__ import annotations

import json
import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


AnnotationType = Literal["highlight", "image", "comment", "bookmark"]


@dataclass
class Annotation:
    id: str
    type: AnnotationType
    page: int                           # halaman (0-indexed)
    color: str = "#FFEB3B"              # warna highlight
    note: str = ""                      # catatan teks
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    linked_notes: list[str] = field(default_factory=list)

    # Hanya untuk highlight: koordinat rect [x0, y0, x1, y1] dalam PDF points
    rect: list[float] | None = None
    quads: list[list[float]] | None = None  # NEW: list of [x0,y0, x1,y1, x2,y2, x3,y3]
    text_content: str = ""              # teks yang di-highlight
    image_path: str = ""              # path ke image capture (jika ada)

    # Hanya untuk comment: posisi [x, y]
    position: list[float] | None = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class DocumentAnnotations:
    """Semua anotasi untuk satu dokumen PDF."""
    papis_key: str
    pdf_hash: str
    pdf_path_relative: str
    annotations: list[Annotation] = field(default_factory=list)
    last_page: int = 0
    reading_progress: float = 0.0

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, annotation: Annotation) -> None:
        self.annotations.append(annotation)

    def remove(self, ann_id: str) -> bool:
        original = len(self.annotations)
        self.annotations = [a for a in self.annotations if a.id != ann_id]
        return len(self.annotations) < original

    def get(self, ann_id: str) -> Annotation | None:
        for a in self.annotations:
            if a.id == ann_id:
                return a
        return None

    def update(self, ann_id: str, **kwargs) -> bool:
        ann = self.get(ann_id)
        if ann is None:
            return False
        for k, v in kwargs.items():
            if hasattr(ann, k):
                setattr(ann, k, v)
        return True

    def for_page(self, page: int) -> list[Annotation]:
        return [a for a in self.annotations if a.page == page]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
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
    """
    Muat dan simpan DocumentAnnotations dari/ke:
    vault/annotations/<papis_key>.json
    """

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._annotations_dir = vault_path / "annotations"
        self._annotations_dir.mkdir(parents=True, exist_ok=True)
        self._images_dir = self._annotations_dir / "images"
        self._images_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, DocumentAnnotations] = {}

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _json_path(self, papis_key: str) -> Path:
        return self._annotations_dir / f"{papis_key}.json"

    def load(self, papis_key: str, force_reload: bool = False) -> DocumentAnnotations:
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
        if papis_key not in self._cache:
            return
        doc = self._cache[papis_key]
        json_path = self._json_path(papis_key)
        with open(json_path, "w") as f:
            json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

    def save_all(self) -> None:
        for key in self._cache:
            self.save(key)

    # ------------------------------------------------------------------
    # Helper: buat highlight baru
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
    # Image helpers
    # ------------------------------------------------------------------

    @property
    def images_dir(self) -> Path:
        return self._images_dir

    def save_image(self, papis_key: str, ann_id: str, image_bytes: bytes) -> str:
        filename = f"{papis_key}_{ann_id}.png"
        image_path = self._images_dir / filename
        with open(image_path, "wb") as f:
            f.write(image_bytes)
        return str(image_path)


# ------------------------------------------------------------------
# Utility: hash PDF file
# ------------------------------------------------------------------

def hash_pdf(pdf_path: Path) -> str:
    """Hitung SHA-256 dari file PDF untuk verifikasi cross-device."""
    sha256 = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return f"sha256:{sha256.hexdigest()}"
