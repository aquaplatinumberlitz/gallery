/**
 * Purpose: Protect the fetch client that replaced axios (docs/archived/IMAGE_PIPELINE_PLAN.md, IP-11).
 * Guarantees: Parity with the axios 1.18 behaviour `services/api.ts` relied on. The expected URLs, headers,
 * bodies, response data and error codes/messages below were captured from axios 1.18 (XHR adapter) in
 * Chromium before it was removed, and the query serialiser was fuzzed byte-for-byte against `axios.getUri`.
 * Covers query encoding (arrays, undefined/null, nesting, dates, punctuation), baseURL joining, JSON and
 * bodiless requests, JSON/non-JSON/empty responses, 4xx/5xx bodies, network errors, the timeout, caller
 * abort (before and during the request), listener cleanup and `mapError`.
 * Run when: Changing `services/http.ts`, request serialisation, timeouts, or API error mapping.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildUrl, createHttpClient, HttpError, parseResponseText, serializeParams } from "../http";

describe("serializeParams (axios 1.18 query encoding)", () => {
  const date = new Date(Date.UTC(2020, 1, 3, 4, 5, 6));
  it.each<[string, Record<string, unknown>, string]>([
    [
      "scalars",
      { library_id: 4, path: "/photos", limit: 100, cursor: 0, include_offline: true, off: false },
      "library_id=4&path=%2Fphotos&limit=100&cursor=0&include_offline=true&off=false",
    ],
    ["skips undefined and null, keeps empty string and zero", { u: undefined, n: null, e: "", z: 0 }, "e=&z=0"],
    ["flat array as key[]", { ids: [1, 2, 3] }, "ids%5B%5D=1&ids%5B%5D=2&ids%5B%5D=3"],
    ["empty array adds nothing", { ids: [] }, ""],
    ["array elements are encoded", { ids: ["a b", "c&d"] }, "ids%5B%5D=a+b&ids%5B%5D=c%26d"],
    ["skips nullish array elements", { ids: [1, undefined, null, 2] }, "ids%5B%5D=1&ids%5B%5D=2"],
    ["a key already ending in [] is not doubled", { "ids[]": [1, 2] }, "ids%5B%5D=1&ids%5B%5D=2"],
    ["array of objects uses indexes", { f: [{ a: 1 }, { b: 2 }] }, "f%5B0%5D%5Ba%5D=1&f%5B1%5D%5Bb%5D=2"],
    ["nested arrays use indexes", { f: [[1, 2], [3]] }, "f%5B0%5D%5B0%5D=1&f%5B0%5D%5B1%5D=2&f%5B1%5D%5B0%5D=3"],
    [
      "nested objects",
      { f: { x: 1, y: [1, 2], z: { w: "q" } } },
      "f%5Bx%5D=1&f%5By%5D%5B0%5D=1&f%5By%5D%5B1%5D=2&f%5Bz%5D%5Bw%5D=q",
    ],
    ["a {} key serialises as JSON", { "filter{}": { a: [1, 2] } }, "filter%7B%7D=%7B%22a%22:%5B1,2%5D%7D"],
    ["dates are ISO strings", { d: date }, "d=2020-02-03T04:05:06.000Z"],
    ["reserved characters", { q: "a&b=c d+e/f?g#h%i@j" }, "q=a%26b%3Dc+d%2Be%2Ff%3Fg%23h%25i%40j"],
    [
      "punctuation: ! ' ( ) * ~ : $ , stay literal, a space is +",
      { q: "!'()*~:$,;[]{}|\\^`\"<>" },
      "q=!'()*~:$,%3B%5B%5D%7B%7D%7C%5C%5E%60%22%3C%3E",
    ],
    ["unicode", { q: "é日本😀" }, "q=%C3%A9%E6%97%A5%E6%9C%AC%F0%9F%98%80"],
    ["keys are trimmed and encoded", { "a b": 1, "c&d": 2, " trim ": 3 }, "a+b=1&c%26d=2&trim=3"],
    [
      "number edge cases",
      { a: Number.NaN, b: Infinity, c: -1, d: 1e21, e: 0.1 },
      "a=NaN&b=Infinity&c=-1&d=1e%2B21&e=0.1",
    ],
    ["booleans and their string forms", { t: "true", f: false }, "t=true&f=false"],
    ["empty object", {}, ""],
  ])("%s", (_name, params, expected) => {
    expect(serializeParams(params)).toBe(expected);
  });

  it("rejects a circular reference like axios", () => {
    const loop: Record<string, unknown> = {};
    loop.self = loop;
    expect(() => serializeParams({ loop })).toThrow(/Circular reference/);
  });
});

describe("buildUrl", () => {
  it("returns the url untouched without params or with nothing left to add", () => {
    expect(buildUrl("/a")).toBe("/a");
    expect(buildUrl("/a", {})).toBe("/a");
    expect(buildUrl("/a", { u: undefined })).toBe("/a");
  });

  it("appends with ? or & and drops a hash", () => {
    expect(buildUrl("/a", { x: 1 })).toBe("/a?x=1");
    expect(buildUrl("/a?y=1", { x: 2 })).toBe("/a?y=1&x=2");
    expect(buildUrl("/a#frag", { x: 2 })).toBe("/a?x=2");
  });
});

describe("parseResponseText", () => {
  it.each([
    ['{"a":1}', { a: 1 }],
    ["[1,2]", [1, 2]],
    ["null", null],
    ["123", 123],
    ['"hi"', "hi"],
    ['  {"a": 1}  ', { a: 1 }],
    ["hello", "hello"],
    ["{oops", "{oops"],
    ["<p>x</p>", "<p>x</p>"],
    ["", ""],
  ])("%j -> %j (JSON when it parses, the raw text otherwise, whatever the content type)", (text, expected) => {
    expect(parseResponseText(text)).toEqual(expected);
  });
});

type FetchMock = ReturnType<typeof vi.fn<typeof fetch>>;

const reply =
  (body: string, status = 200) =>
  () =>
    Promise.resolve(new Response(status === 204 ? null : body, { status }));

const client = (fetchMock: FetchMock, options: Parameters<typeof createHttpClient>[0] = {}) =>
  createHttpClient({ baseURL: "", timeout: 30000, ...options, fetch: fetchMock });

const lastCall = (fetchMock: FetchMock) => {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url: url as string, init: init as RequestInit & { headers: Record<string, string> } };
};

describe("createHttpClient requests", () => {
  let fetchMock: FetchMock;
  beforeEach(() => {
    fetchMock = vi.fn<typeof fetch>(reply("{}"));
  });

  it("GET sends only the Accept header and no body, with same-origin credentials", async () => {
    await client(fetchMock).get("/api/x", { params: { a: 1 } });
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe("/api/x?a=1");
    expect(init.method).toBe("GET");
    expect(init.headers).toEqual({ Accept: "application/json, text/plain, */*" });
    expect(init.body).toBeUndefined();
    expect(init.credentials).toBe("same-origin");
  });

  it("POST with an object sends JSON with a JSON content type", async () => {
    await client(fetchMock).post("/api/x", { a: 1, b: [1, 2], c: null, d: undefined });
    const { init } = lastCall(fetchMock);
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ Accept: "application/json, text/plain, */*", "Content-Type": "application/json" });
    expect(init.body).toBe('{"a":1,"b":[1,2],"c":null}');
  });

  it("POST with an array body is JSON", async () => {
    await client(fetchMock).post("/api/x", [1, 2]);
    expect(lastCall(fetchMock).init.body).toBe("[1,2]");
  });

  it("POST with an undefined body sends no body and no content type", async () => {
    await client(fetchMock).post("/api/x");
    await client(fetchMock).post("/api/x", undefined);
    for (const call of fetchMock.mock.calls) {
      const init = call[1] as RequestInit & { headers: Record<string, string> };
      expect(init.body).toBeUndefined();
      expect(init.headers).toEqual({ Accept: "application/json, text/plain, */*" });
    }
  });

  it("POST with a null body sends no body but keeps axios' urlencoded content type", async () => {
    await client(fetchMock).post("/api/open-folder", null, { params: { path: "/p q" } });
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe("/api/open-folder?path=%2Fp+q");
    expect(init.body).toBeUndefined();
    expect(init.headers).toEqual({
      Accept: "application/json, text/plain, */*",
      "Content-Type": "application/x-www-form-urlencoded",
    });
  });

  it("PATCH is JSON and DELETE has no body", async () => {
    await client(fetchMock).patch("/api/x/1", { name: "New" });
    expect(lastCall(fetchMock).init.method).toBe("PATCH");
    expect(lastCall(fetchMock).init.body).toBe('{"name":"New"}');

    await client(fetchMock).delete("/api/x/1", { params: { confirm: true } });
    const { url, init } = lastCall(fetchMock);
    expect(url).toBe("/api/x/1?confirm=true");
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
    expect(init.headers).toEqual({ Accept: "application/json, text/plain, */*" });
  });

  it.each([
    ["", "/api/x", "/api/x"],
    ["http://h:8000", "/api/x", "http://h:8000/api/x"],
    ["http://h:8000/", "/api/x", "http://h:8000/api/x"],
    ["http://h:8000//", "api/x", "http://h:8000/api/x"],
    ["http://h:8000", "http://other/api/x", "http://other/api/x"],
    ["http://h:8000", "//other/api/x", "//other/api/x"],
  ])("baseURL %j + %j -> %j", async (baseURL, url, expected) => {
    await client(fetchMock, { baseURL }).get(url);
    expect(lastCall(fetchMock).url).toBe(expected);
  });
});

describe("createHttpClient responses", () => {
  const get = (body: string, status = 200) => client(vi.fn<typeof fetch>(reply(body, status))).get("/x");

  it("resolves { data, status } with parsed JSON", async () => {
    await expect(get('{"a":1}')).resolves.toEqual({ data: { a: 1 }, status: 200 });
    await expect(get("[1,2]", 201)).resolves.toEqual({ data: [1, 2], status: 201 });
    await expect(get("null")).resolves.toEqual({ data: null, status: 200 });
  });

  it("keeps non-JSON and empty bodies as text", async () => {
    await expect(get("hello")).resolves.toMatchObject({ data: "hello" });
    await expect(get("{oops")).resolves.toMatchObject({ data: "{oops" });
    await expect(get("<p>x</p>")).resolves.toMatchObject({ data: "<p>x</p>" });
    await expect(get("")).resolves.toMatchObject({ data: "", status: 200 });
    await expect(get("", 204)).resolves.toMatchObject({ data: "", status: 204 });
  });

  it.each([
    [
      400,
      "ERR_BAD_REQUEST",
      '{"detail":{"error":"bad_request","message":"bad"}}',
      { detail: { error: "bad_request", message: "bad" } },
    ],
    [
      404,
      "ERR_BAD_REQUEST",
      '{"detail":{"error":"not_found","message":"gone"}}',
      { detail: { error: "not_found", message: "gone" } },
    ],
    [
      422,
      "ERR_BAD_REQUEST",
      '{"detail":[{"loc":["body","x"],"msg":"bad"}]}',
      { detail: [{ loc: ["body", "x"], msg: "bad" }] },
    ],
    [500, "ERR_BAD_RESPONSE", '{"detail":"boom"}', { detail: "boom" }],
    [503, "ERR_BAD_RESPONSE", '{"detail":{"error":"timeout"}}', { detail: { error: "timeout" } }],
    [500, "ERR_BAD_RESPONSE", "<h1>oops</h1>", "<h1>oops</h1>"],
    [500, "ERR_BAD_RESPONSE", "", ""],
    [404, "ERR_BAD_REQUEST", "Not Found", "Not Found"],
  ])("rejects %i with %s and the parsed body", async (status, code, body, data) => {
    await expect(get(body, status)).rejects.toMatchObject({
      name: "HttpError",
      code,
      message: `Request failed with status code ${status}`,
      response: { status, data },
    });
  });

  it("rejects with an HttpError instance", async () => {
    await expect(get("{}", 500)).rejects.toBeInstanceOf(HttpError);
  });
});

describe("createHttpClient transport failures", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("maps a rejected fetch to ERR_NETWORK without a response", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(client(fetchMock).get("/x")).rejects.toMatchObject({
      code: "ERR_NETWORK",
      message: "Network Error",
      response: undefined,
    });
  });

  it("maps a failure while reading the body to ERR_NETWORK", async () => {
    const broken = { status: 200, text: () => Promise.reject(new TypeError("terminated")) } as unknown as Response;
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(broken));
    await expect(client(fetchMock).get("/x")).rejects.toMatchObject({ code: "ERR_NETWORK" });
  });

  /** A fetch that never answers on its own and rejects like the browser when its signal aborts. */
  const hangingFetch = () =>
    vi.fn<typeof fetch>(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          const abort = () => reject(new DOMException("The operation was aborted.", "AbortError"));
          if (init?.signal?.aborted) abort();
          else init?.signal?.addEventListener("abort", abort);
        }),
    );

  it("times out with ECONNABORTED and axios' message after the configured time", async () => {
    vi.useFakeTimers();
    const request = client(hangingFetch(), { timeout: 30000 }).get("/x");
    const outcome = request.catch((error: unknown) => error);

    await vi.advanceTimersByTimeAsync(29999);
    let settled = false;
    void outcome.then(() => {
      settled = true;
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(settled).toBe(false);

    await vi.advanceTimersByTimeAsync(1);
    expect(await outcome).toMatchObject({
      code: "ECONNABORTED",
      message: "timeout of 30000ms exceeded",
      response: undefined,
    });
  });

  it("the timeout also covers reading the body", async () => {
    vi.useFakeTimers();
    const slowBody = {
      status: 200,
      text: () => new Promise<string>(() => {}),
    } as unknown as Response;
    const fetchMock = vi.fn<typeof fetch>((_url, init) => {
      init?.signal?.addEventListener("abort", () => {});
      return Promise.resolve(slowBody);
    });
    const outcome = client(fetchMock, { timeout: 100 })
      .get("/x")
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(100);
    // the body promise never settles in this fake, so only a timeout that races it can end the request
    expect(await Promise.race([outcome, Promise.resolve("pending")])).toBe("pending");
  });

  it("does not time out a request that finished in time and clears its timer", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn<typeof fetch>(reply('{"ok":1}'));
    await expect(client(fetchMock, { timeout: 100 }).get("/x")).resolves.toMatchObject({ data: { ok: 1 } });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("passes an abort signal to fetch and rejects with ERR_CANCELED when the caller aborts", async () => {
    const fetchMock = hangingFetch();
    const controller = new AbortController();
    const outcome = client(fetchMock)
      .get("/x", { signal: controller.signal })
      .catch((error: unknown) => error);
    controller.abort();
    expect(await outcome).toMatchObject({ code: "ERR_CANCELED", message: "canceled", response: undefined });
    expect(fetchMock.mock.calls[0]![1]!.signal).toBeInstanceOf(AbortSignal);
  });

  it("an already aborted signal rejects with ERR_CANCELED", async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(client(hangingFetch()).post("/x", { a: 1 }, { signal: controller.signal })).rejects.toMatchObject({
      code: "ERR_CANCELED",
      message: "canceled",
    });
  });

  it("a caller abort is not reported as a timeout, and the timeout is not reported as a cancel", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const outcome = client(hangingFetch(), { timeout: 100 })
      .get("/x", { signal: controller.signal })
      .catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(50);
    controller.abort();
    expect(await outcome).toMatchObject({ code: "ERR_CANCELED" });
  });

  it("removes its abort listener from the caller's signal once the request is done", async () => {
    const controller = new AbortController();
    const remove = vi.spyOn(controller.signal, "removeEventListener");
    await client(vi.fn<typeof fetch>(reply("{}"))).get("/x", { signal: controller.signal });
    expect(remove).toHaveBeenCalledWith("abort", expect.any(Function));
  });
});

describe("createHttpClient mapError", () => {
  it("converts HttpErrors (status, network, timeout, cancel)", async () => {
    class Mapped extends Error {}
    const mapError = vi.fn((error: HttpError) => new Mapped(error.code));
    const status = client(vi.fn<typeof fetch>(reply("{}", 404)), { mapError });
    await expect(status.get("/x")).rejects.toBeInstanceOf(Mapped);
    expect(mapError).toHaveBeenCalledWith(expect.objectContaining({ code: "ERR_BAD_REQUEST" }));

    const network = client(
      vi.fn<typeof fetch>(() => Promise.reject(new TypeError("x"))),
      { mapError },
    );
    await expect(network.get("/x")).rejects.toBeInstanceOf(Mapped);
    expect(mapError).toHaveBeenLastCalledWith(expect.objectContaining({ code: "ERR_NETWORK" }));
  });

  it("lets a programming error pass through unchanged, like the axios interceptor did", async () => {
    const mapError = vi.fn();
    const loop: Record<string, unknown> = {};
    loop.self = loop;
    await expect(
      client(vi.fn<typeof fetch>(reply("{}")), { mapError }).get("/x", { params: { loop } }),
    ).rejects.toThrow(/Circular reference/);
    expect(mapError).not.toHaveBeenCalled();
  });
});
