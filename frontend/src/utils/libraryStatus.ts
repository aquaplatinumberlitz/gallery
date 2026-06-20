import type { LibraryProgress, LibraryState, RegisteredLibrary } from "@/types";

export type LibraryStatusVariant = "default" | "secondary" | "destructive" | "outline";

export interface LibraryStatusPresentation {
  label: string;
  variant: LibraryStatusVariant;
  meaning: string;
}

const STATUS_PRESENTATIONS: Record<LibraryState | "unknown", LibraryStatusPresentation> = {
  queued: { label: "Queued", variant: "secondary", meaning: "Waiting for library processing to start." },
  discovering: { label: "Discovering", variant: "secondary", meaning: "Finding assets in the library paths." },
  indexing: { label: "Indexing", variant: "secondary", meaning: "Extracting and indexing asset metadata." },
  ready: { label: "Ready", variant: "default", meaning: "The library is available and up to date." },
  offline: { label: "Offline", variant: "destructive", meaning: "One or more library paths are unavailable." },
  error: { label: "Error", variant: "destructive", meaning: "Library processing failed." },
  unknown: { label: "Unknown", variant: "outline", meaning: "The library status is unavailable." },
};

export function isLibraryBusy(state: LibraryState | string | null | undefined): boolean {
  return state === "queued" || state === "discovering" || state === "indexing";
}

export function getLibraryStatusPresentation(
  library: Pick<RegisteredLibrary, "state"> | null | undefined,
  progress?: Pick<LibraryProgress, "library_state"> | null,
): LibraryStatusPresentation {
  const state = progress?.library_state ?? library?.state ?? "unknown";
  return STATUS_PRESENTATIONS[state as LibraryState] ?? STATUS_PRESENTATIONS.unknown;
}

export function getLibraryProgressPercent(progress: LibraryProgress | null | undefined): number {
  if (!progress) return 0;
  if (progress.estimated_assets <= 0) return progress.discovery_complete ? 100 : 0;
  return Math.min(100, Math.max(0, Math.round((progress.indexed_assets / progress.estimated_assets) * 100)));
}

export function formatLibraryTimestamp(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Never";
  const date = new Date(typeof value === "number" ? value * 1_000 : value);
  return Number.isNaN(date.getTime())
    ? "Unknown"
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function formatAssetCount(value: number | null | undefined): string {
  return new Intl.NumberFormat().format(Math.max(0, value ?? 0));
}
