import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import Input from "@/components/ui/Input.vue";

// Regression for CJ-01: the search fields use components/ui/Input.vue. While an IME is composing, the
// uncommitted text must not reach the model (it used to be searched as "さく" before "桜" was committed).
const mountInput = (props: Record<string, unknown> = {}) =>
  mount(Input, { props: { modelValue: "", type: "search", ...props }, attachTo: document.body });

const typeInto = (el: HTMLInputElement, value: string, isComposing: boolean) => {
  el.value = value;
  el.dispatchEvent(new InputEvent("input", { bubbles: true, data: value, isComposing }));
};

describe("ui Input composition handling (CJ-01)", () => {
  it("emits the typed value for ordinary input", async () => {
    const wrapper = mountInput();
    const el = wrapper.element as HTMLInputElement;
    typeInto(el, "night", false);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["night"]);
    wrapper.unmount();
  });

  it("does not emit uncommitted IME text while composing", async () => {
    const wrapper = mountInput();
    const el = wrapper.element as HTMLInputElement;
    el.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "" }));
    typeInto(el, "さ", true);
    typeInto(el, "さく", true);
    typeInto(el, "さくら", true);
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    wrapper.unmount();
  });

  it("emits the committed text on compositionend", async () => {
    const wrapper = mountInput();
    const el = wrapper.element as HTMLInputElement;
    el.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "" }));
    typeInto(el, "さくら", true);
    el.value = "桜";
    el.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: "桜" }));
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["桜"]);
    wrapper.unmount();
  });

  it("keeps emitting plain input after a composition ends", async () => {
    const wrapper = mountInput();
    const el = wrapper.element as HTMLInputElement;
    el.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "" }));
    el.value = "桜";
    el.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: "桜" }));
    typeInto(el, "桜a", false);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["桜a"]);
    wrapper.unmount();
  });
});
