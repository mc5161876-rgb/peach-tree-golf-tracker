import assert from "node:assert/strict";
import test from "node:test";

import { readFile } from "node:fs/promises";

// Read the atlas the same way the other suites do — the accessor module needs
// JSON import attributes the bundler and Node runner disagree about, and the
// data contract is what is under test.
const sources = JSON.parse(
  await readFile(new URL("../public/course/peach-tree/sources.json", import.meta.url), "utf8"),
);

/** Mirrors `holeIllustrationLocked` in app/data/course-atlas.ts. */
const locked = (illustrations, holeNumber) =>
  Boolean(illustrations?.geometryLocked) &&
  Boolean(illustrations?.drift?.[String(holeNumber)]?.pass);

test("every shipped illustration is geometry-locked and carries a passing measurement", () => {
  const info = sources.illustrations;
  assert.equal(info.geometryLocked, true);
  assert.equal(typeof info.driftToleranceYards, "number");

  for (let holeNumber = 1; holeNumber <= 18; holeNumber += 1) {
    const row = info.drift[String(holeNumber)];
    assert.ok(row, `hole ${holeNumber} has no drift measurement`);
    // The pass flag must agree with the numbers it summarises — a card
    // labelled measurable while drifting past the bar would put the yardage
    // band on art that lies.
    assert.equal(
      row.pass,
      row.maxYards <= info.driftToleranceYards,
      `hole ${holeNumber}: pass flag disagrees with maxYards ${row.maxYards}`,
    );
    assert.ok(row.medianYards <= row.maxYards, `hole ${holeNumber}: median exceeds max`);
    assert.equal(locked(info, holeNumber), true, `hole ${holeNumber} should be measurable`);
  }
});

test("the gate closes for freehand art, missing rows, and failed holes", () => {
  // Freehand set (pre-MAR-35 shape): no geometryLocked flag at all.
  assert.equal(locked({ source: "freehand", drift: undefined }, 4), false);

  // Locked set but this hole was never measured.
  assert.equal(locked({ geometryLocked: true, drift: {} }, 4), false);

  // Locked set, measured, failed the bar — browse-only, aerial keeps the band.
  assert.equal(
    locked({ geometryLocked: true, drift: { 4: { maxYards: 7.3, pass: false } } }, 4),
    false,
  );

  // The one combination that opens the gate.
  assert.equal(
    locked({ geometryLocked: true, drift: { 4: { maxYards: 0.48, pass: true } } }, 4),
    true,
  );
});
