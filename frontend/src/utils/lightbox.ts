import type { FileNode } from "../types";
import { getImageUrl, getThumbnailUrl } from "../services/api";

const LIGHTBOX_THUMBNAIL_SIZE = 2400;

/**
 * Shared helper to build a PhotoSwipe item from a FileNode.
 *
 * Uses real image dimensions (item.width / item.height) when available
 * from the backend scan. Falls back to a neutral 1200×1200 square
 * (no portrait/landscape bias) only when metadata is missing.
 *
 * @param item - The FileNode to build a PhotoSwipe item for
 * @param thumbnailSize - If provided, use thumbnail URL at this size; otherwise use full-res image
 */
export function buildPhotoSwipeItem(
  item: FileNode,
  thumbnailSize?: number | null
): {
  src: string;
  width: number;
  height: number;
  alt: string;
  path: string;
} {
  // Use thumbnail URL if a size is specified, otherwise full-res
  const src =
    thumbnailSize != null
      ? getThumbnailUrl(item.path, LIGHTBOX_THUMBNAIL_SIZE)
      : getImageUrl(item.path);

  // Use real dimensions when valid positive numbers are available
  const width =
    typeof item.width === "number" && item.width > 0
      ? item.width
      : 1200; // defensive fallback — missing metadata

  const height =
    typeof item.height === "number" && item.height > 0
      ? item.height
      : 1200; // defensive fallback — missing metadata

  return {
    src,
    width,
    height,
    alt: item.name || "",
    path: item.path,
  };
}
