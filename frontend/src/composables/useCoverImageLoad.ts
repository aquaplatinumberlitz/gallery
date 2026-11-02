import { ref } from "vue";
import { useImageRetry } from "./useImageRetry";

/**
 * Tracks whether an album cover image has settled so the card can hide its loading skeleton.
 *
 * Both a successful load and a load error count as settled: a broken cover must not leave the
 * shimmer running forever. An error event from an image whose `src` was cleared to cancel its request
 * (see useVisibleLoadGate) is not a real error and is ignored.
 *
 * `onCoverError` is the `@error` handler: a real error first retries the cover (see useImageRetry; the
 * skeleton keeps shimmering meanwhile, `retryAttempt` goes into the URL) and only settles once the retries
 * are used up. `resetRetry` re-arms it when the card leaves the viewport.
 */
export function useCoverImageLoad() {
  const loaded = ref(false);
  const markCoverSettled = (event?: Event) => {
    const img = event?.target instanceof HTMLImageElement ? event.target : null;
    if (event?.type === "error" && img && !img.getAttribute("src")) return;
    loaded.value = true;
  };
  const { retryAttempt, scheduleRetry, resetRetry } = useImageRetry();
  const onCoverError = (event?: Event) => {
    const img = event?.target instanceof HTMLImageElement ? event.target : null;
    if (img && !img.getAttribute("src")) return;
    if (scheduleRetry()) return;
    loaded.value = true;
  };
  return { loaded, markCoverSettled, onCoverError, retryAttempt, resetRetry };
}
