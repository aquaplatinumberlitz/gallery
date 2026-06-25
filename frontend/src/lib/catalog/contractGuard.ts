import type { LibraryStatusBatchResponse, StatusResponseEnvelope, UnifiedStatus } from "./status";

export const STATUS_CONTRACT_VERSION = 1 as const;

export const STATUS_CONTRACT_ERROR_MESSAGE = "App updated, please reload";

export class StatusContractError extends Error {
  constructor(message: string = STATUS_CONTRACT_ERROR_MESSAGE) {
    super(message);
    this.name = "StatusContractError";
  }
}

const REQUIRED_STATUS_FIELDS: ReadonlyArray<keyof UnifiedStatus> = [
  "contract_version",
  "generated_at",
  "summary_state",
  "scope",
  "availability",
  "scan",
  "metadata",
  "issue_count",
  "issues",
  "latest_issue",
  "last_scan_at",
  "last_index_at",
];

const SUMMARY_STATES = new Set<string>([
  "unknown",
  "offline",
  "needs_scan",
  "scanning",
  "indexing",
  "needs_update",
  "ready_with_issues",
  "ready",
  "error",
]);

const AVAILABILITY_STATES = new Set<string>(["unknown", "available", "degraded", "unavailable"]);

const SCAN_STATES = new Set<string>(["never", "queued", "scanning", "complete", "failed"]);

const SCOPE_KINDS = new Set<string>(["library", "path"]);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNumberOrNull(value: unknown): value is number | null {
  return typeof value === "number" || value === null;
}

function assertUnifiedStatus(status: unknown): asserts status is UnifiedStatus {
  if (!isObject(status)) throw new StatusContractError();
  for (const field of REQUIRED_STATUS_FIELDS) {
    if (!(field in status)) throw new StatusContractError();
  }
  if (status.contract_version !== STATUS_CONTRACT_VERSION) throw new StatusContractError();
  if (typeof status.generated_at !== "number") throw new StatusContractError();
  if (typeof status.summary_state !== "string" || !SUMMARY_STATES.has(status.summary_state)) {
    throw new StatusContractError();
  }
  if (!isObject(status.scope)) throw new StatusContractError();
  if (typeof status.scope.library_id !== "number") throw new StatusContractError();
  if (typeof status.scope.kind !== "string" || !SCOPE_KINDS.has(status.scope.kind)) {
    throw new StatusContractError();
  }
  if (!isObject(status.availability)) throw new StatusContractError();
  if (typeof status.availability.state !== "string" || !AVAILABILITY_STATES.has(status.availability.state)) {
    throw new StatusContractError();
  }
  if (!isObject(status.scan)) throw new StatusContractError();
  if (typeof status.scan.state !== "string" || !SCAN_STATES.has(status.scan.state)) {
    throw new StatusContractError();
  }
  if (!isObject(status.metadata)) throw new StatusContractError();
  if (!isNumberOrNull(status.metadata.total_assets)) throw new StatusContractError();
  if (!isNumberOrNull(status.metadata.ready_assets)) throw new StatusContractError();
  if (!isNumberOrNull(status.metadata.progress_percent)) throw new StatusContractError();
  if (typeof status.issue_count !== "number") throw new StatusContractError();
  if (!isObject(status.issues)) throw new StatusContractError();
  if (status.latest_issue !== null && !isObject(status.latest_issue)) throw new StatusContractError();
}

function assertMetadataLifecycle(value: unknown): void {
  if (value === null) return;
  if (!isObject(value)) throw new StatusContractError();
  const required: string[] = [
    "queued_metadata_jobs", "running_metadata_jobs", "done_metadata_jobs",
    "stale_metadata_jobs", "failed_metadata_jobs", "skipped_metadata_jobs",
    "oldest_queued_metadata_job_age", "done_jobs_with_pending_assets",
    "current_image_metadata_with_pending_assets", "metadata_jobs_without_matching_assets",
    "assets_done_but_metadata_missing_or_stale", "repairable_metadata_assets",
    "metadata_worker_last_claimed_at", "metadata_worker_last_completed_at",
    "metadata_worker_alive",
  ];
  for (const field of required) {
    if (!(field in value)) throw new StatusContractError();
  }
  if (typeof value.queued_metadata_jobs !== "number") throw new StatusContractError();
  if (typeof value.metadata_worker_alive !== "boolean") throw new StatusContractError();
}

export function assertStatusEnvelope(envelope: unknown): asserts envelope is StatusResponseEnvelope {
  if (!isObject(envelope)) throw new StatusContractError();
  if (envelope.contract_version !== STATUS_CONTRACT_VERSION) throw new StatusContractError();
  if (!isObject(envelope.global_runtime)) throw new StatusContractError();
  assertUnifiedStatus(envelope.status);
  assertMetadataLifecycle(envelope.metadata_lifecycle);
}

export function assertLibraryStatusBatch(response: unknown): asserts response is LibraryStatusBatchResponse {
  if (!isObject(response)) throw new StatusContractError();
  if (response.contract_version !== STATUS_CONTRACT_VERSION) throw new StatusContractError();
  if (typeof response.generated_at !== "number") throw new StatusContractError();
  if (!isObject(response.global_runtime)) throw new StatusContractError();
  if (!Array.isArray(response.items)) throw new StatusContractError();
  for (const item of response.items) {
    if (!isObject(item)) throw new StatusContractError();
    if (typeof item.library_id !== "number") throw new StatusContractError();
    assertUnifiedStatus(item.status);
  }
  assertMetadataLifecycle(response.metadata_lifecycle);
}

export function isStatusContractError(error: unknown): boolean {
  return error instanceof StatusContractError;
}
