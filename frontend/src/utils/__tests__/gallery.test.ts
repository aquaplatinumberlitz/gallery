import { describe, expect, it } from "vitest";
import { shouldLoadMoreImages } from "../gallery";

const allTrue = {
  hasMoreImages: true,
  isLoadingMore: false,
  isFetching: false,
  hasSearchQuery: false,
};

describe("shouldLoadMoreImages", () => {
  it("returns true when all guards pass", () => {
    expect(shouldLoadMoreImages(allTrue)).toBe(true);
  });

  it("returns false when hasMoreImages is false", () => {
    expect(shouldLoadMoreImages({ ...allTrue, hasMoreImages: false })).toBe(false);
  });

  it("returns false when isLoadingMore is true", () => {
    expect(shouldLoadMoreImages({ ...allTrue, isLoadingMore: true })).toBe(false);
  });

  it("returns false when isFetching is true", () => {
    expect(shouldLoadMoreImages({ ...allTrue, isFetching: true })).toBe(false);
  });

  it("returns false when hasSearchQuery is true", () => {
    expect(shouldLoadMoreImages({ ...allTrue, hasSearchQuery: true })).toBe(false);
  });

  it("returns false when all guards fail", () => {
    expect(
      shouldLoadMoreImages({
        hasMoreImages: false,
        isLoadingMore: true,
        isFetching: true,
        hasSearchQuery: true,
      }),
    ).toBe(false);
  });

  it("returns false hasMoreImages=true but all other guards block", () => {
    expect(
      shouldLoadMoreImages({
        hasMoreImages: true,
        isLoadingMore: true,
        isFetching: true,
        hasSearchQuery: true,
      }),
    ).toBe(false);
  });

  it("returns false when only isLoadingMore blocks", () => {
    expect(
      shouldLoadMoreImages({
        hasMoreImages: true,
        isLoadingMore: true,
        isFetching: false,
        hasSearchQuery: false,
      }),
    ).toBe(false);
  });

  it("returns false when only isFetching blocks", () => {
    expect(
      shouldLoadMoreImages({
        hasMoreImages: true,
        isLoadingMore: false,
        isFetching: true,
        hasSearchQuery: false,
      }),
    ).toBe(false);
  });

  it("returns false when only hasSearchQuery blocks", () => {
    expect(
      shouldLoadMoreImages({
        hasMoreImages: true,
        isLoadingMore: false,
        isFetching: false,
        hasSearchQuery: true,
      }),
    ).toBe(false);
  });
});
