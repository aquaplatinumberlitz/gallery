import { mount } from "@vue/test-utils";
import { nextTick, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY } from "@/utils/lightbox";
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
  window.localStorage.clear();
  isPending.value = false;
});

describe("SettingsModal", () => {
  it("shows Danger Zone reset controls for maintenance-capable users", () => {
    const wrapper = mountSubject();

    expect(wrapper.text()).toContain("Danger Zone");
    expect(wrapper.text()).toContain("Reset app data");
    expect(wrapper.text()).toContain("Source photos and videos are not deleted.");
    expect(wrapper.text()).toContain("RESET CATALOG DATABASE");
  });

  it("hides Danger Zone reset controls when capability is false", () => {
    const wrapper = mountSubject({ canResetCatalogDatabase: false });

    expect(wrapper.text()).not.toContain("Danger Zone");
    expect(wrapper.text()).not.toContain("Reset app data");
  });

  it("keeps Reset app data disabled until the confirmation phrase matches", async () => {
    const wrapper = mountSubject();
    const button = wrapper.findAll("button").find((candidate) => candidate.text().includes("Reset app data"));

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
      .find((candidate) => candidate.text().includes("Reset app data"))!
      .trigger("click");

    expect(mutateAsync).toHaveBeenCalledWith("RESET CATALOG DATABASE");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("reloads persisted settings when reopened after reset clears local state", async () => {
    window.localStorage.setItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY, "true");
    const wrapper = mountSubject();
    const alwaysLoadOriginal = () => wrapper.find<HTMLInputElement>('input[type="checkbox"]');

    expect(alwaysLoadOriginal().element.checked).toBe(true);

    window.localStorage.removeItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY);
    await wrapper.setProps({ isOpen: false });
    await wrapper.setProps({ isOpen: true });
    await nextTick();

    expect(alwaysLoadOriginal().element.checked).toBe(false);

    await wrapper.find<HTMLInputElement>('input[type="radio"][value="manual"]').setValue(true);

    expect(window.localStorage.getItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY)).not.toBe("true");
  });
});
