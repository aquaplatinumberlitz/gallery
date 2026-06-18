"""
Purpose:
Exercise uncovered metadata_parse.py branches for cache size estimation
fallbacks, uncached parse error paths, cache/DB/inflight dispatch, and producer
error handling so backend line coverage stays above the release threshold.

Guarantees:
* _estimate_dict_size falls back to sys.getsizeof for non-JSON-serializable
  dicts (TypeError from object keys, ValueError from circular references).
* _parse_metadata_uncached raises APIError(404) for missing files, re-raises
  APIError from check_image_limits, and wraps generic exceptions as
  APIError(400, INVALID_FILE).
* parse_metadata raises APIError(404) when path.stat() fails with OSError.
* parse_metadata returns cached data on LRU hit, DB data on cache-miss/DB-hit,
  and consumer-side future.result() when an inflight producer is active.
* parse_metadata producer error paths set future exceptions and raise
  APIError(404) for OSError, re-raise APIError, and wrap generic exceptions as
  APIError(500, SERVER_ERROR).

Run when:
* changing metadata_parse.py caching, DB-first reads, or inflight future logic
* tweaking _parse_metadata_uncached error handling or _estimate_dict_size
* adjusting cache key computation or producer/consumer dispatch
"""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path

import pytest

from backend.errors import APIError, ErrorType
from backend.metadata_parse import (
    _estimate_dict_size,
    _metadata_cache,
    _metadata_cache_key,
    _metadata_inflight,
    _parse_metadata_uncached,
    parse_metadata,
)
from backend.metadata_store import upsert_extracted_metadata
from tests.conftest import create_test_png


# ---------------------------------------------------------------------------
# _estimate_dict_size fallbacks (lines 26-27)
# ---------------------------------------------------------------------------


def test_estimate_dict_size_typeerror_fallback() -> None:
    d: dict = {object(): 1}
    size = _estimate_dict_size(d)
    assert size > 0


def test_estimate_dict_size_valueerror_circular_reference() -> None:
    d: dict = {}
    d["self"] = d
    size = _estimate_dict_size(d)
    assert size > 0


def test_estimate_dict_size_normal_dict() -> None:
    size = _estimate_dict_size({"prompt": "hello", "steps": 30})
    assert size > 0


# ---------------------------------------------------------------------------
# _parse_metadata_uncached error paths (lines 39, 46-49)
# ---------------------------------------------------------------------------


def test_parse_uncached_missing_file_raises_404(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.png"
    with pytest.raises(APIError) as exc_info:
        _parse_metadata_uncached(missing)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == ErrorType.NOT_FOUND


def test_parse_uncached_apierror_reraised(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    img = tmp_path / "test.png"
    create_test_png(img)

    import backend.metadata_parse as mp

    def raise_apierror(path: Path) -> None:
        raise APIError(400, ErrorType.INVALID_FILE, "too large")

    monkeypatch.setattr(mp, "check_image_limits", raise_apierror)

    with pytest.raises(APIError) as exc_info:
        _parse_metadata_uncached(img)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == ErrorType.INVALID_FILE


def test_parse_uncached_generic_exception_wrapped_as_400(
    tmp_path: Path,
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    img = tmp_path / "test.png"
    create_test_png(img)

    import backend.metadata_parse as mp

    def raise_runtime(path: Path):
        raise RuntimeError("parse boom")

    monkeypatch.setattr(mp, "extract_metadata", raise_runtime)

    with pytest.raises(APIError) as exc_info:
        _parse_metadata_uncached(img)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == ErrorType.INVALID_FILE
    assert "parse boom" in str(exc_info.value)


# ---------------------------------------------------------------------------
# parse_metadata stat OSError (lines 67-68)
# ---------------------------------------------------------------------------


def test_parse_metadata_stat_oserror_raises_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    img = tmp_path / "test.png"
    create_test_png(img)

    import backend.metadata_parse as mp

    def raise_oserror(path: Path):
        raise OSError("stat failed")

    monkeypatch.setattr(mp, "_metadata_cache_key", raise_oserror)

    with pytest.raises(APIError) as exc_info:
        mp.parse_metadata(img)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == ErrorType.NOT_FOUND


# ---------------------------------------------------------------------------
# parse_metadata cache hit (line 73)
# ---------------------------------------------------------------------------


def test_parse_metadata_cache_hit(
    tmp_path: Path,
    isolated_metadata_db: Path,
) -> None:
    img = tmp_path / "cached.png"
    create_test_png(img)

    _metadata_cache.clear()
    result1 = parse_metadata(img)
    result2 = parse_metadata(img)
    assert result1 == result2
    assert "prompt" in result2


# ---------------------------------------------------------------------------
# parse_metadata DB hit (lines 77-78)
# ---------------------------------------------------------------------------


def test_parse_metadata_db_hit(
    tmp_path: Path,
    isolated_metadata_db: Path,
) -> None:
    img = tmp_path / "db_hit.png"
    create_test_png(img)

    _metadata_cache.clear()
    result1 = parse_metadata(img)
    _metadata_cache.clear()
    result2 = parse_metadata(img)
    assert result1 == result2
    assert "prompt" in result2


# ---------------------------------------------------------------------------
# parse_metadata consumer path — inflight future (lines 86, 89)
# ---------------------------------------------------------------------------


def test_parse_metadata_consumer_waits_for_inflight_future(
    tmp_path: Path,
    isolated_metadata_db: Path,
) -> None:
    img = tmp_path / "consumer.png"
    create_test_png(img)

    _metadata_cache.clear()
    _metadata_inflight.clear()

    key = _metadata_cache_key(img)
    future: Future = Future()
    future.set_result({"tool": "TestTool", "prompt": "consumer result", "params": {}})
    _metadata_inflight[key] = future

    try:
        result = parse_metadata(img)
        assert result["prompt"] == "consumer result"
        assert result["tool"] == "TestTool"
    finally:
        _metadata_inflight.pop(key, None)


# ---------------------------------------------------------------------------
# parse_metadata producer error paths (lines 97-107)
# ---------------------------------------------------------------------------


def test_parse_metadata_producer_oserror_wrapped_as_404(
    tmp_path: Path,
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    img = tmp_path / "oserror.png"
    create_test_png(img)

    import backend.metadata_parse as mp

    _metadata_cache.clear()
    _metadata_inflight.clear()

    def raise_oserror(path: Path):
        raise OSError("disk read error")

    monkeypatch.setattr(mp, "_parse_metadata_uncached", raise_oserror)

    with pytest.raises(APIError) as exc_info:
        mp.parse_metadata(img)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == ErrorType.NOT_FOUND
    assert key_not_in_inflight(img)


def test_parse_metadata_producer_apierror_reraised(
    tmp_path: Path,
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    img = tmp_path / "apierror.png"
    create_test_png(img)

    import backend.metadata_parse as mp

    _metadata_cache.clear()
    _metadata_inflight.clear()

    def raise_apierror(path: Path):
        raise APIError(400, ErrorType.INVALID_FILE, "bad image")

    monkeypatch.setattr(mp, "_parse_metadata_uncached", raise_apierror)

    with pytest.raises(APIError) as exc_info:
        mp.parse_metadata(img)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == ErrorType.INVALID_FILE
    assert key_not_in_inflight(img)


def test_parse_metadata_producer_generic_exception_wrapped_as_500(
    tmp_path: Path,
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    img = tmp_path / "generic.png"
    create_test_png(img)

    import backend.metadata_parse as mp

    _metadata_cache.clear()
    _metadata_inflight.clear()

    def raise_runtime(path: Path):
        raise RuntimeError("internal boom")

    monkeypatch.setattr(mp, "_parse_metadata_uncached", raise_runtime)

    with pytest.raises(APIError) as exc_info:
        mp.parse_metadata(img)
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["error"] == ErrorType.SERVER_ERROR
    assert key_not_in_inflight(img)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def key_not_in_inflight(path: Path) -> bool:
    """Verify the producer cleaned up the inflight entry after an error."""
    try:
        key = _metadata_cache_key(path)
    except OSError:
        return True
    return key not in _metadata_inflight
