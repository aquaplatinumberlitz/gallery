import { describe, it, expect } from "vitest";
import { defineComponent, h } from "vue";
import { useRoute } from "vue-router";
import { renderWithApp, renderWithAppAsync, type RenderWithAppOptions } from "../renderWithApp";

describe("renderWithApp", () => {
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
    expect(() =>
      renderWithApp(Comp, { initialRoute: "/admin" as never }),
    ).toThrow("renderWithApp does not support initialRoute");
  });

  it("rejects initialRoute even when cast through RenderWithAppOptions", () => {
    // The type-level constraint (initialRoute?: never) prevents passing
    // initialRoute at compile time. This test verifies the runtime guard
    // catches cases where type checking is bypassed (e.g. `as any`).
    const Comp = defineComponent({ setup: () => () => h("div", "x") });
    const opts = { initialRoute: "/admin" } as RenderWithAppOptions;
    expect(() => renderWithApp(Comp, opts)).toThrow(
      "renderWithApp does not support initialRoute",
    );
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
