import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import IndexStatusCard from "../IndexStatusCard.vue";
import { getCatalogStatusPresentation } from "@/lib/catalog/labels";
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

function indexingStatus(): UnifiedStatus {
  return makeStatus({
    summary_state: "indexing",
    metadata: {
      state: "indexing",
      total_assets: 10,
      ready_assets: 6,
      not_ready_assets: 4,
      queued_assets: 4,
      running_assets: 0,
      stale_assets: 0,
      idle_pending_assets: 0,
      failed_assets: 0,
      progress_percent: 60,
      global_active_outside_scope: false,
    },
  });
}

function mountCard(status: UnifiedStatus) {
  return mount(IndexStatusCard, {
    props: {
      status,
      presentation: getCatalogStatusPresentation(status.summary_state),
    },
    global: {
      stubs: {
        Database: { template: "<span />" },
        IndexStatusBadge: { template: "<span />" },
        IndexStatusDetailsPopover: { template: "<div />" },
        IndexProgressBar: { props: ["percent"], template: '<div data-testid="index-progress-bar">{{ percent }}</div>' },
        Popover: { template: "<div><slot /></div>" },
        PopoverTrigger: { template: "<div><slot /></div>" },
        PopoverContent: { template: "<div><slot /></div>" },
      },
    },
  });
}

describe("IndexStatusCard completion progress", () => {
  it("lingers at 100% briefly after indexing completes", async () => {
    vi.useFakeTimers();
    try {
      const wrapper = mountCard(indexingStatus());
      expect(wrapper.get('[data-testid="index-progress-bar"]').text()).toBe("60");

      const completeStatus = makeStatus();
      await wrapper.setProps({
        status: completeStatus,
        presentation: getCatalogStatusPresentation(completeStatus.summary_state),
      });

      expect(wrapper.get('[data-testid="index-progress-bar"]').text()).toBe("100");

      await vi.advanceTimersByTimeAsync(899);
      await nextTick();
      expect(wrapper.find('[data-testid="index-progress-bar"]').exists()).toBe(true);

      await vi.advanceTimersByTimeAsync(1);
      await nextTick();
      expect(wrapper.find('[data-testid="index-progress-bar"]').exists()).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
});
