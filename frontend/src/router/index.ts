import { createRouter, createWebHistory } from "vue-router";
import type { RouteChromeNav, RouteChromeSection } from "@/composables/useRouteChrome";

declare module "vue-router" {
  interface RouteMeta {
    chromeSection?: RouteChromeSection;
    chromeNav?: RouteChromeNav;
    pageTitle?: string;
    showBackToGallery?: boolean;
  }
}

const GalleryRoute = () => import("@/components/GalleryRoute.vue");
const loadLibraryInspector = () => import("@/components/LibraryInspector.vue");
const LibraryInspector = loadLibraryInspector;
const loadLibraryListPage = () => import("@/components/admin/LibraryListPage.vue");
const loadLibraryDetailPage = () => import("@/components/admin/LibraryDetailPage.vue");
const loadMaintenancePage = () => import("@/components/admin/MaintenancePage.vue");

let metadataRoutePrefetch: Promise<unknown> | null = null;
let librariesRoutePrefetch: Promise<unknown> | null = null;

export function prefetchMetadataRoute() {
  metadataRoutePrefetch ??= loadLibraryInspector();
  return metadataRoutePrefetch;
}

export function prefetchLibrariesRoute() {
  librariesRoutePrefetch ??= loadLibraryListPage();
  return librariesRoutePrefetch;
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "gallery",
      component: GalleryRoute,
      meta: { chromeSection: "gallery", chromeNav: "gallery", pageTitle: "Gallery", showBackToGallery: false },
    },
    {
      path: "/metadata",
      name: "metadata",
      component: LibraryInspector,
      meta: { chromeSection: "metadata", chromeNav: "metadata", pageTitle: "Photo Details", showBackToGallery: true },
    },
    {
      path: "/admin/libraries",
      name: "admin-libraries",
      component: loadLibraryListPage,
      meta: {
        chromeSection: "admin",
        chromeNav: "libraries",
        pageTitle: "Library administration",
        showBackToGallery: true,
      },
    },
    {
      path: "/admin/libraries/:id",
      name: "admin-library-detail",
      component: loadLibraryDetailPage,
      props: (route) => ({ id: Number(route.params.id) }),
      meta: {
        chromeSection: "admin",
        chromeNav: "libraries",
        pageTitle: "Library administration",
        showBackToGallery: true,
      },
    },
    {
      path: "/admin/maintenance",
      name: "admin-maintenance",
      component: loadMaintenancePage,
      meta: { chromeSection: "admin", chromeNav: "maintenance", pageTitle: "Maintenance", showBackToGallery: true },
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/",
    },
  ],
});
