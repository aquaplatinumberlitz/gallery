/**
 * Purpose: Protect the shared folder/media ordering used by the grid and by the pre-mount first-cover choice.
 * Guarantees: Name sorting is natural (album2 before album10) and case-insensitive, date sorting uses mtime
 * (missing counts as 0), descending reverses the order, and the input array is not mutated.
 * Run when: Changing gallery sorting or `GalleryGrid` ordering.
 */
import { describe, expect, it } from "vitest";
import { sortByPreference } from "../sortNodes";

const items = [{ name: "album10", mtime: 30 }, { name: "Album2", mtime: 10 }, { name: "album1" }];

describe("sortByPreference", () => {
  it("sorts by natural name", () => {
    expect(sortByPreference(items, "name", "asc").map((item) => item.name)).toEqual(["album1", "Album2", "album10"]);
    expect(sortByPreference(items, "name", "desc").map((item) => item.name)).toEqual(["album10", "Album2", "album1"]);
  });

  it("sorts by modification time, treating a missing mtime as 0", () => {
    expect(sortByPreference(items, "date", "asc").map((item) => item.name)).toEqual(["album1", "Album2", "album10"]);
    expect(sortByPreference(items, "date", "desc").map((item) => item.name)).toEqual(["album10", "Album2", "album1"]);
  });

  it("does not mutate its input", () => {
    const before = items.map((item) => item.name);
    sortByPreference(items, "name", "desc");
    expect(items.map((item) => item.name)).toEqual(before);
  });
});
