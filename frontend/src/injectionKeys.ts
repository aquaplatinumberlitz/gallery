import type { InjectionKey, Ref } from "vue";

export const galleryScrollContainerRefKey: InjectionKey<Ref<HTMLElement | null>> =
  Symbol("galleryScrollContainerRef");
