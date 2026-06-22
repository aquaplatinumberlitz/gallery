type MediaFixture = {
  name: string;
  path: string;
  type: "image" | "video";
  has_children?: boolean;
  cover_images?: string[];
  mtime?: number;
  image_count?: number;
  width?: number | null;
  height?: number | null;
  duration_ms?: number | null;
  mime_type?: string | null;
};

type FolderFixture = {
  name: string;
  path: string;
  type: "folder";
  has_children?: boolean;
  cover_images?: string[];
  image_count?: number;
  entry_kind?: "import_root";
  display_label?: string;
  availability?: "unknown" | "available" | "degraded" | "unavailable";
};

export function browseResponse({
  libraryId = 1,
  path = null,
  folders = [],
  media = [],
  nextMediaCursor = null,
  totalImages,
  totalVideos,
  totalAssets,
}: {
  libraryId?: number;
  path?: string | null;
  folders?: FolderFixture[];
  media?: MediaFixture[];
  nextMediaCursor?: number | null;
  totalImages?: number;
  totalVideos?: number;
  totalAssets?: number;
}) {
  const imageCount = totalImages ?? media.filter((item) => item.type === "image").length;
  const videoCount = totalVideos ?? media.filter((item) => item.type === "video").length;
  return {
    library_id: libraryId,
    path,
    request_path: path,
    folders,
    media,
    next_media_cursor: nextMediaCursor,
    next_cursor: nextMediaCursor,
    total_images: imageCount,
    total_videos: videoCount,
    total_assets: totalAssets ?? imageCount + videoCount,
    index_source: "catalog",
  };
}

export function globalRuntime(overrides: Record<string, unknown> = {}) {
  return {
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
    scheduled_reconciliation_enabled: true,
    ...overrides,
  };
}

export function statusEnvelope({
  libraryId = 1,
  path = null,
  importPathCount = 1,
  summaryState = "ready",
  totalAssets = 0,
  readyAssets = totalAssets,
  failedAssets = 0,
  queuedAssets = 0,
  runningAssets = 0,
  staleAssets = 0,
  idlePendingAssets = 0,
  metadataState,
  scanState = "complete",
  scanOperation = "scan",
  scanTrigger = "manual",
  scanActiveJobId = null,
  scanCompletedUnits = totalAssets,
  scanTotalUnits = totalAssets,
  scanProgressPercent = 100,
  availabilityState = "available",
  availablePaths = 1,
  totalPaths = 1,
  issueCount = 0,
  issues = { availability: 0, scan: 0, metadata: 0 },
  latestIssue = null,
  lastScanAt = 1_782_036_040_000,
  lastIndexAt = 1_782_036_050_000,
  globalActiveOutsideScope = false,
  runtime = {},
}: {
  libraryId?: number;
  path?: string | null;
  importPathCount?: number;
  summaryState?: string;
  totalAssets?: number;
  readyAssets?: number;
  failedAssets?: number;
  queuedAssets?: number;
  runningAssets?: number;
  staleAssets?: number;
  idlePendingAssets?: number;
  metadataState?: string;
  scanState?: string;
  scanOperation?: string | null;
  scanTrigger?: string | null;
  scanActiveJobId?: number | null;
  scanCompletedUnits?: number | null;
  scanTotalUnits?: number | null;
  scanProgressPercent?: number | null;
  availabilityState?: string;
  availablePaths?: number;
  totalPaths?: number;
  issueCount?: number;
  issues?: { availability: number; scan: number; metadata: number };
  latestIssue?: { source: string; path: string | null; message: string; updated_at: number } | null;
  lastScanAt?: number | null;
  lastIndexAt?: number | null;
  globalActiveOutsideScope?: boolean;
  runtime?: Record<string, unknown>;
} = {}) {
  const notReadyAssets = Math.max(totalAssets - readyAssets - failedAssets, 0);
  const resolvedMetadataState =
    metadataState ??
    (queuedAssets > 0 || runningAssets > 0
      ? "indexing"
      : staleAssets > 0 || idlePendingAssets > 0 || notReadyAssets > 0
        ? "needs_update"
        : failedAssets > 0 && readyAssets === 0
          ? "failed"
          : "complete");

  return {
    contract_version: 1,
    status: {
      contract_version: 1,
      generated_at: 1_782_036_060_000,
      summary_state: summaryState,
      scope: {
        kind: path ? "path" : "library",
        library_id: libraryId,
        path,
        import_path_count: importPathCount,
      },
      availability: {
        state: availabilityState,
        available_paths: availablePaths,
        total_paths: totalPaths,
      },
      scan: {
        state: scanState,
        operation: scanOperation,
        trigger: scanTrigger,
        active_job_id: scanActiveJobId,
        completed_units: scanCompletedUnits,
        total_units: scanTotalUnits,
        progress_percent: scanProgressPercent,
      },
      metadata: {
        state: resolvedMetadataState,
        total_assets: totalAssets,
        ready_assets: readyAssets,
        not_ready_assets: notReadyAssets,
        queued_assets: queuedAssets,
        running_assets: runningAssets,
        stale_assets: staleAssets,
        idle_pending_assets: idlePendingAssets,
        failed_assets: failedAssets,
        progress_percent: totalAssets > 0 ? Math.round((readyAssets / totalAssets) * 100) : 100,
        global_active_outside_scope: globalActiveOutsideScope,
      },
      issue_count: issueCount,
      issues,
      latest_issue: latestIssue,
      last_scan_at: lastScanAt,
      last_index_at: lastIndexAt,
    },
    global_runtime: globalRuntime(runtime),
  };
}

export function statusBatch(libraries: Array<{ id: number; totalAssets?: number; readyAssets?: number }>) {
  return {
    contract_version: 1,
    generated_at: 1_782_036_060_000,
    items: libraries.map((library) => ({
      library_id: library.id,
      status: statusEnvelope({
        libraryId: library.id,
        totalAssets: library.totalAssets ?? 0,
        readyAssets: library.readyAssets ?? library.totalAssets ?? 0,
      }).status,
    })),
    global_runtime: globalRuntime(),
  };
}
