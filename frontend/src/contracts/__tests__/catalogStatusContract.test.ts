/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import type { AnySchema } from "ajv";
import Ajv2020 from "ajv/dist/2020.js";

import {
  deriveSummaryState,
  type GlobalRuntime,
  type LibraryStatusBatchResponse,
  type PrecedenceFacts,
  type StatusResponseEnvelope,
  type SummaryState,
  type UnifiedStatus,
} from "@/lib/catalog/status";

interface PrecedenceDocument {
  contract_version: number;
  defaults: PrecedenceFacts;
  cases: Array<{
    name: string;
    overrides: Partial<PrecedenceFacts>;
    expected: SummaryState;
  }>;
}

interface StatusFixtureDocument {
  contract_version: number;
  fixtures: Array<{ name: string; status: UnifiedStatus }>;
}

interface SchemaDocument {
  $defs: Record<string, { required?: string[] }>;
}

const TIMESTAMP_MS_MINIMUM = 10_000_000_000;
const EXPECTED_FIXTURES = [
  "initial_scan_queued",
  "scan_complete_metadata_indexing",
  "ready_with_unavailable_import_path",
  "failed_rebuild_with_usable_catalog",
  "all_import_paths_unavailable",
  "scan_complete_metadata_stale_without_worker",
  "metadata_disabled_scan_complete",
  "empty_scanned_scope",
];

const fixturePath = (name: string): string => resolve(process.cwd(), "../backend/tests/fixtures/catalog_status", name);
const loadFixture = <T>(name: string): T => JSON.parse(readFileSync(fixturePath(name), "utf8")) as T;

const expectTimestampMs = (value: number | null): void => {
  expect(value === null || (Number.isInteger(value) && value > TIMESTAMP_MS_MINIMUM)).toBe(true);
};

const globalRuntime = {
  catalog_worker_count: 1,
  catalog_active_jobs: 0,
  catalog_queue_depth: 0,
  metadata_worker_count: 2,
  metadata_active_jobs: 0,
  metadata_queue_depth: 0,
  metadata_staged_queue_depth: 0,
  watcher_enabled: true,
  watcher_healthy: true,
  watcher_issue: null,
  scheduled_reconciliation_enabled: true,
} satisfies GlobalRuntime;

describe("catalog status contract fixtures", () => {
  it("uses the production precedence implementation for every shared vector", () => {
    const document = loadFixture<PrecedenceDocument>("summary_precedence_v1.json");
    const expectedStates = new Set<SummaryState>();

    expect(document.contract_version).toBe(1);
    for (const testCase of document.cases) {
      const facts: PrecedenceFacts = { ...document.defaults, ...testCase.overrides };
      expect(deriveSummaryState(facts), testCase.name).toBe(testCase.expected);
      expectedStates.add(testCase.expected);
    }
    expect(expectedStates).toEqual(
      new Set<SummaryState>([
        "unknown",
        "offline",
        "needs_scan",
        "scanning",
        "indexing",
        "needs_update",
        "ready_with_issues",
        "ready",
        "error",
      ]),
    );
  });

  it("validates all unified-status fixtures and nested invariants", () => {
    const document = loadFixture<StatusFixtureDocument>("unified_status_v1.json");
    const validateSchema = new Ajv2020().compile(loadFixture<AnySchema>("schema_v1.json"));

    expect(document.contract_version).toBe(1);
    expect(document.fixtures.map(({ name }) => name)).toEqual(EXPECTED_FIXTURES);

    for (const { status } of document.fixtures) {
      expect(validateSchema(status), JSON.stringify(validateSchema.errors)).toBe(true);
      expect(status.contract_version).toBe(1);
      expectTimestampMs(status.generated_at);
      expectTimestampMs(status.last_scan_at);
      expectTimestampMs(status.last_index_at);

      expect(Number.isInteger(status.scope.library_id)).toBe(true);
      expect(Number.isInteger(status.scope.import_path_count)).toBe(true);
      expect(status.scope.path === null || typeof status.scope.path === "string").toBe(true);
      expect(status.availability.available_paths).toBeLessThanOrEqual(status.availability.total_paths);

      expect(["scan", "rebuild", null]).toContain(status.scan.operation);
      expect(["initial", "manual", "watcher", "scheduled", "startup", null]).toContain(status.scan.trigger);
      for (const value of [status.scan.active_job_id, status.scan.completed_units, status.scan.total_units]) {
        expect(value === null || Number.isInteger(value)).toBe(true);
      }

      const metadata = status.metadata;
      expect(typeof metadata.global_active_outside_scope).toBe("boolean");
      if (metadata.total_assets === null) {
        expect(metadata.state).toBe("disabled");
        expect([
          metadata.ready_assets,
          metadata.not_ready_assets,
          metadata.queued_assets,
          metadata.running_assets,
          metadata.stale_assets,
          metadata.idle_pending_assets,
          metadata.failed_assets,
          metadata.progress_percent,
        ]).toEqual([null, null, null, null, null, null, null, null]);
      } else {
        const counts = [
          metadata.ready_assets,
          metadata.not_ready_assets,
          metadata.queued_assets,
          metadata.running_assets,
          metadata.stale_assets,
          metadata.idle_pending_assets,
          metadata.failed_assets,
        ];
        if (counts.some((count) => count === null)) throw new Error("Enabled metadata counts must be numeric");
        const [ready, notReady, queued, running, stale, idlePending, failed] = counts as number[];
        expect(notReady).toBe(metadata.total_assets - ready - failed);
        expect(notReady).toBe(queued + running + stale + idlePending);
      }

      expect(status.issue_count).toBe(Object.values(status.issues).reduce((sum, count) => sum + count, 0));
      if (status.issue_count === 0) {
        expect(status.latest_issue).toBeNull();
      } else {
        expect(status.latest_issue).not.toBeNull();
        if (status.latest_issue === null) throw new Error("Positive issue count requires latest_issue");
        expect(status.issues[status.latest_issue.source]).toBeGreaterThan(0);
        expect(status.latest_issue.path === null || typeof status.latest_issue.path === "string").toBe(true);
        expect(status.latest_issue.message.length).toBeGreaterThan(0);
        expectTimestampMs(status.latest_issue.updated_at);
      }

      for (const progress of [status.scan.progress_percent, metadata.progress_percent]) {
        expect(progress === null || (progress >= 0 && progress <= 100)).toBe(true);
      }
    }
  });

  it("locks shared schema fields and frontend envelope types", () => {
    const schema = loadFixture<SchemaDocument>("schema_v1.json");
    const status = loadFixture<StatusFixtureDocument>("unified_status_v1.json").fixtures[0]!.status;
    const envelope: StatusResponseEnvelope = { contract_version: 1, status, global_runtime: globalRuntime, metadata_lifecycle: null };
    const batch: LibraryStatusBatchResponse = {
      contract_version: 1,
      generated_at: status.generated_at,
      items: [{ library_id: status.scope.library_id, status }],
      global_runtime: globalRuntime,
      metadata_lifecycle: null,
    };

    expect(schema.$defs.StatusResponseEnvelope?.required).toEqual(["contract_version", "status", "global_runtime", "metadata_lifecycle"]);
    expect(schema.$defs.LibraryStatusBatchResponse?.required).toEqual([
      "contract_version",
      "generated_at",
      "items",
      "global_runtime",
      "metadata_lifecycle",
    ]);
    expect(schema.$defs.GlobalRuntime?.required).toEqual(Object.keys(globalRuntime));
    expect(envelope.status).toBe(status);
    expect(batch.items[0]?.library_id).toBe(status.scope.library_id);
  });

  it("locks empty-scope progress and indexing-with-issues behavior", () => {
    const fixtures = loadFixture<StatusFixtureDocument>("unified_status_v1.json").fixtures;
    const empty = fixtures.find(({ name }) => name === "empty_scanned_scope")!.status;
    const indexing = fixtures.find(({ name }) => name === "scan_complete_metadata_indexing")!.status;
    const stale = fixtures.find(({ name }) => name === "scan_complete_metadata_stale_without_worker")!.status;

    expect(empty.scan.state).toBe("complete");
    expect(empty.metadata.total_assets).toBe(0);
    expect(empty.metadata.progress_percent).toBe(100);
    expect(indexing.summary_state).toBe("indexing");
    expect(indexing.issue_count).toBeGreaterThan(0);
    expect(stale.metadata.global_active_outside_scope).toBe(true);
  });
});
