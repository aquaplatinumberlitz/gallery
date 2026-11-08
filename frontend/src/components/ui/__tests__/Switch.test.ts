import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { Switch } from "@/components/ui/switch";

function mountSubject(props: Record<string, unknown> = {}) {
  return mount(Switch, {
    props: {
      "aria-label": "Test switch",
      ...props,
    },
  });
}

describe("Switch", () => {
  it("renders as an accessible switch with the unchecked state by default", () => {
    const wrapper = mountSubject();
    const toggle = wrapper.get('[role="switch"]');

    expect(toggle.attributes("aria-label")).toBe("Test switch");
    expect(toggle.attributes("aria-checked")).toBe("false");
    expect(toggle.attributes("data-state")).toBe("unchecked");
  });

  it("toggles aria-checked on click and emits update:modelValue", async () => {
    const wrapper = mountSubject({ modelValue: false });
    const toggle = wrapper.get('[role="switch"]');

    await toggle.trigger("click");

    expect(wrapper.emitted("update:modelValue")).toEqual([[true]]);
  });

  it("reflects the modelValue prop", async () => {
    const wrapper = mountSubject({ modelValue: true });
    const toggle = wrapper.get('[role="switch"]');

    expect(toggle.attributes("aria-checked")).toBe("true");
    expect(toggle.attributes("data-state")).toBe("checked");

    await wrapper.setProps({ modelValue: false });

    expect(toggle.attributes("aria-checked")).toBe("false");
  });

  it("merges a custom class onto the switch root", () => {
    const wrapper = mountSubject({ class: "custom-switch" });

    expect(wrapper.get('[role="switch"]').classes()).toContain("custom-switch");
  });
});
