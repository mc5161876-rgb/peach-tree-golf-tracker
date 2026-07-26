import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  cardPointToLatLon,
  distanceYards,
  latLonToCardPoint,
} from "../app/data/course-geometry.ts";
import { HOME_COURSE } from "../app/data/mock-course.ts";

const sources = JSON.parse(
  await readFile(new URL("../public/course/peach-tree/sources.json", import.meta.url), "utf8"),
);

const HOLE_NUMBERS = Array.from({ length: 18 }, (_, index) => index + 1);

/**
 * The exported geometry keeps values shared by every hole at the top level and
 * only what is unique to a hole beside that hole. Consumers work with one flat
 * object, so compose it here rather than duplicating eight numbers 18 times in
 * the data file.
 */
function holeGeometry(holeNumber) {
  const { bbox, source, card, holes } = sources.cardGeometry;
  return { bbox, source, card, ...holes[String(holeNumber)] };
}

const centerline = (holeNumber) =>
  sources.centerlines.holes[String(holeNumber)].map(([lat, lon]) => ({ lat, lon }));

const blackYardage = (holeNumber) =>
  HOME_COURSE.holes.find((hole) => hole.number === holeNumber).yardages.black;

test("exports card geometry for all 18 holes", () => {
  const geometry = sources.cardGeometry;
  assert.ok(geometry, "sources.json should carry a cardGeometry block");
  assert.deepEqual(geometry.bbox, {
    minLon: -121.553,
    minLat: 39.135,
    maxLon: -121.53,
    maxLat: 39.152,
  });
  assert.deepEqual(geometry.card, { width: 900, height: 1200 });
  assert.equal(Object.keys(geometry.holes).length, 18);

  for (const holeNumber of HOLE_NUMBERS) {
    const hole = holeGeometry(holeNumber);
    assert.ok(hole.scale > 0, `hole ${holeNumber} needs a positive scale`);
    // unit and perp must stay orthonormal or the rotation is not invertible.
    assert.ok(
      Math.abs(Math.hypot(hole.unit.x, hole.unit.y) - 1) < 1e-9,
      `hole ${holeNumber} unit vector should be normalised`,
    );
    assert.ok(
      Math.abs(hole.unit.x * hole.perp.x + hole.unit.y * hole.perp.y) < 1e-9,
      `hole ${holeNumber} perp vector should be perpendicular to unit`,
    );
  }
});

test("round-trips card pixels through real coordinates within a pixel", () => {
  // Corners, centre, and off-centre points — a transform can be wrong in a way
  // that still round-trips at the centre alone.
  const probes = [
    { x: 0, y: 0 },
    { x: 900, y: 0 },
    { x: 0, y: 1200 },
    { x: 900, y: 1200 },
    { x: 450, y: 600 },
    { x: 123, y: 987 },
    { x: 781, y: 246 },
  ];

  let worst = 0;
  for (const holeNumber of HOLE_NUMBERS) {
    const geometry = holeGeometry(holeNumber);
    for (const probe of probes) {
      const returned = latLonToCardPoint(cardPointToLatLon(probe, geometry), geometry);
      const drift = Math.hypot(returned.x - probe.x, returned.y - probe.y);
      worst = Math.max(worst, drift);
      assert.ok(
        drift < 1,
        `hole ${holeNumber} drifted ${drift.toFixed(4)}px round-tripping (${probe.x}, ${probe.y})`,
      );
    }
  }

  console.log(`Round-trip: worst drift across 18 holes ${worst.toFixed(6)}px`);
});

test("anchors the tee and green markers to their centerline coordinates", () => {
  let worst = 0;
  for (const holeNumber of HOLE_NUMBERS) {
    const geometry = holeGeometry(holeNumber);
    const points = centerline(holeNumber);

    for (const [label, position] of [
      ["tee", points[0]],
      ["green", points[points.length - 1]],
    ]) {
      const returned = cardPointToLatLon(latLonToCardPoint(position, geometry), geometry);
      const drift = distanceYards(position, returned);
      worst = Math.max(worst, drift);
      assert.ok(
        drift < 3,
        `hole ${holeNumber} ${label} marker landed ${drift.toFixed(3)} yards from its coordinate`,
      );
    }
  }

  console.log(`Anchors: worst tee/green drift ${worst.toFixed(6)} yards`);
});

test("keeps centerline lengths within 15% of the scorecard", () => {
  const rows = HOLE_NUMBERS.map((holeNumber) => {
    const points = centerline(holeNumber);
    let computed = 0;
    for (let index = 1; index < points.length; index += 1) {
      computed += distanceYards(points[index - 1], points[index]);
    }

    const scorecard = blackYardage(holeNumber);
    return {
      holeNumber,
      points: points.length,
      computed,
      scorecard,
      driftPercent: ((computed - scorecard) / scorecard) * 100,
    };
  });

  // Printed whether or not it passes: this is the number that says how far the
  // map data can be trusted, and silent drift is the failure mode to catch.
  console.log("Calibration — OpenStreetMap centerline vs Black-tee scorecard");
  for (const row of rows) {
    const drift = `${row.driftPercent >= 0 ? "+" : ""}${row.driftPercent.toFixed(1)}%`;
    console.log(
      `  hole ${String(row.holeNumber).padStart(2)} · ${row.points} pts · ` +
        `${row.computed.toFixed(0).padStart(3)} yd computed vs ${String(row.scorecard).padStart(3)} yd card · ${drift}`,
    );
  }

  const failures = rows.filter((row) => Math.abs(row.driftPercent) > 15);
  assert.deepEqual(
    failures.map((row) => `hole ${row.holeNumber} at ${row.driftPercent.toFixed(1)}%`),
    [],
    "holes outside 15% mean the centerline no longer matches the course",
  );
});
