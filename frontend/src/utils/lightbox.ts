import type { FileNode } from "../types";
import { getPreviewUrl, getThumbnailUrl } from "../services/api";

export const LIGHTBOX_THUMBNAIL_EDGE = 512;
export const LIGHTBOX_PREVIEW_EDGE = 1440;
export const LIGHTBOX_ORIGINAL_ZOOM_THRESHOLD = 1.2;
export const LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY = "gallery-lightbox-always-load-original";

export type LightboxDimensions = {
  width: number;
  height: number;
  source: "scan" | "thumbnail" | "metadata" | "fallback";
};

export type PhotoSwipeImageItem = {
  src: string;
  previewSrc: string;
  msrc?: string;
  width: number;
  height: number;
  alt: string;
  path: string;
  isAnimatedAsset: boolean;
  isOriginalLoaded?: boolean;
  originalLoadReason?: "zoom" | "preference" | "fullscreen" | "animated" | "fallback";
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

export function shouldAlwaysLoadOriginal(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY) === "true";
  } catch {
    return false;
  }
}

export function isLikelyAnimatedAsset(pathOrName: string): boolean {
  const ext = pathOrName.split("?")[0]?.split("#")[0]?.split(".").pop()?.toLowerCase();
  // TODO: Detect animated WebP by container metadata instead of treating every .webp as animated.
  return ext === "gif" || ext === "apng";
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
  const previewSrc = getPreviewUrl(item.path, LIGHTBOX_PREVIEW_EDGE);
  const msrc = getThumbnailUrl(item.path, LIGHTBOX_THUMBNAIL_EDGE);

  const width = resolvedDimensions?.width ?? 1200;
  const height = resolvedDimensions?.height ?? 1200;
  const isAnimatedAsset = isLikelyAnimatedAsset(item.path || item.name || "");

  return {
    src: previewSrc,
    previewSrc,
    msrc,
    width,
    height,
    alt: item.name || "",
    path: item.path,
    isAnimatedAsset,
  };
}
