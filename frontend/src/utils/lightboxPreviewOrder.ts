import type PhotoSwipe from "photoswipe";

type PhotoSwipeContent = NonNullable<PhotoSwipe["currSlide"]>["content"];

/**
 * Keeps the lightbox's neighbour preloads from competing with the slide the user is looking at.
 *
 * PhotoSwipe starts the current slide's image and, with `preload: [1, 1]`, the previous and next
 * slides' images in the same moment, so on a slow link three ~250 KB previews share the bandwidth and
 * the visible one arrives late. This holds every non-current image load back until the current slide's
 * image has loaded or failed, then releases them. Navigating to a slide whose load is still held
 * releases that slide immediately, because it is the current one now.
 *
 * Returns a function that forgets any held loads.
 */
export function deferNeighbourPreviewsUntilCurrentSettles(pswp: PhotoSwipe): () => void {
  const held = new Set<PhotoSwipeContent>();

  const currentSettled = (): boolean => {
    const content = pswp.currSlide?.content;
    // Nothing to wait for when there is no image content to wait on.
    if (!content || !content.isImageContent()) return true;
    return content.state === "loaded" || content.state === "error";
  };

  const release = () => {
    if (held.size === 0) return;
    const settled = currentSettled();
    for (const content of [...held]) {
      if (!settled && content.index !== pswp.currIndex) continue;
      held.delete(content);
      content.loadImage(content.index !== pswp.currIndex);
    }
  };

  pswp.on("contentLoadImage", (event) => {
    const content = event.content;
    if (content.index === pswp.currIndex || currentSettled()) return;
    event.preventDefault();
    held.add(content);
  });
  // loadComplete fires for loaded and failed images alike.
  pswp.on("loadComplete", release);
  pswp.on("change", release);
  pswp.on("contentDestroy", (event) => {
    held.delete(event.content);
  });

  return () => held.clear();
}
