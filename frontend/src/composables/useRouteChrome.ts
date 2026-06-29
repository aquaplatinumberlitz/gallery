import { computed } from "vue";
import { useRoute } from "vue-router";

export type RouteChromeSection = "gallery" | "metadata" | "admin";
export type RouteChromeNav = "gallery" | "metadata" | "libraries" | "maintenance";

const ROUTE_CHROME_SECTIONS = new Set<RouteChromeSection>(["gallery", "metadata", "admin"]);
const ROUTE_CHROME_NAV_ITEMS = new Set<RouteChromeNav>(["gallery", "metadata", "libraries", "maintenance"]);

export function useRouteChrome() {
  const route = useRoute();

  const section = computed<RouteChromeSection>(() => {
    const value = route.meta.chromeSection;
    return ROUTE_CHROME_SECTIONS.has(value as RouteChromeSection) ? (value as RouteChromeSection) : "gallery";
  });

  const pageTitle = computed(() => (typeof route.meta.pageTitle === "string" ? route.meta.pageTitle : "Gallery"));
  const activeNav = computed<RouteChromeNav>(() => {
    const value = route.meta.chromeNav;
    if (ROUTE_CHROME_NAV_ITEMS.has(value as RouteChromeNav)) return value as RouteChromeNav;
    if (section.value === "metadata") return "metadata";
    if (section.value === "admin") return "libraries";
    return "gallery";
  });
  const isGalleryRoute = computed(() => section.value === "gallery");
  const isMetadataRoute = computed(() => section.value === "metadata");
  const isAdminRoute = computed(() => section.value === "admin");
  const showBackToGallery = computed(() => Boolean(route.meta.showBackToGallery));

  return {
    section,
    activeNav,
    pageTitle,
    isGalleryRoute,
    isMetadataRoute,
    isAdminRoute,
    showBackToGallery,
  };
}
