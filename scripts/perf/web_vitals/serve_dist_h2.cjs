#!/usr/bin/env node
// Serve frontend/dist over TLS + HTTP/2 (HTTP/1.1 still allowed). Port of the scratch h2server2.cjs.
//
// Purpose:
// Match what nginx `listen 443 ssl http2` with pre-compressed (brotli/gzip) and immutable /assets/ gives the browser. Use this for
// the measurement profiles, which the standard describes as HTTP/2 + gzip + immutable /assets/.
//
// Guarantees:
// * binds 127.0.0.1 only
// * text assets under /assets/ are served from a pre-compressed `.br` (client sends `br`) or `.gz` sibling, like nginx
//   `brotli_static on; gzip_static on;`, and fall back to dynamic gzip; other text files use dynamic gzip.
//   Cache-Control: immutable under /assets/, `public, max-age=86400` under /landpage/ (unhashed names, so never
//   immutable), no-cache elsewhere. Every static file carries an ETag and answers If-None-Match with 304, like nginx.
//   `--no-brotli` mimics a server without the module; `--no-landpage-cache` mimics the old template without a
//   /landpage/ block (no-cache, so every landing-page reload revalidates).
// * /api is forwarded to the backend with X-Gallery-Proxy-Secret; hop-by-hop headers are dropped
// * with no --cert/--key, a self-signed localhost certificate is generated into a temp directory that is
//   removed on exit; pass ignoreHTTPSErrors in the browser (the measurement scripts already do)
//
// Usage:
//   node scripts/perf/web_vitals/serve_dist_h2.cjs --secret-file PATH [--dist DIR] [--port 8443]
//        [--backend-port 4701] [--cert CERT.pem --key KEY.pem] [--no-brotli] [--no-landpage-cache]
//
// Manual certificate (equivalent to what the script does when --cert/--key are omitted):
//   openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 2 \
//     -subj /CN=localhost -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
//
// Run when:
// * taking the HTTP/2 measurement profile for home, album and lightbox flows
// * checking that a change is not sensitive to the HTTP/1.1 vs HTTP/2 transport

const http2 = require("http2");
const http = require("http");
const fs = require("fs");
const path = require("path");
const {
  parseArgs,
  intArg,
  readProxySecret,
  assertDist,
  generateSelfSignedCert,
  negotiateStatic,
  cacheControlFor,
  DEFAULT_DIST,
} = require("./lib.cjs");

const args = parseArgs();
const PORT = intArg(args.port, 8443);
const BACKEND_PORT = intArg(args["backend-port"], 4701);
const DIST = path.resolve(typeof args.dist === "string" ? args.dist : DEFAULT_DIST);
const SECRET = readProxySecret(args);
const ALLOW_BROTLI = !args["no-brotli"];
const LANDPAGE_CACHE = !args["no-landpage-cache"];
assertDist(DIST);

let tls;
if (typeof args.cert === "string" && typeof args.key === "string") {
  tls = { cert: fs.readFileSync(path.resolve(args.cert)), key: fs.readFileSync(path.resolve(args.key)) };
} else {
  tls = generateSelfSignedCert();
}

const types = {
  ".js": "text/javascript",
  ".css": "text/css",
  ".html": "text/html",
  ".svg": "image/svg+xml",
  ".json": "application/json",
};

const srv = http2.createSecureServer({ key: tls.key, cert: tls.cert, allowHTTP1: true });
srv.on("request", (req, res) => {
  if (req.url.startsWith("/api/")) {
    const headers = {};
    for (const [k, v] of Object.entries(req.headers)) if (!k.startsWith(":")) headers[k] = v;
    const p = http.request(
      {
        host: "127.0.0.1",
        port: BACKEND_PORT,
        path: req.url,
        method: req.method,
        headers: { ...headers, "x-gallery-proxy-secret": SECRET },
      },
      (pr) => {
        const h = {};
        for (const [k, v] of Object.entries(pr.headers)) {
          if (!["connection", "keep-alive", "transfer-encoding"].includes(k)) h[k] = v;
        }
        res.writeHead(pr.statusCode, h);
        pr.pipe(res);
      },
    );
    p.on("error", () => {
      res.writeHead(502);
      res.end();
    });
    return req.pipe(p);
  }
  let f = path.join(DIST, decodeURIComponent(req.url.split("?")[0]));
  if (!f.startsWith(DIST) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(DIST, "index.html");
  const ext = path.extname(f);
  const rel = path.relative(DIST, f).split(path.sep).join("/");
  const inAssets = rel.startsWith("assets/");
  const st = fs.statSync(f);
  const etag = `"${st.size.toString(16)}-${Math.floor(st.mtimeMs).toString(16)}"`;
  const h = {
    "content-type": types[ext] || "application/octet-stream",
    "cache-control": cacheControlFor(rel, { landpageCache: LANDPAGE_CACHE }),
    etag,
    "last-modified": st.mtime.toUTCString(),
    vary: "Accept-Encoding",
  };
  if (req.headers["if-none-match"] === etag) {
    res.writeHead(304, h);
    return res.end();
  }
  const { body, encoding } = negotiateStatic(f, req.headers["accept-encoding"], {
    textType: !!types[ext],
    staticDir: inAssets,
    allowBrotli: ALLOW_BROTLI,
  });
  if (encoding) h["content-encoding"] = encoding;
  res.writeHead(200, h);
  res.end(body);
});
srv.listen(PORT, "127.0.0.1", () =>
  console.log(`h2 on ${PORT} (dist ${DIST}, backend 127.0.0.1:${BACKEND_PORT}, https)`),
);
