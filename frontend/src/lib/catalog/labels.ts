import type { MetadataState, SummaryState } from "./status";
import { formatAssetCount } from "@/utils/libraryStatus";

export const METADATA_READY_WITH_ISSUES_LABEL = "Ready with issues";

/**
 * A metadata stage with `state === "failed"` is only "failed" when nothing is
 * ready. The backend marks the whole stage failed when any asset is unreadable,
 * so a stage with ready assets reads as "Ready with issues" (amber).
 */
export function isMetadataReadyWithIssues(metadata: {
  state: MetadataState;
  ready_assets: number | null | undefined;
}): boolean {
  return metadata.state === "failed" && (metadata.ready_assets ?? 0) > 0;
}

export function formatMetadataUnreadableDetail(ready: number, unreadable: number): string {
  return `${formatAssetCount(ready)} ready · ${formatAssetCount(unreadable)} can't be read`;
}

export interface CatalogStatusPresentation {
  label: string;
  /** shadcn-style Badge variant for admin status pills. */
  variant: "default" | "secondary" | "destructive" | "outline";
  /** sidebar badge color tone for IndexStatusBadge. */
  tone: "green" | "yellow" | "red" | "gray";
  /** Kibo-style indicator color used inside status pills and icon-only status dots. */
  indicator: "success" | "warning" | "error" | "muted";
  showPulse: boolean;
  meaning: string;
}

const PRESENTATIONS: Record<SummaryState, CatalogStatusPresentation> = {
  unknown: {
    label: "Unknown",
    variant: "outline",
    tone: "gray",
    indicator: "muted",
    showPulse: false,
    meaning: "The library status is unavailable.",
  },
  offline: {
    label: "Offline",
    variant: "destructive",
    tone: "gray",
    indicator: "muted",
    showPulse: false,
    meaning: "All configured import paths are unavailable.",
  },
  needs_scan: {
    label: "Needs update",
    variant: "secondary",
    tone: "yellow",
    indicator: "warning",
    showPulse: false,
    meaning: "This scope has not been updated yet.",
  },
  scanning: {
    label: "Updating",
    variant: "secondary",
    tone: "yellow",
    indicator: "warning",
    showPulse: true,
    meaning: "Catalog discovery is running.",
  },
  indexing: {
    label: "Updating",
    variant: "secondary",
    tone: "yellow",
    indicator: "warning",
    showPulse: true,
    meaning: "Metadata extraction is in progress.",
  },
  needs_update: {
    label: "Needs update",
    variant: "secondary",
    tone: "yellow",
    indicator: "warning",
    showPulse: false,
    meaning: "Pending metadata work without active extraction.",
  },
  ready_with_issues: {
    label: METADATA_READY_WITH_ISSUES_LABEL,
    variant: "default",
    tone: "yellow",
    indicator: "warning",
    showPulse: false,
    meaning: "Catalog is usable but unresolved issues remain.",
  },
  ready: {
    label: "Ready",
    variant: "default",
    tone: "green",
    indicator: "success",
    showPulse: true,
    meaning: "The scope is available and up to date.",
  },
  error: {
    label: "Error",
    variant: "destructive",
    tone: "red",
    indicator: "error",
    showPulse: false,
    meaning: "Catalog work failed and no usable result is available.",
  },
};

export const CATALOG_STATUS_UNAVAILABLE_PRESENTATION: CatalogStatusPresentation = {
  label: "Unavailable",
  variant: "destructive",
  tone: "red",
  indicator: "error",
  showPulse: false,
  meaning: "The app cannot reach the server to refresh catalog status.",
};

export function getCatalogStatusPresentation(state: SummaryState | null | undefined): CatalogStatusPresentation {
  if (!state) return PRESENTATIONS.unknown;
  return PRESENTATIONS[state] ?? PRESENTATIONS.unknown;
}

export const CATALOG_STATUS_LABELS: Record<SummaryState, string> = Object.fromEntries(
  (Object.keys(PRESENTATIONS) as SummaryState[]).map((state) => [state, PRESENTATIONS[state].label]),
) as Record<SummaryState, string>;

export function getCatalogStatusLabel(state: SummaryState | null | undefined): string {
  return getCatalogStatusPresentation(state).label;
}
