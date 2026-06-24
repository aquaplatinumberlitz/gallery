import { computed } from "vue";
import { useWindowSize } from "@vueuse/core";

// Source-of-truth breakpoints — also exists as SCSS vars in _breakpoints.scss
export const BREAKPOINTS = {
  compact: 480,
  mobile: 768,
  desktop: 1200,
  wide: 1440,
} as const;

type Breakpoint = "compact" | "mobile" | "tablet" | "desktop" | "wide";

export function useDevice() {
  const { width } = useWindowSize();

  const breakpoint = computed<Breakpoint>(() => {
    const w = width.value;
    if (w < BREAKPOINTS.compact) return "compact";
    if (w < BREAKPOINTS.mobile) return "mobile";
    if (w < BREAKPOINTS.desktop) return "tablet";
    if (w < BREAKPOINTS.wide) return "desktop";
    return "wide";
  });

  const isCompact = computed(() => breakpoint.value === "compact");
  const isMobileOnly = computed(() => breakpoint.value === "mobile");
  const isTablet = computed(() => breakpoint.value === "tablet");
  const isDesktop = computed(() => breakpoint.value === "desktop");
  const isWide = computed(() => breakpoint.value === "wide");
  const isMobile = computed(() => isCompact.value || isMobileOnly.value);
  const isLargeScreen = computed(() => isTablet.value || isDesktop.value || isWide.value);

  return { breakpoint, isCompact, isMobileOnly, isTablet, isDesktop, isWide, isMobile, isLargeScreen };
}
