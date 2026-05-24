import "./assets/fonts.css";
import "./styles/main.scss";
import "vue-virtual-scroller/dist/vue-virtual-scroller.css";

import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";

const app = createApp(App);

app.use(createPinia());
app.mount("#app");
