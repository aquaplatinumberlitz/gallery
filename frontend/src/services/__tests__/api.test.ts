import { describe, it, expect, vi, beforeEach } from "vitest";
import { GalleryAPIError } from "../api";
import type { AxiosError } from "axios";

function createAxiosError(params: {
  status?: number;
  data?: unknown;
  code?: string;
  message?: string;
}): AxiosError {
  return {
    isAxiosError: true,
    response: params.status
      ? {
          status: params.status,
          data: params.data,
          statusText: "",
          headers: {},
          config: {} as any,
        }
      : undefined,
    code: params.code,
    message: params.message || "",
    name: "AxiosError",
    config: {} as any,
    toJSON: () => ({}),
  } as AxiosError;
}

describe("GalleryAPIError.fromAxiosError", () => {
  it("returns timeout error for aborted/timeout with no response", () => {
    const err = createAxiosError({ code: "ECONNABORTED", message: "timeout" });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("timeout");
    expect(result.canRetry).toBe(true);
  });

  it("returns network error for no response without timeout", () => {
    const err = createAxiosError({ message: "Network Error" });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("network");
    expect(result.canRetry).toBe(true);
  });

  it("parses FastAPI detail wrapped error", () => {
    const err = createAxiosError({
      status: 400,
      data: { detail: { error: "bad_request", message: "Invalid input" } },
    });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("bad_request");
  });

  it("handles library_overlap error", () => {
    const err = createAxiosError({
      status: 409,
      data: { detail: { error: "library_overlap", message: "Overlaps with existing" } },
    });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("library_overlap");
    expect(result.userMessage).toContain("overlaps");
  });

  it("handles library_busy error", () => {
    const err = createAxiosError({
      status: 409,
      data: { detail: { error: "library_busy", message: "Library is busy" } },
    });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("library_busy");
    expect(result.userMessage).toContain("busy");
  });

  it("handles not_found error", () => {
    const err = createAxiosError({
      status: 404,
      data: { detail: { error: "not_found", message: "Not found" } },
    });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("not_found");
  });

  it("handles not_directory error", () => {
    const err = createAxiosError({
      status: 400,
      data: { detail: { error: "not_directory", message: "Not a directory" } },
    });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("not_directory");
  });

  it("handles permission error", () => {
    const err = createAxiosError({
      status: 403,
      data: { detail: { error: "permission", message: "Access denied" } },
    });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("permission");
  });

  it("handles invalid_file error", () => {
    const err = createAxiosError({
      status: 400,
      data: { detail: { error: "invalid_file", message: "Invalid file" } },
    });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("invalid_file");
  });

  it("handles confirmation_required error", () => {
    const err = createAxiosError({
      status: 400,
      data: { detail: { error: "confirmation_required", message: "Confirm first" } },
    });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("confirmation_required");
  });

  it("falls back to server_error for unknown error types", () => {
    const err = createAxiosError({
      status: 500,
      data: { detail: { error: "unknown_type", message: "Something broke" } },
    });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("server_error");
    expect(result.canRetry).toBe(true);
  });

  it("handles response data without detail wrapper", () => {
    const err = createAxiosError({
      status: 400,
      data: { error: "bad_request", message: "Direct error" },
    });
    const result = GalleryAPIError.fromAxiosError(err);
    expect(result.type).toBe("bad_request");
  });
});
