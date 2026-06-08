import "./assets/fonts.css";
import "./styles/main.scss";
import "./styles/tokens.css";

import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { installVueQuery } from "./query";

const app = createApp(App);

// Dev logging: page lifecycle debugging
if (import.meta.env.DEV) {
  // Eruda mobile debug console (iPad Safari)
  import("./utils/erudaDebug").then(({ initErudaDebug }) => initErudaDebug());
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
  // Vue Query Devtools
  import('@tanstack/vue-query-devtools').then(({ VueQueryDevtools }) => {
    app.component('VueQueryDevTools', VueQueryDevtools)
  })
}

app.use(createPinia());
installVueQuery(app);
app.mount("#app");
