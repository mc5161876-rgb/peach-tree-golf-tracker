/**
 * Serve the golf tracker to Mario's own devices over Tailscale HTTPS.
 *
 *   npm run serve:tailnet
 *
 * Everything is on demand: this starts the same production runtime the desktop
 * shortcut uses, then points `tailscale serve` at it. Nothing becomes a
 * service, and nothing is exposed to the public internet — `serve` shares only
 * within the tailnet, unlike `funnel`.
 *
 * The point of the preflight is that a phone out at a golf course is a bad
 * place to discover the desktop was serving last week's build.
 */

import { spawn } from "node:child_process";
import { execFile } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { promisify } from "node:util";

import {
  assetUrlsFrom,
  certDomainFrom,
  isServerStale,
  isTailscaleRunning,
  newestFileTime,
  serveTargetsPort,
} from "./lib/tailnet.mjs";

const run = promisify(execFile);

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = path.join(root, "dist");
const port = Number.parseInt(process.env.PORT || "3000", 10);
const tailscale = process.env.TAILSCALE_EXE
  || "C:\\Program Files\\Tailscale\\tailscale.exe";

let failed = false;
const check = (name, ok, detail) => {
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failed = true;
  return ok;
};

const fail = (message) => {
  console.error(`\n${message}\n`);
  process.exit(1);
};

async function tailscaleJson(...args) {
  const { stdout } = await run(tailscale, args, { maxBuffer: 8 * 1024 * 1024 });
  return JSON.parse(stdout);
}

async function tailscaleText(...args) {
  try {
    const { stdout } = await run(tailscale, args, { maxBuffer: 8 * 1024 * 1024 });
    return stdout;
  } catch (error) {
    // `serve status` exits non-zero when nothing is configured.
    return error.stdout ?? "";
  }
}

/** PID listening on a TCP port, and when that process started. */
async function listenerOn(portNumber) {
  const script = `
    $c = Get-NetTCPConnection -LocalPort ${portNumber} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $c) { '{}' | Write-Output; exit 0 }
    $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
    if (-not $p) { '{}' | Write-Output; exit 0 }
    # DateTimeOffset, not -UFormat %s: in Windows PowerShell 5.1 that format
    # treats a local timestamp as UTC, so the epoch comes back off by the
    # timezone offset and a healthy server reads as seven hours stale.
    $started = [DateTimeOffset]::new($p.StartTime).ToUnixTimeMilliseconds()
    @{ pid = $p.Id; name = $p.ProcessName; startedAt = $started } | ConvertTo-Json -Compress
  `;
  const { stdout } = await run("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script]);
  const parsed = JSON.parse(stdout.trim() || "{}");
  return parsed.pid ? parsed : null;
}

async function fetchStatus(url) {
  try {
    const response = await fetch(url, { redirect: "follow" });
    return { status: response.status, body: await response.text(), type: response.headers.get("content-type") ?? "" };
  } catch (error) {
    return { status: 0, body: "", type: "", error: error.message };
  }
}

console.log("\nPeach Tree · serve to the tailnet\n");
console.log("Preflight");

// 1. Tailscale up.
let status;
try {
  status = await tailscaleJson("status", "--json");
} catch (error) {
  check("tailscale reachable", false, error.message);
  fail("Tailscale is not responding. Start it and try again.");
}
check("tailscale running", isTailscaleRunning(status), `backend ${status.BackendState}`);

// 2. A name with a certificate, or there is no HTTPS to serve on.
const domain = certDomainFrom(status);
check("https certificate available", Boolean(domain), domain ?? "no CertDomains and no Self.DNSName");

// 3. A build to serve.
const newestBuildAt = await newestFileTime(distDir);
check("production build present", newestBuildAt !== null, newestBuildAt ? new Date(newestBuildAt).toLocaleString() : "run `npm run build`");

if (failed) fail("Preflight failed. Nothing was served.");

// 4. The staleness gate. This is the reason the script exists.
let listener = await listenerOn(port);
if (listener) {
  const stale = isServerStale({ serverStartedAt: listener.startedAt, newestBuildAt });
  if (stale) {
    console.log(
      `\n  The server on port ${port} (PID ${listener.pid}) started ${new Date(listener.startedAt).toLocaleString()},\n`
      + `  before the newest build artifact at ${new Date(newestBuildAt).toLocaleString()}.\n`
      + "  It is serving a build it never loaded — the classic unstyled-page trap.\n",
    );
    fail(
      `Refusing to serve a stale build.\n\n`
      + `  Stop it and run this again:\n`
      + `    Stop-Process -Id ${listener.pid} -Force\n`,
    );
  }
  check("server already running on a current build", true, `PID ${listener.pid}, started ${new Date(listener.startedAt).toLocaleString()}`);
} else {
  console.log(`\n  Nothing on port ${port}. Starting the production runtime…`);
  const child = spawn(process.execPath, [path.join(root, "local-runtime.mjs")], {
    cwd: root,
    detached: true,
    stdio: "ignore",
    env: { ...process.env, PORT: String(port) },
  });
  child.unref();

  let up = false;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await delay(750);
    if ((await fetchStatus(`http://127.0.0.1:${port}/`)).status === 200) { up = true; break; }
  }
  if (!check("production runtime started", up, up ? `PID ${child.pid}` : "did not answer within 30s")) {
    fail("The runtime did not come up. Nothing was served.");
  }
  listener = await listenerOn(port);
}

// 5. The app is actually healthy, not merely listening. Same shape as the
//    desktop launcher's check: the page, then its compiled stylesheet.
const local = await fetchStatus(`http://127.0.0.1:${port}/`);
check("app answers locally", local.status === 200, `HTTP ${local.status || local.error}`);
check("serving Peach Tree", /Peach Tree/.test(local.body), local.status === 200 ? "club name present" : "no body");

const assets = assetUrlsFrom(local.body);
let brokenAssets = 0;
for (const asset of assets) {
  if ((await fetchStatus(`http://127.0.0.1:${port}${asset}`)).status !== 200) brokenAssets += 1;
}
check("every referenced asset serves", assets.length > 0 && brokenAssets === 0, `${assets.length - brokenAssets}/${assets.length} at 200`);

if (failed) fail("The app is not healthy. Nothing was served.");

// 6. Point Tailscale at it. `serve`, never `funnel`.
const existing = await tailscaleText("serve", "status");
if (serveTargetsPort(existing, port)) {
  check("tailscale serve configured", true, `already pointing at ${port}`);
} else {
  try {
    await run(tailscale, ["serve", "--bg", String(port)], { maxBuffer: 8 * 1024 * 1024 });
    check("tailscale serve configured", true, `--bg ${port}`);
  } catch (error) {
    check("tailscale serve configured", false, (error.stderr || error.message).trim().split("\n")[0]);
    fail(
      "Could not configure `tailscale serve`. It usually needs an elevated shell on Windows.\n\n"
      + "  Run this once in an Administrator terminal, then re-run this script:\n"
      + `    & "${tailscale}" serve --bg ${port}\n`,
    );
  }
}

// 7. Prove it over the real HTTPS name, not just locally.
const url = `https://${domain}/`;
const remote = await fetchStatus(url);
check("tailnet https answers", remote.status === 200, `HTTP ${remote.status || remote.error}`);
check("tailnet serves the current build", /Peach Tree/.test(remote.body), remote.status === 200 ? "club name present" : "no body");

let remoteBroken = 0;
for (const asset of assetUrlsFrom(remote.body)) {
  if ((await fetchStatus(`https://${domain}${asset}`)).status !== 200) remoteBroken += 1;
}
check("tailnet assets serve", remoteBroken === 0, `${remoteBroken} broken`);

if (failed) fail("Serving is configured but the tailnet URL is not healthy.");

console.log(`\nOpen this on the iPhone:\n\n    ${url}\n`);
console.log("Then Share → Add to Home Screen to install it.");
console.log(`\nTo stop sharing:  & "${tailscale}" serve reset\n`);
