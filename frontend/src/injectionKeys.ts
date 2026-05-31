import type { InjectionKey, Ref } from "vue";

export const galleryScrollContainerRefKey: InjectionKey<Ref<HTMLElement | null>> =
  Symbol("galleryScrollContainerRef");

export const closeSidebarKey: InjectionKey<() => void> =
  Symbol("closeSidebar");
