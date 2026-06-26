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

import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount, type VueWrapper } from "@vue/test-utils";
import { defineComponent, h, type Component } from "vue";

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
  const match = all.find((q) => key.every((k, i) => q.queryKey[i] === k));
  expect(match?.state?.isInvalidated ?? false).toBe(true);
}

/**
 * Mount a composable inside a host component with a fresh isolated QueryClient.
 *
 * Guarantees:
 * * A new QueryClient with `retry: false` and `gcTime: 0` is created per call
 * * The composable's setup lifecycle (onMounted, watch, etc.) runs normally
 * * Returns the composable result, the QueryClient, and the wrapper so tests
 *   can inspect cache state or unmount to trigger cleanup
 *
 * Example:
 * ```ts
 * const { result, queryClient } = mountWithQuery(() => useMyQuery(1))
 * await vi.waitFor(() => expect(result.data.value).toBeDefined())
 * ```
 */
export function mountWithQuery<T>(setupFn: () => T): {
  result: T;
  queryClient: QueryClient;
  wrapper: VueWrapper<Component>;
} {
  const queryClient = createIsolatedQueryClient();
  let result!: T;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = setupFn();
        return () => h("div");
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  );
  return { result, queryClient, wrapper };
}
