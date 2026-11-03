import type { SearchIndexStateV1 } from "../types";

/** Derived indexes the Maintenance pipeline note reports on, in display order. */
const NOTE_INDEXES = [
  { indexName: "prompt_values", label: "prompt groups" },
  { indexName: "workflow_properties", label: "workflow fields" },
] as const;

type NoteState = "failed" | "building" | "pending" | "degraded" | "ready";

function aggregateState(rows: readonly SearchIndexStateV1[]): NoteState {
  if (rows.some((row) => row.state === "failed")) return "failed";
  if (rows.some((row) => row.state === "building")) return "building";
  if (rows.some((row) => row.state === "pending")) return "pending";
  if (rows.some((row) => row.state === "degraded")) return "degraded";
  return "ready";
}

function buildingPercent(rows: readonly SearchIndexStateV1[]): number | null {
  const building = rows.filter((row) => row.state === "building");
  const target = building.reduce((sum, row) => sum + row.target_count, 0);
  if (target <= 0) return null;
  const done = building.reduce((sum, row) => sum + row.indexed_count + row.skipped_count + row.failed_count, 0);
  return Math.min(99, Math.floor((100 * done) / target));
}

function describe(rows: readonly SearchIndexStateV1[]): string {
  const state = aggregateState(rows);
  switch (state) {
    case "building": {
      const percent = buildingPercent(rows);
      return percent === null ? "building" : `building ${percent} %`;
    }
    case "pending":
      return "waiting to start";
    case "degraded":
      return "needs a rebuild";
    case "failed":
      return "failed";
    default:
      return "ready";
  }
}

/**
 * One-line state of the derived search indexes across all libraries, for the unnumbered note under the
 * Maintenance pipeline, for example "Search indexes: prompt groups ready, workflow fields building 40 %".
 * Returns `null` when no enabled prompt/workflow index row exists (nothing to report yet).
 */
export function summarizeDerivedSearchIndexes(rows: readonly SearchIndexStateV1[] | null | undefined): string | null {
  if (!rows?.length) return null;
  const parts: string[] = [];
  for (const { indexName, label } of NOTE_INDEXES) {
    const indexRows = rows.filter((row) => row.index_name === indexName && row.enabled && row.state !== "disabled");
    if (!indexRows.length) continue;
    parts.push(`${label} ${describe(indexRows)}`);
  }
  return parts.length ? `Search indexes: ${parts.join(", ")}` : null;
}
