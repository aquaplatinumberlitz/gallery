/**
 * Isolated QueryClient for frontend unit tests.
 *
 * Purpose:
 * Provide a deterministic QueryClient with retries disabled, sensible defaults,
 * and helpers for asserting invalidation and cache state.
 *
 * Guarantees:
 * * retry: false prevents flaky async retries
 * * gcTime: 0 prevents cross-test cache leaks
 * * createIsolatedQueryClient() is called per test
 *
 * Run when:
 * * testing Vue Query composables or components that depend on query cache
 */

import { QueryClient } from "@tanstack/vue-query";

export function createIsolatedQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

/**
 * Assert that a query key was invalidated.
 * Checks the query cache's mutation observer list for a matching key.
 */
export function expectQueryInvalidated(client: QueryClient, key: ReadonlyArray<unknown>): void {
  const queryCache = client.getQueryCache();
  const all = queryCache.getAll();
  const match = all.find((q) =>
    key.every((k, i) => q.queryKey[i] === k),
  );
  expect(match?.state?.isInvalidated ?? false).toBe(true);
}
