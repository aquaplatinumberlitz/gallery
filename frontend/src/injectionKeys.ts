import type { InjectionKey, Ref } from "vue";

export const galleryScrollContainerRefKey: InjectionKey<Ref<HTMLElement | null>> = Symbol("galleryScrollContainerRef");

/** Opens the app-level Settings dialog from nested chrome (e.g. the mobile/tablet sidebar). */
export const openSettingsKey: InjectionKey<() => void> = Symbol("openSettings");
