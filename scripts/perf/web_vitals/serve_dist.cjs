#!/usr/bin/env node
// Serve frontend/dist over HTTP/1.1 and proxy /api to the backend. Port of the scratch server.cjs.
//
// Purpose:
// Stand in for the production nginx shape during web-vitals measurements: static files from the built SPA,
// /api forwarded to a backend that runs with PRODUCTION=1 and the trusted proxy secret.
//
// Guarantees:
// * binds 127.0.0.1 only
// * --mode asis (default) matches the nginx template as written: gzip for text/html only, ETag, no Cache-Control
// * --mode tuned adds gzip for every text asset and immutable caching for /assets/ (plus no-cache for other files)
// * --mode dev proxies everything that is not /api to a Vite dev server (--vite-port)
// * /api requests get the X-Gallery-Proxy-Secret header from the secret file or GALLERY_PROXY_SECRET
// * no key material or secret is written into the repository
//
// Usage:
//   node scripts/perf/web_vitals/serve_dist.cjs --secret-file PATH [--dist DIR] [--port 8080]
//        [--backend-port 4701] [--mode asis|tuned|dev] [--vite-port 4833]
//   GALLERY_PROXY_SECRET=... node scripts/perf/web_vitals/serve_dist.cjs --mode tuned
//
// Run when:
// * measuring the built SPA behind a backend started as described in scripts/perf/web_vitals/README.md
// * comparing caching or compression shapes (asis vs tuned)

const http = require("http");
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const crypto = require("crypto");
const { parseArgs, intArg, readProxySecret, assertDist, DEFAULT_DIST } = require("./lib.cjs");

const args = parseArgs();
const MODE = typeof args.mode === "string" ? args.mode : "asis";
if (!["asis", "tuned", "dev"].includes(MODE)) throw new Error(`unknown --mode ${MODE} (asis|tuned|dev)`);
const PORT = intArg(args.port, 8080);
const BACKEND_PORT = intArg(args["backend-port"], 4701);
const VITE_PORT = intArg(args["vite-port"], 4833);
const DIST = path.resolve(typeof args.dist === "string" ? args.dist : DEFAULT_DIST);
const SECRET = readProxySecret(args);
assertDist(DIST);

const types = {
  ".js": "text/javascript",
  ".css": "text/css",
  ".html": "text/html",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".woff2": "font/woff2",
};

function proxy(req, res, port, extra) {
  const p = http.request(
    { host: "127.0.0.1", port, path: req.url, method: req.method, headers: { ...req.headers, ...extra } },
    (pr) => {
      res.writeHead(pr.statusCode, pr.headers);
      pr.pipe(res);
    },
  );
  p.on("error", () => {
    res.writeHead(502);
    res.end();
  });
  req.pipe(p);
}

http
  .createServer((req, res) => {
    if (req.url.startsWith("/api/")) return proxy(req, res, BACKEND_PORT, { "x-gallery-proxy-secret": SECRET });
    if (MODE === "dev") return proxy(req, res, VITE_PORT, {});
    let f = path.join(DIST, decodeURIComponent(req.url.split("?")[0]));
    if (!f.startsWith(DIST) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(DIST, "index.html");
    const ext = path.extname(f);
    const body = fs.readFileSync(f);
    const st = fs.statSync(f);
    const etag = '"' + crypto.createHash("md5").update(body).digest("hex").slice(0, 16) + '"';
    const h = { "content-type": types[ext] || "application/octet-stream", etag, "last-modified": st.mtime.toUTCString() };
    if (MODE === "tuned") h["cache-control"] = f.includes("/assets/") ? "public, max-age=31536000, immutable" : "no-cache";
    if (req.headers["if-none-match"] === etag) {
      res.writeHead(304, h);
      return res.end();
    }
    const gz = MODE === "tuned" ? !!types[ext] && ext !== ".woff2" : ext === ".html";
    if (gz && /gzip/.test(req.headers["accept-encoding"] || "")) {
      h["content-encoding"] = "gzip";
      res.writeHead(200, h);
      return res.end(zlib.gzipSync(body, { level: 6 }));
    }
    res.writeHead(200, h);
    res.end(body);
  })
  .listen(PORT, "127.0.0.1", () =>
    console.log(`${MODE} on ${PORT} (dist ${DIST}, backend 127.0.0.1:${BACKEND_PORT})`),
  );
