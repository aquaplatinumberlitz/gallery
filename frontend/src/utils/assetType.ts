import type { AssetType, LegacySearchAssetType } from "@/types";

/**
 * Normalize a possibly-legacy asset-type string from the unified-search or
 * `file_index`-backed response shapes to the canonical `AssetType` vocabulary.
 *
 * The backend `assets` table stores only `AssetType` values
 * (`backend/metadata_store.py` normalizes at every write site), but the
 * unified-search response is backed by the legacy `file_index` table and by
 * `_format_prompt_rows`, which still emit the legacy strings `"photo"` and
 * (rarely) `"file"`. Consumers that compare against `AssetType` should run
 * search/file_index response values through this normalizer first. Do not
 * introduce new emit sites for the legacy strings.
 */
export function normalizeAssetType(type: AssetType | LegacySearchAssetType | string | undefined): AssetType {
  switch (type) {
    case "image":
    case "photo":
    case "file":
      return "image";
    case "video":
      return "video";
    case "folder":
      return "folder";
    default:
      return "image";
  }
}

/** True when the normalized type is an image or video (i.e. a servable media asset). */
export function isMediaAssetType(type: AssetType | LegacySearchAssetType | string | undefined): boolean {
  switch (type) {
    case "image":
    case "photo":
    case "file":
    case "video":
      return true;
    default:
      return false;
  }
}
