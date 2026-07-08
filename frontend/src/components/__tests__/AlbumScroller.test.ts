import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AlbumScroller from "../AlbumScroller.vue";
import type { FileNode } from "@/types";

vi.mock("@/composables/useDevice", () => ({
  useDevice: () => ({
    isMobile: { value: false },
    isTablet: { value: false },
  }),
}));

const folders: FileNode[] = [
  {
    name: "Album A",
    path: "/photos/album-a",
    type: "folder",
    has_children: false,
    image_count: 3,
  },
];

function mountSubject() {
  return mount(AlbumScroller, {
    props: { folders },
    global: {
      stubs: {
        GallerySectionHeader: {
          props: ["title", "count", "collapsed"],
          template:
            "<div data-testid='section-header'>{{ title }} {{ count }} {{ collapsed ? 'closed' : 'open' }}</div>",
        },
        AlbumCarouselDesktop: {
          template: "<div data-testid='album-carousel' />",
        },
        AlbumScrollerNative: {
          template: "<div data-testid='album-native' />",
        },
        Transition: false,
      },
    },
  });
}

describe("AlbumScroller", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows albums by default so users can see folders exist", () => {
    const wrapper = mountSubject();
    const toggle = wrapper.get(".album-toggle");

    expect(toggle.attributes("aria-expanded")).toBe("true");
    expect(toggle.attributes("aria-label")).toBe("Collapse albums");
    expect(wrapper.get("[data-testid='section-header']").text()).toContain("open");
    expect(wrapper.get("[data-testid='album-native']").isVisible()).toBe(true);
  });

  it("still lets users collapse albums and remembers the preference", async () => {
    const wrapper = mountSubject();

    await wrapper.get(".album-toggle").trigger("click");

    expect(wrapper.get(".album-toggle").attributes("aria-expanded")).toBe("false");
    expect(wrapper.get(".album-toggle").attributes("aria-label")).toBe("Expand albums");
    expect(localStorage.getItem("gallery-albums-collapsed-v2")).toBe("true");
  });
});
