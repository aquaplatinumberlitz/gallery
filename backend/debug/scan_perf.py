"""Provide gated scan performance log emission for backend `/api/scan` diagnostics.

Purpose:
Centralize optional scan performance log lines outside the scan algorithm.

Guarantees:
* scan perf output is emitted only when the caller passes enabled=True
* warm and direct scan summaries use a consistent field order

Scan perf output is emitted only when the caller passes `enabled=True`, keeping
diagnostic message content centralized outside the scan algorithm.

Run when:
* debugging slow /api/scan responses, warm listing hits, or pagination timing.
* changing SCAN_PERF_LOGS behavior, scan timing fields, or warm listing diagnostics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def log_warm_db_hit(*, enabled: bool, target: Path, warm_get_ms: float) -> None:
    """Print a warm indexed listing hit timing line when scan perf logging is enabled."""
    if not enabled:
        return
    print(f"[SCAN PERF] warm_db hit path={target} warm_get={warm_get_ms:.0f}ms", flush=True)


def log_warm_scan_summary(
    *,
    enabled: bool,
    target: Path,
    image_limit: int | None,
    image_cursor: int,
    total_ms: float,
    resolve_ms: float,
    serialize_ms: float,
    warm_result: dict[str, Any],
) -> None:
    """Print the timing summary for a scan served from the warm folder index."""
    if not enabled:
        return

    wr_total = warm_result.get("total_images", 0)
    wr_images = warm_result.get("images", [])
    wr_next = warm_result.get("next_cursor")
    print(
        "[SCAN PERF] "
        f"path={target} "
        f"limit={image_limit if image_limit is not None else 'none'} "
        f"cursor={image_cursor} "
        f"total={total_ms:.0f}ms "
        f"resolve={resolve_ms:.0f}ms "
        f"source=warm_db "
        f"serialize={serialize_ms:.0f}ms "
        f"images_total={wr_total} "
        f"images_returned={len(wr_images)} "
        f"next_cursor={wr_next}",
        flush=True,
    )


def log_direct_scan_summary(
    *,
    enabled: bool,
    target: Path,
    image_limit: int | None,
    image_cursor: int,
    total_ms: float,
    resolve_ms: float,
    scan_perf: dict[str, int | float | None],
    pagination_ms: float,
    serialize_ms: float,
    total_images: int,
    returned_images: int,
    next_cursor: int | None,
) -> None:
    """Print the timing summary for a direct filesystem scan."""
    if not enabled:
        return

    print(
        "[SCAN PERF] "
        f"path={target} "
        f"limit={image_limit if image_limit is not None else 'none'} "
        f"cursor={image_cursor} "
        f"total={total_ms:.0f}ms "
        f"resolve={resolve_ms:.0f}ms "
        f"list={scan_perf['list_ms']:.0f}ms "
        f"recursive_walk={scan_perf['recursive_walk_ms']:.0f}ms "
        f"stat={scan_perf['stat_ms']:.0f}ms "
        f"image_filter={scan_perf['image_filter_ms']:.0f}ms "
        f"folder_filter={scan_perf['folder_filter_ms']:.0f}ms "
        f"metadata={scan_perf['metadata_ms']:.0f}ms "
        f"sort={scan_perf['sort_ms']:.0f}ms "
        f"pagination={pagination_ms:.0f}ms "
        f"serialize={serialize_ms:.0f}ms "
        f"entries={scan_perf['entries_scanned']} "
        f"folders={scan_perf['folders_found']} "
        f"images_total={total_images} "
        f"images_returned={returned_images} "
        f"next_cursor={next_cursor}",
        flush=True,
    )
