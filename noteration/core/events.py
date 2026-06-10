"""noteration/core/events.py
Simple EventBus for decoupling components through a Publish-Subscribe pattern.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Type, TypeVar

from noteration.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Event:
    """Base class for all events."""

    pass


T = TypeVar("T", bound=Event)


class EventBus:
    """A simple in-process event bus that allows publishing and subscribing to events.
    Thread-safe implementation.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[Type[Event], List[Callable[[Any], None]]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: Type[T], callback: Callable[[T], None]) -> None:
        """Subscribe to an event type."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)  # type: ignore
        logger.debug(f"Subscribed {callback} to {event_type.__name__}")

    def unsubscribe(self, event_type: Type[T], callback: Callable[[T], None]) -> None:
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)  # type: ignore
                except ValueError:
                    pass
        logger.debug(f"Unsubscribed {callback} from {event_type.__name__}")

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers of its type."""
        event_type = type(event)
        subscribers = []

        with self._lock:
            if event_type in self._subscribers:
                subscribers = list(self._subscribers[event_type])

        if not subscribers:
            logger.debug(f"No subscribers for {event_type.__name__}")
            return

        logger.debug(f"Publishing {event_type.__name__} to {len(subscribers)} subscribers")
        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in event callback {callback} for {event_type.__name__}: {e}")


# ── Domain Events ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NoteOpenedEvent(Event):
    """Fired when a note is requested to be opened."""

    note_path: Any  # Path
    heading: str | None = None


@dataclass(frozen=True)
class NoteSavedEvent(Event):
    """Fired when a note has been saved to disk."""

    note_path: Any  # Path


@dataclass(frozen=True)
class VaultChangedEvent(Event):
    """Fired when the entire vault content might have changed (e.g. after sync)."""

    reason: str = "unknown"


@dataclass(frozen=True)
class LiteratureSelectedEvent(Event):
    """Fired when a literature entry is selected (e.g. to show in PDF viewer)."""

    papis_key: str
