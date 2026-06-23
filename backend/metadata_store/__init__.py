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
from ._asset_store import (
    _upsert_asset_conn as _upsert_asset_conn,
)
from ._db import (
    _DB_INITIALIZED as _DB_INITIALIZED,
)
from ._db import (
    _DB_INITIALIZED_PATH as _DB_INITIALIZED_PATH,
)
from ._db import (
    _DB_LOCK as _DB_LOCK,
)
from ._db import (
    ACTIVE_ASSET_WHERE as ACTIVE_ASSET_WHERE,
)
from ._db import (
    LIBRARY_JOB_ACTIVE_STATES as LIBRARY_JOB_ACTIVE_STATES,
)
from ._db import (
    LIBRARY_JOB_TERMINAL_STATES as LIBRARY_JOB_TERMINAL_STATES,
)
from ._db import (
    MAX_METADATA_JOB_ATTEMPTS as MAX_METADATA_JOB_ATTEMPTS,
)
from ._db import (
    METADATA_JOB_STATES as METADATA_JOB_STATES,
)
from ._db import (
    _active_asset_where as _active_asset_where,
)
from ._db import (
    _connect as _connect,
)
from ._db import (
    _database_has_application_tables as _database_has_application_tables,
)
from ._db import (
    _ensure_column as _ensure_column,
)
from ._db import (
    _table_columns as _table_columns,
)
from ._db import (
    _table_exists as _table_exists,
)
from ._db import (
    init_db as init_db,
)
from ._resources import (
    _backfill_image_resources_conn as _backfill_image_resources_conn,
)
from ._resources import (
    _clean_resource_text as _clean_resource_text,
)
from ._resources import (
    _iter_metadata_loras as _iter_metadata_loras,
)
from ._resources import (
    _iter_metadata_resources as _iter_metadata_resources,
)
from ._resources import (
    _lora_summary as _lora_summary,
)
from ._resources import (
    _normalize_resource_kind as _normalize_resource_kind,
)
from ._resources import (
    _replace_image_resources_conn as _replace_image_resources_conn,
)
from ._resources import (
    _resource_raw_json as _resource_raw_json,
)
from ._resources import (
    _resource_rows_from_metadata as _resource_rows_from_metadata,
)
from ._resources import (
    _split_lora_text as _split_lora_text,
)
from ._schema import (
    CATALOG_SCHEMA_VERSION as CATALOG_SCHEMA_VERSION,
)
from ._schema import (
    _backup_database_before_v9 as _backup_database_before_v9,
)
from ._schema import (
    _ensure_v9_catalog_schema as _ensure_v9_catalog_schema,
)
from ._schema import (
    _format_path_conflict as _format_path_conflict,
)
from ._schema import (
    _import_cached_derivatives_conn as _import_cached_derivatives_conn,
)
from ._schema import (
    _initialize_database_conn as _initialize_database_conn,
)
from ._schema import (
    _migrate_v8_to_v9 as _migrate_v8_to_v9,
)
from ._schema import (
    _populate_v9_file_index_library_ids as _populate_v9_file_index_library_ids,
)
from ._schema import (
    _rebuild_libraries_without_root_path as _rebuild_libraries_without_root_path,
)
from ._schema import (
    _v9_backup_path as _v9_backup_path,
)
from ._schema import (
    _v9_import_paths as _v9_import_paths,
)
from ._schema import (
    _validate_v9_preflight as _validate_v9_preflight,
)
from ._schema import (
    initialize_database as initialize_database,
)
from .browse_store import (
    _browse_availability_from_library_state as _browse_availability_from_library_state,
)
from .browse_store import (
    _browse_folder_counts_batch_conn as _browse_folder_counts_batch_conn,
)
from .browse_store import (
    _browse_folder_counts_conn as _browse_folder_counts_conn,
)
from .browse_store import (
    _browse_import_paths_conn as _browse_import_paths_conn,
)
from .browse_store import (
    _browse_import_root_name as _browse_import_root_name,
)
from .browse_store import (
    _browse_visibility_sql as _browse_visibility_sql,
)
from .browse_store import (
    _catalog_browse_path_conn as _catalog_browse_path_conn,
)
from .browse_store import (
    _catalog_browse_virtual_root_conn as _catalog_browse_virtual_root_conn,
)
from .browse_store import (
    _import_root_availability as _import_root_availability,
)
from .browse_store import (
    _validate_browse_scope as _validate_browse_scope,
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
    _scoped_path_where as _scoped_path_where,
)
from .file_index import (
    cleanup_ignored_index as cleanup_ignored_index,
)
from .file_index import (
    cleanup_stale_index as cleanup_stale_index,
)
from .file_index import (
    clear_index_records as clear_index_records,
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
    index_files_from_scan as index_files_from_scan,
)
from .folder_index import (
    mark_folder_index_incomplete as mark_folder_index_incomplete,
)
from .folder_index import (
    update_folder_index_state as update_folder_index_state,
)
from .inspector_store import (
    _build_library_inspector_keyset_where as _build_library_inspector_keyset_where,
)
from .inspector_store import (
    _dedupe_inspector_rows as _dedupe_inspector_rows,
)
from .inspector_store import (
    _encode_inspector_cursor as _encode_inspector_cursor,
)
from .inspector_store import (
    _format_inspector_row as _format_inspector_row,
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
    _job_scope_covers as _job_scope_covers,
)
from .job_store import (
    _serialize_catalog_enqueue_result as _serialize_catalog_enqueue_result,
)
from .job_store import (
    _serialize_library_job as _serialize_library_job,
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
    create_or_get_active_scan_job as create_or_get_active_scan_job,
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
    _assert_no_import_path_overlap_conn as _assert_no_import_path_overlap_conn,
)
from .library_store import (
    _ensure_default_library_conn as _ensure_default_library_conn,
)
from .library_store import (
    _find_library_for_path_conn as _find_library_for_path_conn,
)
from .library_store import (
    _library_exclusion_patterns_conn as _library_exclusion_patterns_conn,
)
from .library_store import (
    _reconcile_library_configuration_conn as _reconcile_library_configuration_conn,
)
from .library_store import (
    _replace_library_paths_conn as _replace_library_paths_conn,
)
from .library_store import (
    _replace_library_patterns_conn as _replace_library_patterns_conn,
)
from .library_store import (
    _serialize_library_conn as _serialize_library_conn,
)
from .library_store import (
    create_library as create_library,
)
from .library_store import (
    get_asset_state_for_path as get_asset_state_for_path,
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
    _needs_reindex as _needs_reindex,
)
from .metadata_persist import (
    _sync_dimensions_to_file_index as _sync_dimensions_to_file_index,
)
from .metadata_persist import (
    _upsert_extracted_metadata_conn as _upsert_extracted_metadata_conn,
)
from .metadata_persist import (
    get_cached_dimensions_for_files as get_cached_dimensions_for_files,
)
from .metadata_persist import (
    get_lightbox_metadata as get_lightbox_metadata,
)
from .metadata_persist import (
    index_image as index_image,
)
from .metadata_persist import (
    index_images as index_images,
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
    _mark_current_metadata_done as _mark_current_metadata_done,
)
from .metadata_queue import (
    _metadata_job_from_path as _metadata_job_from_path,
)
from .metadata_queue import (
    get_metadata_index_status as get_metadata_index_status,
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
from .metadata_queue import (
    queue_metadata_index_paths as queue_metadata_index_paths,
)
from .path_utils import (
    _catalog_paths_overlap as _catalog_paths_overlap,
)
from .path_utils import (
    _compare_natural_sql as _compare_natural_sql,
)
from .path_utils import (
    _natural_sort_parts as _natural_sort_parts,
)
from .path_utils import (
    _path_is_within as _path_is_within,
)
from .path_utils import (
    canonicalize_catalog_path as canonicalize_catalog_path,
)
from .path_utils import (
    catalog_path_contains as catalog_path_contains,
)
from .rebuild_store import (
    _reconcile_assets_conn as _reconcile_assets_conn,
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
    PROMPT_SEARCH_FIELDS as PROMPT_SEARCH_FIELDS,
)
from .search_store import (
    SEARCH_FIELDS as SEARCH_FIELDS,
)
from .search_store import (
    _build_scope_named as _build_scope_named,
)
from .search_store import (
    _count_fts as _count_fts,
)
from .search_store import (
    _count_like as _count_like,
)
from .search_store import (
    _escape_fts_token as _escape_fts_token,
)
from .search_store import (
    _folder_relative_path as _folder_relative_path,
)
from .search_store import (
    _format_file_index_rows as _format_file_index_rows,
)
from .search_store import (
    _format_prompt_rows as _format_prompt_rows,
)
from .search_store import (
    _format_rows as _format_rows,
)
from .search_store import (
    _is_inside_root as _is_inside_root,
)
from .search_store import (
    _like_escape as _like_escape,
)
from .search_store import (
    _like_pattern as _like_pattern,
)
from .search_store import (
    _optional_row_value as _optional_row_value,
)
from .search_store import (
    _path_prefix as _path_prefix,
)
from .search_store import (
    _scope_clause as _scope_clause,
)
from .search_store import (
    _search_fielded_photos as _search_fielded_photos,
)
from .search_store import (
    _search_file_index_fts as _search_file_index_fts,
)
from .search_store import (
    _search_fts as _search_fts,
)
from .search_store import (
    _search_like as _search_like,
)
from .search_store import (
    _search_prompt_rows as _search_prompt_rows,
)
from .search_store import (
    _snippet as _snippet,
)
from .search_store import (
    _trigram_match_query as _trigram_match_query,
)
from .search_store import (
    _unicode_match_query as _unicode_match_query,
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
    CachedDimensions as CachedDimensions,
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
