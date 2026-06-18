import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { defineComponent, h, onBeforeUnmount, ref } from "vue";
import { mount } from "@vue/test-utils";
import { useFocusTrap } from "../useFocusTrap";

/**
 * jsdom's requestAnimationFrame is async (setTimeout-based), but useFocusTrap
 * focuses inside a rAF callback. Override it to run synchronously so tests can
 * assert focus state immediately after activate().
 */
beforeEach(() => {
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    cb(0);
    return 0;
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * jsdom does not perform layout, so `element.offsetParent` is always null.
 * The focus trap uses `offsetParent !== null` as a visibility check, which
 * would filter out every element in tests. We patch the accessor on a per-
 * element basis to mimic a visible element.
 */
function markVisible(el: HTMLElement) {
  Object.defineProperty(el, "offsetParent", {
    configurable: true,
    get: () => document.body,
  });
}

function mountWithTrap(buttonsHtml: string) {
  const container = ref<HTMLElement | null>(null);
  const initialFocus = ref<HTMLElement | null>(null);
  let trap: ReturnType<typeof useFocusTrap> | null = null;

  const wrapper = mount(
    defineComponent({
      setup() {
        trap = useFocusTrap(container, { initialFocus, returnFocus: true });
        // Auto-deactivate on unmount so keydown listeners don't leak between tests.
        onBeforeUnmount(() => trap?.deactivate());
        return () =>
          h("div", { ref: container }, [
            h("div", {
              innerHTML: buttonsHtml,
            }),
          ]);
      },
    }),
    { attachTo: document.body },
  );

  return {
    wrapper,
    container,
    initialFocus,
    getTrap: () => trap!,
  };
}

describe("useFocusTrap", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("returns no focusable elements when the container ref is null", () => {
    const container = ref<HTMLElement | null>(null);
    let trap: ReturnType<typeof useFocusTrap> | null = null;
    mount(
      defineComponent({
        setup() {
          trap = useFocusTrap(container);
          return () => h("div");
        },
      }),
    );
    expect(trap!.getFocusableElements()).toEqual([]);
    expect(trap!.getFirstFocusable()).toBeNull();
    expect(trap!.getLastFocusable()).toBeNull();
  });

  it("finds visible buttons and links inside the container", () => {
    const { wrapper, container, getTrap } = mountWithTrap(
      `<button id="b1">One</button><a href="#" id="a1">Link</a><button id="b2" disabled>Disabled</button>`,
    );
    for (const id of ["b1", "a1"]) {
      const el = container.value!.querySelector<HTMLElement>(`#${id}`)!;
      markVisible(el);
    }

    const focusable = getTrap().getFocusableElements();
    const ids = focusable.map((e) => e.id);
    expect(ids).toContain("b1");
    expect(ids).toContain("a1");
    // Disabled button should NOT be in the focusable list.
    expect(ids).not.toContain("b2");

    wrapper.unmount();
  });

  it("getFirstFocusable / getLastFocusable return the first/last focusable elements", () => {
    const { wrapper, container, getTrap } = mountWithTrap(
      `<button id="b1">One</button><button id="b2">Two</button><button id="b3">Three</button>`,
    );
    for (const id of ["b1", "b2", "b3"]) {
      markVisible(container.value!.querySelector<HTMLElement>(`#${id}`)!);
    }

    expect(getTrap().getFirstFocusable()?.id).toBe("b1");
    expect(getTrap().getLastFocusable()?.id).toBe("b3");

    wrapper.unmount();
  });

  it("getFirstFocusable / getLastFocusable return null when no focusable elements exist", () => {
    const { wrapper, getTrap } = mountWithTrap(`<div>no focusable elements here</div>`);
    expect(getTrap().getFirstFocusable()).toBeNull();
    expect(getTrap().getLastFocusable()).toBeNull();
    wrapper.unmount();
  });

  it("activate() focuses the initialFocus element when provided", () => {
    const { wrapper, container, initialFocus, getTrap } = mountWithTrap(
      `<button id="b1">One</button><button id="b2">Two</button>`,
    );
    for (const id of ["b1", "b2"]) {
      markVisible(container.value!.querySelector<HTMLElement>(`#${id}`)!);
    }
    // Add a separate initial focus target inside the container.
    const initial = document.createElement("button");
    initial.id = "initial";
    markVisible(initial);
    container.value!.appendChild(initial);
    initialFocus.value = initial;

    getTrap().activate();
    // The activate() helper uses requestAnimationFrame which is synchronous
    // in jsdom via the setup file, so the rAF callback runs immediately.
    expect(document.activeElement).toBe(initial);

    wrapper.unmount();
  });

  it("activate() focuses the first focusable element when no initialFocus is provided", () => {
    const { wrapper, container, getTrap } = mountWithTrap(`<button id="b1">One</button><button id="b2">Two</button>`);
    for (const id of ["b1", "b2"]) {
      markVisible(container.value!.querySelector<HTMLElement>(`#${id}`)!);
    }
    getTrap().activate();
    expect(document.activeElement?.id).toBe("b1");
    wrapper.unmount();
  });

  it("activate() focuses the container itself when no focusable elements exist", () => {
    const { wrapper, container, getTrap } = mountWithTrap(`<div>nothing</div>`);
    const containerEl = container.value!;
    containerEl.setAttribute("tabindex", "-1");
    getTrap().activate();
    expect(document.activeElement).toBe(containerEl);
    wrapper.unmount();
  });

  it("Tab on the last focusable element wraps focus back to the first", () => {
    const { wrapper, container, getTrap } = mountWithTrap(`<button id="b1">One</button><button id="b2">Two</button>`);
    for (const id of ["b1", "b2"]) {
      markVisible(container.value!.querySelector<HTMLElement>(`#${id}`)!);
    }
    getTrap().activate();
    const lastButton = container.value!.querySelector<HTMLElement>("#b2")!;
    lastButton.focus();
    expect(document.activeElement?.id).toBe("b2");

    const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement?.id).toBe("b1");

    wrapper.unmount();
  });

  it("Shift+Tab on the first focusable element wraps focus to the last", () => {
    const { wrapper, container, getTrap } = mountWithTrap(`<button id="b1">One</button><button id="b2">Two</button>`);
    for (const id of ["b1", "b2"]) {
      markVisible(container.value!.querySelector<HTMLElement>(`#${id}`)!);
    }
    getTrap().activate();
    const firstButton = container.value!.querySelector<HTMLElement>("#b1")!;
    firstButton.focus();

    const event = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement?.id).toBe("b2");

    wrapper.unmount();
  });

  it("ignores keydown events for keys other than Tab", () => {
    const { wrapper, container, getTrap } = mountWithTrap(`<button id="b1">One</button>`);
    markVisible(container.value!.querySelector<HTMLElement>("#b1")!);
    getTrap().activate();

    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);

    wrapper.unmount();
  });

  it("Tab does nothing visible but defaultPrevents when there are no focusable elements", () => {
    const { wrapper, getTrap } = mountWithTrap(`<div>no focusable</div>`);
    getTrap().activate();

    const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);

    wrapper.unmount();
  });

  it("deactivate() removes the keydown listener so Tab no longer traps", () => {
    const { wrapper, container, getTrap } = mountWithTrap(`<button id="b1">One</button><button id="b2">Two</button>`);
    for (const id of ["b1", "b2"]) {
      markVisible(container.value!.querySelector<HTMLElement>(`#${id}`)!);
    }
    getTrap().activate();
    getTrap().deactivate();

    const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);

    wrapper.unmount();
  });

  it("Tab wraps to last when the active element is outside the container", () => {
    const { wrapper, container, getTrap } = mountWithTrap(`<button id="b1">One</button><button id="b2">Two</button>`);
    for (const id of ["b1", "b2"]) {
      markVisible(container.value!.querySelector<HTMLElement>(`#${id}`)!);
    }
    getTrap().activate();
    // Move focus outside the container.
    const outside = document.createElement("button");
    outside.id = "outside";
    document.body.appendChild(outside);
    outside.focus();
    expect(document.activeElement?.id).toBe("outside");

    const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement?.id).toBe("b1");

    wrapper.unmount();
  });
});
