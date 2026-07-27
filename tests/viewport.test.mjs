import assert from "node:assert/strict";
import test from "node:test";

import {
  IDENTITY_VIEW,
  MAX_ZOOM,
  MIN_ZOOM,
  clampView,
  contentToScreen,
  panBy,
  screenToContent,
  zoomAt,
} from "../app/data/viewport.ts";

/** The hole guide box at phone width, roughly. */
const BOX = { width: 360, height: 480 };

const close = (a, b, message) => assert.ok(Math.abs(a - b) < 1e-9, `${message}: ${a} vs ${b}`);

test("zooming keeps the point under the fingers stationary", () => {
  // Pinch centred on the green, two-thirds up the card and left of centre.
  const focal = { x: 120, y: 140 };
  const before = screenToContent(focal, IDENTITY_VIEW);

  const zoomed = zoomAt(IDENTITY_VIEW, focal, 2, BOX);
  const after = screenToContent(focal, zoomed);

  close(after.x, before.x, "focal content x moved");
  close(after.y, before.y, "focal content y moved");
  assert.equal(zoomed.z, 2);
});

test("zoom is clamped to its limits", () => {
  const tooFar = zoomAt(IDENTITY_VIEW, { x: 180, y: 240 }, 100, BOX);
  assert.equal(tooFar.z, MAX_ZOOM);

  const tooClose = zoomAt(tooFar, { x: 180, y: 240 }, 0.0001, BOX);
  assert.equal(tooClose.z, MIN_ZOOM);
  // Fully zoomed out, the card must sit exactly in the box again.
  assert.deepEqual(tooClose, IDENTITY_VIEW);
});

test("the card always fills the box — no gaps at any edge", () => {
  // Try to drag the content far off in every direction at 2x.
  const zoomed = zoomAt(IDENTITY_VIEW, { x: 180, y: 240 }, 2, BOX);
  for (const delta of [
    { x: 5000, y: 5000 },
    { x: -5000, y: -5000 },
    { x: 5000, y: -5000 },
    { x: -5000, y: 5000 },
  ]) {
    const panned = panBy(zoomed, delta, BOX);
    assert.ok(panned.tx <= 0, "left edge gap");
    assert.ok(panned.ty <= 0, "top edge gap");
    assert.ok(panned.tx >= BOX.width * (1 - panned.z), "right edge gap");
    assert.ok(panned.ty >= BOX.height * (1 - panned.z), "bottom edge gap");
  }
});

test("clamping is exactly what pinch and wheel both flow through", () => {
  const wild = clampView({ z: 9, tx: 300, ty: -99999 }, BOX);
  assert.equal(wild.z, MAX_ZOOM);
  assert.equal(wild.tx, 0);
  close(wild.ty, BOX.height * (1 - MAX_ZOOM), "ty should clamp to the bottom edge");
});

test("screen and content coordinates round-trip at any view", () => {
  const view = panBy(zoomAt(IDENTITY_VIEW, { x: 90, y: 400 }, 2.7, BOX), { x: -31, y: 17 }, BOX);
  for (const probe of [{ x: 0, y: 0 }, { x: 180, y: 240 }, { x: 359, y: 479 }]) {
    const there = contentToScreen(screenToContent(probe, view), view);
    close(there.x, probe.x, "round-trip x");
    close(there.y, probe.y, "round-trip y");
  }
});

test("a pin placed at 1x reads the same spot when placed again zoomed in", () => {
  // The regression that matters: zooming must not change WHERE a tap lands,
  // only how big it looks. Pick a screen point at rest, find its content
  // position, zoom so that content point is on screen, and tap it again.
  const restingTap = { x: 200, y: 130 };
  const content = screenToContent(restingTap, IDENTITY_VIEW);

  const view = zoomAt(IDENTITY_VIEW, restingTap, 3, BOX);
  const zoomedTap = contentToScreen(content, view);
  const contentAgain = screenToContent(zoomedTap, view);

  close(contentAgain.x, content.x, "content x drifted under zoom");
  close(contentAgain.y, content.y, "content y drifted under zoom");
});
