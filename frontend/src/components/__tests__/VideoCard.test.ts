import { fireEvent, render } from "@testing-library/vue";
import { describe, expect, it } from "vitest";
import VideoCard from "../VideoCard.vue";

describe("VideoCard", () => {
  it("renders the poster endpoint, play affordance, and duration", async () => {
    const { emitted, getByAltText, getByRole, getByText } = render(VideoCard, {
      props: { src: "/library/clip.mp4", name: "clip.mp4", durationMs: 65_000 },
    });

    expect(getByAltText("Poster for clip.mp4")).toHaveAttribute("src", "/api/video/poster?path=%2Flibrary%2Fclip.mp4");
    expect(getByText("1:05")).toBeVisible();
    await fireEvent.click(getByRole("button", { name: "Play video clip.mp4" }));
    expect(emitted().click).toHaveLength(1);
  });

  it("shows a stable fallback when poster generation fails", async () => {
    const { getByAltText, getByTestId } = render(VideoCard, {
      props: { src: "/library/broken.mkv", name: "broken.mkv" },
    });

    await fireEvent.error(getByAltText("Poster for broken.mkv"));
    expect(getByTestId("video-poster-fallback")).toHaveTextContent("Preview unavailable");
  });
});
