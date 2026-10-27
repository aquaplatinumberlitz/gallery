import { ref } from "vue";

/**
 * Tracks whether an album cover image has settled so the card can hide its loading skeleton.
 *
 * Both a successful load and a load error count as settled: a broken cover must not leave the
 * shimmer running forever.
 */
export function useCoverImageLoad() {
  const loaded = ref(false);
  const markCoverSettled = () => {
    loaded.value = true;
  };
  return { loaded, markCoverSettled };
}
