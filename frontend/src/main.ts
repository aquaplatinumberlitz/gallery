import "./assets/fonts.css";
import "./styles/main.scss";
import "./styles/tokens.css";

// Reload BlackBox monitor — installs BEFORE Vue init to patch WebSocket
// and capture lifecycle events. Enable via ?debugReload=1.
import { installReloadBlackBoxIfEnabled } from "./debug/reloadBlackBox";
installReloadBlackBoxIfEnabled();

import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { installVueQuery } from "./query";

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

// Eruda mobile debug console (iPad Safari) — available in all builds via ?eruda=1
import("./utils/erudaDebug").then(({ initErudaDebug }) => initErudaDebug());

// Dev logging: page lifecycle debugging
if (import.meta.env.DEV) {
  window.addEventListener('pageshow', (e) => {
    console.log('[LIFECYCLE] pageshow', {
      persisted: e.persisted,
      timestamp: Date.now(),
      navType: (performance as any)?.getEntriesByType?.('navigation')?.[0]?.type
    });
  });
  window.addEventListener('pagehide', (e) => {
    console.log('[LIFECYCLE] pagehide', {
      persisted: e.persisted,
      timestamp: Date.now()
    });
  });
  window.addEventListener('beforeunload', (_e) => {
    console.log('[LIFECYCLE] beforeunload', { timestamp: Date.now() });
  });
  document.addEventListener('visibilitychange', () => {
    console.log('[LIFECYCLE] visibilitychange', {
      state: document.visibilityState,
      timestamp: Date.now()
    });
  });
  // Icon debug overlay for tablet icon sizing investigation
  import('./utils/iconDebugOverlay')
    .then(({ initIconDebugOverlay }) => initIconDebugOverlay())
    .catch((error) => {
      console.warn('[IconDebug] failed to load', error);
    });
}

app.use(createPinia());
installVueQuery(app);
app.mount("#app");
