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

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function assertUnifiedStatus(status: unknown): asserts status is UnifiedStatus {
  if (!isObject(status)) throw new StatusContractError();
  for (const field of REQUIRED_STATUS_FIELDS) {
    if (!(field in status)) throw new StatusContractError();
  }
  if (status.contract_version !== STATUS_CONTRACT_VERSION) throw new StatusContractError();
  if (typeof status.generated_at !== "number") throw new StatusContractError();
  if (typeof status.summary_state !== "string") throw new StatusContractError();
  if (!isObject(status.scope)) throw new StatusContractError();
  if (!isObject(status.availability)) throw new StatusContractError();
  if (!isObject(status.scan)) throw new StatusContractError();
  if (!isObject(status.metadata)) throw new StatusContractError();
  if (typeof status.issue_count !== "number") throw new StatusContractError();
  if (!isObject(status.issues)) throw new StatusContractError();
  if (status.latest_issue !== null && !isObject(status.latest_issue)) throw new StatusContractError();
}

export function assertStatusEnvelope(envelope: unknown): asserts envelope is StatusResponseEnvelope {
  if (!isObject(envelope)) throw new StatusContractError();
  if (envelope.contract_version !== STATUS_CONTRACT_VERSION) throw new StatusContractError();
  if (!isObject(envelope.global_runtime)) throw new StatusContractError();
  assertUnifiedStatus(envelope.status);
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
}

export function isStatusContractError(error: unknown): boolean {
  return error instanceof StatusContractError;
}
