/**
 * `sizes` for a grid thumbnail whose `srcset` offers the 256 and 512 px derivatives.
 *
 * The card shows the image with `object-fit: cover` in a square box. A derivative has a long edge of
 * 256 or 512 px, so its short edge is `long / aspect`: for the image to cover a card `W` CSS px wide
 * without being upscaled, the long edge must be at least `W * aspect`. The `w` descriptors are the long
 * edges, so the slot width handed to the browser is `W * aspect`: the browser then only picks the 256 px
 * derivative when it already has enough pixels for the covered area (a 3:2 photo in a 230 px card needs a
 * 345 px long edge, so it keeps the 512 px one), and the picture looks the same as with 512 px only.
 */

/**
 * Used when the asset dimensions are unknown: wide enough that the 256 px derivative is never chosen
 * for a card above 128 px, because an upscaled thumbnail would be a visible change.
 */
export const UNKNOWN_ASPECT_RATIO = 2;

/** Long edge over short edge (>= 1) of an image, or `UNKNOWN_ASPECT_RATIO` when it is not known. */
export function coverAspectRatio(width?: number | null, height?: number | null): number {
  if (typeof width !== "number" || typeof height !== "number" || !(width > 0) || !(height > 0)) {
    return UNKNOWN_ASPECT_RATIO;
  }
  return Math.max(width, height) / Math.min(width, height);
}

/** The `sizes` value for a card `cardWidth` CSS px wide, or undefined while the width is unknown. */
export function thumbnailSizes(cardWidth: number, aspectRatio: number): string | undefined {
  if (!(cardWidth > 0)) return undefined;
  return `${Math.ceil(cardWidth * Math.max(1, aspectRatio))}px`;
}
