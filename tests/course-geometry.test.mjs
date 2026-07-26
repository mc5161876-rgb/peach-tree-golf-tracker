import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  cardPointToLatLon,
  distanceYards,
  greenCentre,
  greenDistances,
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

const greenPolygon = (holeNumber) =>
  sources.greens.holes[String(holeNumber)].points.map(([lat, lon]) => ({ lat, lon }));

/** A point `yards` back down the hole from the green, along the closing leg. */
function approachPoint(holeNumber, yards) {
  const points = centerline(holeNumber);
  const green = points[points.length - 1];
  const previous = points[points.length - 2];
  const legYards = distanceYards(previous, green);
  const fraction = yards / legYards;
  return {
    lat: green.lat + (previous.lat - green.lat) * fraction,
    lon: green.lon + (previous.lon - green.lon) * fraction,
  };
}

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

test("matches every hole to a distinct green", () => {
  const greens = sources.greens;
  assert.ok(greens, "sources.json should carry a greens block");
  assert.equal(greens.source, "OpenStreetMap contributors");
  assert.equal(greens.license, "ODbL");
  assert.equal(Object.keys(greens.holes).length, 18);

  const assigned = HOLE_NUMBERS.map((holeNumber) => greens.holes[String(holeNumber)].wayId);
  assert.equal(
    new Set(assigned).size,
    18,
    "two holes sharing a green means the match picked the wrong one",
  );

  // The centerline already ends on the putting surface, so a correct pairing
  // lands within a couple of yards. Anything larger is a different green.
  let worst = 0;
  for (const holeNumber of HOLE_NUMBERS) {
    const green = greens.holes[String(holeNumber)];
    assert.ok(green.points.length >= 3, `hole ${holeNumber} green needs a real ring`);
    worst = Math.max(worst, green.offsetYards);
    assert.ok(
      green.offsetYards <= 10,
      `hole ${holeNumber} green centroid sits ${green.offsetYards.toFixed(1)} yards from the centerline end`,
    );
  }

  console.log(`Greens: worst centroid offset ${worst.toFixed(2)} yards`);
});

test("orders front, middle, and back when approaching a green", () => {
  console.log("Green depth from 150 yards out");
  for (const holeNumber of HOLE_NUMBERS) {
    const readout = greenDistances(approachPoint(holeNumber, 150), greenPolygon(holeNumber));

    assert.ok(
      readout.frontYards < readout.middleYards,
      `hole ${holeNumber}: front ${readout.frontYards.toFixed(1)} should be nearer than middle ${readout.middleYards.toFixed(1)}`,
    );
    assert.ok(
      readout.middleYards < readout.backYards,
      `hole ${holeNumber}: middle ${readout.middleYards.toFixed(1)} should be nearer than back ${readout.backYards.toFixed(1)}`,
    );

    // Real greens run roughly 15 to 40 yards front to back. A spread outside
    // that says the ring is wrong, not that the green is unusual.
    const depth = readout.backYards - readout.frontYards;
    assert.ok(
      depth >= 15 && depth <= 40,
      `hole ${holeNumber} green measures ${depth.toFixed(1)} yards deep`,
    );
    console.log(
      `  hole ${String(holeNumber).padStart(2)} · ${readout.frontYards.toFixed(0).padStart(3)} front · ` +
        `${readout.middleYards.toFixed(0).padStart(3)} mid · ${readout.backYards.toFixed(0).padStart(3)} back · ` +
        `${depth.toFixed(0).padStart(2)} yd deep`,
    );
  }
});

test("counts every number down as the player walks up the fairway", () => {
  for (const holeNumber of HOLE_NUMBERS) {
    const green = greenPolygon(holeNumber);
    const far = greenDistances(approachPoint(holeNumber, 200), green);
    const near = greenDistances(approachPoint(holeNumber, 100), green);

    assert.ok(near.frontYards < far.frontYards, `hole ${holeNumber} front did not shrink`);
    assert.ok(near.middleYards < far.middleYards, `hole ${holeNumber} middle did not shrink`);
    assert.ok(near.backYards < far.backYards, `hole ${holeNumber} back did not shrink`);
  }
});

test("swaps which edge is front when standing behind the green", () => {
  for (const holeNumber of HOLE_NUMBERS) {
    const green = greenPolygon(holeNumber);
    const centre = greenCentre(green);
    const inFront = approachPoint(holeNumber, 120);

    // Mirror the approach point through the centre of the green to stand an
    // equal distance beyond it.
    const behind = {
      lat: centre.lat + (centre.lat - inFront.lat),
      lon: centre.lon + (centre.lon - inFront.lon),
    };

    const frontSide = greenDistances(inFront, green);
    const backSide = greenDistances(behind, green);

    // Both sides see a nearest and a farthest edge, and the middle stays put.
    assert.ok(backSide.frontYards < backSide.middleYards, `hole ${holeNumber} behind: front not nearest`);
    assert.ok(backSide.middleYards < backSide.backYards, `hole ${holeNumber} behind: back not farthest`);
    assert.ok(
      Math.abs(frontSide.middleYards - backSide.middleYards) < 1,
      `hole ${holeNumber}: the middle of the green should not move`,
    );
  }
});

test("collapses to a plain distance for a single-point green", () => {
  const from = { lat: 39.1384472, lon: -121.5419038 };
  const point = { lat: 39.1369162, lon: -121.5456708 };
  const readout = greenDistances(from, [point]);
  const plain = distanceYards(from, point);

  assert.ok(Math.abs(readout.frontYards - plain) < 1e-9);
  assert.ok(Math.abs(readout.middleYards - plain) < 1e-9);
  assert.ok(Math.abs(readout.backYards - plain) < 1e-9);
});
