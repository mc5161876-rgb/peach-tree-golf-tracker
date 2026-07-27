/**
 * Pure helpers behind `npm run serve:tailnet`.
 *
 * Kept separate from the runner so the one piece with real consequences — the
 * staleness check — can be tested without a Tailscale daemon or a live server.
 */

import { readdir, stat } from "node:fs/promises";
import path from "node:path";

/**
 * Newest modification time anywhere under a directory, in epoch milliseconds.
 * Returns null when the directory does not exist.
 */
export async function newestFileTime(directory) {
  let newest = null;

  async function walk(current) {
    let entries;
    try {
      entries = await readdir(current, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        await walk(full);
      } else {
        const info = await stat(full).catch(() => null);
        if (info && (newest === null || info.mtimeMs > newest)) newest = info.mtimeMs;
      }
    }
  }

  await walk(directory);
  return newest;
}

/**
 * Is a running server serving a build it never loaded?
 *
 * `local-runtime.mjs` imports the compiled server once at boot and then serves
 * `dist/client` from disk. Rebuild underneath it and the in-memory SSR keeps
 * emitting HTML that points at hashed filenames which no longer exist — the
 * page renders unstyled, or worse, looks fine and is silently the old build.
 * That trap has cost time on four separate occasions.
 *
 * A server started before the newest build artifact cannot be serving it. The
 * grace window absorbs the ordinary case where the build finishes a moment
 * before the process it is about to start.
 */
export function isServerStale({ serverStartedAt, newestBuildAt, graceMs = 4000 }) {
  if (serverStartedAt === null || serverStartedAt === undefined) return false;
  if (newestBuildAt === null || newestBuildAt === undefined) return false;
  return newestBuildAt > serverStartedAt + graceMs;
}

/**
 * Is this request a person navigating to a page, rather than a page pulling
 * in one of its assets?
 *
 * The stale-build guard must intercept navigations — that is where a human
 * can be told to relaunch — while letting asset requests through untouched,
 * or the guard page itself could never load. "/" is always a navigation; a
 * path with a file extension never is; anything else counts only when the
 * browser says it wants HTML.
 */
export function isHtmlNavigation(pathname, acceptHeader) {
  if (pathname === "/") return true;
  if (path.posix.extname(pathname) !== "") return false;
  return typeof acceptHeader === "string" && acceptHeader.includes("text/html");
}

/**
 * The HTTPS name Tailscale will answer on, from `tailscale status --json`.
 *
 * Prefers CertDomains, since a name without a certificate cannot serve HTTPS
 * no matter what MagicDNS reports. Falls back to the node's own DNS name with
 * its trailing dot removed.
 */
export function certDomainFrom(status) {
  const domains = status?.CertDomains;
  if (Array.isArray(domains) && domains.length > 0) return domains[0];
  const self = status?.Self?.DNSName;
  return self ? self.replace(/\.$/, "") : null;
}

/** Is the Tailscale backend actually up? */
export function isTailscaleRunning(status) {
  return status?.BackendState === "Running" && status?.Self?.Online === true;
}

/**
 * Does `tailscale serve status` already point at our port?
 *
 * The text form is parsed rather than the JSON because the JSON shape has
 * moved between Tailscale releases while the printed form has not.
 */
export function serveTargetsPort(serveStatusText, port) {
  if (!serveStatusText || /no serve config/i.test(serveStatusText)) return false;
  return new RegExp(`(?:127\\.0\\.0\\.1|localhost):${port}\\b`).test(serveStatusText);
}

/** Collect the asset URLs an HTML document references, for the health check. */
export function assetUrlsFrom(html) {
  const urls = new Set();
  for (const match of html.matchAll(/(?:href|src)="(\/assets\/[^"]+)"/g)) urls.add(match[1]);
  return [...urls];
}
