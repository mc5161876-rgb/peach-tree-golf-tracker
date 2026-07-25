import assert from "node:assert/strict";
import { access, readFile, stat } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the Roundwell product shell and mobile metadata", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Roundwell[^<]*Personal Golf Scoring<\/title>/i);
  assert.match(html, /Roundwell/);
  assert.match(html, /Start a round/);
  assert.match(html, /manifest\.webmanifest/);
  assert.match(html, /mobile-web-app-capable/);
  assert.match(html, /apple-mobile-web-app-title/);
  assert.match(html, /og\.png/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("keeps prototype data, modes, and PWA configuration explicit", async () => {
  const [page, layout, course, manifestText, packageText, readme] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/data/mock-course.ts", import.meta.url), "utf8"),
    readFile(new URL("../public/manifest.webmanifest", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
    readFile(new URL("../README.md", import.meta.url), "utf8"),
  ]);

  assert.equal(course.match(/\bhole\(\d+,/g)?.length, 18);
  assert.match(course, /Peach Tree Golf & Country Club/);
  assert.match(course, /Marysville, California/);
  assert.match(course, /black: 407, blue: 401, white: 386/);
  assert.match(course, /TEE_OPTIONS/);
  assert.doesNotMatch(`${page}\n${course}`, /Cypress Meadow/);
  assert.match(page, /type ScoreMethod = "stepper" \| "numbers" \| "relative"/);
  assert.match(page, /type RoundLayout = "focus" \| "grid"/);
  assert.match(page, /type TagBehavior = "manual" \| "smart"/);
  assert.match(page, /localStorage/);
  assert.match(layout, /viewportFit: "cover"/);

  const manifest = JSON.parse(manifestText);
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.orientation, "portrait-primary");
  assert.equal(manifest.short_name, "Roundwell");
  assert.ok(Array.isArray(manifest.icons) && manifest.icons.length > 0);

  assert.doesNotMatch(packageText, /react-loading-skeleton|drizzle/);
  assert.match(readme, /app\/data\/mock-course\.ts/);
  assert.match(readme, /Prototype Lab/);

  await assert.rejects(access(new URL("../app/_sites-preview/SkeletonPreview.tsx", import.meta.url)));
});

test("ships premium birdie and eagle celebrations without blocking scoring", async () => {
  const [page, css, birdie, eagle] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    stat(new URL("../public/celebrations/birdie.png", import.meta.url)),
    stat(new URL("../public/celebrations/eagle.png", import.meta.url)),
  ]);

  assert.match(page, /relativeScore <= -2\) playCelebration\("eagle"\)/);
  assert.match(page, /relativeScore === -1\) playCelebration\("birdie"\)/);
  assert.match(css, /pointer-events: none/);
  assert.match(css, /@keyframes birdie-flight/);
  assert.match(css, /@keyframes eagle-sweep/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.ok(birdie.size > 500_000, "birdie asset should retain high-resolution detail");
  assert.ok(eagle.size > 500_000, "eagle asset should retain high-resolution detail");
});

test("ships the Peach Tree course atlas with real-source attribution", async () => {
  const [page, css, course, sourceText, overview, holeImages, illustratedHoleImages] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/data/mock-course.ts", import.meta.url), "utf8"),
    readFile(new URL("../public/course/peach-tree/sources.json", import.meta.url), "utf8"),
    stat(new URL("../public/course/peach-tree/course-aerial.webp", import.meta.url)),
    Promise.all(Array.from({ length: 18 }, (_, index) => stat(new URL(`../public/course/peach-tree/hole-${String(index + 1).padStart(2, "0")}.webp`, import.meta.url)))),
    Promise.all(Array.from({ length: 18 }, (_, index) => stat(new URL(`../public/course/peach-tree/hole-${String(index + 1).padStart(2, "0")}-illustrated.png`, import.meta.url)))),
  ]);

  const sources = JSON.parse(sourceText);
  assert.equal(sources.imagery.publicDomain, true);
  assert.match(sources.imagery.source, /USDA NAIP via USGS/);
  assert.match(sources.centerlines.source, /OpenStreetMap contributors/);
  assert.equal(Object.keys(sources.centerlines.holes).length, 18);
  assert.equal(sources.illustrations.authoritative, false);
  assert.equal(sources.illustrations.files.length, 18);
  assert.ok(overview.size > 100_000, "course overview should retain aerial detail");
  assert.equal(holeImages.length, 18);
  assert.equal(illustratedHoleImages.length, 18);
  assert.ok(holeImages.every((image) => image.size > 25_000), "every hole guide should retain useful aerial detail");
  assert.ok(illustratedHoleImages.every((image) => image.size > 500_000), "every AI hole concept should retain premium visual detail");
  assert.match(page, /className="hole-atlas-card"/);
  assert.match(page, /className="bottom-sheet hole-guide-sheet"/);
  assert.match(page, /className="hole-guide-mode"/);
  assert.match(page, /setHoleVisualMode\("aerial"\)/);
  assert.match(page, /event\.key === "Escape"/);
  assert.match(page, /event\.key !== "Tab"/);
  assert.match(page, /holeAtlasTriggerRef/);
  assert.match(course, /Illustrated course guide/);
  assert.match(css, /\.hole-atlas-card/);
  assert.match(css, /\.hole-guide-visual/);
  assert.match(css, /\.hole-local-note/);
  assert.match(course, /scorecardNote/);
  assert.match(course, /dogleg left begins earlier/);
});
