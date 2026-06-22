"""Shared tab contract for Noteration UI tabs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from PySide6.QtWidgets import QWidget


class NoterationTab(QWidget):
    """Base widget for all top-level tabs in MainWindow."""

    def display_title(self) -> str:
        return ""

    def is_dirty(self) -> bool:
        return False

    def session_state(self) -> dict | None:
        return None

    def save_if_dirty(self) -> None:
        return None

    def can_close(self) -> bool:
        return True

    def shutdown(self) -> None:
        return None

    def set_focus_mode(self, enabled: bool) -> None:
        return None

    def refresh(self) -> None:
        return None


@runtime_checkable
class EditorLike(Protocol):
    def insert_text(self, text: str) -> None: ...

    def insert_quote(self, text: str, citation_key: str, locator: str = "") -> None: ...

    def insert_image(self, rel_path: str) -> None: ...

    def go_to_heading(self, heading_text: str) -> None: ...

    def go_to_citation(self, key: str) -> None: ...


@runtime_checkable
class ExportableTab(Protocol):
    def export_as(self, fmt: str) -> None: ...


@runtime_checkable
class NavigableTab(Protocol):
    @property
    def file_path(self) -> object: ...

    @property
    def pdf_path(self) -> object: ...
