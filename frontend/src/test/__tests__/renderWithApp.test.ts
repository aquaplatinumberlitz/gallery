import { afterAll, describe, it, expect, vi } from "vitest";
import { defineComponent, h, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import { renderWithApp, renderWithAppAsync, type RenderWithAppOptions } from "../renderWithApp";
import { assertNoUnexpectedRuntimeMessages } from "../setup";
import { withSetup } from "../withSetup";

const autoUnmountSpy = vi.fn();

afterAll(() => {
  expect(autoUnmountSpy).toHaveBeenCalledOnce();
});

describe("renderWithApp", () => {
  it("fails the runtime-message gate for unexpected console errors", () => {
    expect(() => assertNoUnexpectedRuntimeMessages(["boom"], [])).toThrow("Unexpected console errors detected:\nboom");
  });

  it("automatically unmounts wrappers after each test", () => {
    withSetup(() => {
      onUnmounted(autoUnmountSpy);
      return {};
    });
    expect(autoUnmountSpy).not.toHaveBeenCalled();
  });

  it("mounts a simple component", () => {
    const Comp = defineComponent({ setup: () => () => h("div", "hello") });
    const { wrapper } = renderWithApp(Comp);
    expect(wrapper.text()).toBe("hello");
  });

  it("passes props to the component", () => {
    const Comp = defineComponent({
      props: { msg: { type: String, required: true } },
      setup: (props: { msg: string }) => () => h("div", props.msg),
    });
    const { wrapper } = renderWithApp(Comp, { props: { msg: "world" } });
    expect(wrapper.text()).toBe("world");
  });

  it("provides router, Pinia, and Vue Query", () => {
    const Comp = defineComponent({
      setup: () => {
        const route = useRoute();
        return () => h("div", route.fullPath);
      },
    });
    const { wrapper } = renderWithApp(Comp);
    // Sync helper starts at "/"
    expect(wrapper.text()).toBe("/");
  });

  it("rejects initialRoute at runtime", () => {
    const Comp = defineComponent({ setup: () => () => h("div", "x") });
    expect(() => renderWithApp(Comp, { initialRoute: "/admin" as never })).toThrow(
      "renderWithApp does not support initialRoute",
    );
  });

  it("rejects initialRoute even when cast through RenderWithAppOptions", () => {
    // The type-level constraint (initialRoute?: never) prevents passing
    // initialRoute at compile time. This test verifies the runtime guard
    // catches cases where type checking is bypassed (e.g. `as any`).
    const Comp = defineComponent({ setup: () => () => h("div", "x") });
    const opts = { initialRoute: "/admin" } as unknown as RenderWithAppOptions;
    expect(() => renderWithApp(Comp, opts)).toThrow("renderWithApp does not support initialRoute");
  });
});

describe("renderWithAppAsync", () => {
  it("mounts with initial route resolved before mount", async () => {
    const Comp = defineComponent({
      setup: () => {
        const route = useRoute();
        return () => h("div", route.fullPath);
      },
    });
    const { wrapper } = await renderWithAppAsync(Comp, { initialRoute: "/admin" });
    expect(wrapper.text()).toBe("/admin");
  });
});
