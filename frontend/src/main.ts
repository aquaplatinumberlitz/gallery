import "./assets/fonts.css";
import "./styles/tokens.css";
import "./styles/_shadcn-token-bridge.css";
import "./styles/tailwind.css";
import "./styles/main.scss";

// Reload BlackBox monitor — installs BEFORE Vue init to patch WebSocket
// and capture lifecycle events. Enable via ?debugReload=1.
import { installReloadBlackBoxIfEnabled } from "./debug/reloadBlackBox";
installReloadBlackBoxIfEnabled();

import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { installVueQuery } from "./query";
import { router } from "./router";

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
app.mount("#app");
