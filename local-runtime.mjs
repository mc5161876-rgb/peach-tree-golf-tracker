import fs from "node:fs";
import fsp from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { pipeline } from "node:stream";
import { startProdServer } from "./node_modules/vinext/dist/server/prod-server.js";

const root = process.cwd();
const clientDir = path.resolve(root, "dist", "client");
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
