import { describe, expect, it } from "vitest";
import { useCoverImageLoad } from "../useCoverImageLoad";
import { ALBUM_PLACEHOLDER_SVG } from "@/utils/albumCardPlaceholder";

describe("useCoverImageLoad", () => {
  it("starts unsettled so the loading skeleton is visible", () => {
    const { loaded } = useCoverImageLoad();
    expect(loaded.value).toBe(false);
  });

  it("settles once the cover has loaded or errored", () => {
    const { loaded, markCoverSettled } = useCoverImageLoad();

    markCoverSettled();

    expect(loaded.value).toBe(true);
  });

  it("ignores the error event of an image whose src was cleared to cancel its request", () => {
    const { loaded, markCoverSettled } = useCoverImageLoad();
    const cancelled = document.createElement("img");
    const failed = document.createElement("img");
    failed.setAttribute("src", "/broken.png");

    cancelled.addEventListener("error", markCoverSettled);
    cancelled.dispatchEvent(new Event("error"));
    expect(loaded.value).toBe(false);

    failed.addEventListener("error", markCoverSettled);
    failed.dispatchEvent(new Event("error"));
    expect(loaded.value).toBe(true);
  });

  it("keeps independent state per card", () => {
    const first = useCoverImageLoad();
    const second = useCoverImageLoad();

    first.markCoverSettled();

    expect(first.loaded.value).toBe(true);
    expect(second.loaded.value).toBe(false);
  });
});

describe("ALBUM_PLACEHOLDER_SVG", () => {
  it("is a self-contained 640x640 svg that inherits the card colour", () => {
    expect(ALBUM_PLACEHOLDER_SVG.startsWith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640">')).toBe(
      true,
    );
    expect(ALBUM_PLACEHOLDER_SVG).toContain('fill="currentColor"');
    expect(ALBUM_PLACEHOLDER_SVG.endsWith("</svg>")).toBe(true);
  });
});
