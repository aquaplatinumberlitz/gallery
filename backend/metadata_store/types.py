"""Shared metadata store value types and exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CachedDimensions:
    """Cached image dimensions keyed by path, mtime, and size."""

    width: int
    height: int


@dataclass(frozen=True)
class MetadataIndexJob:
    """Durable metadata indexing job for one image file version."""

    path: str
    name: str
    parent_path: str
    mtime: float
    size: int
    folder_path: str
    root_path: str
    mtime_ns: int | None = None
    library_id: int | None = None

    @property
    def key(self) -> tuple[str, float, int]:
        """Return the in-memory deduplication key for this file version."""
        return (self.path, self.mtime, self.size)


@dataclass(frozen=True)
class MetadataQueueResult:
    """Summary of metadata jobs queued, coalesced, skipped, or failed."""

    enqueued: list[MetadataIndexJob]
    coalesced: int = 0
    skipped: int = 0
    failed: int = 0


class CatalogJobConflict(Exception):
    """Raised when a catalog request conflicts with already-active catalog work."""

    def __init__(self, active_job: dict[str, Any]) -> None:
        """Store the conflicting active job for API-layer 409 rendering."""
        self.active_job = active_job
        super().__init__("Catalog work is already active for this library.")


class CatalogMaintenanceBusy(Exception):
    """Raised when catalog work is requested during a maintenance operation."""


class LibraryOverlapError(ValueError):
    """Raised when an import path overlaps another registered library."""


class CatalogBrowseScopeError(ValueError):
    """Raised when a browse request points outside the selected library."""
