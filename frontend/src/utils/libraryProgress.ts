import type { UnifiedStatus } from "@/lib/catalog/status";
import { formatAssetCount } from "@/utils/libraryStatus";

function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return count === 1 ? singular : plural;
}

export function isCatalogUpdating(status: UnifiedStatus | null | undefined): boolean {
  return status?.scan.state === "queued" || status?.scan.state === "scanning";
}

export function formatCatalogProgressLabel(status: UnifiedStatus): string | null {
  if (!isCatalogUpdating(status)) return null;

  const total = status.scan.total_units;
  if (typeof total === "number" && total > 0) {
    return `Scanning ${formatAssetCount(total)} ${pluralize(total, "folder")}`;
  }
  return "Scanning folders";
}

export function formatMetadataReadyLabel(status: UnifiedStatus, options: { completeLabel?: boolean } = {}): string {
  const ready = status.metadata.ready_assets ?? 0;
  const total = status.metadata.total_assets ?? 0;
  const failed = status.metadata.failed_assets ?? 0;

  if (total === 0) return failed > 0 ? `${formatAssetCount(failed)} failed` : "No photos";
  if (options.completeLabel && ready >= total) return "All metadata ready";
  return `${formatAssetCount(ready)} / ${formatAssetCount(total)} metadata ready`;
}

export function formatLibraryProgressLabel(status: UnifiedStatus, options: { completeLabel?: boolean } = {}): string {
  return formatCatalogProgressLabel(status) ?? formatMetadataReadyLabel(status, options);
}
