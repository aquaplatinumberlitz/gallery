/**
 * Purpose: Protect `services/api.ts` end to end over a stubbed global `fetch` (no mocked HTTP client), i.e.
 * the behaviour callers saw with axios: request shape, `GalleryAPIError` mapping and the 30 s timeout.
 * Guarantees: Endpoint wrappers send the same URLs/bodies as before; 4xx/5xx JSON bodies become typed
 * `GalleryAPIError`s (also FastAPI 422 detail arrays); a network failure is `network`; a stalled request
 * ends as `timeout` after 30 s; an aborted request rejects as the `network` GalleryAPIError (axios'
 * CanceledError was mapped the same way) and sends nothing when already aborted; non-JSON 200 bodies are
 * returned as text.
 * Run when: Changing `services/api.ts`, `services/http.ts`, request timeouts, or API error mapping.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  browseDirectory,
  fetchLibrary,
  fetchMetadata,
  GalleryAPIError,
  generateMissingImages,
  openFolder,
  unifiedSearchV2,
} from "../api";

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const call = () => {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url, init: init as RequestInit & { headers: Record<string, string> } };
};

describe("requests", () => {
  it("browseDirectory sends the same query string as with axios", async () => {
    fetchMock.mockImplementation(() => json({ folders: [], media: [], next_cursor: null }));
    await browseDirectory(4, "/photos", { limit: 100, cursor: 0, includeOffline: true });
    expect(call().url).toBe("/api/browse?library_id=4&path=%2Fphotos&limit=100&cursor=0&include_offline=true");
  });

  it("openFolder and generateMissingImages POST a null body with params", async () => {
    fetchMock.mockImplementation(() => json({}));
    await openFolder("/p q");
    expect(call().url).toBe("/api/open-folder?path=%2Fp+q");
    expect(call().init.method).toBe("POST");
    expect(call().init.body).toBeUndefined();

    await generateMissingImages(4, "thumbnail");
    expect(call().url).toBe("/api/derivatives/warm?library_id=4&kind=thumbnail");
  });

  it("unifiedSearchV2 POSTs the JSON request", async () => {
    fetchMock.mockImplementation(() => json({ media: [] }));
    const request = { schema_version: 1 as const, text: "cat" } as unknown as Parameters<typeof unifiedSearchV2>[0];
    await unifiedSearchV2(request);
    expect(call().init.method).toBe("POST");
    expect(call().init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(call().init.body as string)).toEqual(request);
  });

  it("returns a non-JSON 200 body as text", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response("plain", { status: 200 })));
    await expect(fetchLibrary(1)).resolves.toBe("plain");
  });
});

describe("error mapping", () => {
  it("maps a 404 detail body to a typed not_found GalleryAPIError", async () => {
    fetchMock.mockImplementation(() => json({ detail: { error: "not_found", message: "gone" } }, 404));
    const error = await fetchLibrary(1).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(GalleryAPIError);
    expect(error).toMatchObject({ type: "not_found", userMessage: "Folder not found", canRetry: false });
  });

  it("maps a library error code with its fixed user message", async () => {
    fetchMock.mockImplementation(() => json({ detail: { error: "library_overlap", message: "overlap" } }, 409));
    await expect(fetchLibrary(1)).rejects.toMatchObject({
      type: "library_overlap",
      userMessage: "This folder overlaps with an existing library",
    });
  });

  it("maps a FastAPI 422 detail array to bad_request with field errors", async () => {
    fetchMock.mockImplementation(() =>
      json(
        {
          detail: [
            { loc: ["body", "filters", "workflow_groups", 1, "predicates", 2, "op"], msg: "Unsupported operator" },
          ],
        },
        422,
      ),
    );
    await expect(fetchLibrary(1)).rejects.toMatchObject({
      type: "bad_request",
      fieldErrors: { "filters.workflow_groups[1].predicates[2].op": "Unsupported operator" },
    });
  });

  it("keeps the relation status of a typed 4xx body", async () => {
    const status = { metadata: { state: "ready" } };
    fetchMock.mockImplementation(() =>
      json({ detail: { error: "relation_index_not_ready", message: "x", status } }, 409),
    );
    await expect(fetchLibrary(1)).rejects.toMatchObject({ type: "relation_index_not_ready", relatedStatus: status });
  });

  it("maps a 500 with an HTML or empty body to a retryable server_error", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response("<h1>oops</h1>", { status: 500 })));
    await expect(fetchLibrary(1)).rejects.toMatchObject({ type: "server_error", canRetry: true });
    fetchMock.mockImplementation(() => Promise.resolve(new Response("", { status: 500 })));
    await expect(fetchLibrary(1)).rejects.toMatchObject({ type: "server_error", canRetry: true });
  });

  it("maps a 503 timeout detail to the retryable timeout GalleryAPIError", async () => {
    fetchMock.mockImplementation(() =>
      json({ detail: { error: "timeout", message: "Derivative generation timed out" } }, 503),
    );
    await expect(fetchLibrary(1)).rejects.toMatchObject({ type: "timeout", canRetry: true });
  });

  it("maps a rejected fetch to the retryable network GalleryAPIError", async () => {
    fetchMock.mockImplementation(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(fetchLibrary(1)).rejects.toMatchObject({
      type: "network",
      userMessage: "Can't connect to server",
      canRetry: true,
    });
  });
});

describe("compatibility", () => {
  it("keeps GalleryAPIError.fromAxiosError as an alias of fromHttpError", () => {
    const err = { response: { data: { detail: { error: "permission", message: "no" } } }, message: "x" };
    expect(GalleryAPIError.fromAxiosError(err).type).toBe("permission");
    expect(GalleryAPIError.fromAxiosError({ message: "Network Error" }).type).toBe("network");
  });
});

describe("timeout and cancellation", () => {
  const stalledFetch = () =>
    fetchMock.mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          const abort = () => reject(new DOMException("aborted", "AbortError"));
          if (init?.signal?.aborted) abort();
          else init?.signal?.addEventListener("abort", abort);
        }),
    );

  it("ends a stalled request as the timeout GalleryAPIError after 30 s", async () => {
    vi.useFakeTimers();
    stalledFetch();
    const outcome = fetchLibrary(1).catch((e: unknown) => e);

    await vi.advanceTimersByTimeAsync(29_999);
    expect(fetchMock).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);

    expect(await outcome).toMatchObject({ type: "timeout", userMessage: "Request timed out", canRetry: true });
  });

  it("an aborted request rejects with the same GalleryAPIError axios' CanceledError was mapped to", async () => {
    stalledFetch();
    const controller = new AbortController();
    const outcome = fetchMetadata("/a.png", controller.signal).catch((e: unknown) => e);
    controller.abort();
    const error = await outcome;
    expect(error).toBeInstanceOf(GalleryAPIError);
    expect(error).toMatchObject({ type: "network", userMessage: "Can't connect to server" });
  });

  it("forwards the caller's signal to fetch (aborting it aborts the in-flight request)", async () => {
    stalledFetch();
    const controller = new AbortController();
    const outcome = fetchMetadata("/a.png", controller.signal).catch((e: unknown) => e);
    const sent = call().init.signal!;
    expect(sent.aborted).toBe(false);
    controller.abort();
    await outcome;
    expect(sent.aborted).toBe(true);
  });
});
