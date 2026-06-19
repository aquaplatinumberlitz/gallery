import type { AxiosError } from "axios";
import { describe, expect, it } from "vitest";
import { GalleryAPIError, LIBRARY_ERRORS } from "../api";

describe("GalleryAPIError", () => {
  it("maps library error codes to user-friendly messages", () => {
    const error = {
      response: {
        data: {
          detail: {
            error: "library_not_registered",
            message: "Register this root before browsing it",
          },
        },
      },
    } as unknown as AxiosError;

    const apiError = GalleryAPIError.fromAxiosError(error);

    expect(LIBRARY_ERRORS.library_not_registered).toBe("Register this folder before browsing it");
    expect(apiError.type).toBe("library_not_registered");
    expect(apiError.userMessage).toBe("Register this folder before browsing it");
    expect(apiError.suggestion).toBe("Register this root before browsing it");
  });
});
