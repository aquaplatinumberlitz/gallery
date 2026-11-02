import "./assets/fonts.css";
import "./styles/tokens.css";
import "./styles/_shadcn-token-bridge.css";
import "./styles/tailwind.css";
import "./styles/main.scss";

import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { installVueQuery, queryClient } from "./query";
import { queryKeys } from "./query/keys";
import { fetchLibraries } from "./services/api";
import { router } from "./router";
import type { RegisteredLibrary } from "./types";
import { startHomeBrowsePrefetch } from "./utils/homeBrowsePrefetch";
import { BREAKPOINTS } from "./composables/useDevice";

// Reload BlackBox monitor — installs BEFORE Vue init to patch WebSocket
// and capture lifecycle events. Enable via ?debugReload=1 or the persisted
// GALLERY_DEBUG_RELOAD flag. The module is only downloaded when one of them is set.
function reloadBlackBoxRequested(): boolean {
  if (new URLSearchParams(window.location.search).has("debugReload")) return true;
  try {
    return localStorage.getItem("GALLERY_DEBUG_RELOAD") !== null;
  } catch {
    return false;
  }
}

const reloadBlackBoxReady: Promise<void> = reloadBlackBoxRequested()
  ? import("./debug/reloadBlackBox").then(({ installReloadBlackBoxIfEnabled }) => installReloadBlackBoxIfEnabled())
  : Promise.resolve();

// Start the first network work while the router still resolves the lazy route chunk.
// The library list is needed by every screen; the layout chunk for this viewport is
// the next thing App renders. Both previously waited until the route chunk tree had
// loaded and the app had mounted. Same query key/fn and module specifiers as their
// consumers, so TanStack Query and the module cache dedupe them.
const librariesReady = queryClient.prefetchQuery({ queryKey: queryKeys.libraries(), queryFn: fetchLibraries });
// The root browse page (and first cover) of the library the gallery opens on follows as soon as the list is
// known, before the route chunks have loaded and the app has mounted. Best effort; see homeBrowsePrefetch.ts.
void startHomeBrowsePrefetch(queryClient, librariesReady, () =>
  queryClient.getQueryData<RegisteredLibrary[]>(queryKeys.libraries()),
);
const viewportWidth = window.innerWidth;
void (
  viewportWidth < BREAKPOINTS.mobile
    ? import("./layouts/MobileLayout.vue")
    : viewportWidth < BREAKPOINTS.desktop
      ? import("./layouts/TabletLayout.vue")
      : import("./layouts/DesktopLayout.vue")
).catch(() => undefined);

const app = createApp(App);

app.config.errorHandler = (err, _instance, info) => {
  console.error("[APP] Unhandled Vue error:", err, { info });
};

if (typeof window !== "undefined") {
  window.addEventListener("unhandledrejection", (event) => {
    console.error("[APP] Unhandled promise rejection:", event.reason);
  });

  window.addEventListener("error", (event) => {
    if (event.error) {
      console.error("[APP] Unhandled error:", event.error);
    }
  });
}

// Eruda mobile debug console — bật lại
import("./debug/erudaDebug").then(({ initErudaDebug }) => initErudaDebug());

// Dev logging: page lifecycle debugging
// NOTE: Do NOT add beforeunload or unload listeners here — they block bfcache
// on iOS Safari and cause page discards when the user switches apps/tabs.
// pagehide + visibilitychange + freeze/resume cover all lifecycle states safely.
if (import.meta.env.DEV) {
  import("./debug/lifecycleDebug").then(({ installLifecycleDebug }) => installLifecycleDebug());
  // Icon debug overlay for tablet icon sizing investigation
  import("./debug/iconDebugOverlay")
    .then(({ initIconDebugOverlay }) => initIconDebugOverlay())
    .catch((error) => {
      console.warn("[IconDebug] failed to load", error);
    });
}

app.use(createPinia());
app.use(router);
installVueQuery(app);

// Resolve the browser's initial URL before App setup reads route metadata.
// Otherwise a hard reload on a lazy route can briefly render the gallery intro.
Promise.all([router.isReady(), reloadBlackBoxReady]).then(() => {
  app.mount("#app");
});
