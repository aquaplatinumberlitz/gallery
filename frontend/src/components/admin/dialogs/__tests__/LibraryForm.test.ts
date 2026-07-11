import { describe, it, expect, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { setActivePinia, createPinia } from "pinia";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { VueQueryPlugin } from "@tanstack/vue-query";
import LibraryForm from "../LibraryForm.vue";

const mutationMocks = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  validate: vi.fn(),
  scan: vi.fn(),
}));

vi.mock("@/composables/admin/useLibraryMutations", () => ({
  useLibraryMutations: () => ({
    createMutation: { isPending: { value: false }, mutateAsync: mutationMocks.create },
    updateMutation: { isPending: { value: false }, mutateAsync: mutationMocks.update },
    validateMutation: {
      isPending: { value: false },
      mutateAsync: mutationMocks.validate,
    },
    scanMutation: { isPending: { value: false }, mutateAsync: mutationMocks.scan },
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
    vi.clearAllMocks();
    mutationMocks.validate.mockResolvedValue({ is_valid: true, import_paths: [], exclusion_patterns: [] });
    mutationMocks.create.mockResolvedValue({ id: 42, name: "Photos", import_paths: [] });
    mutationMocks.update.mockResolvedValue({ id: 42, name: "Photos", import_paths: [] });
    mutationMocks.scan.mockResolvedValue({});
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

  it("shows a checked scan-after-add option by default", () => {
    const wrapper = createWrapper();
    const checkbox = wrapper.get("#library-scan-after-add");

    expect(wrapper.text()).toContain("Scan library after adding");
    expect(checkbox.attributes("aria-checked")).toBe("true");
  });

  it("keeps only Cancel and Add library in the create footer", () => {
    const wrapper = createWrapper();
    expect(wrapper.text()).toContain("Cancel");
    expect(wrapper.text()).toContain("Add library");
    expect(wrapper.text()).not.toContain("Validate");
    expect(wrapper.text()).not.toContain("Add and update");
  });

  it("validates, creates, and scans when the default option is enabled", async () => {
    const wrapper = createWrapper();
    await wrapper.get("#library-import-path-0").setValue("/photos");

    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(mutationMocks.validate).toHaveBeenCalledOnce();
    expect(mutationMocks.create).toHaveBeenCalledOnce();
    expect(mutationMocks.scan).toHaveBeenCalledWith({ id: 42 });
    expect(wrapper.emitted("saved")).toHaveLength(1);
  });

  it("creates without scanning when the option is disabled", async () => {
    const wrapper = createWrapper();
    await wrapper.get("#library-import-path-0").setValue("/photos");
    await wrapper.get("#library-scan-after-add").trigger("click");

    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(mutationMocks.validate).toHaveBeenCalledOnce();
    expect(mutationMocks.create).toHaveBeenCalledOnce();
    expect(mutationMocks.scan).not.toHaveBeenCalled();
  });

  it("shows server validation errors inline without creating the library", async () => {
    mutationMocks.validate.mockResolvedValueOnce({
      is_valid: false,
      import_paths: [
        {
          value: "/missing",
          is_valid: false,
          message: "This folder is not available.",
          warnings: [],
        },
      ],
      exclusion_patterns: [],
    });
    const wrapper = createWrapper();
    await wrapper.get("#library-import-path-0").setValue("/missing");

    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("This folder is not available.");
    expect(wrapper.text()).toContain("Server validation found errors");
    expect(mutationMocks.create).not.toHaveBeenCalled();
    expect(mutationMocks.scan).not.toHaveBeenCalled();
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
