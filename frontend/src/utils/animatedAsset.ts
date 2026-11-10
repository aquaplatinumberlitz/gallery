/**
 * The one definition of "animated image" shared by the grid hover preview and the lightbox.
 *
 * The backend inspects the container header (GIF frames, WebP animation flag, APNG `acTL`) and sends
 * `animated` on browse, search and related rows: `true`/`false` once detected, `null`/absent while unknown.
 * An unknown row is animated only when its extension is `.gif`; a `.webp` or `.png` is never guessed animated.
 */
export type AnimatedAssetLike = {
  animated?: boolean | null;
  path?: string | null;
  name?: string | null;
};

export function isAnimatedAsset(asset: AnimatedAssetLike): boolean {
  if (typeof asset.animated === "boolean") return asset.animated;
  const pathOrName = asset.path || asset.name || "";
  return pathOrName.split("?")[0]?.split("#")[0]?.split(".").pop()?.toLowerCase() === "gif";
}
