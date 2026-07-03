import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { UnifiedStatus } from "@/lib/catalog/status";
import LibraryStatusBadge from "../LibraryStatusBadge.vue";

function makeStatus(summary_state: UnifiedStatus["summary_state"] = "ready"): UnifiedStatus {
  return {
    contract_version: 1,
    generated_at: Date.now(),
    summary_state,
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
      total_assets: 12,
      ready_assets: 12,
      not_ready_assets: 0,
      queued_assets: 0,
      running_assets: 0,
      stale_assets: 0,
      idle_pending_assets: 0,
      failed_assets: 0,
      progress_percent: 100,
      global_active_outside_scope: false,
    },
    issue_count: 0,
    issues: { availability: 0, scan: 0, metadata: 0 },
    latest_issue: null,
    last_scan_at: null,
    last_index_at: null,
  };
}

describe("LibraryStatusBadge", () => {
  it("renders Ready with the same green tone used by File catalog", () => {
    const wrapper = mount(LibraryStatusBadge, {
      props: { status: makeStatus() },
    });

    const badge = wrapper.getComponent({ name: "Badge" });

    expect(wrapper.text()).toContain("Ready");
    expect(badge.classes()).toContain("bg-[rgba(34,197,94,0.10)]");
    expect(badge.classes()).toContain("text-[#15803d]");
  });
});
