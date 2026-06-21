/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

type SummaryState =
  | "unknown"
  | "offline"
  | "needs_scan"
  | "scanning"
  | "indexing"
  | "needs_update"
  | "ready_with_issues"
  | "ready"
  | "error";

interface PrecedenceFacts {
  resolved: boolean;
  availability: "available" | "degraded" | "unavailable";
  active_catalog_job_state: "queued" | "running" | "cancelled" | null;
  active_metadata_state: "queued" | "running" | null;
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
  fixtures: Array<{
    name: string;
    status: {
      contract_version: number;
      generated_at: number;
      summary_state: SummaryState;
      issue_count: number;
      issues: Record<string, number>;
      scan: { progress_percent: number | null };
      metadata: {
        total_assets: number;
        ready_assets: number;
        not_ready_assets: number;
        queued_assets: number;
        running_assets: number;
        stale_assets: number;
        idle_pending_assets: number;
        failed_assets: number;
        progress_percent: number | null;
      };
    };
  }>;
}

const fixturePath = (name: string): string => resolve(process.cwd(), "../tests/fixtures/catalog_status", name);

const loadFixture = <T>(name: string): T => JSON.parse(readFileSync(fixturePath(name), "utf8")) as T;

const deriveSummaryState = (facts: PrecedenceFacts): SummaryState => {
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
  if (facts.metadata_pending_without_active_work) return "needs_update";
  if (
    !facts.metadata_disabled &&
    facts.total_assets > 0 &&
    facts.ready_assets === 0 &&
    facts.failed_assets === facts.total_assets
  ) {
    return "error";
  }
  if (facts.later_scan_failure || facts.current_metadata_failures > 0 || facts.availability === "degraded") {
    return "ready_with_issues";
  }
  return "ready";
};

describe("catalog status contract fixtures", () => {
  it("loads the four required v1 fixtures and enforces count invariants", () => {
    const document = loadFixture<StatusFixtureDocument>("unified_status_v1.json");

    expect(document.contract_version).toBe(1);
    expect(document.fixtures.map(({ name }) => name)).toEqual([
      "initial_scan_queued",
      "scan_complete_metadata_indexing",
      "ready_with_unavailable_import_path",
      "failed_rebuild_with_usable_catalog",
    ]);

    for (const { status } of document.fixtures) {
      expect(status.contract_version).toBe(1);
      expect(Number.isInteger(status.generated_at)).toBe(true);
      expect(status.issue_count).toBe(Object.values(status.issues).reduce((sum, count) => sum + count, 0));
      expect(status.metadata.not_ready_assets).toBe(
        status.metadata.total_assets - status.metadata.ready_assets - status.metadata.failed_assets,
      );
      expect(status.metadata.not_ready_assets).toBe(
        status.metadata.queued_assets +
          status.metadata.running_assets +
          status.metadata.stale_assets +
          status.metadata.idle_pending_assets,
      );
      for (const progress of [status.scan.progress_percent, status.metadata.progress_percent]) {
        expect(progress === null || (progress >= 0 && progress <= 100)).toBe(true);
      }
    }
  });

  it("locks the full summary-state precedence matrix", () => {
    const document = loadFixture<PrecedenceDocument>("summary_precedence_v1.json");
    const expectedStates = new Set<SummaryState>();

    expect(document.contract_version).toBe(1);
    for (const testCase of document.cases) {
      const facts = { ...document.defaults, ...testCase.overrides };
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
});
