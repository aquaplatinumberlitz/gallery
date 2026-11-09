import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import HeaderSearchBox from "@/components/HeaderSearchBox.vue";

// Regression for CJ-02: the Enter that confirms an IME candidate must not submit the search.
const mountBox = () => mount(HeaderSearchBox, { props: { id: "gallery-search", modelValue: "さくら" } });

const keydown = (el: Element, init: KeyboardEventInit & { keyCode?: number }) => {
  const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
  if (init.keyCode !== undefined) Object.defineProperty(event, "keyCode", { value: init.keyCode });
  el.dispatchEvent(event);
};

describe("HeaderSearchBox Enter handling (CJ-02)", () => {
  it("submits on a plain Enter", () => {
    const wrapper = mountBox();
    keydown(wrapper.find("input").element, { key: "Enter", keyCode: 13 });
    expect(wrapper.emitted("submit")).toHaveLength(1);
    wrapper.unmount();
  });

  it("does not submit on the Enter that confirms an IME candidate (isComposing)", () => {
    const wrapper = mountBox();
    keydown(wrapper.find("input").element, { key: "Enter", isComposing: true });
    expect(wrapper.emitted("submit")).toBeUndefined();
    wrapper.unmount();
  });

  it("does not submit on keyCode 229 (IME processing)", () => {
    const wrapper = mountBox();
    keydown(wrapper.find("input").element, { key: "Enter", keyCode: 229 });
    expect(wrapper.emitted("submit")).toBeUndefined();
    wrapper.unmount();
  });
});
