/**
 * Purpose: Protect the build-time pre-compression of `dist/assets/` that nginx `brotli_static` / `gzip_static` serve.
 * Guarantees: Text assets get a `.br` and a `.gz` sibling that decompress to the exact original; woff2 and images get
 * none; a file that does not shrink gets none; nested directories are walked; stale siblings are replaced.
 * Run when: Changing src/build/precompressAssets.ts, the compression levels, or the nginx /assets/ location.
 */
import { mkdirSync, mkdtempSync, readFileSync, existsSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { brotliDecompressSync, gunzipSync } from "node:zlib";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { isPrecompressible, precompressDirectory } from "../precompressAssets";

let dir = "";

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "gallery-precompress-"));
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

const repetitive = (label: string) => `export const ${label} = ${JSON.stringify("gallery ".repeat(400))};\n`;

describe("precompressDirectory", () => {
  it("writes .br and .gz siblings that decompress to the original text assets", async () => {
    const js = repetitive("a");
    const css = ".a{color:red}\n".repeat(200);
    writeFileSync(join(dir, "index-abc123.js"), js);
    writeFileSync(join(dir, "index-abc123.css"), css);

    const results = await precompressDirectory(dir);

    expect(results.map((r) => r.file).sort()).toEqual(["index-abc123.css", "index-abc123.js"]);
    for (const [name, original] of [
      ["index-abc123.js", js],
      ["index-abc123.css", css],
    ] as const) {
      expect(brotliDecompressSync(readFileSync(join(dir, `${name}.br`))).toString()).toBe(original);
      expect(gunzipSync(readFileSync(join(dir, `${name}.gz`))).toString()).toBe(original);
      expect(readFileSync(join(dir, `${name}.br`)).length).toBeLessThan(readFileSync(join(dir, `${name}.gz`)).length);
    }
  });

  it("skips already-compressed types", async () => {
    writeFileSync(join(dir, "font-abc.woff2"), "wOF2".repeat(2000));
    writeFileSync(join(dir, "pic-abc.webp"), "RIFF".repeat(2000));
    writeFileSync(join(dir, "pic-abc.png"), "PNG!".repeat(2000));

    expect(await precompressDirectory(dir)).toEqual([]);
    for (const name of ["font-abc.woff2", "pic-abc.webp", "pic-abc.png"]) {
      expect(existsSync(join(dir, `${name}.br`))).toBe(false);
      expect(existsSync(join(dir, `${name}.gz`))).toBe(false);
    }
  });

  it("does not write a sibling that is not smaller than the original", async () => {
    writeFileSync(join(dir, "tiny.js"), "x");

    const [result] = await precompressDirectory(dir);

    expect(result).toMatchObject({ file: "tiny.js", raw: 1, gzip: null, brotli: null });
    expect(existsSync(join(dir, "tiny.js.br"))).toBe(false);
    expect(existsSync(join(dir, "tiny.js.gz"))).toBe(false);
  });

  it("walks nested directories and replaces stale siblings", async () => {
    mkdirSync(join(dir, "nested"));
    writeFileSync(join(dir, "nested", "chunk.js"), repetitive("b"));
    writeFileSync(join(dir, "nested", "chunk.js.br"), "stale");

    await precompressDirectory(dir);

    expect(brotliDecompressSync(readFileSync(join(dir, "nested", "chunk.js.br"))).toString()).toBe(repetitive("b"));
    expect(existsSync(join(dir, "nested", "chunk.js.gz"))).toBe(true);
  });
});

describe("isPrecompressible", () => {
  it("accepts text assets and rejects binary assets and existing siblings", () => {
    for (const file of ["a.js", "a.css", "a.svg", "a.json", "A.JS"]) expect(isPrecompressible(file)).toBe(true);
    for (const file of ["a.woff2", "a.png", "a.webp", "a.js.br", "a.js.gz", "a.map"])
      expect(isPrecompressible(file)).toBe(false);
  });
});
