import { ref } from "vue";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OfflineFilesDialog from "../OfflineFilesDialog.vue";

const mutateAsync = vi.fn().mockResolvedValue({ forgotten: 2, items: [] });
const refetch = vi.fn();
const query = {
  data: ref({
    total: 2,
    items: [
      {
        id: 1,
        name: "a (4) - Copy.png",
        path: "/library/a (4) - Copy.png",
        type: "image" as const,
        size: 1024,
        indexed_at: null,
      },
      {
        id: 2,
        name: "ai meta (2).png",
        path: "/library/ai meta (2).png",
        type: "image" as const,
        size: 2048,
        indexed_at: null,
      },
    ],
  }),
  isPending: ref(false),
  isError: ref(false),
  refetch,
};

vi.mock("@/composables/admin/useOfflineLibraryAssets", () => ({
  useOfflineLibraryAssets: () => ({
    query,
    forgetMutation: { isPending: ref(false), mutateAsync },
  }),
}));

function mountSubject() {
  return mount(OfflineFilesDialog, {
    props: { open: true, libraryId: 19, expectedCount: 2 },
    global: {
      stubs: {
        Dialog: { template: "<div><slot /></div>" },
        DialogScrollContent: { template: "<div><slot /></div>" },
        DialogHeader: { template: "<header><slot /></header>" },
        DialogTitle: { template: "<h2><slot /></h2>" },
        DialogDescription: { template: "<p><slot /></p>" },
        DialogFooter: { template: "<footer><slot /></footer>" },
        Button: { template: "<button v-bind='$attrs'><slot /></button>" },
      },
    },
  });
}

describe("OfflineFilesDialog", () => {
  beforeEach(() => mutateAsync.mockClear());

  it("shows exact names and paths with a catalog-only warning", () => {
    const wrapper = mountSubject();
    expect(wrapper.text()).toContain("a (4) - Copy.png");
    expect(wrapper.text()).toContain("/library/a (4) - Copy.png");
    expect(wrapper.text()).toContain("ai meta (2).png");
    expect(wrapper.text()).toContain("does not delete source files");
    expect(wrapper.text()).toContain("Forget 2 files");
  });

  it("forgets the listed rows and closes after success", async () => {
    const wrapper = mountSubject();
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Forget 2 files"))!
      .trigger("click");
    expect(mutateAsync).toHaveBeenCalledOnce();
    expect(wrapper.emitted("update:open")).toContainEqual([false]);
  });
});
