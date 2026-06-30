export type SummaryState =
  | "unknown"
  | "offline"
  | "needs_scan"
  | "scanning"
  | "indexing"
  | "needs_update"
  | "ready_with_issues"
  | "ready"
  | "error";

export type AvailabilityState = "unknown" | "available" | "degraded" | "unavailable";
export type ScanState = "never" | "queued" | "scanning" | "complete" | "failed";
export type MetadataState = "disabled" | "queued" | "indexing" | "needs_update" | "complete" | "failed";
export type CatalogOperation = "scan" | "rebuild";
export type CatalogTrigger = "initial" | "manual" | "watcher" | "scheduled" | "startup";
export type IssueSource = "availability" | "scan" | "metadata";

export interface PrecedenceFacts {
  resolved: boolean;
  availability: AvailabilityState;
  active_catalog_job_state: "queued" | "running" | "cancelled" | null;
  active_metadata_state: "queued" | "running" | "cancelled" | null;
  latest_covering_scan_failed: boolean;
  prior_successful_covering_scan: boolean;
  has_failed_scan_attempt: boolean;
  metadata_pending_without_active_work: boolean;
  total_assets: number;
  ready_assets: number;
  failed_assets: number;
  later_scan_failure: boolean;
  current_metadata_failures: number;
  metadata_disabled: boolean;
}

export interface UnifiedStatus {
  contract_version: 1;
  generated_at: number;
  summary_state: SummaryState;
  scope: {
    kind: "library" | "path";
    library_id: number;
    path: string | null;
    import_path_count: number;
  };
  availability: {
    state: AvailabilityState;
    available_paths: number;
    total_paths: number;
  };
  scan: {
    state: ScanState;
    operation: CatalogOperation | null;
    trigger: CatalogTrigger | null;
    active_job_id: number | null;
    completed_units: number | null;
    total_units: number | null;
    progress_percent: number | null;
  };
  metadata: {
    state: MetadataState;
    total_assets: number | null;
    ready_assets: number | null;
    not_ready_assets: number | null;
    queued_assets: number | null;
    running_assets: number | null;
    stale_assets: number | null;
    idle_pending_assets: number | null;
    failed_assets: number | null;
    progress_percent: number | null;
    global_active_outside_scope: boolean;
  };
  issue_count: number;
  issues: Record<IssueSource, number>;
  latest_issue: {
    source: IssueSource;
    path: string | null;
    message: string;
    updated_at: number;
  } | null;
  last_scan_at: number | null;
  last_index_at: number | null;
}

export interface GlobalRuntime {
  catalog_worker_count: number;
  catalog_alive_workers?: number;
  catalog_active_jobs: number;
  catalog_queue_depth: number;
  metadata_worker_count: number;
  metadata_active_jobs: number;
  metadata_queue_depth: number;
  metadata_staged_queue_depth: number;
  watcher_enabled: boolean;
  watcher_healthy: boolean;
  watcher_issue: string | null;
  scheduled_reconciliation_enabled: boolean;
}

export interface MetadataLifecycle {
  queued_metadata_jobs: number;
  running_metadata_jobs: number;
  done_metadata_jobs: number;
  stale_metadata_jobs: number;
  failed_metadata_jobs: number;
  skipped_metadata_jobs: number;
  oldest_queued_metadata_job_age: number | null;
  done_jobs_with_pending_assets: number;
  current_image_metadata_with_pending_assets: number;
  metadata_jobs_without_matching_assets: number;
  assets_done_but_metadata_missing_or_stale: number;
  repairable_metadata_assets: number;
  metadata_worker_last_claimed_at: number | null;
  metadata_worker_last_completed_at: number | null;
  metadata_worker_alive: boolean;
}

export interface StatusResponseEnvelope {
  contract_version: 1;
  status: UnifiedStatus;
  global_runtime: GlobalRuntime;
  metadata_lifecycle: MetadataLifecycle | null;
}

export interface LibraryStatusBatchResponse {
  contract_version: 1;
  generated_at: number;
  items: Array<{ library_id: number; status: UnifiedStatus }>;
  global_runtime: GlobalRuntime;
  metadata_lifecycle: MetadataLifecycle | null;
}

export const deriveSummaryState = (facts: PrecedenceFacts): SummaryState => {
  if (!facts.resolved) return "unknown";
  if (facts.availability === "unavailable") return "offline";
  if (facts.active_catalog_job_state === "queued" || facts.active_catalog_job_state === "running") {
    return "scanning";
  }
  if (facts.active_metadata_state === "queued" || facts.active_metadata_state === "running") {
    return "indexing";
  }
  if (facts.latest_covering_scan_failed && !facts.prior_successful_covering_scan) return "error";
  if (!facts.prior_successful_covering_scan && !facts.has_failed_scan_attempt) return "needs_scan";
  if (
    !facts.metadata_disabled &&
    facts.total_assets > 0 &&
    facts.ready_assets === 0 &&
    facts.failed_assets === facts.total_assets
  ) {
    return "error";
  }
  if (facts.metadata_pending_without_active_work) return "needs_update";
  if (facts.later_scan_failure || facts.current_metadata_failures > 0 || facts.availability === "degraded") {
    return "ready_with_issues";
  }
  return "ready";
};
