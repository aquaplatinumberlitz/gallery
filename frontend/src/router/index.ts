import { createRouter, createWebHistory } from "vue-router";

const GalleryRoute = () => import("@/components/GalleryRoute.vue");
const LibraryInspector = () => import("@/components/LibraryInspector.vue");

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
