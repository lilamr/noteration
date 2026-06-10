"""noteration/core/repository.py
Abstractions for vault data access (Notes, Literature, etc.)
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from noteration.logger import get_logger

logger = get_logger(__name__)


class NoteRepository:
    """Handles all operations related to Markdown notes within the vault.
    Centralizes file system access to allow for easier testing and refactoring.
    """

    def __init__(self, notes_dir: Path) -> None:
        self.notes_dir = notes_dir
        if not self.notes_dir.exists():
            self.notes_dir.mkdir(parents=True, exist_ok=True)

    def list_notes(self) -> List[Path]:
        """Return a list of all Markdown notes in the vault, sorted by name.
        """
        try:
            return sorted(list(self.notes_dir.rglob("*.md")))
        except Exception as e:
            logger.error(f"Failed to list notes in {self.notes_dir}: {e}")
            return []

    def read_note(self, note_path: Path) -> Optional[str]:
        """Read the content of a note.
        """
        try:
            if not note_path.is_absolute():
                note_path = self.notes_dir / note_path

            if not note_path.exists():
                return None

            return note_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read note {note_path}: {e}")
            return None

    def write_note(self, note_path: Path, content: str) -> bool:
        """Write content to a note.
        """
        try:
            if not note_path.is_absolute():
                note_path = self.notes_dir / note_path

            # Ensure parent directory exists
            note_path.parent.mkdir(parents=True, exist_ok=True)

            note_path.write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to write note {note_path}: {e}")
            return False

    def delete_note(self, note_path: Path) -> bool:
        """Delete a note.
        """
        try:
            if not note_path.is_absolute():
                note_path = self.notes_dir / note_path

            if note_path.exists():
                note_path.unlink()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete note {note_path}: {e}")
            return False

    def exists(self, note_path: Path) -> bool:
        """Check if a note exists.
        """
        if not note_path.is_absolute():
            note_path = self.notes_dir / note_path
        return note_path.exists()
