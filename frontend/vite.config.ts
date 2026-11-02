import { defineConfig, type Plugin, type Rollup } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
import vitePluginIstanbul from "vite-plugin-istanbul";

const DEV_PORT = Number(process.env.VITE_PORT) || 4702;
const API_TARGET = process.env.VITE_API_URL || "http://localhost:4701";

// Chunk graphs that `index.html` should start downloading together with the entry instead of
// after it has executed: the gallery route (router.isReady() waits for it before mounting) and
// the layout for the current viewport. Widths mirror BREAKPOINTS in src/composables/useDevice.ts.
const EARLY_CHUNKS: Array<{ module: string; when: string }> = [
  { module: "src/components/GalleryRoute.vue", when: 'location.pathname === "/"' },
  { module: "src/layouts/MobileLayout.vue", when: "innerWidth < 768" },
  { module: "src/layouts/TabletLayout.vue", when: "innerWidth >= 768 && innerWidth < 1200" },
  { module: "src/layouts/DesktopLayout.vue", when: "innerWidth >= 1200" },
];

function earlyChunkPreload(): Plugin {
  return {
    name: "gallery-early-chunk-preload",
    apply: "build",
    transformIndexHtml: {
      order: "post",
      handler(html, ctx) {
        const bundle = ctx.bundle;
        if (!bundle) return html;
        const chunks = Object.values(bundle).filter((item): item is Rollup.OutputChunk => item.type === "chunk");
        const entry = chunks.find((chunk) => chunk.isEntry);
        const alreadyLoaded = new Set<string>(entry ? [entry.fileName, ...entry.imports] : []);
        const groups = EARLY_CHUNKS.flatMap(({ module, when }) => {
          const root = chunks.find((chunk) => chunk.facadeModuleId?.endsWith(module));
          if (!root) return [];
          const js = new Set<string>();
          const css = new Set<string>();
          const visit = (fileName: string) => {
            if (js.has(fileName) || alreadyLoaded.has(fileName)) return;
            const chunk = bundle[fileName];
            if (!chunk || chunk.type !== "chunk") return;
            js.add(fileName);
            chunk.viteMetadata?.importedCss.forEach((file) => css.add(file));
            chunk.imports.forEach(visit);
          };
          visit(root.fileName);
          return [{ when, js: [...js], css: [...css] }];
        });
        if (!groups.length) return html;
        const script = `(() => {
  const seen = new Set();
  const add = (rel, href, as) => {
    if (seen.has(href)) return;
    seen.add(href);
    const link = document.createElement("link");
    link.rel = rel;
    link.href = "/" + href;
    if (as) link.as = as;
    link.crossOrigin = "";
    document.head.appendChild(link);
  };
${groups
  .map(
    (group) =>
      `  if (${group.when}) {\n${group.js.map((file) => `    add("modulepreload", ${JSON.stringify(file)});`).join("\n")}\n${group.css
        .map((file) => `    add("preload", ${JSON.stringify(file)}, "style");`)
        .join("\n")}\n  }`,
  )
  .join("\n")}
})();`;
        return [{ tag: "script", children: script, injectTo: "head" }];
      },
    },
  };
}

const plugins = [tailwindcss(), vue(), earlyChunkPreload()];
if (process.env.VITE_COVERAGE === "true") {
  plugins.push(
    vitePluginIstanbul({
      include: ["src/**/*"],
      exclude: ["src/**/*.spec.ts", "src/debug/**"],
      extension: [".ts", ".vue"],
    }),
  );
}

export default defineConfig({
  plugins,
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "0.0.0.0",
    port: DEV_PORT,
    strictPort: true,
    allowedHosts: ["150.230.56.153"],
    hmr: process.env.VITE_MOBILE_NO_HMR === "1" ? false : undefined,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: DEV_PORT,
    strictPort: true,
  },
  build: {
    rollupOptions: {
      output: {
        // Icons are tree-shaken per component, which produced ~20 separate sub-1 KB chunks on the
        // gallery route alone; one shared chunk saves those round trips on slow mobile links.
        // Vue itself gets its own chunk: otherwise Rollup hoists the Vue runtime (a shared
        // dependency of every icon) into the icons chunk.
        manualChunks(id) {
          if (!id.includes("/node_modules/")) return undefined;
          if (id.includes("/lucide-vue-next/")) return "icons";
          if (/\/node_modules\/(\.pnpm\/[^/]+\/node_modules\/)?(vue|@vue\/[^/]+)\//.test(id)) return "vue";
          return undefined;
        },
      },
    },
  },
});
