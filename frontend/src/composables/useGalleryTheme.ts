import { computed } from "vue";
import { useColorMode } from "@vueuse/core";

export type GalleryThemeMode = "light" | "dark" | "system";
export type GalleryResolvedTheme = "light" | "dark";

function applyWithTransition(fn: () => void) {
  if (typeof window === "undefined") {
    fn();
    return;
  }
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (prefersReduced) {
    fn();
    return;
  }
  if ("startViewTransition" in document) {
    document.startViewTransition?.(fn);
    return;
  }
  window.document.documentElement.classList.add("theme-transitioning");
  fn();
  setTimeout(() => {
    window.document.documentElement.classList.remove("theme-transitioning");
  }, 200);
}

export function useGalleryTheme() {
  const colorMode = useColorMode({
    selector: "html",
    attribute: "data-theme",
    modes: {
      light: "light",
      dark: "dark",
    },
    storageKey: "gallery-theme",
    initialValue: "auto",
    disableTransition: false,
  });

  const mode = computed<GalleryThemeMode>({
    get: () => (colorMode.store.value === "auto" ? "system" : (colorMode.store.value as "light" | "dark")),
    set: (next) => {
      colorMode.store.value = next === "system" ? "auto" : next;
    },
  });

  const resolvedTheme = computed<GalleryResolvedTheme>(() => colorMode.state.value as GalleryResolvedTheme);

  const systemTheme = computed<GalleryResolvedTheme>(() => colorMode.system.value);

  const isDark = computed(() => resolvedTheme.value === "dark");

  function setTheme(next: GalleryThemeMode) {
    applyWithTransition(() => {
      mode.value = next;
    });
  }

  function toggleTheme() {
    applyWithTransition(() => {
      const next = resolvedTheme.value === "dark" ? "light" : "dark";
      colorMode.store.value = next;
    });
  }

  function cycleTheme() {
    const order: GalleryThemeMode[] = ["light", "dark", "system"];
    const current = mode.value;
    const idx = order.indexOf(current);
    setTheme(order[(idx + 1) % order.length]);
  }

  return { mode, resolvedTheme, systemTheme, isDark, setTheme, toggleTheme, cycleTheme };
}
