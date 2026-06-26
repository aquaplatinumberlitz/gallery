#!/usr/bin/env node
/** Enforce Vitest V8 coverage thresholds. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const summaryPath = resolve(__dirname, "../coverage/vitest/coverage-summary.json");
// Phase 3 target thresholds (not yet reachable — see plan status note).
// Updated from current baseline as coverage improves.
const thresholds = {
  lines: 21,
  statements: 20,
  functions: 15,
  branches: 15,
};

let summary;
try {
  summary = JSON.parse(readFileSync(summaryPath, "utf-8"));
} catch {
  console.error("No coverage summary found. Run `pnpm test:unit:coverage` first.");
  process.exit(1);
}

const total = summary.total;
let failed = false;
for (const [metric, required] of Object.entries(thresholds)) {
  const actual = total[metric]?.pct ?? 0;
  const ok = actual >= required;
  console.log(`  ${metric.padEnd(10)} ${ok ? "✓" : "✗"} ${String(actual).padStart(5)}% (required ${required}%)`);
  if (!ok) failed = true;
}

if (failed) {
  console.error("\nCoverage thresholds not met.");
  process.exit(1);
}
console.log("\nAll coverage thresholds met.");
