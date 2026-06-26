import { describe, it, expect } from "vitest";
import { defineComponent, h } from "vue";
import { useRoute } from "vue-router";
import { renderWithApp, renderWithAppAsync } from "../renderWithApp";

describe("renderWithApp", () => {
  it("mounts a simple component", () => {
    const Comp = defineComponent({ setup: () => () => h("div", "hello") });
    const { wrapper } = renderWithApp(Comp);
    expect(wrapper.text()).toBe("hello");
  });

  it("passes props to the component", () => {
    const Comp = defineComponent({ props: { msg: String }, setup: (props) => () => h("div", props.msg) });
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
