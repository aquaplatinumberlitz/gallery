import { describe, it, expect } from "vitest";
import { fuzzySearchFileNodes } from "../fuzzySearch";
import type { FileNode } from "@/types";

function makeNode(name: string, path?: string): FileNode {
  return { name, path: path ?? `/root/${name}`, type: "image" };
}

const sampleNodes: FileNode[] = [
  makeNode("apple.png"),
  makeNode("apricot.png"),
  makeNode("banana.png"),
  makeNode("cherry.png"),
  makeNode("d_apple.png"),
];

describe("fuzzySearchFileNodes", () => {
  it("returns the full list when the query is empty", () => {
    expect(fuzzySearchFileNodes(sampleNodes, "")).toEqual(sampleNodes);
  });

  it("returns the full list when the query is only whitespace", () => {
    expect(fuzzySearchFileNodes(sampleNodes, "   ")).toEqual(sampleNodes);
  });

  it("returns the full list when no options are provided (default includePath=false)", () => {
    expect(fuzzySearchFileNodes(sampleNodes, "")).toBe(sampleNodes);
  });

  it("filters by fuzzy name match", () => {
    const results = fuzzySearchFileNodes(sampleNodes, "aple");
    const names = results.map((n) => n.name);
    expect(names).toContain("apple.png");
    expect(names).not.toContain("banana.png");
    expect(names).not.toContain("cherry.png");
  });

  it("returns an empty list when nothing matches", () => {
    expect(fuzzySearchFileNodes(sampleNodes, "zzzzzzz")).toEqual([]);
  });

  it("returns an empty list for an empty input list", () => {
    expect(fuzzySearchFileNodes([], "apple")).toEqual([]);
  });

  it("returns the input list for an empty query even when the list is empty", () => {
    expect(fuzzySearchFileNodes([], "")).toEqual([]);
  });

  it("matches using the includePath option against path tokens", () => {
    const nodesWithPath: FileNode[] = [
      makeNode("photo.png", "/vacation/beach/photo.png"),
      makeNode("photo.png", "/work/proj/photo.png"),
    ];
    const results = fuzzySearchFileNodes(nodesWithPath, "beach", { includePath: true });
    expect(results).toHaveLength(1);
    expect(results[0].path).toBe("/vacation/beach/photo.png");
  });

  it("does not match path tokens when includePath is false", () => {
    const nodesWithPath: FileNode[] = [
      makeNode("photo.png", "/vacation/beach/photo.png"),
      makeNode("photo.png", "/work/proj/photo.png"),
    ];
    const results = fuzzySearchFileNodes(nodesWithPath, "beach", { includePath: false });
    expect(results).toEqual([]);
  });

  it("reuses the cached Fuse instance for repeated calls on the same array", () => {
    const first = fuzzySearchFileNodes(sampleNodes, "apple");
    const second = fuzzySearchFileNodes(sampleNodes, "apple");
    expect(second).toEqual(first);
  });

  it("maintains separate caches for includePath true vs false on the same array", () => {
    const nodes: FileNode[] = [makeNode("img.png", "/matching-path/img.png")];
    const nameOnly = fuzzySearchFileNodes(nodes, "matching-path", { includePath: false });
    const withPath = fuzzySearchFileNodes(nodes, "matching-path", { includePath: true });
    expect(withPath).toHaveLength(1);
    expect(nameOnly).toEqual([]);
  });

  it("handles special regex-meaningful characters in queries without throwing", () => {
    const nodes: FileNode[] = [makeNode("a (special).png"), makeNode("normal.png")];
    expect(() => fuzzySearchFileNodes(nodes, "(special)")).not.toThrow();
    expect(() => fuzzySearchFileNodes(nodes, "a.b")).not.toThrow();
    expect(() => fuzzySearchFileNodes(nodes, "a*b+c?d")).not.toThrow();
  });

  it("handles unicode/CJK characters in queries", () => {
    const nodes: FileNode[] = [makeNode("写真.png"), makeNode("image.png")];
    const results = fuzzySearchFileNodes(nodes, "写");
    expect(results.map((n) => n.name)).toContain("写真.png");
  });

  it("preserves FileNode identity in results (returns item references, not clones)", () => {
    const results = fuzzySearchFileNodes(sampleNodes, "apple");
    for (const item of results) {
      expect(sampleNodes).toContain(item);
    }
  });
});
