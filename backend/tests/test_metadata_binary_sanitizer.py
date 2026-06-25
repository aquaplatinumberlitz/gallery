"""
Purpose:
Verifies binary metadata sanitization before JSON storage and API serialization.

Guarantees:
* known binary PIL info fields are omitted while useful text metadata is preserved
* indexing does not fail when image metadata contains bytes-only payloads

Run when:
* changing metadata extraction, JSON sanitization, or metadata indexer storage
* touching support for PNG/PIL metadata fields
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from backend import indexer, metadata_extract
from backend.metadata_extract import safe_text, sanitize_metadata_for_json
from backend.metadata_store import _persist_metadata_index_jobs


class _FakeImage:
    format = "PNG"
    mode = "RGB"
    size = (32, 24)
    info: dict[str, Any] = {
        "icc_profile": b"binary-icc",
        "exif": b"binary-exif",
        "photoshop": {1061: b"binary-resource"},
        "parameters": "a textual prompt\nSteps: 7, Sampler: Euler, CFG scale: 6.5, Seed: 42, Model: model-a",
    }

    def __enter__(self) -> _FakeImage:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def getexif(self) -> dict[int, Any]:
        return {}


def test_json_sanitizer_omits_known_binary_image_info_and_preserves_text() -> None:
    payload = {
        "image": {
            "icc_profile": b"icc",
            "exif": b"exif",
            "prompt": "keep this prompt",
            "custom_binary": b"unexpected",
        }
    }

    sanitized = sanitize_metadata_for_json(payload)

    assert sanitized == {
        "image": {
            "prompt": "keep this prompt",
            "custom_binary": {"type": "bytes", "length": 10},
        }
    }
    assert safe_text({"photoshop": {1061: b"resource"}, "prompt": "keep"}) == '{"prompt": "keep"}'
    json.dumps(sanitized, ensure_ascii=False, sort_keys=True)


def test_metadata_indexing_sanitizes_pil_binary_info(
    tmp_path: Path,
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_path = tmp_path / "binary-info.png"
    image_path.write_bytes(b"placeholder")

    monkeypatch.setattr(metadata_extract.Image, "open", lambda *_args, **_kwargs: _FakeImage())
    monkeypatch.setattr(metadata_extract.ImageOps, "exif_transpose", lambda img: img)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_WORKER_SLEEP_SECONDS", 0)

    queued = _persist_metadata_index_jobs([image_path], tmp_path)
    assert len(queued.enqueued) == 1

    # Seed a matching asset row so complete_metadata_job can materialize done
    from backend.indexer import MetadataLifecycleWorker
    from backend.metadata_store import _DB_LOCK, _connect, claim_next_metadata_job, create_library

    job_row_data = queued.enqueued[0]
    create_library([tmp_path], name="TestLib")
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size,
               indexed_at, metadata_state) VALUES (
                 (SELECT id FROM libraries WHERE name = 'TestLib'), ?, ?, ?, 'image', ?, ?, ?, 'pending'
               )""",
            (
                job_row_data.path,
                str(Path(job_row_data.path).parent),
                Path(job_row_data.path).name,
                job_row_data.mtime_ns,
                job_row_data.size,
                time.time(),
            ),
        )

    job = claim_next_metadata_job()
    assert job is not None, "Should be able to claim the queued job"
    worker = MetadataLifecycleWorker()
    worker._run_job(job)

    conn = sqlite3.connect(isolated_metadata_db)
    conn.row_factory = sqlite3.Row
    metadata_row = conn.execute(
        "SELECT prompt, model, seed, metadata_json FROM image_metadata WHERE path = ?",
        (str(image_path.resolve()),),
    ).fetchone()
    job_row = conn.execute(
        "SELECT state, error FROM metadata_index_jobs WHERE path = ?",
        (str(image_path.resolve()),),
    ).fetchone()

    assert metadata_row is not None
    assert "a textual prompt" in metadata_row["prompt"]
    assert metadata_row["model"] == "model-a"
    assert metadata_row["seed"] == "42"
    parsed = json.loads(metadata_row["metadata_json"])
    assert parsed["prompt"] == "a textual prompt"
    assert "icc_profile" not in metadata_row["metadata_json"]
    assert "photoshop" not in metadata_row["metadata_json"]
    assert job_row["state"] == "done"
    assert job_row["error"] is None
    assert "Object of type bytes is not JSON serializable" not in (job_row["error"] or "")
