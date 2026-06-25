"""Persist gallery file indexes, extracted metadata, job queues, and search queries."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "backend.metadata_store"

from ..albums import build_album_metadata as build_album_metadata
from ..config import (
    ENABLE_WARM_INDEXED_LISTING as ENABLE_WARM_INDEXED_LISTING,
)
from ..config import (
    GALLERY_CATALOG_WRITE_BATCH_SIZE as GALLERY_CATALOG_WRITE_BATCH_SIZE,
)
from ..config import GALLERY_METADATA_DB as GALLERY_METADATA_DB
from ..config import (
    PATH_SAFETY_ROOT as PATH_SAFETY_ROOT,
)
from ..config import THUMBNAIL_CACHE_DIR as THUMBNAIL_CACHE_DIR
from ..files import asset_type_for_path as asset_type_for_path
from ..files import is_asset_path as is_asset_path
from ..files import is_image_path as is_image_path
from ..files import is_index_excluded_path as is_index_excluded_path
from ..metadata_extract import ExtractedMetadata as ExtractedMetadata
from ..metadata_extract import contains_cjk as contains_cjk
from ..metadata_extract import extract_metadata as extract_metadata
from ..metadata_extract import parse_float as parse_float
from ..metadata_extract import parse_int as parse_int
from ..metadata_extract import safe_text as safe_text
from ..metadata_extract import sanitize_metadata_for_json as sanitize_metadata_for_json
from ..models import FileNode as FileNode
from ..models import VideoFileNode as VideoFileNode
from . import _db as _db
from . import path_utils as path_utils
from ._db import (
    _DB_LOCK as _DB_LOCK,
)
from ._db import (
    MAX_METADATA_JOB_ATTEMPTS as MAX_METADATA_JOB_ATTEMPTS,
)
from ._db import (
    _connect as _connect,
)
from ._resources import (
    _replace_image_resources_conn as _replace_image_resources_conn,
)
from ._schema import (
    initialize_database as initialize_database,
)
from .browse_store import (
    get_asset_folder_listing as get_asset_folder_listing,
)
from .browse_store import (
    get_catalog_browse_listing as get_catalog_browse_listing,
)
from .file_index import (
    _cleanup_ignored_index_conn as _cleanup_ignored_index_conn,
)
from .file_index import (
    _cleanup_stale_index_conn as _cleanup_stale_index_conn,
)
from .file_index import (
    _normalize_file_type as _normalize_file_type,
)
from .file_index import (
    _path_value as _path_value,
)
from .file_index import (
    cleanup_ignored_index as cleanup_ignored_index,
)
from .file_index import (
    cleanup_stale_index as cleanup_stale_index,
)
from .file_index import (
    index_directory_tree as index_directory_tree,
)
from .file_index import (
    index_file as index_file,
)
from .folder_index import (
    _scan_folder_counts as _scan_folder_counts,
)
from .folder_index import (
    get_folder_index_state as get_folder_index_state,
)
from .folder_index import (
    get_folder_indexed_paths as get_folder_indexed_paths,
)
from .folder_index import (
    get_warm_folder_listing as get_warm_folder_listing,
)
from .folder_index import (
    mark_folder_index_incomplete as mark_folder_index_incomplete,
)
from .folder_index import (
    update_folder_index_state as update_folder_index_state,
)
from .inspector_store import (
    _encode_inspector_cursor as _encode_inspector_cursor,
)
from .inspector_store import (
    _safe_json_loads as _safe_json_loads,
)
from .inspector_store import (
    _truncate_preview as _truncate_preview,
)
from .inspector_store import (
    get_library_inspector_metadata as get_library_inspector_metadata,
)
from .inspector_store import (
    list_library_inspector_rows as list_library_inspector_rows,
)
from .job_store import (
    claim_next_catalog_job as claim_next_catalog_job,
)
from .job_store import (
    create_job as create_job,
)
from .job_store import (
    create_or_coalesce_catalog_job as create_or_coalesce_catalog_job,
)
from .job_store import (
    enqueue_startup_catalog_scans as enqueue_startup_catalog_scans,
)
from .job_store import (
    get_job as get_job,
)
from .job_store import (
    get_library_jobs as get_library_jobs,
)
from .job_store import (
    list_active_jobs as list_active_jobs,
)
from .job_store import (
    list_jobs as list_jobs,
)
from .job_store import (
    recover_stale_jobs as recover_stale_jobs,
)
from .job_store import (
    update_job_state as update_job_state,
)
from .library_store import (
    create_library as create_library,
)
from .library_store import (
    get_first_library_root as get_first_library_root,
)
from .library_store import (
    get_gallery_stats as get_gallery_stats,
)
from .library_store import (
    get_library as get_library,
)
from .library_store import (
    get_library_for_path as get_library_for_path,
)
from .library_store import (
    get_library_progress as get_library_progress,
)
from .library_store import (
    get_library_stats as get_library_stats,
)
from .library_store import (
    list_libraries as list_libraries,
)
from .library_store import (
    register_library as register_library,
)
from .library_store import (
    unregister_library as unregister_library,
)
from .library_store import (
    update_library as update_library,
)
from .library_store import (
    update_library_state as update_library_state,
)
from .metadata_persist import (
    _metadata_param as _metadata_param,
)
from .metadata_persist import (
    get_cached_dimensions_for_files as get_cached_dimensions_for_files,
)
from .metadata_persist import (
    get_lightbox_metadata as get_lightbox_metadata,
)
from .metadata_persist import (
    upsert_extracted_metadata as upsert_extracted_metadata,
)
from .metadata_persist import (
    upsert_image_dimensions as upsert_image_dimensions,
)
from .metadata_persist import (
    upsert_metadata_batch as upsert_metadata_batch,
)
from .metadata_persist import (
    upsert_metadata_result as upsert_metadata_result,
)
from .metadata_queue import (
    _current_metadata_is_complete as _current_metadata_is_complete,
)
from .metadata_queue import (
    _metadata_job_from_path as _metadata_job_from_path,
)
from .metadata_queue import (
    claim_next_metadata_job as claim_next_metadata_job,
)
from .metadata_queue import (
    complete_metadata_job as complete_metadata_job,
)
from .metadata_queue import (
    fail_metadata_job as fail_metadata_job,
)
from .metadata_queue import (
    get_metadata_index_status as get_metadata_index_status,
)
from .metadata_queue import (
    list_recoverable_metadata_jobs as list_recoverable_metadata_jobs,
)
from .metadata_queue import (
    mark_metadata_job_stale as mark_metadata_job_stale,
)
from .metadata_queue import (
    _persist_metadata_index_jobs as _persist_metadata_index_jobs,
)
from .metadata_queue import (
    mark_metadata_jobs_done as mark_metadata_jobs_done,
)
from .metadata_queue import (
    mark_metadata_jobs_failed as mark_metadata_jobs_failed,
)
from .metadata_queue import (
    mark_metadata_jobs_running as mark_metadata_jobs_running,
)
from .metadata_queue import (
    mark_metadata_jobs_stale as mark_metadata_jobs_stale,
)

# Backward compatibility alias for callers using the old public name
queue_metadata_index_paths = _persist_metadata_index_jobs
from .metadata_queue import (
    repair_inconsistent_asset_states as repair_inconsistent_asset_states,
)
from .metadata_queue import (
    reset_running_jobs_to_queued as reset_running_jobs_to_queued,
)
from .path_utils import (
    canonicalize_catalog_path as canonicalize_catalog_path,
)
from .path_utils import (
    catalog_path_contains as catalog_path_contains,
)
from .rebuild_store import (
    activate_rebuild_staging as activate_rebuild_staging,
)
from .rebuild_store import (
    delete_rebuild_staging as delete_rebuild_staging,
)
from .rebuild_store import (
    enumerate_to_rebuild_staging as enumerate_to_rebuild_staging,
)
from .rebuild_store import (
    reconcile_library_assets as reconcile_library_assets,
)
from .search_store import (
    _is_inside_root as _is_inside_root,
)
from .search_store import (
    _like_escape as _like_escape,
)
from .search_store import (
    search_index as search_index,
)
from .search_store import (
    search_index_fielded as search_index_fielded,
)
from .search_store import (
    search_metadata as search_metadata,
)
from .types import (
    CatalogBrowseScopeError as CatalogBrowseScopeError,
)
from .types import (
    CatalogJobConflict as CatalogJobConflict,
)
from .types import (
    LibraryOverlapError as LibraryOverlapError,
)
from .types import (
    MetadataIndexJob as MetadataIndexJob,
)
from .types import (
    MetadataQueueResult as MetadataQueueResult,
)

logger = logging.getLogger(__name__)
