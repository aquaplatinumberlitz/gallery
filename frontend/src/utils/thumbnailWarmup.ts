/**
 * Starts the thumbnail requests of the first viewport before the grid has been rendered.
 *
 * Album open is request-bound: the grid mounts about 150 ms (4x CPU) after the browse response lands, and
 * until then no `<img>` exists, so the first thumbnails only start downloading after the render. When the
 * browse data arrives, `GalleryGrid` plans the thumbnails the first viewport will request and hands them to
 * `warmThumbnails`, which adds `<link rel="preload" as="image">` elements with the same `imagesrcset` /
 * `imagesizes` / URL the `PhotoCard` `<img>` will use. The browser picks the candidate exactly as it does for
 * an `<img>`, and the card later reuses the in-flight or finished response, so nothing is downloaded twice
 * and the picture is unchanged.
 *
 * The plan only covers cards that are certain to be in view (rows that start above the viewport bottom,
 * minus an allowance for the section header and the album strip), and skips an image whose 256/512 choice
 * depends on the exact card width (the estimate is the skeleton cell, a few pixels wider than the card).
 */
import { GRID_THUMBNAIL_EDGES, getThumbnailSrcset, getThumbnailUrl } from "../services/api";
import { coverAspectRatio, thumbnailSizes } from "./thumbnailSizes";

export interface WarmupItem {
  path: string;
  type?: string;
  content_version?: string | null;
  width?: number | null;
  height?: number | null;
}

export interface WarmupGeometry {
  /** Grid columns. */
  columns: number;
  /** Estimated rendered card width in CSS px. */
  cardWidth: number;
  /** Distance between the tops of two rows (card height plus the row gap). */
  rowPitch: number;
  /** Top of the first card row in the viewport (CSS px). */
  top: number;
  viewportHeight: number;
  devicePixelRatio: number;
}

export interface WarmupTarget {
  href: string;
  imagesrcset: string;
  imagesizes: string;
  fetchpriority: "high" | "auto";
}

/** Space above the first card row that the estimate cannot see: the "Media" section header. */
export const WARMUP_HEADER_ALLOWANCE = 64;
/** The album strip sits above the media section when the folder has subfolders. */
export const WARMUP_ALBUM_STRIP_ALLOWANCE = 170;
/** The 256/512 choice must hold across this relative error of the width estimate, else the image is skipped. */
export const WARMUP_WIDTH_TOLERANCE = 0.07;
/** Upper bound for one plan, so a degenerate geometry cannot start dozens of requests. */
export const WARMUP_MAX_TARGETS = 24;

/** The candidate edge a browser picks for a slot of `slotPx` CSS px at `dpr`: the smallest one that is large enough. */
const pickEdge = (slotPx: number, dpr: number): number =>
  GRID_THUMBNAIL_EDGES.find((edge) => edge >= slotPx * dpr) ?? GRID_THUMBNAIL_EDGES[GRID_THUMBNAIL_EDGES.length - 1];

const isFinitePositive = (value: number) => Number.isFinite(value) && value > 0;

/**
 * Thumbnails the first viewport requests, in grid order. The first row gets `fetchpriority=high`, as
 * `PhotoCard` does.
 */
export function planThumbnailWarmup(
  items: readonly WarmupItem[],
  geometry: WarmupGeometry,
  options: { hasFolders?: boolean } = {},
): WarmupTarget[] {
  const { columns, cardWidth, rowPitch, top, viewportHeight, devicePixelRatio } = geometry;
  if (!Number.isInteger(columns) || columns < 1) return [];
  if (![cardWidth, rowPitch, viewportHeight, devicePixelRatio].every(isFinitePositive) || !Number.isFinite(top)) {
    return [];
  }

  const firstRowTop = top + WARMUP_HEADER_ALLOWANCE + (options.hasFolders ? WARMUP_ALBUM_STRIP_ALLOWANCE : 0);
  const rows = Math.max(0, Math.ceil((viewportHeight - firstRowTop) / rowPitch));
  const limit = Math.min(rows * columns, items.length, WARMUP_MAX_TARGETS);

  const targets: WarmupTarget[] = [];
  for (let index = 0; index < limit; index += 1) {
    const item = items[index];
    if (item.type === "video" || !item.path) continue;
    const slot = Math.ceil(cardWidth * Math.max(1, coverAspectRatio(item.width, item.height)));
    const sizes = thumbnailSizes(cardWidth, coverAspectRatio(item.width, item.height));
    if (!sizes) continue;
    const small = pickEdge(slot * (1 - WARMUP_WIDTH_TOLERANCE), devicePixelRatio);
    const large = pickEdge(slot * (1 + WARMUP_WIDTH_TOLERANCE), devicePixelRatio);
    if (small !== large) continue;
    const version = item.content_version ?? undefined;
    targets.push({
      href: getThumbnailUrl(item.path, 512, version),
      imagesrcset: getThumbnailSrcset(item.path, version),
      imagesizes: sizes,
      fetchpriority: index < columns ? "high" : "auto",
    });
  }
  return targets;
}

const warmed = new Set<string>();

/** How long a preload link stays in `<head>`: long enough for the card to claim it, short enough not to leak. */
export const WARMUP_LINK_LIFETIME_MS = 15_000;

/** Adds one `<link rel="preload" as="image">` per target that was not already warmed. Returns the links added. */
export function warmThumbnails(targets: readonly WarmupTarget[], doc: Document = document): HTMLLinkElement[] {
  const added: HTMLLinkElement[] = [];
  for (const target of targets) {
    if (warmed.has(target.href)) continue;
    warmed.add(target.href);
    const link = doc.createElement("link");
    link.rel = "preload";
    link.setAttribute("as", "image");
    link.href = target.href;
    link.setAttribute("imagesrcset", target.imagesrcset);
    link.setAttribute("imagesizes", target.imagesizes);
    link.setAttribute("fetchpriority", target.fetchpriority);
    doc.head.appendChild(link);
    added.push(link);
    setTimeout(() => {
      link.remove();
      warmed.delete(target.href);
    }, WARMUP_LINK_LIFETIME_MS);
  }
  return added;
}
