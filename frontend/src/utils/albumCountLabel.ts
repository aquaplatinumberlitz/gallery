import type { FileNode } from "@/types";

/**
 * Count label for an album card.
 *
 * `image_count` only counts images directly inside the folder. A folder that only holds
 * subfolders (or only videos) reports 0, so "0 photos" would wrongly suggest it is empty;
 * omit the label there and reserve "Empty" for folders without any children.
 */
export function albumCountLabel(node: Pick<FileNode, "image_count" | "has_children">): string | null {
  const count = node.image_count;
  if (count === undefined || count === null) return null;
  if (count > 0) return `${count} ${count === 1 ? "photo" : "photos"}`;
  return node.has_children ? null : "Empty";
}
