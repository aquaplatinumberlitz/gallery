#!/usr/bin/env node
/** Enforce Vitest V8 coverage thresholds. */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const summaryPath = resolve(__dirname, "../coverage/vitest/coverage-summary.json");
// Measured 2026-07-15 baseline, rounded down to whole-percent ratchets.
const thresholds = {
  lines: 70,
  statements: 68,
  functions: 62,
  branches: 57,
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

// Aggregate per-directory coverage from per-file entries.
function aggregateArea(prefix) {
  let totalLines = 0,
    coveredLines = 0;
  for (const [file, metrics] of Object.entries(summary)) {
    if (metrics.lines && file.includes(`/${prefix}/`)) {
      totalLines += metrics.lines.total;
      coveredLines += metrics.lines.covered;
    }
  }
  if (totalLines === 0) return null;
  return (coveredLines / totalLines) * 100;
}

// Same measured baseline policy for high-value areas. These are hard ratchets,
// not generic industry targets; raise them only after adding durable coverage.
const areaThresholds = {
  "src/services": 91,
  "src/stores": 91,
  "src/utils": 93,
  "src/lib/catalog": 97,
  "src/query": 95,
  "src/composables": 89,
  "src/components": 60,
};

console.log("\nPer-area coverage (enforced ratchets):");
for (const [area, required] of Object.entries(areaThresholds)) {
  const pct = aggregateArea(area);
  if (pct === null) {
    console.log(`  ${area.padEnd(25)} — no data (area not found in summary)`);
    continue;
  }
  const ok = pct >= required;
  if (!ok) failed = true;
  console.log(
    `  ${area.padEnd(25)} ${ok ? "✓" : "✗"} ${String(pct.toFixed(1)).padStart(5)}% lines (required ${required}%)`,
  );
}

if (failed) {
  console.error("\nCoverage thresholds not met.");
  process.exit(1);
}
console.log("\nAll coverage thresholds met.");
