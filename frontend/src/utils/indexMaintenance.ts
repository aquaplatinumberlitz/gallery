import { reactive } from "vue";
import { normalizeQueryPath } from "@/query/keys";

const rebuildStartedByRoot = reactive<Record<string, number>>({});

function isPathInsideRoot(path: string, root: string) {
  if (!path || !root) return false;
  if (path === root) return true;
  if (root === "/") return path.startsWith("/");
  return path.startsWith(`${root}/`);
}

export function markScopeRebuildStarted(path: string, rebuildStartedAt: number) {
  const root = normalizeQueryPath(path);
  if (!root || !Number.isFinite(rebuildStartedAt)) return;
  rebuildStartedByRoot[root] = Math.max(rebuildStartedByRoot[root] ?? 0, rebuildStartedAt);
}

export function getScopeRebuildStartedAt(path: string) {
  const scopedPath = normalizeQueryPath(path);
  if (!scopedPath) return 0;

  let latest = 0;
  for (const [root, startedAt] of Object.entries(rebuildStartedByRoot)) {
    if (isPathInsideRoot(scopedPath, root)) {
      latest = Math.max(latest, startedAt);
    }
  }
  return latest;
}

export function clearScopeRebuildMarker(path: string, generatedAt: number) {
  const scopedPath = normalizeQueryPath(path);
  if (!scopedPath || !Number.isFinite(generatedAt)) return;

  for (const [root, startedAt] of Object.entries(rebuildStartedByRoot)) {
    if (isPathInsideRoot(scopedPath, root) && generatedAt >= startedAt) {
      delete rebuildStartedByRoot[root];
    }
  }
}
