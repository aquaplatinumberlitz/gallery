import type { FileNode } from "../types";
import { getImageUrl, getThumbnailUrl } from "../services/api";

const LIGHTBOX_THUMBNAIL_SIZE = 2400;

export type LightboxDimensions = {
  width: number;
  height: number;
  source: "scan" | "thumbnail" | "metadata" | "fallback";
};

export type PhotoSwipeImageItem = {
  src: string;
  msrc?: string;
  width: number;
  height: number;
  alt: string;
  path: string;
};

export function hasValidDimensions(
  dimensions: { width?: number | null; height?: number | null } | null | undefined
): dimensions is { width: number; height: number } {
  return (
    typeof dimensions?.width === "number" &&
    dimensions.width > 0 &&
    typeof dimensions.height === "number" &&
    dimensions.height > 0
  );
}

/**
 * Shared helper to build a PhotoSwipe item from a FileNode.
 *
 * Uses real image dimensions (item.width / item.height) when available
 * from the backend scan. Falls back to a neutral 1200×1200 square
 * (no portrait/landscape bias) only when metadata is missing.
 *
 * @param item - The FileNode to build a PhotoSwipe item for
 * @param resolvedDimensions - Pre-resolved dimensions to use (width/height)
 */
export function buildPhotoSwipeItem(
  item: FileNode,
  resolvedDimensions?: LightboxDimensions | null
): PhotoSwipeImageItem {
  const src = getImageUrl(item.path);
  const msrc = getThumbnailUrl(item.path, LIGHTBOX_THUMBNAIL_SIZE);

  // PhotoSwipe requires dimensions up front. Use the best known ratio, then
  // let the resolver refresh the item when async metadata arrives.
  const width = resolvedDimensions?.width ?? 1200;
  const height = resolvedDimensions?.height ?? 1200;

  return {
    src,
    msrc,
    width,
    height,
    alt: item.name || "",
    path: item.path,
  };
}
