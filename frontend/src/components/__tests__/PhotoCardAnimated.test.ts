/**
 * Purpose: Pin PhotoCard's hover play to the backend `animated` value instead of the file extension.
 * Guarantees: A static WebP (`animated=false`) never requests the original through `/api/image` on hover and never
 * shows the "PLAYING" badge; an animated WebP, GIF or APNG loads the original after the 150 ms hover delay and
 * shows the badge; an unknown value (null or absent) plays only a `.gif`; leaving the card stops the preview.
 * Run when: Changing PhotoCard hover behaviour or the `animated` prop.
 */
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PhotoCard from "../PhotoCard.vue";

let counter = 0;

const mountCard = (props: Record<string, unknown>) =>
  mount(PhotoCard, {
    props: { src: `/animated-test/${++counter}/${String(props.name)}`, fetchPriority: "high", ...props },
    attachTo: document.body,
    global: { stubs: { AssetActionMenu: true } },
  });

const hover = async (wrapper: ReturnType<typeof mountCard>) => {
  await wrapper.find("img.thumbnail-img").trigger("load");
  await wrapper.find(".photo-card-shell").trigger("mouseenter");
  await vi.advanceTimersByTimeAsync(150);
  await nextTick();
};

const originalRequest = (wrapper: ReturnType<typeof mountCard>) => wrapper.find("img.preview-overlay");

describe("PhotoCard hover play", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // jsdom has no hover media: report a hover-capable pointer.
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({ matches: false, media: query, addEventListener: vi.fn() })),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("does not download the original or show PLAYING for a static WebP", async () => {
    const wrapper = mountCard({ name: "still.webp", animated: false });
    await hover(wrapper);
    expect(originalRequest(wrapper).exists()).toBe(false);
    expect(wrapper.find(".type-badge").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("PLAYING");
  });

  it.each(["moving.webp", "moving.gif", "moving.png"])("plays an animated %s on hover", async (name) => {
    const wrapper = mountCard({ name, animated: true });
    await hover(wrapper);
    expect(originalRequest(wrapper).attributes("src")).toContain("/api/image");
    expect(wrapper.text()).toContain("PLAYING");
  });

  it("does not play a GIF the backend found static", async () => {
    const wrapper = mountCard({ name: "still.gif", animated: false });
    await hover(wrapper);
    expect(originalRequest(wrapper).exists()).toBe(false);
  });

  it("while the value is unknown, plays a .gif and nothing else", async () => {
    const gif = mountCard({ name: "unknown.gif", animated: null });
    await hover(gif);
    expect(originalRequest(gif).exists()).toBe(true);

    for (const name of ["unknown.webp", "unknown.png"]) {
      const wrapper = mountCard({ name });
      await hover(wrapper);
      expect(originalRequest(wrapper).exists()).toBe(false);
    }
  });

  it("stops the original request when the pointer leaves", async () => {
    const wrapper = mountCard({ name: "moving.webp", animated: true });
    await hover(wrapper);
    expect(originalRequest(wrapper).exists()).toBe(true);
    await wrapper.find(".photo-card-shell").trigger("mouseleave");
    expect(originalRequest(wrapper).exists()).toBe(false);
  });
});
