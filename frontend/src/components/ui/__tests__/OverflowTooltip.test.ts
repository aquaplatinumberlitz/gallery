import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, nextTick, ref } from "vue";
import { TooltipProvider } from "reka-ui";
import OverflowTooltip from "../OverflowTooltip.vue";

const PARENT_SCOPE_ID = "data-v-parent-scope";

let overflowing = false;
const originalScrollWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollWidth");
const originalClientWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth");

function mountInScopedParent(initialText: string) {
  const text = ref(initialText);
  const Parent = defineComponent({
    // Mimics an SFC with <style scoped>: Vue stamps this id onto child component roots.
    __scopeId: PARENT_SCOPE_ID,
    components: { OverflowTooltip, TooltipProvider },
    setup: () => ({ text }),
    template: `<TooltipProvider><OverflowTooltip :text="text" class="result-name">{{ text }}</OverflowTooltip></TooltipProvider>`,
  });
  const wrapper = mount(Parent, { attachTo: document.body });
  return { wrapper, text };
}

describe("OverflowTooltip", () => {
  beforeEach(() => {
    overflowing = false;
    Object.defineProperty(HTMLElement.prototype, "scrollWidth", {
      configurable: true,
      get() {
        return overflowing ? 200 : 100;
      },
    });
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get() {
        return 100;
      },
    });
  });

  afterEach(() => {
    if (originalScrollWidth) Object.defineProperty(HTMLElement.prototype, "scrollWidth", originalScrollWidth);
    if (originalClientWidth) Object.defineProperty(HTMLElement.prototype, "clientWidth", originalClientWidth);
    document.body.innerHTML = "";
  });

  it("keeps the parent scoped-style attribute while the label does not overflow", async () => {
    const { wrapper } = mountInScopedParent("short.png");
    await nextTick();
    await nextTick();

    const label = wrapper.get(".result-name");
    expect(label.attributes()).toHaveProperty(PARENT_SCOPE_ID);
    expect(wrapper.find(".break-words").exists()).toBe(false);
  });

  it("keeps the parent scoped-style attribute and the same element once the tooltip turns on", async () => {
    const { wrapper, text } = mountInScopedParent("short.png");
    await nextTick();
    await nextTick();
    const before = wrapper.get(".result-name").element;

    overflowing = true;
    text.value = "very_long_filename_generated_by_comfyui_00001.png";
    await flushPromises();
    await nextTick();

    const label = wrapper.get(".result-name");
    // The tooltip content is enabled, but the measured element was not remounted and still
    // carries the parent's scope id, so `.result-name` scoped rules keep applying.
    expect(wrapper.find(".break-words").exists()).toBe(true);
    expect(label.attributes()).toHaveProperty(PARENT_SCOPE_ID);
    expect(label.element).toBe(before);
  });
});
