import os
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .albums import build_album_metadata
from .config import DEFAULT_ROOT, SCAN_PERF_LOGS_ENABLED
from .errors import APIError, ErrorType
from .files import is_image, natural_sort_key
from .indexer import enqueue_metadata_jobs_from_scan
from .metadata_store import (
    get_cached_dimensions_for_files,
    index_directory_tree,
    index_file,
    index_files_from_scan,
)
from .models import FileNode
from .paths import is_path_safe, resolve_path

router = APIRouter()


def _new_scan_perf() -> dict[str, int | float | None]:
    return {
        "list_ms": 0.0,
        "recursive_walk_ms": 0.0,
        "stat_ms": 0.0,
        "image_filter_ms": 0.0,
        "folder_filter_ms": 0.0,
        "metadata_ms": 0.0,
        "sort_ms": 0.0,
        "entries_scanned": 0,
        "folders_found": 0,
        "images_found": 0,
    }


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def scan_directory(target_path: Path) -> tuple[list[FileNode], list[FileNode], dict[str, int | float | None]]:
    perf = _new_scan_perf()
    if not target_path.exists():
        raise APIError(404, ErrorType.NOT_FOUND, "Folder not found")
    if not target_path.is_dir():
        raise APIError(400, ErrorType.NOT_DIRECTORY, "Path is not a folder")

    folders: list[FileNode] = []
    images: list[FileNode] = []
    image_entries: list[tuple[str, str, float, int]] = []
    try:
        list_started = time.perf_counter()
        entries = list(os.scandir(target_path))
        perf["list_ms"] = _elapsed_ms(list_started)
        perf["entries_scanned"] = len(entries)

        for entry in entries:
            if entry.name.startswith("."):
                continue

            entry_path = Path(entry.path)

            folder_filter_started = time.perf_counter()
            try:
                is_dir = entry.is_dir()
            except OSError:
                is_dir = False
            perf["folder_filter_ms"] += _elapsed_ms(folder_filter_started)

            if is_dir:
                folder_filter_started = time.perf_counter()
                meta = build_album_metadata(entry_path)
                perf["folder_filter_ms"] += _elapsed_ms(folder_filter_started)
                folders.append(
                    FileNode(
                        name=entry.name,
                        path=str(entry_path.resolve()),
                        type="folder",
                        has_children=meta["has_children"],
                        cover_images=meta["cover_images"],
                        mtime=meta["mtime"],
                        image_count=meta["image_count"],
                    )
                )
                continue

            image_filter_started = time.perf_counter()
            try:
                is_file = entry.is_file()
            except OSError:
                is_file = False
            is_image_file = is_file and is_image(entry_path)
            perf["image_filter_ms"] += _elapsed_ms(image_filter_started)

            if is_image_file:
                try:
                    stat_started = time.perf_counter()
                    stat = entry.stat()
                    mtime = stat.st_mtime
                    size = stat.st_size
                except OSError:
                    mtime = 0
                    size = 0
                finally:
                    perf["stat_ms"] += _elapsed_ms(stat_started)

                try:
                    resolved_path = str(entry_path.resolve())
                except OSError:
                    resolved_path = str(entry_path.absolute())
                image_entries.append((entry.name, resolved_path, mtime, size))
            else:
                continue

        metadata_started = time.perf_counter()
        cached_dimensions = get_cached_dimensions_for_files(
            (path, mtime, size) for _, path, mtime, size in image_entries
        )
        perf["metadata_ms"] += _elapsed_ms(metadata_started)

        for name, path, mtime, _size in image_entries:
            dimensions = cached_dimensions.get(path)
            images.append(
                FileNode(
                    name=name,
                    path=path,
                    type="image",
                    has_children=False,
                    cover_images=[],
                    mtime=mtime,
                    width=dimensions.width if dimensions else None,
                    height=dimensions.height if dimensions else None,
                )
            )
    except PermissionError:
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Permission denied")

    sort_started = time.perf_counter()
    folders.sort(key=lambda x: natural_sort_key(x.name))
    images.sort(key=lambda x: natural_sort_key(x.name))
    perf["sort_ms"] = _elapsed_ms(sort_started)
    perf["folders_found"] = len(folders)
    perf["images_found"] = len(images)

    return folders, images, perf


@router.get("/api/scan")
async def api_scan(
    background_tasks: BackgroundTasks,
    path: str | None = Query(None, description="Absolute path to scan"),
    image_limit: int | None = Query(None, ge=1, le=5000, description="Max images to return"),
    image_cursor: int = Query(0, ge=0, description="Cursor/offset for images"),
):
    request_started = time.perf_counter()
    resolve_started = time.perf_counter()
    target = resolve_path(path) if path else DEFAULT_ROOT
    resolve_ms = _elapsed_ms(resolve_started)
    if not is_path_safe(target):
        raise APIError(403, "permission", "Access denied: path outside allowed root")
    folders, images, scan_perf = await run_in_threadpool(scan_directory, target)

    pagination_started = time.perf_counter()
    total_images = len(images)
    start = image_cursor
    end = image_cursor + image_limit if image_limit else total_images
    paged_images = images[start:end]
    next_cursor = end if end < total_images else None
    pagination_ms = _elapsed_ms(pagination_started)

    target_stat_started = time.perf_counter()
    target_mtime = target.stat().st_mtime
    scan_perf["stat_ms"] += _elapsed_ms(target_stat_started)
    background_tasks.add_task(index_file, target, target.name or str(target), target.parent, "folder", target_mtime, None, None, None)
    background_tasks.add_task(index_files_from_scan, folders, images)
    background_tasks.add_task(index_directory_tree, target, False)
    background_tasks.add_task(enqueue_metadata_jobs_from_scan, images, target)

    response_payload = {
        "folders": folders,
        "images": paged_images,
        "next_cursor": next_cursor,
        "total_images": total_images,
    }
    serialize_started = time.perf_counter()
    encoded_payload = jsonable_encoder(response_payload)
    serialize_ms = _elapsed_ms(serialize_started)
    total_ms = _elapsed_ms(request_started)

    if SCAN_PERF_LOGS_ENABLED:
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
            f"images_returned={len(paged_images)} "
            f"next_cursor={next_cursor}",
            flush=True,
        )

    return JSONResponse(content=encoded_payload)
