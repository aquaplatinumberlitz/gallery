import { IMAGE_PAGE_SIZE } from "../constants";
import { scanDirectory } from "../services/api";
import type { ScanResponse } from "../types";
import { queryClient } from "./index";
import { normalizeQueryPath, queryKeys } from "./keys";

const withScanRequestPath = (data: ScanResponse, requestPath: string): ScanResponse => ({
  ...data,
  request_path: requestPath,
});

/**
 * Fetch scan data and propagate API errors to the caller.
 * Used where existing UI error/toast handling must remain intact.
 */
export async function fetchScanOrThrow(path: string): Promise<ScanResponse> {
  const normalized = normalizeQueryPath(path);
  if (!normalized) {
    throw new Error("Scan path is required");
  }

  return queryClient.fetchQuery({
    queryKey: queryKeys.scan(normalized, IMAGE_PAGE_SIZE),
    queryFn: async () => withScanRequestPath(
      await scanDirectory(normalized, { imageLimit: IMAGE_PAGE_SIZE, imageCursor: 0 }),
      normalized
    ),
    staleTime: 60_000,
  });
}
