import { pathContains } from "../stores/gallery";

export type BreadcrumbSegment = { name: string; fullPath: string; isLast: boolean; index: number };

const splitParts = (path: string) => path.split(/[\\/]+/).filter(Boolean);

/**
 * Builds breadcrumb segments for `path`. When `rootPath` (the active import root)
 * contains `path`, the trail starts at that root, shown with its folder name,
 * like the folder tree. Otherwise it starts at the filesystem root.
 */
export function buildBreadcrumbSegments(path: string, rootPath = ""): BreadcrumbSegment[] {
  const raw = path || "";
  const sep = raw.includes("\\") ? "\\" : "/";
  const prefix = raw.startsWith("\\\\") ? "\\\\" : raw.startsWith(sep) ? sep : "";
  const parts = splitParts(raw);

  const all: BreadcrumbSegment[] = [];
  let current = prefix;
  parts.forEach((part, idx) => {
    current = current && !current.endsWith(sep) ? current + sep + part : current + part;
    all.push({ name: part, fullPath: current, isLast: idx === parts.length - 1, index: idx });
  });

  const root = rootPath.trim();
  if (!root || !raw || !pathContains(root, raw)) return all;

  const rootPartCount = splitParts(root).length;
  if (rootPartCount === 0 || parts.length < rootPartCount) return all;

  return all.slice(rootPartCount - 1).map((segment, index) => ({ ...segment, index }));
}
