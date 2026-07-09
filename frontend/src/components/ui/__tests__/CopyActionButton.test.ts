import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import CopyActionButton from "../CopyActionButton.vue";

function mountSubject(props: Record<string, unknown> = {}) {
  return mount(CopyActionButton, {
    props: {
      copied: false,
      label: "Copy prompt",
      successAriaLabel: "Prompt copied",
      ...props,
    },
  });
}

describe("CopyActionButton", () => {
  it("renders the default copy state", () => {
    const wrapper = mountSubject();
    const button = wrapper.get("button");

    expect(button.text()).toBe("Copy prompt");
    expect(button.attributes("aria-label")).toBe("Copy prompt");
    expect(button.attributes("data-copied")).toBe("false");
    expect(wrapper.get(".copy-state-icon").attributes("data-copied")).toBe("false");
  });

  it("renders the shared success state and aria label", () => {
    const wrapper = mountSubject({ copied: true });
    const button = wrapper.get("button");

    expect(button.text()).toBe("Copied");
    expect(button.attributes("aria-label")).toBe("Prompt copied");
    expect(button.attributes("data-copied")).toBe("true");
    expect(wrapper.get(".copy-state-icon__check").classes()).toContain("text-[var(--gallery-success)]");
  });

  it("stops pointer and click propagation, prevents the click default, and emits the MouseEvent", async () => {
    const parentClick = vi.fn();
    const parentPointerDown = vi.fn();
    const wrapper = mount({
      components: { CopyActionButton },
      methods: { parentClick, parentPointerDown },
      template: `
        <div @click="parentClick" @pointerdown="parentPointerDown">
          <CopyActionButton :copied="false" label="Copy prompt" success-aria-label="Prompt copied" />
        </div>
      `,
    });
    const button = wrapper.get("button");

    await button.trigger("pointerdown");
    await button.trigger("click");

    const emittedEvent = wrapper.getComponent(CopyActionButton).emitted("click")?.[0]?.[0];
    expect(emittedEvent).toBeInstanceOf(MouseEvent);
    expect((emittedEvent as MouseEvent).defaultPrevented).toBe(true);
    expect(parentPointerDown).not.toHaveBeenCalled();
    expect(parentClick).not.toHaveBeenCalled();
  });
});
