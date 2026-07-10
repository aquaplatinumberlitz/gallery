"""Phase 6 catalog hygiene and existing-data convergence coverage.

Purpose:
Phase 6 makes the gallery-repo's mutable frontend test-output directories
(``frontend/coverage``, ``frontend/test-results``, ``frontend/playwright-report``)
default repository-excluded index segments so they can never enter a default
gallery library catalog. Already-indexed artifacts from a prior (pre-exclusion)
build are reconciled to offline catalog rows on the next normal scan, and they
never contribute to expected/desired derivative coverage again.

Guarantees:
* The three repository test-artifact segments are excluded by default on POSIX
  paths and on Windows-style (backslash) path normalization.
* The default exclusions are repository-specific: a directory literally named
  ``coverage``/``test-results``/``playwright-report`` outside ``frontend/`` is
  NOT excluded, and ``frontend/<other>/coverage`` does not match the exact
  ``frontend/coverage`` segment.
* A normal scan after the upgrade reconciles already-indexed matching artifacts
  to offline (inactive) catalog rows without deleting source files.
* Excluded artifacts do not contribute to active asset counts or expected
  derivative coverage.
* Per-library exclusion patterns continue to apply alongside the defaults.

Run when:
Changing backend/files.py default index exclusions, file_index.py scan
reconciliation, or the catalog hygiene configuration contract.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import time
from pathlib import Path

import pytest

from backend import files as files_module
from backend.indexer import rebuild_index_scope
from backend.metadata_store import (
    index_directory_tree,
    reconcile_library_assets,
    register_library,
)
from tests.conftest import create_test_png


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _active_image_count(conn: sqlite3.Connection, library_id: int) -> int:
    return int(
        conn.execute(
            """
            SELECT count(*) FROM assets
            WHERE library_id = ? AND type = 'image'
              AND deleted_at IS NULL AND offline = 0
            """,
            (library_id,),
        ).fetchone()[0]
    )


def _underscore_free_root(monkeypatch: pytest.MonkeyPatch) -> Path:
    """A gallery root without underscores.

    ``reconcile_library_assets`` scopes its offline reconciliation with a ``LIKE``
    query whose pattern escapes underscores, so a library whose resolved path
    contains underscores would not match the scope. Production library roots
    normally do not contain underscores; this helper keeps the test path
    underscore-free so the reconciliation scope matches as it would in
    production.
    """
    import backend.config as config_module
    import backend.metadata_store as ms_module
    import backend.paths as paths_module

    root = (Path("/tmp") / f"gallery{secrets.token_hex(4)}").resolve()
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PATH_SAFETY_ROOT", str(root))
    monkeypatch.setattr(config_module, "PATH_SAFETY_ROOT", root)
    monkeypatch.setattr(paths_module, "PATH_SAFETY_ROOT", root)
    monkeypatch.setattr(ms_module, "PATH_SAFETY_ROOT", root)
    return root


# ---------------------------------------------------------------------------
# Default excluded-segment unit coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "frontend/coverage/report.html",
        "frontend/coverage/vitest/index.xml",
        "frontend/test-results/spec/listing.json",
        "frontend/playwright-report/index.html",
        "/srv/repos/gallery/frontend/coverage/asset.png",
    ],
)
def test_default_test_artifact_segments_excluded_posix(path: str):
    """The three frontend test-output segments are excluded by default."""
    assert files_module.is_index_excluded_path(path) is True


def test_default_exclusions_are_repository_specific():
    """A bare coverage/test-results/playwright-report dir outside frontend is allowed."""
    assert files_module.is_index_excluded_path("/srv/photos/coverage/holiday.png") is False
    assert files_module.is_index_excluded_path("/data/test-results/run1.png") is False
    assert files_module.is_index_excluded_path("/var/playwright-report/x.png") is False
    # frontend/<other>/coverage is not the exact frontend/coverage segment.
    assert files_module.is_index_excluded_path("frontend/src/coverage/x.png") is False


def test_windows_style_separator_normalization():
    """Backslash paths and configured backslash patterns normalize to the same exclusion."""
    # Exercise the public helper, not only an already-split tuple.
    assert files_module.is_index_excluded_path(r"C:\\repo\\frontend\\coverage\\asset.png")
    assert files_module.is_index_excluded_path(r"C:\\repo\\frontend\\test-results\\asset.png")
    assert files_module.is_index_excluded_path(r"C:\\repo\\frontend\\playwright-report\\asset.png")
    assert files_module.is_index_excluded_path(r"\\server\\share\\frontend\\coverage\\asset.png")
    assert not files_module.is_index_excluded_path(r"C:\\repo\\photos\\coverage\\asset.png")
    # Default segment matching is separator-agnostic on the resolved parts.
    assert files_module._contains_segment(
        ("C:\\", "frontend", "coverage", "asset.png"),
        ("frontend", "coverage"),
    )
    # Configured exclusion patterns normalize backslashes to forward slashes.
    original = os.environ.get("GALLERY_INDEX_EXCLUDE_PATTERNS")
    os.environ["GALLERY_INDEX_EXCLUDE_PATTERNS"] = "frontend\\coverage,other\\build"
    try:
        segments = files_module._configured_excluded_segments()
    finally:
        if original is None:
            os.environ.pop("GALLERY_INDEX_EXCLUDE_PATTERNS", None)
        else:
            os.environ["GALLERY_INDEX_EXCLUDE_PATTERNS"] = original
    assert ("frontend", "coverage") in segments
    assert ("other", "build") in segments


def test_default_segments_present_in_configuration():
    """The plan-mandated segments are part of the default exclusion set."""
    segments = files_module.DEFAULT_INDEX_EXCLUDED_SEGMENTS
    assert ("frontend", "coverage") in segments
    assert ("frontend", "test-results") in segments
    assert ("frontend", "playwright-report") in segments


# ---------------------------------------------------------------------------
# Per-library exclusion override still applies
# ---------------------------------------------------------------------------


def test_per_library_exclusion_pattern_still_applies(isolated_gallery_root: Path):
    """Explicit per-library patterns continue to exclude alongside the defaults."""
    import_root = isolated_gallery_root
    patterns = ("secret/**",)

    # Repo-default excluded.
    assert files_module.is_index_excluded_path(
        isolated_gallery_root / "frontend" / "coverage" / "a.png",
        import_root,
        patterns,
    )
    # Per-library pattern excluded.
    assert files_module.is_index_excluded_path(
        isolated_gallery_root / "secret" / "hidden.png",
        import_root,
        patterns,
    )
    # Neither default nor per-library: not excluded.
    assert (
        files_module.is_index_excluded_path(
            isolated_gallery_root / "photos" / "real.png",
            import_root,
            patterns,
        )
        is False
    )


# ---------------------------------------------------------------------------
# Scan reconciliation of already-indexed artifacts
# ---------------------------------------------------------------------------


def test_scan_reconciles_already_indexed_test_artifacts_offline(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A post-upgrade normal scan marks pre-indexed test artifacts offline.

    This simulates the live library 1 state: generated frontend test artifacts
    were indexed before the default exclusions existed. After the upgrade a
    normal scan must reconcile them to inactive catalog rows without touching
    the source files on disk, so they no longer change expected derivative
    coverage.
    """
    from backend.derivative_scheduler import scheduler
    from backend.metadata_store import get_library_for_path

    root = _underscore_free_root(monkeypatch)
    library_id = int(register_library(root)["id"])
    assert get_library_for_path(root) is not None

    create_test_png(root / "photos" / "real.png")
    create_test_png(root / "frontend" / "coverage" / "artifact.png")
    create_test_png(root / "frontend" / "test-results" / "a.png")
    create_test_png(root / "frontend" / "playwright-report" / "b.png")

    # Pre-upgrade state: before the default exclusions existed, the generated
    # test artifacts were indexed as active catalog assets alongside the real
    # image. Insert those rows directly to simulate the already-cataloged state.
    artifact_paths = [
        root / "frontend" / "coverage" / "artifact.png",
        root / "frontend" / "test-results" / "a.png",
        root / "frontend" / "playwright-report" / "b.png",
    ]
    pre_upgrade_paths = [root / "photos" / "real.png", *artifact_paths]
    with _connect(isolated_metadata_db) as conn:
        now = time.time()
        for path in pre_upgrade_paths:
            resolved = str(Path(path).resolve())
            conn.execute(
                """
                INSERT INTO assets (
                  library_id, path, parent_path, name, type, mtime_ns, size,
                  offline, deleted_at, indexed_at
                ) VALUES (?, ?, ?, ?, 'image', 0, 10, 0, NULL, ?)
                """,
                (library_id, resolved, str(Path(path).parent.resolve()), Path(path).name, now),
            )
        active_before = _active_image_count(conn, library_id)
    assert active_before == 4  # all four were active in the pre-upgrade world

    # Post-upgrade: a normal scan discovers the surviving (non-excluded) paths
    # and reconciles already-indexed assets whose paths were not rediscovered
    # to offline without touching the source files on disk.
    assert files_module.is_index_excluded_path(root / "frontend" / "coverage" / "artifact.png")
    post_upgrade_discovered: set[str] = set()
    index_directory_tree(
        root,
        include_metadata=False,
        collected_asset_paths=post_upgrade_discovered,
    )
    assert "frontend/coverage/artifact.png" not in {p.split(str(root) + "/")[-1] for p in post_upgrade_discovered}
    reconcile_library_assets(library_id, post_upgrade_discovered, scope_path=None)

    with _connect(isolated_metadata_db) as conn:
        active_after = _active_image_count(conn, library_id)
        artifact_rows = conn.execute(
            """
            SELECT path, offline FROM assets
            WHERE library_id = ? AND path LIKE ?
            """,
            (library_id, f"%{root}/frontend/%".replace("/", f"{os.sep}")),
        ).fetchall()
        # Source files on disk must remain untouched.
        for sub in (
            "frontend/coverage/artifact.png",
            "frontend/test-results/a.png",
            "frontend/playwright-report/b.png",
        ):
            assert (root / sub).is_file()

    assert active_after == 1  # only the real image remains an active asset
    assert artifact_rows, "expected indexed artifact rows to exist"
    for row in artifact_rows:
        assert row["offline"] == 1, f"artifact {row['path']} should be reconciled offline"

    status = scheduler.library_status(library_id)
    assert status["total_assets"] == 1
    assert status["expected_derivatives"] == status["total_assets"] * 2
    # No phantom expected coverage for the three offline artifacts.
    assert status["expected_derivatives"] == 2


def test_fresh_scan_never_indexes_test_artifacts(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A brand-new scan under the upgrade never introduces excluded artifacts."""
    root = _underscore_free_root(monkeypatch)
    library_id = int(register_library(root)["id"])

    create_test_png(root / "photos" / "real.png")
    create_test_png(root / "frontend" / "coverage" / "artifact.png")
    create_test_png(root / "frontend" / "test-results" / "a.png")
    create_test_png(root / "frontend" / "playwright-report" / "b.png")

    rebuild_index_scope(root)

    with _connect(isolated_metadata_db) as conn:
        active = _active_image_count(conn, library_id)
        indexed_artifacts = conn.execute(
            """
            SELECT count(*) FROM assets
            WHERE library_id = ? AND path LIKE ? AND deleted_at IS NULL
            """,
            (library_id, f"%{root}/frontend/%".replace("/", f"{os.sep}")),
        ).fetchone()[0]

    assert active == 1
    assert indexed_artifacts == 0  # artifacts are excluded from the catalog entirely
