import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import LibraryForm from "../LibraryForm.vue";

vi.mock("@/composables/admin/useLibraryMutations", () => ({
  useLibraryMutations: () => ({
    createMutation: { isPending: { value: false }, mutateAsync: vi.fn().mockRejectedValue(new Error("fail")) },
    updateMutation: { isPending: { value: false }, mutateAsync: vi.fn().mockRejectedValue(new Error("fail")) },
    validateMutation: {
      isPending: { value: false },
      mutateAsync: vi.fn().mockResolvedValue({ is_valid: true, import_paths: [], exclusion_patterns: [] }),
    },
    scanMutation: { isPending: { value: false }, mutateAsync: vi.fn().mockRejectedValue(new Error("fail")) },
  }),
}));

vi.mock("@/services/api", () => ({
  GalleryAPIError: class extends Error {
    userMessage = "Validation failed";
    suggestion = "Check input";
    constructor() {
      super("Validation failed");
    }
  },
}));

function createWrapper(props: Record<string, unknown> = {}) {
  setActivePinia(createPinia());
  const queryClient = createIsolatedQueryClient();
  return mount(LibraryForm, {
    props: {
      library: null,
      libraries: [],
      ...props,
    },
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: {
        Button: { template: "<button :disabled='disabled' @click='$attrs.onClick?.()'><slot /></button>" },
        Input: {
          template:
            "<input v-bind='$attrs' :value='$attrs.modelValue ?? modelValue' @input='$emit(\"update:modelValue\", $event.target.value)' />",
        },
      },
    },
  });
}

describe("LibraryForm", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders the form with display name field", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Display name");
  });

  it("renders folders section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Folders");
  });

  it("shows visible labels for each folder row", async () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Folder 1");

    const addFolder = wrapper.findAll("button").find((button) => button.text().includes("Add folder"));
    await addFolder?.trigger("click");

    expect(wrapper.text()).toContain("Folder 1");
    expect(wrapper.text()).toContain("Folder 2");
  });

  it("marks only the invalid folder row as aria-invalid", async () => {
    const wrapper = createWrapper();
    const addFolder = wrapper.findAll("button").find((button) => button.text().includes("Add folder"));
    await addFolder?.trigger("click");

    await wrapper.find("#library-import-path-0").setValue("/photos");
    await wrapper.find("#library-import-path-1").setValue("relative/path");

    expect(wrapper.find("#library-import-path-0").attributes("aria-invalid")).toBe("false");
    expect(wrapper.find("#library-import-path-1").attributes("aria-invalid")).toBe("true");
    expect(wrapper.text()).toContain("Use an absolute folder path.");
  });

  it("renders exclusion patterns section", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Exclusion patterns");
  });

  it("shows Add library button when no library prop", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Add library");
  });

  it("shows Save changes when library prop provided", () => {
    const wrapper = createWrapper({
      library: {
        id: 1,
        name: "Test",
        state: "ready",
        watch_enabled: 1,
        warm_enabled: 1,
        import_paths: [
          { id: 1, path: "/test", library_id: 1, position: 0, created_at: Date.now(), updated_at: Date.now() },
        ],
        exclusion_patterns: [],
        root_path: "/test",
        asset_count: 0,
        created_at: Date.now(),
        updated_at: Date.now(),
        last_scan_at: null,
        last_error: null,
      },
    });
    expect(wrapper.text()).toContain("Save changes");
  });

  it("shows Add and update button when no library", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Add and update");
  });

  it("renders Cancel and Validate buttons", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Cancel");
    expect(wrapper.text()).toContain("Validate");
  });

  it("emits cancel when Cancel clicked", async () => {
    const wrapper = createWrapper();
    const cancelBtn = wrapper.findAll("button").filter((b) => b.text().trim() === "Cancel" && b.isVisible())[0];
    if (cancelBtn) {
      await cancelBtn.trigger("click");
      expect(wrapper.emitted("cancel")?.length).toBeGreaterThan(0);
    }
  });
});
