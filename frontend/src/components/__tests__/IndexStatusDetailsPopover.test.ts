import { render } from "@testing-library/vue";
import { describe, expect, it } from "vitest";
import { TooltipProvider } from "reka-ui";
import IndexStatusDetailsPopover from "../IndexStatusDetailsPopover.vue";
import { getCatalogStatusPresentation } from "@/lib/catalog/labels";
import { STATUS_CONTRACT_ERROR_MESSAGE } from "@/lib/catalog/contractGuard";
import type { UnifiedStatus } from "@/lib/catalog/status";

function makeStatus(overrides: Partial<UnifiedStatus> = {}): UnifiedStatus {
  return {
    contract_version: 1,
    generated_at: 1782036000000,
    summary_state: "ready",
    scope: { kind: "library", library_id: 7, path: null, import_path_count: 1 },
    availability: { state: "available", available_paths: 1, total_paths: 1 },
    scan: {
      state: "complete",
      operation: "scan",
      trigger: "manual",
      active_job_id: null,
      completed_units: 10,
      total_units: 10,
      progress_percent: 100,
    },
    metadata: {
      state: "complete",
      total_assets: 10,
      ready_assets: 10,
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
    last_scan_at: 1782036040000,
    last_index_at: 1782036050000,
    ...overrides,
  } as UnifiedStatus;
}

function renderPopover(status: UnifiedStatus | null, extra: Record<string, unknown> = {}) {
  return render(
    {
      components: { IndexStatusDetailsPopover },
      template: `<TooltipProvider><IndexStatusDetailsPopover :status="status" :presentation="presentation" v-bind="extra" /></TooltipProvider>`,
      setup() {
        return {
          status,
          presentation: getCatalogStatusPresentation(status?.summary_state ?? null),
          extra,
        };
      },
    },
    { global: { components: { TooltipProvider } } },
  );
}

describe("IndexStatusDetailsPopover edge states", () => {
  it("renders the Ready badge when summary_state is ready", () => {
    const { getByText } = renderPopover(makeStatus());
    expect(getByText("Ready")).toBeVisible();
  });

  it("renders Ready with issues and total issue count when issue_count > 0", () => {
    const status = makeStatus({
      summary_state: "ready_with_issues",
      issue_count: 3,
      issues: { availability: 1, scan: 0, metadata: 2 },
    });
    const { getByText } = renderPopover(status);
    expect(getByText("Ready with issues")).toBeVisible();
    expect(getByText("Total issues")).toBeVisible();
    expect(getByText("3")).toBeVisible();
  });

  it("renders the Offline badge when availability is unavailable", () => {
    const status = makeStatus({
      summary_state: "offline",
      availability: { state: "unavailable", available_paths: 0, total_paths: 2 },
    });
    const { getByText } = renderPopover(status);
    expect(getByText("Offline")).toBeVisible();
  });

  it("renders the global-work-outside-scope note when metadata.global_active_outside_scope is true", () => {
    const status = makeStatus({
      metadata: {
        state: "indexing",
        total_assets: 10,
        ready_assets: 5,
        not_ready_assets: 5,
        queued_assets: 5,
        running_assets: 0,
        stale_assets: 0,
        idle_pending_assets: 0,
        failed_assets: 0,
        progress_percent: 50,
        global_active_outside_scope: true,
      },
    });
    const { getByText } = renderPopover(status, { globalWorkOutsideScope: true });
    expect(getByText("Indexer working in another folder")).toBeVisible();
  });

  it("renders the latest issue message when latest_issue is non-null", () => {
    const status = makeStatus({
      summary_state: "ready_with_issues",
      issue_count: 1,
      issues: { availability: 1, scan: 0, metadata: 0 },
      latest_issue: {
        source: "availability",
        path: "/mnt/archive",
        message: "Import path is unavailable",
        updated_at: 1782036990000,
      },
    });
    const { getByText } = renderPopover(status);
    expect(getByText("Latest issue")).toBeVisible();
    expect(getByText("Import path is unavailable")).toBeVisible();
  });

  it("renders the contract error message when contractError is true", () => {
    const { getByText } = renderPopover(null, { contractError: true });
    expect(getByText(STATUS_CONTRACT_ERROR_MESSAGE)).toBeVisible();
  });

  it("uses Update vocabulary and does not show a rebuild action", () => {
    const { getByRole, queryByRole } = renderPopover(makeStatus(), { isVirtualRoot: true });

    expect(getByRole("button", { name: "Update library" })).toBeVisible();
    expect(queryByRole("button", { name: "Scan" })).toBeNull();
    expect(queryByRole("button", { name: "Rebuild" })).toBeNull();
  });

  it("uses current-folder Update vocabulary for scoped catalog status", () => {
    const { getByRole } = renderPopover(
      makeStatus({ scope: { kind: "path", library_id: 7, path: "/photos", import_path_count: 1 } }),
      {
        path: "/photos",
      },
    );

    expect(getByRole("button", { name: "Update current folder" })).toBeVisible();
  });
});
