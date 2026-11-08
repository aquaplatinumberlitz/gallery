// Shared helpers for the web-vitals harness (serve_dist*.cjs and the measurement scripts).
//
// Purpose:
// Keep argument parsing, the proxy-secret lookup, the self-signed certificate and Playwright
// resolution in one place so each script stays a direct port of its scratch original.
//
// Guarantees:
// * the proxy secret comes from --secret-file or GALLERY_PROXY_SECRET; nothing is committed
// * the self-signed certificate for HTTP/2 is generated into a temp directory that is removed on exit
// * Playwright resolves from the script directory or from the current directory (run from frontend/)
//
// Run when:
// * changing a script in scripts/perf/web_vitals/ (this file is required by all of them)

const { execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const zlib = require("zlib");
const { createRequire } = require("module");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const DEFAULT_DIST = path.join(REPO_ROOT, "frontend", "dist");

// Parse `--key value`, `--key=value` and bare `--flag` arguments. Positional values go to `_`.
function parseArgs(argv = process.argv.slice(2)) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (!arg.startsWith("--")) {
      out._.push(arg);
      continue;
    }
    const eq = arg.indexOf("=");
    if (eq >= 0) {
      out[arg.slice(2, eq)] = arg.slice(eq + 1);
    } else if (argv[i + 1] !== undefined && !argv[i + 1].startsWith("--")) {
      out[arg.slice(2)] = argv[++i];
    } else {
      out[arg.slice(2)] = true;
    }
  }
  return out;
}

function intArg(value, fallback) {
  if (value === undefined || value === true) return fallback;
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1 || n > 65535) throw new Error(`invalid port: ${value}`);
  return n;
}

// Proxy secret shared with the backend (GALLERY_TRUSTED_PROXY_SECRET). Required, no default.
function readProxySecret(args) {
  if (typeof args["secret-file"] === "string") {
    return fs.readFileSync(path.resolve(args["secret-file"]), "utf8").trim();
  }
  if (process.env.GALLERY_PROXY_SECRET) return process.env.GALLERY_PROXY_SECRET.trim();
  throw new Error(
    "proxy secret missing: pass --secret-file PATH or set GALLERY_PROXY_SECRET " +
      "(the same value as the backend's GALLERY_TRUSTED_PROXY_SECRET)",
  );
}

function assertDist(dist) {
  if (!fs.existsSync(path.join(dist, "index.html"))) {
    throw new Error(`no index.html in ${dist}; run "corepack pnpm run build" in frontend/ or pass --dist`);
  }
}

// Generate a 2-day self-signed certificate for localhost into a fresh temp directory.
// The directory is removed when the process exits, so no key material is kept.
function generateSelfSignedCert() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "gallery-h2-"));
  const key = path.join(dir, "key.pem");
  const cert = path.join(dir, "cert.pem");
  execFileSync(
    "openssl",
    [
      "req",
      "-x509",
      "-newkey",
      "rsa:2048",
      "-nodes",
      "-keyout",
      key,
      "-out",
      cert,
      "-days",
      "2",
      "-subj",
      "/CN=localhost",
      "-addext",
      "subjectAltName=DNS:localhost,IP:127.0.0.1",
    ],
    { stdio: "ignore" },
  );
  const cleanup = () => fs.rmSync(dir, { recursive: true, force: true });
  process.on("exit", cleanup);
  for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => process.exit(0));
  return { key: fs.readFileSync(key), cert: fs.readFileSync(cert), dir };
}

// Pick the encoding nginx would use for a static file and return the body to send.
//
// Order for files under /assets/: a pre-compressed `<file>.br` when the client accepts `br` (nginx `brotli_static on`),
// then `<file>.gz` when it accepts gzip (`gzip_static on`), then dynamic gzip for text types (`gzip on`), then the
// plain file. Other paths (index.html) get dynamic gzip only, as in the nginx template.
// Options: `textType` (the file is compressible text), `staticDir` (the file is under /assets/), `allowBrotli`
// (false mimics a server without the Brotli module), `gzipLevel` (dynamic gzip level, 6 by default).
// Returns `{ body, encoding }` where `encoding` is "br", "gzip" or null.
function negotiateStatic(file, acceptEncoding, { textType, staticDir, allowBrotli = true, gzipLevel = 6 }) {
  const accepts = (name) => new RegExp(`(^|[\\s,])${name}(\\s*(;|,|$))`).test(acceptEncoding || "");
  if (staticDir && textType) {
    if (allowBrotli && accepts("br") && fs.existsSync(`${file}.br`)) {
      return { body: fs.readFileSync(`${file}.br`), encoding: "br" };
    }
    if (accepts("gzip") && fs.existsSync(`${file}.gz`)) {
      return { body: fs.readFileSync(`${file}.gz`), encoding: "gzip" };
    }
  }
  const body = fs.readFileSync(file);
  if (textType && accepts("gzip")) {
    return { body: zlib.gzipSync(body, { level: gzipLevel }), encoding: "gzip" };
  }
  return { body, encoding: null };
}

// Cache-Control the production nginx template sends for a file, given its dist-relative POSIX path
// (`assets/x.js`, `landpage/normal_angel/index.html`, `index.html`). `/assets/` is content-hashed, so it is
// immutable. `/landpage/` keeps its original, unhashed file names, so it gets a day of freshness and then ETag
// revalidation, never `immutable`. Everything else is revalidated. `landpageCache: false` reproduces the old
// template (no `/landpage/` block, so `no-cache`) to measure the "before" of the landing-page cache change.
function cacheControlFor(relPath, { landpageCache = true } = {}) {
  if (relPath.startsWith("assets/")) return "public, max-age=31536000, immutable";
  if (landpageCache && relPath.startsWith("landpage/")) return "public, max-age=86400";
  return "no-cache";
}

// Playwright is pinned as a devDependency of frontend/ (@playwright/test). Resolve it from the current directory
// first, so running from frontend/ uses the pinned version, then fall back to a plain `playwright` install.
function loadChromium() {
  const fromCwd = createRequire(path.join(process.cwd(), "noop.js"));
  const attempts = [fromCwd, require];
  for (const req of attempts) {
    for (const id of ["@playwright/test", "playwright"]) {
      try {
        const mod = req(id);
        if (mod && mod.chromium) return mod.chromium;
      } catch {
        // try the next resolution path
      }
    }
  }
  throw new Error(
    "cannot resolve playwright: run from frontend/ after `corepack pnpm install`, " +
      "and set PLAYWRIGHT_BROWSERS_PATH to the Chromium download directory",
  );
}

module.exports = {
  REPO_ROOT,
  DEFAULT_DIST,
  parseArgs,
  intArg,
  readProxySecret,
  assertDist,
  generateSelfSignedCert,
  negotiateStatic,
  cacheControlFor,
  loadChromium,
};
