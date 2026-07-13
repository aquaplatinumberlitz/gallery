/**
 * Purpose: Protect image-card Find Related overflow behavior and keyboard semantics.
 * Guarantees: The action does not open the image and emits a separate reference event.
 * Run when: Changing PhotoCard actions, focusability, or Related Assets entry points.
 */
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PhotoCard from "../PhotoCard.vue";

describe("PhotoCard related action", () => {
  it("renders a focusable image card and emits find-related separately", async () => {
    const wrapper = mount(PhotoCard, {
      props: { src: "/photo.png", name: "photo.png", canFindRelated: true },
      global: {
        stubs: {
          AssetActionMenu: {
            template: '<button class="related-action" @click.stop="$emit(\'find-related\')">Find related</button>',
          },
        },
      },
    });
    expect(wrapper.get('[data-testid="photo-card"]').attributes()).toMatchObject({
      role: "button",
      tabindex: "0",
      "aria-label": "Open photo.png",
    });
    await wrapper.get(".related-action").trigger("click");
    expect(wrapper.emitted("find-related")).toHaveLength(1);
    expect(wrapper.emitted("click")).toBeUndefined();
  });
});
