"""Image pipeline plan B1/B2: faster derivative generation and the thumb_256 variant.

Purpose:
Pin the generation-speed work of `docs/archived/IMAGE_PIPELINE_PLAN.md` (B1) and the new 256 px thumbnail
(B2). A cold album used to render every variant with its own decode of the source, a method-6 WebP encode and
a writer op for the (unchanged) source dimensions. Now one claimed job also claims the queued sibling variants
of the same asset and renders them from a single decode as a cascade, while each variant keeps its own claim
token, lease, revalidation, fenced completion and failure handling.

Guarantees:
WebP derivatives use libwebp method 4; the cascade resize matches `Image.thumbnail` sizes; one job renders every
queued variant of an asset from one decode and the requested variant completes first; a sibling whose claim was
lost (recovery) is not written by the stale worker; one sibling failing, or a changed or invalid source, is
handled per claim and never marks another variant ready by mistake; the group heartbeat renews every open
claim; cached variants are not re-rendered; the source dimension upsert is skipped when the catalog already
holds them and still runs when they differ; `thumb_256` is a configured variant, accepted by `/api/thumbnail`,
and scheduled by reconcile.

Run when:
Changing derivative rendering or encoding, the sibling claim/batch path in `derivative_scheduler/execution.py`,
`render_derivatives`, `image_dimensions_unchanged`, or `DERIVATIVE_VARIANTS`.
"""

from __future__ import annotations

import errno
import os
import random
import sqlite3
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import backend.derivative_scheduler.execution as scheduler_execution_module
import backend.thumbnails as thumbnails
from backend.config import DERIVATIVE_VARIANTS
from backend.derivative_scheduler import DerivativeScheduler, derivative_variant
from backend.metadata_store import index_file
from tests.conftest import create_test_png
from tests.worker_contention_support import seed_library

BIG_QUOTA = 1024 * 1024 * 1024
VARIANTS = {
    "thumb_128": ("thumbnail", 128, 78),
    "thumb_256": ("thumbnail", 256, 78),
    "thumb_512": ("thumbnail", 512, 78),
    "preview_1440": ("preview", 1440, 86),
}


@pytest.fixture
def catalog(isolated_metadata_db: Path, isolated_gallery_root: Path, isolated_thumbnail_cache: Path, monkeypatch):
    """One library with one 1800x1200 indexed PNG: ``(db_path, asset_id, path, scheduler)``."""
    import backend.visual_fingerprints as visual_fingerprints

    monkeypatch.setattr(visual_fingerprints, "notify_derivative_ready", lambda _asset_id: None)
    root = isolated_gallery_root / "pipeline"
    root.mkdir(parents=True, exist_ok=True)
    seed_library(root)
    image = root / "photo.png"
    create_test_png(image, size=(1800, 1200))
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 1800, 1200)
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=BIG_QUOTA)
    asset_id = scheduler.find_asset_id(image)
    assert asset_id is not None
    return isolated_metadata_db, asset_id, image, scheduler


def _queue_all_variants(scheduler: DerivativeScheduler, asset_id: int, *, requested: str | None = None) -> None:
    """Queue the four variants the way warm-up does (priority 3); ``requested`` is then bumped to priority 0."""
    summary = scheduler.reconcile_desired_derivatives(asset_ids=[asset_id], reason="phase_1")
    assert summary.created_jobs == 4
    if requested is not None:
        kind, edge, quality = VARIANTS[requested]
        scheduler.schedule_derivative(asset_id, kind, requested, 0, max_long_edge=edge, quality=quality, format="webp")


def _derivatives(db_path: Path) -> dict[str, dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT d.variant, d.status, d.cache_path, d.byte_size, j.state AS job_state,
                   j.result_code AS result_code, j.claim_token AS claim_token
            FROM asset_derivatives d JOIN derivative_jobs j ON j.derivative_id = d.id
            """
        ).fetchall()
    return {row["variant"]: dict(row) for row in rows}


def test_webp_derivatives_use_encoder_method_4(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Method 6 cost ~2x the encode time for ~7 % fewer bytes; every variant now uses method 4."""
    source = tmp_path / "source.png"
    create_test_png(source, size=(300, 200))
    seen: list[dict[str, Any]] = []
    real_save = Image.Image.save

    def spy(self, fp, format=None, **params):  # noqa: A002, ANN001, ANN003
        seen.append({"format": format, **params})
        return real_save(self, fp, format, **params)

    monkeypatch.setattr(Image.Image, "save", spy)
    monkeypatch.setattr(thumbnails, "_record_image_dimensions", lambda *_a, **_k: None, raising=False)
    monkeypatch.setattr(thumbnails, "upsert_image_dimensions", lambda *_a, **_k: True)
    thumbnails._render_derivative_impl(source, max_long_edge=128, quality=78, format="webp", no_upscale=True)
    thumbnails._render_derivative_impl(source, max_long_edge=128, quality=80, format="jpeg", no_upscale=True)

    assert seen[0]["format"] == "WEBP" and seen[0]["method"] == 4
    assert seen[1]["format"] == "JPEG" and "method" not in seen[1]


@pytest.mark.parametrize(
    "size", [(1800, 1200), (1200, 1800), (1000, 1000), (4000, 33), (33, 4000), (300, 200), (513, 7)]
)
@pytest.mark.parametrize("edge", [128, 256, 512, 1440])
def test_cascade_resize_matches_pillow_thumbnail_dimensions(size: tuple[int, int], edge: int) -> None:
    """The non-mutating resize used to share one decode must give the dimensions `thumbnail()` always gave."""
    image = Image.new("RGB", size, (10, 200, 90))
    expected = image.copy()
    expected.thumbnail((edge, edge), Image.Resampling.LANCZOS)

    fitted = thumbnails._fit_image(image, edge, no_upscale=True)

    assert fitted.size == expected.size
    assert image.size == size, "the shared intermediate must not be mutated"


def test_one_job_renders_every_queued_variant_of_the_asset_from_one_decode(
    catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, asset_id, image, scheduler = catalog
    _queue_all_variants(scheduler, asset_id)
    decodes: list[Path] = []
    real_decode = thumbnails._decode_source_rgb

    def counting_decode(path):  # noqa: ANN001
        decodes.append(Path(path))
        return real_decode(path)

    monkeypatch.setattr(thumbnails, "_decode_source_rgb", counting_decode)

    job = scheduler._claim_job("worker-1")
    assert job is not None
    scheduler._run_job(job)

    rows = _derivatives(db_path)
    assert {name: row["status"] for name, row in rows.items()} == dict.fromkeys(VARIANTS, "ready")
    assert {row["job_state"] for row in rows.values()} == {"done"}
    assert len(decodes) == 1, "all four variants must come from one decode of the source"
    for name, (_kind, edge, _quality) in VARIANTS.items():
        with Image.open(rows[name]["cache_path"]) as derivative:
            assert derivative.format == "WEBP"
            assert max(derivative.size) == edge, (name, derivative.size)
            assert derivative.size[0] / derivative.size[1] == pytest.approx(1.5, abs=0.02)
        assert rows[name]["byte_size"] == Path(rows[name]["cache_path"]).stat().st_size


def test_the_requested_variant_is_completed_before_its_interactive_siblings(
    catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, asset_id, _image, scheduler = catalog
    _queue_all_variants(scheduler, asset_id, requested="thumb_512")
    kind, edge, quality = VARIANTS["thumb_256"]
    scheduler.schedule_derivative(asset_id, kind, "thumb_256", 1, max_long_edge=edge, quality=quality, format="webp")
    completed: list[str] = []
    real_complete = scheduler._complete_claim

    def recording(job, cache_path, byte_size):  # noqa: ANN001
        completed.append(str(job["variant"]))
        return real_complete(job, cache_path, byte_size)

    monkeypatch.setattr(scheduler, "_complete_claim", recording)

    job = scheduler._claim_job("worker-1")
    assert job is not None and job["variant"] == "thumb_512"
    scheduler._run_job(job)

    assert completed == ["thumb_512", "thumb_256"], "the waiting request's variant is completed first"


def test_an_interactive_job_does_not_drag_background_siblings_into_its_latency(catalog) -> None:
    """A request waiting for thumb_512 must not wait for a whole cascade; the rest is one later background batch."""
    db_path, asset_id, _image, scheduler = catalog
    _queue_all_variants(scheduler, asset_id, requested="thumb_512")

    job = scheduler._claim_job("worker-1")
    assert job is not None and job["variant"] == "thumb_512"
    assert scheduler._claim_siblings(job) == [], "background siblings are not claimed by an interactive job"
    scheduler._run_job(job)  # nothing to batch: the single-variant path

    rows = _derivatives(db_path)
    assert (rows["thumb_512"]["status"], rows["thumb_512"]["job_state"]) == ("ready", "done")
    assert {rows[name]["job_state"] for name in ("thumb_128", "thumb_256", "preview_1440")} == {"queued"}

    background = scheduler._claim_job("worker-2")
    assert background is not None
    scheduler._run_job(background)  # a background claim batches the three that are left

    rows = _derivatives(db_path)
    assert {name: row["job_state"] for name, row in rows.items()} == dict.fromkeys(VARIANTS, "done")


def test_siblings_of_other_assets_or_identities_are_not_claimed(catalog) -> None:
    db_path, asset_id, image, scheduler = catalog
    other = image.parent / "other.png"
    create_test_png(other, size=(400, 300))
    stat = other.stat()
    assert index_file(other, other.name, other.parent, "image", stat.st_mtime, stat.st_size, 400, 300)
    other_id = scheduler.find_asset_id(other)
    assert other_id is not None
    scheduler.schedule_derivative(asset_id, "thumbnail", "thumb_128", 3, max_long_edge=128, quality=78)
    scheduler.schedule_derivative(other_id, "thumbnail", "thumb_128", 3, max_long_edge=128, quality=78)
    scheduler.schedule_derivative(other_id, "thumbnail", "thumb_512", 3, max_long_edge=512, quality=78)

    job = scheduler._claim_job("worker-1")
    assert job is not None and job["asset_id"] == asset_id
    assert scheduler._claim_siblings(job) == []

    with sqlite3.connect(db_path) as conn:
        states = conn.execute(
            "SELECT d.asset_id, j.state FROM derivative_jobs j JOIN asset_derivatives d ON d.id = j.derivative_id"
        ).fetchall()
    assert sorted(states) == sorted([(asset_id, "running"), (other_id, "queued"), (other_id, "queued")])


def test_a_sibling_claim_lost_to_recovery_is_not_completed_by_the_stale_worker(
    catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each sibling is fenced by its own claim token: recovery re-queueing one leaves the others untouched."""
    db_path, asset_id, _image, scheduler = catalog
    _queue_all_variants(scheduler, asset_id)
    real_validate = scheduler._validate_claimed_source
    tampered = threading.Event()

    def validate_and_lose_one_claim(job, source):  # noqa: ANN001
        if not tampered.is_set():
            tampered.set()
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "UPDATE derivative_jobs SET state = 'queued', claim_token = NULL, claimed_by = NULL, "
                    "lease_expires_at = NULL WHERE derivative_id = (SELECT id FROM asset_derivatives "
                    "WHERE variant = 'thumb_256')"
                )
        return real_validate(job, source)

    monkeypatch.setattr(scheduler, "_validate_claimed_source", validate_and_lose_one_claim)

    job = scheduler._claim_job("worker-1")
    assert job is not None
    scheduler._run_job(job)

    rows = _derivatives(db_path)
    assert rows["thumb_256"]["status"] != "ready", "a stale claim must write nothing"
    assert rows["thumb_256"]["job_state"] == "queued"
    for name in ("thumb_128", "thumb_512", "preview_1440"):
        assert (rows[name]["status"], rows[name]["job_state"]) == ("ready", "done"), name


def test_one_sibling_failing_does_not_fail_or_block_the_others(catalog, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, asset_id, _image, scheduler = catalog
    _queue_all_variants(scheduler, asset_id)
    real_fit = thumbnails._fit_image

    def fit_or_break(img, max_long_edge, *, no_upscale):  # noqa: ANN001
        if max_long_edge == 256:
            raise RuntimeError("boom")  # an internal fault, not a decode error (ValueError is a permanent decode error)
        return real_fit(img, max_long_edge, no_upscale=no_upscale)

    monkeypatch.setattr(thumbnails, "_fit_image", fit_or_break)

    job = scheduler._claim_job("worker-1")
    assert job is not None
    scheduler._run_job(job)

    rows = _derivatives(db_path)
    assert (rows["thumb_256"]["status"], rows["thumb_256"]["job_state"]) == ("failed", "failed")
    assert rows["thumb_256"]["result_code"] == "internal_error"
    for name in ("thumb_128", "thumb_512", "preview_1440"):
        assert (rows[name]["status"], rows[name]["job_state"]) == ("ready", "done"), name


def test_a_source_that_changed_after_the_claim_skips_every_claimed_variant(catalog) -> None:
    db_path, asset_id, image, scheduler = catalog
    _queue_all_variants(scheduler, asset_id)
    job = scheduler._claim_job("worker-1")
    assert job is not None
    create_test_png(image, size=(1700, 1100))  # new size: the identity the jobs were queued for is gone

    scheduler._run_job(job)

    rows = _derivatives(db_path)
    assert {row["job_state"] for row in rows.values()} == {"skipped"}
    assert {row["result_code"] for row in rows.values()} == {"source_changed"}
    assert not any(row["status"] == "ready" for row in rows.values())


def test_an_invalid_source_fails_every_claimed_variant_permanently(catalog) -> None:
    db_path, asset_id, image, scheduler = catalog
    _queue_all_variants(scheduler, asset_id)
    stat = image.stat()
    garbage = b"definitely not a png" * 8
    image.write_bytes(garbage)
    # keep the identity the jobs were queued for so the source still validates, but the decode fails
    import os

    os.utime(image, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE assets SET size = ? WHERE id = ?", (len(garbage), asset_id))
        conn.execute("UPDATE asset_derivatives SET source_size = ? WHERE asset_id = ?", (len(garbage), asset_id))

    job = scheduler._claim_job("worker-1")
    assert job is not None
    scheduler._run_job(job)

    rows = _derivatives(db_path)
    assert {row["job_state"] for row in rows.values()} == {"failed"}
    assert {row["result_code"] for row in rows.values()} == {"invalid_source"}


def _write_truncated_png(path: Path, size: tuple[int, int] = (800, 600)) -> None:
    """A random-noise PNG cut in half: the header still opens, the pixel data does not decode."""
    pixels = random.Random(20260211).randbytes(size[0] * size[1] * 3)
    Image.frombytes("RGB", size, pixels).save(path, format="PNG")
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])


def _job_rows(db_path: Path, asset_path: str | None = None) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT j.id AS job_id, j.state, j.result_code, j.attempts
            FROM derivative_jobs j
            JOIN asset_derivatives d ON d.id = j.derivative_id
            JOIN assets a ON a.id = d.asset_id
            WHERE ? IS NULL OR a.path = ?
            ORDER BY j.id
            """,
            (asset_path, asset_path),
        ).fetchall()
    return [dict(row) for row in rows]


def test_a_truncated_source_fails_every_claimed_variant_without_retry(catalog) -> None:
    db_path, asset_id, image, scheduler = catalog
    _queue_all_variants(scheduler, asset_id)
    stat = image.stat()
    _write_truncated_png(image)
    truncated_size = image.stat().st_size
    os.utime(image, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE assets SET size = ? WHERE id = ?", (truncated_size, asset_id))
        conn.execute("UPDATE asset_derivatives SET source_size = ? WHERE asset_id = ?", (truncated_size, asset_id))

    job = scheduler._claim_job("worker-1")
    assert job is not None
    started = time.monotonic()
    scheduler._run_job(job)
    elapsed = time.monotonic() - started

    assert elapsed < 1.5, f"a permanent decode failure must not back off ({elapsed:.2f}s)"
    rows = _derivatives(db_path)
    assert {row["job_state"] for row in rows.values()} == {"failed"}
    assert {row["result_code"] for row in rows.values()} == {"invalid_source"}
    assert {row["attempts"] for row in _job_rows(db_path)} == {1}


def test_a_transient_os_error_while_rendering_still_requeues_the_job(catalog, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, asset_id, _image, scheduler = catalog
    kind, edge, quality = VARIANTS["thumb_128"]
    scheduler.schedule_derivative(asset_id, kind, "thumb_128", 0, max_long_edge=edge, quality=quality, format="webp")
    job = scheduler._claim_job("worker-1")
    assert job is not None
    monkeypatch.setattr(scheduler, "_claim_siblings", lambda _job: [])

    def busy_decode(_path):  # noqa: ANN001
        raise OSError(errno.EBUSY, "device or resource busy")

    monkeypatch.setattr(thumbnails, "_decode_source_rgb", busy_decode)
    scheduler._run_job(job)

    row = _job_rows(db_path)[0]
    assert (row["state"], row["result_code"], row["attempts"]) == ("queued", None, 1)


def test_the_group_heartbeat_renews_the_lease_of_every_open_claim(catalog, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path, asset_id, _image, scheduler = catalog
    _queue_all_variants(scheduler, asset_id)
    monkeypatch.setattr(scheduler_execution_module, "DERIVATIVE_LEASE_HEARTBEAT_SECONDS", 0.1)
    renewed: set[int] = set()
    real_renew = scheduler._renew_lease

    def recording_renew(job_id, claim_token):  # noqa: ANN001
        renewed.add(int(job_id))
        return real_renew(job_id, claim_token)

    monkeypatch.setattr(scheduler, "_renew_lease", recording_renew)
    real_encode = thumbnails._encode_image

    def slow_encode(*args, **kwargs):  # noqa: ANN002, ANN003
        time.sleep(0.5)
        return real_encode(*args, **kwargs)

    monkeypatch.setattr(thumbnails, "_encode_image", slow_encode)

    job = scheduler._claim_job("worker-1")
    assert job is not None
    scheduler._run_job(job)

    with sqlite3.connect(db_path) as conn:
        all_jobs = {row[0] for row in conn.execute("SELECT id FROM derivative_jobs")}
    assert renewed == all_jobs, "every claim of the batch must be kept alive while the cascade runs"


def test_a_variant_already_in_the_cache_is_not_rendered_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "cached.png"
    create_test_png(source, size=(900, 600))
    monkeypatch.setattr(thumbnails, "upsert_image_dimensions", lambda *_a, **_k: True)
    monkeypatch.setattr(thumbnails, "image_dimensions_unchanged", lambda *_a, **_k: True)
    monkeypatch.setattr(
        thumbnails, "_thumbnail_disk_cache", type(thumbnails._thumbnail_disk_cache)(str(tmp_path / "dc"))
    )
    monkeypatch.setattr(thumbnails, "_thumbnail_file_dir", tmp_path / "files")
    specs = [
        thumbnails.DerivativeSpec("thumbnail", 128, 78, "webp"),
        thumbnails.DerivativeSpec("thumbnail", 512, 78, "webp"),
    ]
    first = dict(thumbnails.render_derivatives(source, specs))
    assert all(isinstance(result, thumbnails.RenderedDerivative) for result in first.values())

    decoded: list[Any] = []
    real_decode = thumbnails._decode_source_rgb
    monkeypatch.setattr(thumbnails, "_decode_source_rgb", lambda path: (decoded.append(path), real_decode(path))[1])
    second = dict(thumbnails.render_derivatives(source, specs))

    assert decoded == [], "a fully cached request must not decode the source"
    assert {i: r.path for i, r in second.items()} == {i: r.path for i, r in first.items()}


def test_source_dimensions_are_written_only_when_the_catalog_does_not_hold_them(
    catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, asset_id, image, _scheduler = catalog
    calls: list[tuple[Any, ...]] = []
    real_upsert = thumbnails.upsert_image_dimensions

    def counting_upsert(*args, **kwargs):  # noqa: ANN002, ANN003
        calls.append(args)
        return real_upsert(*args, **kwargs)

    monkeypatch.setattr(thumbnails, "upsert_image_dimensions", counting_upsert)

    thumbnails._render_derivative_impl(image, max_long_edge=128, quality=78, format="webp", no_upscale=True)
    after_first = len(calls)
    thumbnails._render_derivative_impl(image, max_long_edge=512, quality=78, format="webp", no_upscale=True)
    thumbnails._render_derivative_impl(image, max_long_edge=256, quality=78, format="webp", no_upscale=True)

    assert after_first <= 1
    assert len(calls) == after_first, "an unchanged catalog row must not cost a writer op per render"

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE assets SET width = 1, height = 1 WHERE id = ?", (asset_id,))
    thumbnails._render_derivative_impl(image, max_long_edge=128, quality=78, format="webp", no_upscale=True)

    assert len(calls) == after_first + 1, "dimensions that differ from the catalog must still be written"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT width, height FROM assets WHERE id = ?", (asset_id,)).fetchone() == (1800, 1200)


# --- B2: thumb_256 -----------------------------------------------------------------------------------


def test_thumb_256_is_a_configured_variant() -> None:
    names = [str(variant["name"]) for variant in DERIVATIVE_VARIANTS["thumbnail"]]
    assert "thumb_256" in names
    assert names[0] == "thumb_128", "the first variant is the scheduling default and must not change"
    assert derivative_variant("thumbnail", 256, 78, "webp") == "thumb_256"


def test_reconcile_schedules_thumb_256_with_the_other_variants(catalog) -> None:
    db_path, asset_id, _image, scheduler = catalog
    _queue_all_variants(scheduler, asset_id)
    assert set(_derivatives(db_path)) == set(VARIANTS)


def test_thumbnail_endpoint_serves_the_256_variant(isolated_app: TestClient, temp_gallery: Path) -> None:
    path = temp_gallery / "album_a" / "001.png"

    response = isolated_app.get("/api/thumbnail", params={"path": str(path), "max_long_edge": 256})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert "-256-webp-" in response.headers["etag"]
    with Image.open(BytesIO(response.content)) as img:
        assert max(img.size) == 256

    rejected = isolated_app.get("/api/thumbnail", params={"path": str(path), "max_long_edge": 300})
    assert rejected.status_code == 422


def test_a_truncated_image_is_a_fast_400_and_is_not_retried_over_http(
    isolated_app: TestClient, temp_gallery: Path, isolated_metadata_db: Path
) -> None:
    path = temp_gallery / "album_a" / "truncated.png"
    _write_truncated_png(path)
    stat = path.stat()
    assert index_file(path, path.name, path.parent, "image", stat.st_mtime, stat.st_size, 800, 600)

    for request_number in (1, 2):
        started = time.monotonic()
        response = isolated_app.get("/api/thumbnail", params={"path": str(path)})
        elapsed = time.monotonic() - started

        assert response.status_code == 400, response.text
        assert "invalid_file" in response.text
        assert elapsed < 1.5, f"request {request_number} took {elapsed:.2f}s; a permanent failure must not back off"

    jobs = _job_rows(isolated_metadata_db, str(path))
    assert len(jobs) == 2, "each request creates one job; a retry loop would show more attempts per job"
    assert {(job["state"], job["result_code"], job["attempts"]) for job in jobs} == {("failed", "invalid_source", 1)}
