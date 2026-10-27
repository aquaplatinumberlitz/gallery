"""Derivative catalog and cache-file clearing."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from ..config import THUMBNAIL_CACHE_DIR
from ..metadata_store import _connect
from ._common import _ensure_database


class CacheMaintenanceMixin:
    """Clear derivative rows and cache files for ``DerivativeScheduler``."""

    def clear_database_rows(self, conn: sqlite3.Connection) -> dict[str, Any]:
        """Delete derivative rows using the caller's transaction."""
        paths = [
            row[0] for row in conn.execute("SELECT cache_path FROM asset_derivatives WHERE cache_path IS NOT NULL")
        ]
        catalog_entries = int(conn.execute("SELECT count(*) FROM asset_derivatives").fetchone()[0])
        jobs = int(conn.execute("SELECT count(*) FROM derivative_jobs").fetchone()[0])
        conn.execute("DELETE FROM derivative_jobs")
        conn.execute("DELETE FROM asset_derivatives")
        return {
            "catalog_entries_cleared": catalog_entries,
            "jobs_cleared": jobs,
            "cache_paths": paths,
        }

    def clear_cache_files(self, paths: Sequence[str]) -> dict[str, int]:
        """Delete committed derivative cache files while preserving served files."""
        from ..thumbnails import clear_thumbnail_disk_cache

        paths = list(paths)
        files_dir = THUMBNAIL_CACHE_DIR / "files"
        paths.extend(str(path) for path in files_dir.iterdir() if path.is_file()) if files_dir.is_dir() else None
        poster_dir = THUMBNAIL_CACHE_DIR / "video_posters"
        paths.extend(str(path) for path in poster_dir.iterdir() if path.is_file()) if poster_dir.is_dir() else None
        paths = list(dict.fromkeys(paths))
        deleted = 0
        with self._file_lock:
            protected = self._served_paths | self._generating_paths
            for path in paths:
                if path in protected:
                    continue
                with suppress(OSError):
                    Path(path).unlink()
                    deleted += 1
        disk_entries = clear_thumbnail_disk_cache()
        return {
            "files_deleted": deleted,
            "disk_entries_cleared": disk_entries,
        }

    def clear_all(self) -> dict[str, int]:
        """Clear derivative jobs/catalog rows and delete unserved cache files."""
        _ensure_database()
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            result = self.clear_database_rows(conn)
            conn.commit()
        cache_result = self.clear_cache_files(result.pop("cache_paths"))
        return {**result, **cache_result}
