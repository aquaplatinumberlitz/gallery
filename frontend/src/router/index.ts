import { createRouter, createWebHistory } from "vue-router";

const GalleryRoute = () => import("@/components/GalleryRoute.vue");
const loadLibraryInspector = () => import("@/components/LibraryInspector.vue");
const LibraryInspector = loadLibraryInspector;

let metadataRoutePrefetch: Promise<unknown> | null = null;

export function prefetchMetadataRoute() {
  metadataRoutePrefetch ??= loadLibraryInspector();
  return metadataRoutePrefetch;
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
      path: "/:pathMatch(.*)*",
      redirect: "/",
    },
  ],
});
