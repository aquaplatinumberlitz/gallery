/**
 * Typed fixture factories for frontend unit tests.
 *
 * Purpose:
 * Provide consistent test data shapes so tests do not hand-roll inline objects
 * with varying or incorrect shapes.
 *
 * Guarantees:
 * * All required fields are populated with sensible defaults
 * * Overrides can be supplied per-call
 * * No mutable shared state between calls
 *
 * Run when:
 * * testing API services, stores, composables, or components that consume
 *   server-response-shaped data
 */

import type {
  BrowseResponse,
  FacetsResponse,
  FileNode,
  LibraryImportPath,
  LibraryInspectorResponse,
  LibraryJob,
  LibraryStats,
  RegisteredLibrary,
  UnifiedStatus,
} from "../types";
import type { StatusResponseEnvelope } from "../lib/catalog/status";

export function makeLibrary(overrides: Partial<RegisteredLibrary> = {}): RegisteredLibrary {
  const id = overrides.id ?? 1;
  return {
    id,
    name: "Test Library",
    state: "ready",
    watch_enabled: 1,
    warm_enabled: 1,
    import_paths: [makeImportPath({ library_id: id })],
    exclusion_patterns: [],
    root_path: "/test",
    asset_count: 0,
    created_at: Date.now(),
    updated_at: Date.now(),
    last_scan_at: null,
    last_error: null,
    ...overrides,
  } as RegisteredLibrary;
}

export function makeImportPath(overrides: Partial<LibraryImportPath> = {}): LibraryImportPath {
  return {
    id: 1,
    library_id: 1,
    path: "/test",
    position: 0,
    created_at: Date.now(),
    updated_at: Date.now(),
    ...overrides,
  };
}

export function makeFileNode(overrides: Partial<FileNode> = {}): FileNode {
  return {
    path: "/test/file.png",
    name: "file.png",
    type: "image",
    has_children: false,
    cover_images: [],
    mtime: Date.now() / 1000,
    ...overrides,
  } as FileNode;
}

export function makeBrowseResponse(overrides: Partial<BrowseResponse> = {}): BrowseResponse {
  return {
    folders: [],
    media: [],
    next_cursor: null,
    next_media_cursor: null,
    total_images: 0,
    total_videos: 0,
    total_assets: 0,
    index_source: "catalog",
    ...overrides,
  } as BrowseResponse;
}

export function makeStatusEnvelope(overrides: Partial<StatusResponseEnvelope> = {}): StatusResponseEnvelope {
  return {
    contract_version: 1,
    status: makeUnifiedStatus(),
    global_runtime: {
      catalog_worker_count: 1,
      catalog_active_jobs: 0,
      catalog_queue_depth: 0,
      metadata_worker_count: 1,
      metadata_active_jobs: 0,
      metadata_queue_depth: 0,
      metadata_staged_queue_depth: 0,
      watcher_enabled: true,
      watcher_healthy: true,
      watcher_issue: null,
      scheduled_reconciliation_enabled: false,
    },
    metadata_lifecycle: null,
    ...overrides,
  };
}

export function makeUnifiedStatus(overrides: Partial<UnifiedStatus> = {}): UnifiedStatus {
  return {
    contract_version: 1,
    generated_at: Date.now(),
    summary_state: "ready",
    scope: { kind: "library", library_id: 1, path: null, import_path_count: 1 },
    availability: { state: "available", available_paths: 1, total_paths: 1 },
    scan: {
      state: "complete",
      operation: null,
      trigger: null,
      active_job_id: null,
      completed_units: null,
      total_units: null,
      progress_percent: null,
    },
    metadata: {
      state: "complete",
      total_assets: 0,
      ready_assets: 0,
      not_ready_assets: 0,
      queued_assets: 0,
      running_assets: 0,
      stale_assets: 0,
      idle_pending_assets: 0,
      failed_assets: 0,
      progress_percent: null,
      global_active_outside_scope: false,
    },
    issue_count: 0,
    issues: { availability: 0, scan: 0, metadata: 0 },
    latest_issue: null,
    last_scan_at: null,
    last_index_at: null,
    ...overrides,
  };
}

export function makeLibraryJob(overrides: Partial<LibraryJob> = {}): LibraryJob {
  return {
    id: 1,
    library_id: 1,
    type: "scan",
    state: "queued",
    trigger: "manual",
    priority: 50,
    progress_current: 0,
    progress_total: null,
    message: "",
    error: null,
    created_at: Date.now(),
    updated_at: Date.now(),
    ...overrides,
  } as LibraryJob;
}

export function makeInspectorResponse(overrides: Partial<LibraryInspectorResponse> = {}): LibraryInspectorResponse {
  return {
    rows: [],
    truncated: false,
    next_cursor: null,
    has_more: false,
    total: 0,
    ...overrides,
  } as LibraryInspectorResponse;
}

export function makeFacetsResponse(overrides: Partial<FacetsResponse> = {}): FacetsResponse {
  return {
    facets: {},
    ...overrides,
  } as FacetsResponse;
}

export function makeLibraryStats(overrides: Partial<LibraryStats> = {}): LibraryStats {
  return {
    photos: 0,
    videos: 0,
    total_assets: 0,
    active_assets: 0,
    offline_assets: 0,
    usage_bytes: 0,
    import_path_count: 1,
    ...overrides,
  } as LibraryStats;
}
