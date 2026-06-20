import { createRouter, createWebHistory } from "vue-router";

const GalleryRoute = () => import("@/components/GalleryRoute.vue");
const loadLibraryInspector = () => import("@/components/LibraryInspector.vue");
const LibraryInspector = loadLibraryInspector;
const loadLibraryListPage = () => import("@/components/admin/LibraryListPage.vue");
const loadLibraryDetailPage = () => import("@/components/admin/LibraryDetailPage.vue");

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
    },
    {
      path: "/metadata",
      name: "metadata",
      component: LibraryInspector,
    },
    {
      path: "/admin/libraries",
      name: "admin-libraries",
      component: loadLibraryListPage,
    },
    {
      path: "/admin/libraries/:id",
      name: "admin-library-detail",
      component: loadLibraryDetailPage,
      props: (route) => ({ id: Number(route.params.id) }),
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/",
    },
  ],
});
