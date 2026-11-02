import { ref } from "vue";

/**
 * Tracks whether an album cover image has settled so the card can hide its loading skeleton.
 *
 * Both a successful load and a load error count as settled: a broken cover must not leave the
 * shimmer running forever. An error event from an image whose `src` was cleared to cancel its request
 * (see useVisibleLoadGate) is not a real error and is ignored.
 */
export function useCoverImageLoad() {
  const loaded = ref(false);
  const markCoverSettled = (event?: Event) => {
    const img = event?.target instanceof HTMLImageElement ? event.target : null;
    if (event?.type === "error" && img && !img.getAttribute("src")) return;
    loaded.value = true;
  };
  return { loaded, markCoverSettled };
}
