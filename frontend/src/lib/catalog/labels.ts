import type { SummaryState } from "./status";

export interface CatalogStatusPresentation {
  label: string;
  /** shadcn-style Badge variant for admin status pills. */
  variant: "default" | "secondary" | "destructive" | "outline";
  /** sidebar badge color tone for IndexStatusBadge. */
  tone: "green" | "yellow" | "red" | "gray";
  showPulse: boolean;
  meaning: string;
}

const PRESENTATIONS: Record<SummaryState, CatalogStatusPresentation> = {
  unknown: {
    label: "Unknown",
    variant: "outline",
    tone: "gray",
    showPulse: false,
    meaning: "The library status is unavailable.",
  },
  offline: {
    label: "Offline",
    variant: "destructive",
    tone: "gray",
    showPulse: false,
    meaning: "All configured import paths are unavailable.",
  },
  needs_scan: {
    label: "Needs scan",
    variant: "secondary",
    tone: "yellow",
    showPulse: false,
    meaning: "This scope has not been scanned yet.",
  },
  scanning: {
    label: "Scanning",
    variant: "secondary",
    tone: "yellow",
    showPulse: true,
    meaning: "Catalog discovery is running.",
  },
  indexing: {
    label: "Updating",
    variant: "secondary",
    tone: "yellow",
    showPulse: true,
    meaning: "Metadata extraction is in progress.",
  },
  needs_update: {
    label: "Needs update",
    variant: "secondary",
    tone: "yellow",
    showPulse: false,
    meaning: "Pending metadata work without active extraction.",
  },
  ready_with_issues: {
    label: "Ready with issues",
    variant: "default",
    tone: "yellow",
    showPulse: false,
    meaning: "Catalog is usable but unresolved issues remain.",
  },
  ready: {
    label: "Ready",
    variant: "default",
    tone: "green",
    showPulse: false,
    meaning: "The scope is available and up to date.",
  },
  error: {
    label: "Error",
    variant: "destructive",
    tone: "red",
    showPulse: false,
    meaning: "Catalog work failed and no usable result is available.",
  },
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
