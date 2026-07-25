import assert from "node:assert/strict";
import { access, readFile, stat } from "node:fs/promises";
import test from "node:test";

async function fetchPath(path = "/", accept = "text/html") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

const render = () => fetchPath("/");

test("server-renders the Peach Tree product shell and mobile metadata", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Peach Tree Golf &(?:amp;)? Country Club[^<]*Personal golf scoring<\/title>/i);
  assert.match(html, /Peach Tree/);
  assert.match(html, /Start a round/);
  assert.match(html, /manifest\.webmanifest/);
  assert.match(html, /mobile-web-app-capable/);
  assert.match(html, /apple-mobile-web-app-title/);
  assert.match(html, /og\.png/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("keeps prototype data, modes, and PWA configuration explicit", async () => {
  const [page, layout, course, manifestResponse, packageText, readme] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/data/mock-course.ts", import.meta.url), "utf8"),
    fetchPath("/manifest.webmanifest", "application/manifest+json"),
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

  assert.equal(manifestResponse.status, 200);
  const manifestText = await manifestResponse.text();
  const manifest = JSON.parse(manifestText);
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.orientation, "portrait-primary");
  assert.equal(manifest.short_name, "Peach Tree");
  assert.ok(Array.isArray(manifest.icons) && manifest.icons.length > 0);
  // The old static manifest shipped a mis-encoded em-dash. Generated JSON
  // cannot regress that way, but assert it so nobody reintroduces a static file.
  assert.doesNotMatch(manifestText, /â€”|Ã|�/);

  assert.doesNotMatch(packageText, /react-loading-skeleton|drizzle/);
  assert.match(readme, /app\/data\/mock-course\.ts/);
  assert.match(readme, /Prototype Lab/);

  await assert.rejects(access(new URL("../app/_sites-preview/SkeletonPreview.tsx", import.meta.url)));
});

test("brands the app to the club from a single identity constant", async () => {
  const [page, layout, course, manifestModule] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/data/mock-course.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/manifest.ts", import.meta.url), "utf8"),
  ]);

  // CLUB_IDENTITY is the one place the club is named.
  assert.match(course, /export const CLUB_IDENTITY = \{/);
  assert.match(course, /wordmark: "Peach Tree"/);
  assert.match(course, /crest: "PT"/);

  // Consumers must read from it rather than repeating the club's name. If the
  // club renames, editing CLUB_IDENTITY has to be enough.
  for (const [name, source] of [["layout.tsx", layout], ["manifest.ts", manifestModule]]) {
    assert.doesNotMatch(source, /Peach Tree|Marysville/, `${name} should read club names from CLUB_IDENTITY, not hardcode them`);
    assert.match(source, /CLUB_IDENTITY|CLUB_PAGE_TITLE|CLUB_DESCRIPTION/, `${name} should import the identity constant`);
  }

  // page.tsx is allowed exactly one legacy reference: the localStorage key.
  // Renaming it would orphan every round Mario has already recorded, so it
  // stays put deliberately. See MAR-20.
  const pageWithoutStorageKey = page.replace(/const STORAGE_KEY = "[^"]*";/, "");
  assert.doesNotMatch(pageWithoutStorageKey, /Peach Tree|Marysville/, "page.tsx should read club names from CLUB_IDENTITY");
  assert.match(page, /const STORAGE_KEY = "roundwell-prototype-v2-peach-tree";/, "storage key must not change — it would orphan saved rounds");

  // The retired product name must not survive anywhere user-visible.
  assert.doesNotMatch(pageWithoutStorageKey, /Roundwell/i);
  assert.doesNotMatch(layout, /Roundwell/i);
  assert.doesNotMatch(manifestModule, /Roundwell/i);

  // The "Name & icon concepts" screen is gone.
  assert.doesNotMatch(page, /NameConcepts|showConcepts|concepts-link|mini-concepts/);
});

test("renders the club identity in the served shell", async () => {
  const html = await (await render()).text();
  assert.match(html, /Peach Tree/);
  assert.match(html, /Golf &(?:amp;)? Country Club · Marysville/);
  assert.doesNotMatch(html, /Roundwell/i);
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
