import "./assets/fonts.css";
import "./styles/main.scss";
import "./styles/tokens.css";
import "vue-virtual-scroller/dist/vue-virtual-scroller.css";

import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";

// Dev logging: page lifecycle debugging
if (import.meta.env.DEV || true) {
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
}

const app = createApp(App);

app.use(createPinia());
app.mount("#app");
