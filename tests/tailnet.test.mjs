import assert from "node:assert/strict";
import { mkdtemp, mkdir, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assetUrlsFrom,
  certDomainFrom,
  isHtmlNavigation,
  isServerStale,
  isTailscaleRunning,
  newestFileTime,
  serveTargetsPort,
} from "../scripts/lib/tailnet.mjs";

test("intercepts navigations for the stale guard, never asset requests", () => {
  // The root is a navigation no matter what the client claims to accept —
  // the shortcut opens exactly this URL.
  assert.equal(isHtmlNavigation("/", undefined), true);
  assert.equal(isHtmlNavigation("/", "*/*"), true);

  // Assets must always pass through, or the guard page itself could break
  // other resources; anything with a file extension is never intercepted.
  assert.equal(isHtmlNavigation("/assets/index-BsKdPn4A.css", "text/html,*/*"), false);
  assert.equal(isHtmlNavigation("/course/peach-tree/hole-02.webp", "image/webp"), false);
  assert.equal(isHtmlNavigation("/favicon.ico", "*/*"), false);

  // Extensionless paths are navigations exactly when the browser asks for HTML.
  assert.equal(isHtmlNavigation("/history", "text/html,application/xhtml+xml"), true);
  assert.equal(isHtmlNavigation("/history", "application/json"), false);
  assert.equal(isHtmlNavigation("/history", undefined), false);
});

test("refuses a server that started before the newest build", () => {
  const started = Date.parse("2026-07-26T08:00:00Z");

  // The trap: rebuild an hour after the server booted.
  assert.equal(
    isServerStale({ serverStartedAt: started, newestBuildAt: started + 3_600_000 }),
    true,
    "a build newer than the running process must be refused",
  );

  // The normal case: the server booted moments after the build finished.
  assert.equal(
    isServerStale({ serverStartedAt: started + 3000, newestBuildAt: started }),
    false,
  );

  // A build finishing a beat before the process it is about to start is
  // ordinary, not stale — that is what the grace window is for.
  assert.equal(
    isServerStale({ serverStartedAt: started, newestBuildAt: started + 1500 }),
    false,
    "the grace window must absorb a build finishing just before launch",
  );
  assert.equal(
    isServerStale({ serverStartedAt: started, newestBuildAt: started + 1500, graceMs: 0 }),
    true,
    "with no grace window the same pair is stale",
  );

  // Nothing running, or nothing built: not a staleness problem.
  assert.equal(isServerStale({ serverStartedAt: null, newestBuildAt: started }), false);
  assert.equal(isServerStale({ serverStartedAt: started, newestBuildAt: null }), false);
});

test("finds the newest file anywhere under the build directory", async () => {
  const base = await mkdtemp(path.join(tmpdir(), "tailnet-"));
  const nested = path.join(base, "client", "assets");
  await mkdir(nested, { recursive: true });

  const old = path.join(base, "old.js");
  const fresh = path.join(nested, "fresh.css");
  await writeFile(old, "a");
  await writeFile(fresh, "b");

  const oldTime = new Date("2026-07-01T00:00:00Z");
  const freshTime = new Date("2026-07-26T00:00:00Z");
  await utimes(old, oldTime, oldTime);
  await utimes(fresh, freshTime, freshTime);

  // The newest file is nested two levels down — a shallow check would miss it,
  // and a missed rebuild is exactly the failure this guards against.
  assert.equal(await newestFileTime(base), freshTime.getTime());
  assert.equal(await newestFileTime(path.join(base, "does-not-exist")), null);
});

test("reads the certificate domain, preferring one that can actually serve https", () => {
  assert.equal(
    certDomainFrom({ CertDomains: ["desktop-1ofknrj.tail98ce4e.ts.net"], Self: { DNSName: "other.ts.net." } }),
    "desktop-1ofknrj.tail98ce4e.ts.net",
  );
  // Falls back to the node's own name, trailing dot removed.
  assert.equal(certDomainFrom({ Self: { DNSName: "desktop-1ofknrj.tail98ce4e.ts.net." } }), "desktop-1ofknrj.tail98ce4e.ts.net");
  assert.equal(certDomainFrom({ CertDomains: [] }), null);
  assert.equal(certDomainFrom({}), null);
});

test("treats the backend as up only when it is running and online", () => {
  assert.equal(isTailscaleRunning({ BackendState: "Running", Self: { Online: true } }), true);
  assert.equal(isTailscaleRunning({ BackendState: "Stopped", Self: { Online: true } }), false);
  assert.equal(isTailscaleRunning({ BackendState: "Running", Self: { Online: false } }), false);
  assert.equal(isTailscaleRunning({}), false);
});

test("recognises an existing serve config for our port", () => {
  assert.equal(serveTargetsPort("No serve config", 3000), false);
  assert.equal(serveTargetsPort("", 3000), false);
  assert.equal(
    serveTargetsPort("https://desktop.ts.net (tailnet only)\n|-- / proxy http://127.0.0.1:3000", 3000),
    true,
  );
  assert.equal(
    serveTargetsPort("https://desktop.ts.net (tailnet only)\n|-- / proxy http://localhost:3000", 3000),
    true,
  );
  // A config pointing somewhere else must not be mistaken for ours.
  assert.equal(
    serveTargetsPort("https://desktop.ts.net (tailnet only)\n|-- / proxy http://127.0.0.1:8080", 3000),
    false,
  );
  // 30000 must not satisfy a check for 3000.
  assert.equal(
    serveTargetsPort("|-- / proxy http://127.0.0.1:30000", 3000),
    false,
  );
});

test("collects referenced assets for the health check", () => {
  const html = `<link rel="stylesheet" href="/assets/index-DsVxLhML.css"/><script src="/assets/page-Cg4yWs72.js"></script><img src="/icons/crest-84.png"/><script src="/assets/page-Cg4yWs72.js"></script>`;
  assert.deepEqual(assetUrlsFrom(html), ["/assets/index-DsVxLhML.css", "/assets/page-Cg4yWs72.js"]);
});
