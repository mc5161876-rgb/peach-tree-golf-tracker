import fs from "node:fs";
import fsp from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { pipeline } from "node:stream";
import { startProdServer } from "./node_modules/vinext/dist/server/prod-server.js";
import { isHtmlNavigation, isServerStale, newestFileTime } from "./scripts/lib/tailnet.mjs";

const root = process.cwd();
const clientDir = path.resolve(root, "dist", "client");
const distDir = path.resolve(root, "dist");
const publicPort = Number.parseInt(process.env.PORT || "3000", 10);
const backendPort = Number.parseInt(process.env.BACKEND_PORT || String(publicPort + 1), 10);
const host = process.env.HOST || "127.0.0.1";

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".webmanifest", "application/manifest+json; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".webp", "image/webp"],
  [".avif", "image/avif"],
  [".gif", "image/gif"],
  [".ico", "image/x-icon"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
  [".ttf", "font/ttf"],
  [".txt", "text/plain; charset=utf-8"],
]);

function safeClientPath(rawPathname) {
  let pathname;
  try {
    pathname = decodeURIComponent(rawPathname);
  } catch {
    return null;
  }
  if (pathname === "/" || pathname.startsWith("/.vite/") || pathname === "/.vite") return null;
  const relative = pathname.replace(/^\/+/, "");
  const candidate = path.resolve(clientDir, relative);
  const prefix = clientDir.endsWith(path.sep) ? clientDir : clientDir + path.sep;
  if (candidate !== clientDir && !candidate.startsWith(prefix)) return null;
  return candidate;
}

async function serveClientFile(req, res, pathname) {
  if (req.method !== "GET" && req.method !== "HEAD") return false;
  const candidate = safeClientPath(pathname);
  if (!candidate) return false;
  let stat;
  try {
    stat = await fsp.stat(candidate);
  } catch {
    return false;
  }
  if (!stat.isFile()) return false;
  const ext = path.extname(candidate).toLowerCase();
  const headers = {
    "Content-Type": contentTypes.get(ext) || "application/octet-stream",
    "Content-Length": String(stat.size),
    "Cache-Control": pathname.startsWith("/assets/")
      ? "public, max-age=31536000, immutable"
      : "public, max-age=3600",
    "X-Content-Type-Options": "nosniff",
  };
  res.writeHead(200, headers);
  if (req.method === "HEAD") {
    res.end();
    return true;
  }
  pipeline(fs.createReadStream(candidate), res, (error) => {
    if (error) res.destroy(error);
  });
  return true;
}

function proxyToBackend(req, res) {
  const headers = { ...req.headers, host: `127.0.0.1:${backendPort}` };
  const upstream = http.request(
    {
      hostname: "127.0.0.1",
      port: backendPort,
      method: req.method,
      path: req.url,
      headers,
    },
    (upstreamResponse) => {
      res.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
      upstreamResponse.pipe(res);
    },
  );
  upstream.on("error", (error) => {
    if (!res.headersSent) res.writeHead(502, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(`Roundwell backend unavailable: ${error.message}`);
  });
  req.pipe(upstream);
}

if (!fs.existsSync(clientDir)) {
  throw new Error(`Roundwell production client build is missing: ${clientDir}`);
}

// The stale-build guard. This process imports the compiled server once at
// boot and serves dist/client from disk; rebuild underneath it and the
// in-memory SSR keeps emitting HTML that points at hashed filenames which no
// longer exist — the page arrives unstyled, or silently shows the old build.
// A server started before the newest build artifact cannot be serving it
// (2026-07-27: this exact trap shipped Mario an unstyled app). The walk over
// dist is throttled so the check costs nothing per ordinary request.
const serverStartedAt = Date.now();
let staleCheckedAt = 0;
let staleCached = false;
async function rebuiltUnderneath() {
  const now = Date.now();
  if (now - staleCheckedAt > 5000) {
    staleCached = isServerStale({
      serverStartedAt,
      newestBuildAt: await newestFileTime(distDir),
    });
    staleCheckedAt = now;
    if (staleCached) console.error("[roundwell-runtime] dist was rebuilt after this server started — refusing to serve the mismatch");
  }
  return staleCached;
}

const STALE_PAGE = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relaunch Peach Tree</title>
<style>body{margin:0;display:grid;place-items:center;min-height:100dvh;background:#0a251a;color:#fffdf4;font-family:system-ui,sans-serif}main{max-width:26rem;padding:2rem;text-align:center}h1{font-size:1.4rem}p{line-height:1.5;color:#d8d4c4}</style>
</head><body><main><h1>The app was rebuilt while this server was running</h1>
<p>This window would show a broken mix of old and new files, so it stopped instead.</p>
<p><b>Close this tab and open the app again</b> with the <i>OPEN Peach Tree Golf Score Tracker</i> shortcut — the fresh launch picks up the new build.</p>
</main></body></html>`;

const backend = await startProdServer({
  port: backendPort,
  host: "127.0.0.1",
  outDir: path.resolve(root, "dist"),
  purpose: "Roundwell backend",
});

const front = http.createServer(async (req, res) => {
  const rawUrl = req.url || "/";
  const pathname = rawUrl.split("?")[0];
  try {
    if (isHtmlNavigation(pathname, req.headers.accept) && (await rebuiltUnderneath())) {
      res.writeHead(503, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" });
      res.end(STALE_PAGE);
      return;
    }
    if (await serveClientFile(req, res, pathname)) return;
    proxyToBackend(req, res);
  } catch (error) {
    if (!res.headersSent) res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(`Roundwell runtime error: ${error instanceof Error ? error.message : String(error)}`);
  }
});

await new Promise((resolve, reject) => {
  front.once("error", reject);
  front.listen(publicPort, host, resolve);
});

console.log(`[roundwell-runtime] Ready at http://${host}:${publicPort}`);
console.log(`[roundwell-runtime] SSR backend at http://127.0.0.1:${backendPort}`);
console.log(`[roundwell-runtime] Static assets served from ${clientDir}`);

let stopping = false;
async function shutdown(signal) {
  if (stopping) return;
  stopping = true;
  console.log(`[roundwell-runtime] Stopping after ${signal}`);
  await Promise.allSettled([
    new Promise((resolve) => front.close(resolve)),
    new Promise((resolve) => backend.server.close(resolve)),
  ]);
  process.exit(0);
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
