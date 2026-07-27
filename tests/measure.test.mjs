import assert from "node:assert/strict";
import test from "node:test";

import { readFile } from "node:fs/promises";

import {
  cardPointToCover,
  coverPointToCard,
  isWithinCourse,
  measureCrosshair,
  measureOrigin,
} from "../app/data/measure.ts";
import { greenCentre, latLonToCardPoint } from "../app/data/course-geometry.ts";
import { HOME_COURSE } from "../app/data/mock-course.ts";

// Read the atlas the same way the app's accessor does. Importing JSON through
// the accessor module would need import attributes that the bundler and the
// Node runner disagree about, and the data is what is under test here.
const sources = JSON.parse(
  await readFile(new URL("../public/course/peach-tree/sources.json", import.meta.url), "utf8"),
);

const COURSE_BOUNDS = sources.cardGeometry.bbox;
const CARD_SIZE = sources.cardGeometry.card;
const holeCardGeometry = (holeNumber) => {
  const { bbox, source, card, holes } = sources.cardGeometry;
  return { bbox, source, card, ...holes[String(holeNumber)] };
};
const centerline = (holeNumber) =>
  sources.centerlines.holes[String(holeNumber)].map(([lat, lon]) => ({ lat, lon }));
const holeTee = (holeNumber) => centerline(holeNumber)[0];
const holeGreen = (holeNumber) => centerline(holeNumber).at(-1);
const holeGreenPolygon = (holeNumber) =>
  sources.greens.holes[String(holeNumber)].points.map(([lat, lon]) => ({ lat, lon }));

const HOLE = 1;
const tee = holeTee(HOLE);
const green = holeGreen(HOLE);
const greenRing = holeGreenPolygon(HOLE);
const pin = greenCentre(greenRing);
const geometry = holeCardGeometry(HOLE);

/** Somewhere on the property — midway down the first fairway. */
const onCourse = { lat: (tee.lat + green.lat) / 2, lon: (tee.lon + green.lon) / 2 };
/** Downtown Marysville, a few miles off. */
const offCourse = { lat: 39.1457, lon: -121.5914 };

test("treats a fix as usable only when it is on the course", () => {
  assert.equal(isWithinCourse(tee, COURSE_BOUNDS), true);
  assert.equal(isWithinCourse(green, COURSE_BOUNDS), true);
  assert.equal(isWithinCourse(onCourse, COURSE_BOUNDS), true);
  assert.equal(isWithinCourse(offCourse, COURSE_BOUNDS), false);
});

test("falls back to the tee whenever there is no trustworthy position", () => {
  // GPS present and on the course — measure from the player.
  assert.deepEqual(measureOrigin(onCourse, tee, COURSE_BOUNDS), {
    point: onCourse,
    reference: "position",
  });

  // Denied, unsupported, or no fix yet all arrive here as null.
  assert.deepEqual(measureOrigin(null, tee, COURSE_BOUNDS), { point: tee, reference: "tee" });

  // AC-7 — a fix from off the property is worse than no fix, so it is refused
  // rather than used to produce a confidently wrong carry.
  assert.deepEqual(measureOrigin(offCourse, tee, COURSE_BOUNDS), { point: tee, reference: "tee" });
});

test("measures all three numbers from the right reference point in each case", () => {
  const located = measureCrosshair({ crosshair: pin, tee, green: greenRing, position: onCourse, bounds: COURSE_BOUNDS });
  const denied = measureCrosshair({ crosshair: pin, tee, green: greenRing, position: null, bounds: COURSE_BOUNDS });
  const stray = measureCrosshair({ crosshair: pin, tee, green: greenRing, position: offCourse, bounds: COURSE_BOUNDS });

  assert.equal(located.reference, "position");
  assert.equal(denied.reference, "tee");
  assert.equal(stray.reference, "tee");

  // AC-3 — standing halfway down the hole must read shorter than standing on
  // the tee, on every number — otherwise the reference point is not applied.
  for (const key of ["frontYards", "middleYards", "backYards"]) {
    assert.ok(
      located[key] < denied[key],
      `${key} from mid-fairway (${located[key]}) should be shorter than from the tee (${denied[key]})`,
    );
  }

  // An out-of-bounds fix must produce exactly the tee answer, not a third one.
  assert.deepEqual(stray, denied);

  // AC-4 — the tee fallback is numbers, never blanks.
  for (const result of [located, denied, stray]) {
    for (const key of ["frontYards", "middleYards", "backYards"]) {
      assert.equal(Number.isFinite(result[key]), true);
    }
    // Approaching from up the hole, the near edge is nearer than the far edge.
    assert.ok(result.frontYards < result.backYards);
  }
});

test("dragging the crosshair moves only the middle number", () => {
  const atPin = measureCrosshair({ crosshair: pin, tee, green: greenRing, position: null, bounds: COURSE_BOUNDS });
  // AC-6 — a pin dragged 50 yards back up the fairway shrinks the middle;
  // front and back stay locked to the real green edges.
  const draggedShort = { lat: pin.lat + (tee.lat - pin.lat) * 0.15, lon: pin.lon + (tee.lon - pin.lon) * 0.15 };
  const dragged = measureCrosshair({ crosshair: draggedShort, tee, green: greenRing, position: null, bounds: COURSE_BOUNDS });

  assert.ok(dragged.middleYards < atPin.middleYards, "middle should follow the crosshair");
  assert.equal(dragged.frontYards, atPin.frontYards);
  assert.equal(dragged.backYards, atPin.backYards);
});

test("middle from the tee with the pin on the green matches the scorecard", () => {
  const scorecard = HOME_COURSE.holes.find((hole) => hole.number === HOLE).yardages.black;
  const { middleYards, reference } = measureCrosshair({
    crosshair: pin,
    tee,
    green: greenRing,
    position: null,
    bounds: COURSE_BOUNDS,
  });

  assert.equal(reference, "tee");
  // Same ±15% calibration gate MAR-22 holds the centerlines to.
  const drift = Math.abs(middleYards - scorecard) / scorecard;
  assert.ok(drift < 0.15, `tee-to-pin measured ${middleYards} against a carded ${scorecard}`);
});

test("the default pin — the green centre — lands on every hole's card", () => {
  // AC-5 — the crosshair starts on the green, so its default position must
  // project inside the card for all 18 holes or it would spawn off-screen.
  for (let holeNumber = 1; holeNumber <= 18; holeNumber += 1) {
    const holeGeo = holeCardGeometry(holeNumber);
    const centre = greenCentre(holeGreenPolygon(holeNumber));
    const onCard = latLonToCardPoint(centre, holeGeo);
    assert.ok(
      onCard.x >= 0 && onCard.x <= CARD_SIZE.width && onCard.y >= 0 && onCard.y <= CARD_SIZE.height,
      `hole ${holeNumber} default pin fell outside the card at ${onCard.x.toFixed(1)}, ${onCard.y.toFixed(1)}`,
    );
  }
});

test("maps pointer positions through the cover crop, not a flat percentage", () => {
  // A tall narrow box crops the 900x1200 card vertically.
  const container = { width: 360, height: 440 };
  const scale = Math.max(container.width / CARD_SIZE.width, container.height / CARD_SIZE.height);

  // Centre of the box is the centre of the card either way — the centre is the
  // one point a naive percentage also gets right, so it proves nothing alone.
  const centre = coverPointToCard({ x: 180, y: 220 }, container, CARD_SIZE);
  assert.ok(Math.abs(centre.x - 450) < 1e-9);
  assert.ok(Math.abs(centre.y - 600) < 1e-9);

  // The top edge of the box is NOT the top of the card, because the overflow is
  // cropped. Reading it as 0% would be wrong by the cropped amount.
  const top = coverPointToCard({ x: 180, y: 0 }, container, CARD_SIZE);
  const croppedPixels = (CARD_SIZE.height * scale - container.height) / 2 / scale;
  assert.ok(top.y > 0, "the visible top edge sits below the card's top edge");
  assert.ok(Math.abs(top.y - croppedPixels) < 1e-9);

  // Round-trips both ways.
  for (const probe of [{ x: 12, y: 30 }, { x: 180, y: 220 }, { x: 359, y: 439 }]) {
    const returned = cardPointToCover(coverPointToCard(probe, container, CARD_SIZE), container, CARD_SIZE);
    assert.ok(Math.hypot(returned.x - probe.x, returned.y - probe.y) < 1e-9);
  }
});

test("places the tee and green markers inside the card for every hole", () => {
  for (let holeNumber = 1; holeNumber <= 18; holeNumber += 1) {
    const holeGeo = holeCardGeometry(holeNumber);
    for (const [label, point] of [["tee", holeTee(holeNumber)], ["green", holeGreen(holeNumber)]]) {
      const onCard = latLonToCardPoint(point, holeGeo);
      assert.ok(
        onCard.x >= 0 && onCard.x <= CARD_SIZE.width && onCard.y >= 0 && onCard.y <= CARD_SIZE.height,
        `hole ${holeNumber} ${label} fell outside the card at ${onCard.x.toFixed(1)}, ${onCard.y.toFixed(1)}`,
      );
    }
  }
});

test("geometry lookups agree with the hole they were asked for", () => {
  // A silent off-by-one here would put every yardage on the wrong hole.
  const second = holeCardGeometry(2);
  assert.notDeepEqual(geometry.center, second.center);
  assert.deepEqual(geometry.card, CARD_SIZE);
});
