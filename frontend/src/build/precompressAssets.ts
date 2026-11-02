/**
 * Purpose: Build-time pre-compression of the fingerprinted files under `dist/assets/`. Writes `<file>.br` (Brotli
 * quality 11) and `<file>.gz` (gzip level 9) next to every text asset, so nginx can serve them with
 * `brotli_static on;` / `gzip_static on;` instead of compressing on every request, and at a level it would never
 * use dynamically.
 * Guarantees: Only compressible text types are processed (js, css, svg, json, html, txt, xml);
 * woff2 and images are skipped because they are already compressed. A sibling is written only when it is smaller
 * than the original, so a missing `.br`/`.gz` simply means "serve the plain file" and nginx falls back to dynamic gzip.
 * Run when: Changing the compression levels or the file-type allow-list, or when the nginx static-compression
 * contract in docs/CONFIGURATION.md changes.
 */
import { constants, brotliCompress, gzip } from "node:zlib";
import { promisify } from "node:util";
import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import { extname, join, resolve } from "node:path";
import type { Plugin } from "vite";

const brotliAsync = promisify(brotliCompress);
const gzipAsync = promisify(gzip);

/** Extensions worth compressing. Everything else under assets/ (woff2, png, webp, ...) is already compressed. */
export const PRECOMPRESS_EXTENSIONS: ReadonlySet<string> = new Set([
  ".js",
  ".mjs",
  ".css",
  ".svg",
  ".json",
  ".html",
  ".txt",
  ".xml",
]);

export interface PrecompressResult {
  /** Path relative to the compressed directory. */
  file: string;
  raw: number;
  /** Size of the `.gz` sibling, or `null` when it was not smaller than the original and was not written. */
  gzip: number | null;
  /** Size of the `.br` sibling, or `null` when it was not smaller than the original and was not written. */
  brotli: number | null;
}

async function* walk(dir: string, prefix = ""): AsyncGenerator<string> {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) yield* walk(join(dir, entry.name), relative);
    else if (entry.isFile()) yield relative;
  }
}

export function isPrecompressible(file: string): boolean {
  return PRECOMPRESS_EXTENSIONS.has(extname(file).toLowerCase());
}

/** Compress every eligible file below `dir` and write `.br` / `.gz` siblings. Stale siblings are overwritten. */
export async function precompressDirectory(dir: string): Promise<PrecompressResult[]> {
  const files: string[] = [];
  for await (const file of walk(dir)) if (isPrecompressible(file)) files.push(file);

  return Promise.all(
    files.map(async (file): Promise<PrecompressResult> => {
      const path = join(dir, file);
      const source = await readFile(path);
      const [brotli, gz] = await Promise.all([
        brotliAsync(source, {
          params: {
            [constants.BROTLI_PARAM_QUALITY]: constants.BROTLI_MAX_QUALITY,
            [constants.BROTLI_PARAM_SIZE_HINT]: source.length,
          },
        }),
        gzipAsync(source, { level: 9 }),
      ]);
      const writes: Promise<void>[] = [];
      if (brotli.length < source.length) writes.push(writeFile(`${path}.br`, brotli));
      if (gz.length < source.length) writes.push(writeFile(`${path}.gz`, gz));
      await Promise.all(writes);
      return {
        file,
        raw: source.length,
        gzip: gz.length < source.length ? gz.length : null,
        brotli: brotli.length < source.length ? brotli.length : null,
      };
    }),
  );
}

/** Vite build plugin: pre-compress `<outDir>/assets` once the bundle is on disk. */
export function precompressAssets(): Plugin {
  let assetsDir = "";
  return {
    name: "gallery-precompress-assets",
    apply: "build",
    enforce: "post",
    configResolved(config) {
      assetsDir = resolve(config.root, config.build.outDir, config.build.assetsDir);
    },
    async closeBundle() {
      // `closeBundle` also fires when the build failed before writing anything.
      if (!assetsDir || !(await stat(assetsDir).then((s) => s.isDirectory(), () => false))) return;
      const results = await precompressDirectory(assetsDir);
      const sum = (pick: (r: PrecompressResult) => number) => results.reduce((total, r) => total + pick(r), 0);
      const kb = (bytes: number) => (bytes / 1024).toFixed(0);
      console.log(
        `precompressed ${results.length} assets: ${kb(sum((r) => r.raw))} KB raw, ` +
          `${kb(sum((r) => r.gzip ?? r.raw))} KB gzip, ${kb(sum((r) => r.brotli ?? r.raw))} KB brotli`,
      );
    },
  };
}
