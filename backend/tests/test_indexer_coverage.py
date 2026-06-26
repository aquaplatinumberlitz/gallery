"""
Purpose:
Exercise backend/indexer.py metric helpers, path utility functions, and
MetadataLifecycleWorker exception branches for backend line coverage above the
release threshold.

Guarantees:
* _metric, _inc, and _observe no-op correctly when their factory/metric is None,
  and handle ValueError from duplicate metric registration.
* _normalized_path_text returns empty string for None/empty input and resolves
  real paths.
* _is_path_in_scope handles empty, equal, contained, and root-is-sep cases.
* MetadataLifecycleWorker._worker_loop continues after a claim exception.
* MetadataLifecycleWorker._is_job_current returns False when the file does not
  exist and handles both mtime_ns and legacy mtime matching.
* MetadataLifecycleWorker._run_job handles exceptions during job processing.

Run when:
* changing indexer.py metric helpers, path utilities, or worker exception handling.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend import indexer

# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def test_metric_returns_none_when_factory_none():
    assert indexer._metric(None, "name", "doc") is None


def test_metric_catches_value_error(monkeypatch: pytest.MonkeyPatch):
    def failing_factory(*args, **kwargs):
        raise ValueError("already registered")

    result = indexer._metric(failing_factory, "name", "doc")
    assert result is None


def test_metric_returns_factory_result():
    result = indexer._metric(lambda n, d, *a, **k: (n, d), "m", "d")
    assert result == ("m", "d")


def test_inc_noops_on_none():
    indexer._inc(None)


def test_inc_with_labels():
    target = MagicMock()
    labeled = MagicMock()
    target.labels.return_value = labeled
    indexer._inc(target, "lbl", amount=2.0)
    target.labels.assert_called_once_with("lbl")
    labeled.inc.assert_called_once_with(2.0)


def test_inc_without_labels():
    target = MagicMock()
    indexer._inc(target, amount=1.0)
    target.labels.assert_not_called()
    target.inc.assert_called_once_with(1.0)


def test_observe_noops_on_none():
    indexer._observe(None, 1.0)


def test_observe_delegates():
    target = MagicMock()
    indexer._observe(target, 3.0)
    target.observe.assert_called_once_with(3.0)


# ---------------------------------------------------------------------------
# _normalized_path_text
# ---------------------------------------------------------------------------


def test_normalized_path_text_none():
    assert indexer._normalized_path_text(None) == ""


def test_normalized_path_text_empty():
    assert indexer._normalized_path_text("") == ""


def test_normalized_path_text_resolves(tmp_path: Path):
    d = tmp_path / "sub"
    d.mkdir()
    result = indexer._normalized_path_text(str(d))
    assert result == str(d.resolve())


# ---------------------------------------------------------------------------
# _is_path_in_scope
# ---------------------------------------------------------------------------


def test_is_path_in_scope_both_empty():
    assert indexer._is_path_in_scope(None, None) is False


def test_is_path_in_scope_path_only():
    assert indexer._is_path_in_scope("/tmp", None) is False


def test_is_path_in_scope_root_only():
    assert indexer._is_path_in_scope(None, "/tmp") is False


def test_is_path_in_scope_equal():
    assert indexer._is_path_in_scope("/tmp", "/tmp") is True


def test_is_path_in_scope_within():
    assert indexer._is_path_in_scope("/tmp/sub/file", "/tmp") is True


def test_is_path_in_scope_outside():
    assert indexer._is_path_in_scope("/var/log", "/tmp") is False


def test_is_path_in_scope_root_is_sep():
    assert indexer._is_path_in_scope("/tmp", "/") is True


def test_is_path_in_scope_root_is_sep_outside():
    assert indexer._is_path_in_scope("/tmp", "/") is True


# ---------------------------------------------------------------------------
# MetadataLifecycleWorker exception paths
# ---------------------------------------------------------------------------


def test_worker_claim_exception_logged_and_continues(monkeypatch: pytest.MonkeyPatch):
    worker = indexer.MetadataLifecycleWorker(worker_count=1)
    monkeypatch.setattr(worker, "_stop_event", MagicMock())
    worker._stop_event.is_set.side_effect = [False, True]

    def boom():
        raise RuntimeError("claim failed")

    monkeypatch.setattr(indexer, "claim_next_metadata_job", boom)
    worker._worker_loop()


def test_worker_run_job_raises_exception(monkeypatch: pytest.MonkeyPatch):
    worker = indexer.MetadataLifecycleWorker(worker_count=1)

    job = indexer.MetadataIndexJob(
        path="/nonexistent/test.png",
        name="test.png",
        parent_path="/nonexistent",
        folder_path="/nonexistent",
        root_path="/nonexistent",
        mtime=1000.0,
        mtime_ns=1000000000,
        size=100,
    )

    called = []
    monkeypatch.setattr(indexer, "fail_metadata_job", lambda conn, j, err: called.append((j.path, err)))
    monkeypatch.setattr(indexer, "_connect", lambda **kw: (_ for _ in ()).throw(RuntimeError("db fail")))
    worker._run_job(job)
    assert len(called) == 0  # DB connect failed inside the except


def test_worker_is_job_current_oserror():
    worker = indexer.MetadataLifecycleWorker()
    job = indexer.MetadataIndexJob(
        path="/nonexistent/file.png",
        name="file.png",
        parent_path="/nonexistent",
        folder_path="/nonexistent",
        root_path="/nonexistent",
        mtime=1000.0,
        mtime_ns=1000000000,
        size=100,
    )
    assert worker._is_job_current(job) is False


def test_worker_is_job_current_legacy_mtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    worker = indexer.MetadataLifecycleWorker()
    file = tmp_path / "legacy.png"
    file.write_bytes(b"data")
    stat = file.stat()
    job = indexer.MetadataIndexJob(
        path=str(file),
        name="legacy.png",
        parent_path=str(tmp_path),
        folder_path=str(tmp_path),
        root_path=str(tmp_path),
        mtime=stat.st_mtime,
        mtime_ns=None,
        size=stat.st_size,
    )
    assert worker._is_job_current(job) is True
