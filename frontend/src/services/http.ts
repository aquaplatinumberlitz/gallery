/**
 * Minimal `fetch` JSON client that replaces axios (docs/archived/IMAGE_PIPELINE_PLAN.md, IP-11).
 *
 * It deliberately keeps axios' observable behaviour for the call shapes `services/api.ts` uses, so the
 * endpoint wrappers and `GalleryAPIError` mapping did not change:
 *
 * - Call shape: `get(url, {params, signal})`, `post(url, data?, {params, signal})`, `patch(...)`,
 *   `delete(url, {params, signal})`, each resolving to `{data, status}`.
 * - URL: `baseURL` is joined like axios (`combineURLs`, absolute URLs bypass it) and `params` are
 *   serialised like axios' default `buildURL`: `undefined` / `null` values are skipped, a flat array
 *   becomes `key[]=a&key[]=b`, nested objects and arrays use `a[b]` / `a[0]` keys, dates are ISO strings,
 *   `: $ ,` stay unescaped and a space is `+`. Keys are trimmed.
 * - Request: `Accept: application/json, text/plain, *\/*`; a non-null `data` is sent as JSON with
 *   `Content-Type: application/json`; `null` / `undefined` send no body (a POST/PATCH with `null` still
 *   carries axios' `Content-Type: application/x-www-form-urlencoded`).
 * - Response: the body is read as text; a non-empty text is parsed as JSON whatever the content type, and
 *   kept as the raw string when it is not JSON (axios' `silentJSONParsing`). Statuses outside 2xx reject
 *   with an `HttpError` whose `response.data` is parsed the same way.
 * - Errors are `HttpError`s with axios' codes and messages: `ERR_BAD_REQUEST` / `ERR_BAD_RESPONSE`
 *   ("Request failed with status code N"), `ECONNABORTED` ("timeout of Nms exceeded"), `ERR_CANCELED`
 *   ("canceled") and `ERR_NETWORK` ("Network Error").
 * - `timeout` covers the whole exchange including the body, like an XHR timeout. A caller `signal` aborts
 *   it. Credentials follow the `fetch` default (`same-origin`), which equals XHR without `withCredentials`.
 *
 * Not carried over because the app never used them: interceptors, XSRF cookie forwarding, upload and
 * download progress, request/response transformers, form-data bodies, `responseType`.
 */

export type HttpParams = Record<string, unknown>;

export interface HttpRequestConfig {
  params?: HttpParams;
  signal?: AbortSignal;
}

export interface HttpResponse<T = unknown> {
  data: T;
  status: number;
}

/** Shape `GalleryAPIError.fromHttpError` reads; a structural subset of `HttpError`. */
export interface HttpErrorLike {
  message: string;
  code?: string;
  response?: { data?: unknown; status?: number };
}

export class HttpError extends Error implements HttpErrorLike {
  readonly code: string | undefined;
  readonly response: { data: unknown; status: number } | undefined;

  constructor(message: string, code?: string, response?: { data: unknown; status: number }) {
    super(message);
    this.name = "HttpError";
    this.code = code;
    this.response = response;
  }
}

export const HTTP_ERROR_CODES = {
  badRequest: "ERR_BAD_REQUEST",
  badResponse: "ERR_BAD_RESPONSE",
  timeout: "ECONNABORTED",
  canceled: "ERR_CANCELED",
  network: "ERR_NETWORK",
} as const;

// ---------------------------------------------------------------------------
// URL
// ---------------------------------------------------------------------------

/** axios `isAbsoluteURL`: `<scheme>://` or protocol-relative `//`. */
const isAbsoluteUrl = (url: string) => /^([a-z][a-z\d+\-.]*:)?\/\//i.test(url);

/** axios `combineURLs`. */
const combineUrls = (baseURL: string, relativeURL: string) =>
  relativeURL ? `${baseURL.replace(/\/?\/$/, "")}/${relativeURL.replace(/^\/+/, "")}` : baseURL;

/** axios' `buildURL` encoder: `encodeURIComponent` with `: $ ,` kept and a space as `+`. */
const encodeParam = (value: unknown) =>
  encodeURIComponent(String(value))
    .replace(/%3A/gi, ":")
    .replace(/%24/g, "$")
    .replace(/%2C/gi, ",")
    .replace(/%20/g, "+");

const isPlainObject = (value: unknown): value is Record<string, unknown> => {
  if (value === null || typeof value !== "object") return false;
  const proto = Object.getPrototypeOf(value) as unknown;
  return proto === Object.prototype || proto === null;
};

const isVisitable = (value: unknown) => isPlainObject(value) || Array.isArray(value);

const removeBrackets = (key: string) => (key.endsWith("[]") ? key.slice(0, -2) : key);

/** axios `renderKey` (brackets mode): `["a", "b", 0]` -> `a[b][0]`. */
const renderKey = (path: Array<string | number> | undefined, key: string | number) => {
  if (!path) return String(key);
  return [...path, key]
    .map((token, i) => (i ? `[${removeBrackets(String(token))}]` : removeBrackets(String(token))))
    .join("");
};

const scalarToString = (value: unknown): string => {
  if (value === null) return "";
  if (value instanceof Date) return value.toISOString();
  return String(value);
};

/** Serialises `params` exactly like axios' default serializer. Returns "" when nothing is left. */
export function serializeParams(params: HttpParams): string {
  const pairs: Array<[string, unknown]> = [];
  const stack: unknown[] = [];

  const visit = (value: unknown, path: Array<string | number> | undefined) => {
    if (value === undefined) return;
    if (stack.includes(value)) throw new Error(`Circular reference detected in ${(path ?? []).join(".")}`);
    stack.push(value);
    // axios visits with the trimmed key but recurses with the original one.
    const entries: Array<[string | number, string | number, unknown]> = Array.isArray(value)
      ? value.map((el, index) => [index, index, el] as [number, number, unknown])
      : Object.entries(value as Record<string, unknown>).map(([k, v]) => [k.trim(), k, v] as [string, string, unknown]);
    for (const [key, rawKey, el] of entries) {
      if (el === undefined || el === null) continue;
      if (typeof key === "string" && !path && typeof el === "object") {
        if (key.endsWith("{}")) {
          pairs.push([key, JSON.stringify(el)]);
          continue;
        }
        if (Array.isArray(el) && (key.endsWith("[]") || !el.some(isVisitable))) {
          for (const item of el) {
            if (item !== undefined && item !== null) pairs.push([`${removeBrackets(key)}[]`, scalarToString(item)]);
          }
          continue;
        }
      }
      if (isVisitable(el)) {
        visit(el, path ? [...path, rawKey] : [rawKey]);
      } else {
        pairs.push([renderKey(path, key), scalarToString(el)]);
      }
    }
    stack.pop();
  };

  visit(params, undefined);
  return pairs.map(([key, value]) => `${encodeParam(key)}=${encodeParam(value)}`).join("&");
}

/** axios `buildURL`: appends the serialised params, dropping any hash. */
export function buildUrl(url: string, params?: HttpParams): string {
  if (!params) return url;
  const serialized = serializeParams(params);
  if (!serialized) return url;
  const hash = url.indexOf("#");
  const base = hash === -1 ? url : url.slice(0, hash);
  return `${base}${base.indexOf("?") === -1 ? "?" : "&"}${serialized}`;
}

// ---------------------------------------------------------------------------
// Response
// ---------------------------------------------------------------------------

/** axios `transformResponse` with `silentJSONParsing`: JSON when it parses, the raw text otherwise. */
export function parseResponseText(text: string): unknown {
  if (!text) return text;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

const isAbortError = (error: unknown) =>
  typeof error === "object" && error !== null && (error as { name?: unknown }).name === "AbortError";

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export interface HttpClientOptions {
  baseURL?: string;
  /** Milliseconds for the whole request including the body; 0 or missing means no timeout. */
  timeout?: number;
  /** Converts every `HttpError` before it is rejected (api.ts maps it to `GalleryAPIError`). */
  mapError?: (error: HttpError) => unknown;
  /** Defaults to the global `fetch`, resolved on every request so tests can stub it. */
  fetch?: typeof fetch;
}

export interface HttpClient {
  get<T = unknown>(url: string, config?: HttpRequestConfig): Promise<HttpResponse<T>>;
  post<T = unknown>(url: string, data?: object | null, config?: HttpRequestConfig): Promise<HttpResponse<T>>;
  patch<T = unknown>(url: string, data?: object | null, config?: HttpRequestConfig): Promise<HttpResponse<T>>;
  delete<T = unknown>(url: string, config?: HttpRequestConfig): Promise<HttpResponse<T>>;
}

export function createHttpClient(options: HttpClientOptions = {}): HttpClient {
  const { baseURL = "", timeout = 0, mapError } = options;

  async function send<T>(
    method: string,
    url: string,
    data: object | null | undefined,
    config: HttpRequestConfig = {},
  ): Promise<HttpResponse<T>> {
    const fullUrl = buildUrl(baseURL && !isAbsoluteUrl(url) ? combineUrls(baseURL, url) : url, config.params);
    const headers: Record<string, string> = { Accept: "application/json, text/plain, */*" };
    let body: string | undefined;
    if (data !== undefined && data !== null) {
      body = JSON.stringify(data);
      headers["Content-Type"] = "application/json";
    } else if (data === null && method !== "GET" && method !== "DELETE") {
      // axios (XHR) labels a bodiless POST/PATCH with an explicit `null` payload as a urlencoded form.
      headers["Content-Type"] = "application/x-www-form-urlencoded";
    }

    const controller = new AbortController();
    const { signal } = config;
    const abortFromCaller = () => controller.abort();
    let timedOut = false;
    const timer =
      timeout > 0
        ? setTimeout(() => {
            timedOut = true;
            controller.abort();
          }, timeout)
        : null;
    if (signal?.aborted) controller.abort();
    else signal?.addEventListener("abort", abortFromCaller, { once: true });

    try {
      const doFetch = options.fetch ?? globalThis.fetch.bind(globalThis);
      let status: number;
      let text: string;
      try {
        const response = await doFetch(fullUrl, {
          method,
          headers,
          body,
          credentials: "same-origin",
          signal: controller.signal,
        });
        status = response.status;
        text = await response.text();
      } catch (error) {
        if (timedOut) throw new HttpError(`timeout of ${timeout}ms exceeded`, HTTP_ERROR_CODES.timeout);
        if (controller.signal.aborted || isAbortError(error))
          throw new HttpError("canceled", HTTP_ERROR_CODES.canceled);
        throw new HttpError("Network Error", HTTP_ERROR_CODES.network);
      }

      const parsed = parseResponseText(text);
      if (status >= 200 && status < 300) return { data: parsed as T, status };
      throw new HttpError(
        `Request failed with status code ${status}`,
        [HTTP_ERROR_CODES.badRequest, HTTP_ERROR_CODES.badResponse][Math.floor(status / 100) - 4],
        { data: parsed, status },
      );
    } catch (error) {
      throw error instanceof HttpError && mapError ? mapError(error) : error;
    } finally {
      if (timer) clearTimeout(timer);
      signal?.removeEventListener("abort", abortFromCaller);
    }
  }

  return {
    get: (url, config) => send("GET", url, undefined, config),
    post: (url, data, config) => send("POST", url, data, config),
    patch: (url, data, config) => send("PATCH", url, data, config),
    delete: (url, config) => send("DELETE", url, undefined, config),
  };
}
