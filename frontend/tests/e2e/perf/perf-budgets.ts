/**
 * Typed accessor for the shared perf budgets JSON.
 *
 * The JSON file (`perf-budgets.json`) is the single source of truth for the
 * Playwright perf specs and mirrors `scripts/perf_budgets.toml`. We load it via
 * `fs.readFileSync` so the JSON stays the single source of truth and we don't
 * depend on per-tool JSON-module resolution. The validator
 * `scripts/check_perf_budgets.py` checks that the JSON stays in sync with the
 * TOML, so updating the JSON is enough.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const raw = JSON.parse(readFileSync(join(here, "perf-budgets.json"), "utf-8")) as {
  album_open: { scan_p95_ms: number; first_thumbnail_ms: number; thumbnail_p95_ms: number };
  lightbox: { open_ms: number; transition_ms: number; preview_check_ms: number };
  metadata_nav: {
    nav_ms: number;
    render_ms: number;
    search_debounce_ms: number;
    state_restore_ms: number;
  };
};

export const perfBudgets = {
  album_open: raw.album_open,
  lightbox: raw.lightbox,
  metadata_nav: raw.metadata_nav,
};
