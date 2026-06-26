#!/usr/bin/env node
/** Enforce Vitest V8 coverage thresholds. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const summaryPath = resolve(__dirname, "../coverage/vitest/coverage-summary.json");
// Ratchet thresholds — raised as F5-F7 coverage lands. Final target: 90/90/85/80.
const thresholds = {
  lines: 50,
  statements: 49,
  functions: 40,
  branches: 35,
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

let overallFailed = failed;

// Aggregate per-directory coverage from per-file entries.
function aggregateArea(prefix) {
  let totalLines = 0, coveredLines = 0;
  const search = prefix.includes(":/") ? prefix : prefix;
  for (const [file, metrics] of Object.entries(summary)) {
    if (metrics.lines && file.includes(`/${prefix}/`)) {
      totalLines += metrics.lines.total;
      coveredLines += metrics.lines.covered;
    }
  }
  if (totalLines === 0) return null;
  return (coveredLines / totalLines) * 100;
}

// Per-area soft checks (warn-only — do not block CI).
const areaThresholds = {
  "src/services": 90,
  "src/stores": 90,
  "src/utils": 90,
  "src/lib/catalog": 90,
  "src/query": 90,
  "src/composables": 80,
  "src/components": 80,
};

let anyAreaBelow = false;
console.log("\nPer-area coverage (soft checks):");
for (const [area, required] of Object.entries(areaThresholds)) {
  const pct = aggregateArea(area);
  if (pct === null) {
    console.log(`  ${area.padEnd(25)} — no data (area not found in summary)`);
    continue;
  }
  const ok = pct >= required;
  if (!ok) anyAreaBelow = true;
  console.log(`  ${area.padEnd(25)} ${ok ? "✓" : "✗"} ${String(pct.toFixed(1)).padStart(5)}% lines (suggested ${required}%)`);
}

if (anyAreaBelow) {
  console.warn("\n⚠ Some areas are below suggested thresholds. Consider adding tests.");
}

if (overallFailed) {
  console.error("\nCoverage thresholds not met.");
  process.exit(1);
}
console.log("\nAll coverage thresholds met.");
