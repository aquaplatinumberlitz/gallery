import { mount } from "@vue/test-utils";
import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SettingsModal from "../SettingsModal.vue";

const mutateAsync = vi.fn();
const isPending = ref(false);

vi.mock("@/db/composables/useLandingPagesLiveQuery", () => ({
  useLandingPagesLiveQuery: () => ({
    data: ref([{ url: "/landpage/lunar_newyear/index.html", index: 0 }]),
    isLoading: ref(false),
    isError: ref(false),
  }),
}));

vi.mock("@/composables/admin/useCatalogResetMutation", () => ({
  useCatalogResetMutation: () => ({
    isPending,
    mutateAsync,
  }),
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: { props: ["open"], template: "<div v-if='open'><slot /></div>" },
  DialogContent: { template: "<div><slot /></div>" },
  DialogDescription: { template: "<p><slot /></p>" },
  DialogHeader: { template: "<div><slot /></div>" },
  DialogTitle: { template: "<h2><slot /></h2>" },
}));

function mountSubject(props: { isOpen?: boolean; canResetCatalogDatabase?: boolean } = {}) {
  return mount(SettingsModal, {
    props: {
      isOpen: true,
      ...props,
    },
    global: {
      stubs: {
        Button: { template: "<button v-bind='$attrs'><slot /></button>" },
      },
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  isPending.value = false;
});

describe("SettingsModal", () => {
  it("shows Danger Zone reset controls for maintenance-capable users", () => {
    const wrapper = mountSubject();

    expect(wrapper.text()).toContain("Danger Zone");
    expect(wrapper.text()).toContain("Reset All");
    expect(wrapper.text()).toContain("RESET CATALOG DATABASE");
  });

  it("hides Danger Zone reset controls when capability is false", () => {
    const wrapper = mountSubject({ canResetCatalogDatabase: false });

    expect(wrapper.text()).not.toContain("Danger Zone");
    expect(wrapper.text()).not.toContain("Reset All");
  });

  it("keeps Reset All disabled until the confirmation phrase matches", async () => {
    const wrapper = mountSubject();
    const button = wrapper.findAll("button").find((candidate) => candidate.text().includes("Reset All"));

    expect(button?.attributes("disabled")).toBeDefined();

    await wrapper.find("#catalog-reset-confirm").setValue("RESET CATALOG DATABASE");

    expect(button?.attributes("disabled")).toBeUndefined();
  });

  it("resets the catalog and closes after confirmation", async () => {
    mutateAsync.mockResolvedValue({});
    const wrapper = mountSubject();

    await wrapper.find("#catalog-reset-confirm").setValue("RESET CATALOG DATABASE");
    await wrapper
      .findAll("button")
      .find((candidate) => candidate.text().includes("Reset All"))!
      .trigger("click");

    expect(mutateAsync).toHaveBeenCalledWith("RESET CATALOG DATABASE");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });
});
