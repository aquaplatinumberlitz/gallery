import { isIndexRebuildDebugEnabled } from "@/debug/indexRebuildDebug";

export interface IndexStatusFieldCopy {
  label: string;
  tooltip: string;
  /** API trace shown in debug mode only */
  apiTrace: string;
}

export const INDEX_FIELD_COPY: Record<string, IndexStatusFieldCopy> = {
  metadata_records: {
    label: "Photo details ready",
    tooltip: "Known indexed images with metadata ready for search and inspection.",
    apiTrace: "API: metadata_records",
  },
  indexed_photos: {
    label: "Photos found",
    tooltip: "Images found in this folder and its subfolders.",
    apiTrace: "API: indexed_photos",
  },
  done: {
    label: "Details processed",
    tooltip: "Progress reading and saving image metadata.",
    apiTrace: "API: done / total",
  },
  path: {
    label: "Folder",
    tooltip: "Current folder used for this view.",
    apiTrace: "API: path",
  },
  recursive: {
    label: "Including subfolders",
    tooltip: "",
    apiTrace: "API: recursive",
  },
};

export function getFieldCopy(field: string): IndexStatusFieldCopy {
  return INDEX_FIELD_COPY[field] ?? { label: field, tooltip: "", apiTrace: field };
}

export function getFieldTooltip(field: string): string {
  const copy = getFieldCopy(field);
  if (!copy.tooltip) return "";
  if (isIndexRebuildDebugEnabled() && copy.apiTrace) {
    return `${copy.tooltip}\n${copy.apiTrace}`;
  }
  return copy.tooltip;
}

export function getFieldLabel(field: string): string {
  return getFieldCopy(field).label;
}

export const INDEX_STATUS_LABELS: Record<string, string> = {
  unknown: "Unknown",
  ready: "Ready",
  indexing: "Updating",
  stale: "Needs update",
  warning: "Unavailable",
  error: "Error",
};
