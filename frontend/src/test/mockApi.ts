/**
 * Reusable axios mock factory for frontend unit tests.
 *
 * Purpose:
 * Provide a consistent mockApi fixture so tests do not hand-roll
 * inconsistent axios mocks.
 *
 * Guarantees:
 * * vi.hoisted is called before vi.mock("axios") in the test file
 * * mockApi exposes get/post/patch/delete + interceptors
 * * All mocks clear automatically via beforeEach (setup.ts afterEach)
 *
 * Usage:
 * ```ts
 * const { mockApi } = useMockApi();
 * vi.mock("axios", async () => {
 *   const actual = await vi.importActual("axios");
 *   return { ...actual, default: { ...actual.default, create: vi.fn(() => mockApi) } };
 * });
 * ```
 *
 * Run when:
 * * writing new tests for API service functions
 */

import { vi } from "vitest";

export interface MockApi {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
  interceptors: { response: { use: ReturnType<typeof vi.fn> } };
}

export function useMockApi(): { mockApi: MockApi } {
  return vi.hoisted(() => ({
    mockApi: {
      get: vi.fn(),
      post: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
      interceptors: { response: { use: vi.fn() } },
    },
  }));
}
