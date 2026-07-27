/**
 * Typed access to the atlas geometry the generator writes.
 *
 * `sources.json` is produced by `scripts/generate_peach_tree_atlas.py` and
 * doubles as the published provenance document. It is imported rather than
 * fetched so the numbers are bundled and the hole guide keeps working with no
 * network at all.
 *
 * The file stores values shared by every hole once, at the top of
 * `cardGeometry`, with only the per-hole transform beside each hole. Consumers
 * want one flat object, so the composition happens here.
 */

import sources from "../../public/course/peach-tree/sources.json";

import type { CardGeometry, GreenPolygon, LatLon } from "./course-geometry";

export type CourseBounds = {
  minLon: number;
  minLat: number;
  maxLon: number;
  maxLat: number;
};

export const COURSE_BOUNDS: CourseBounds = sources.cardGeometry.bbox;

/** Card dimensions in pixels, shared by all 18 holes. */
export const CARD_SIZE = sources.cardGeometry.card;

const holeKey = (holeNumber: number) => String(holeNumber);

export function holeCardGeometry(holeNumber: number): CardGeometry {
  const { bbox, source, card, holes } = sources.cardGeometry;
  return { bbox, source, card, ...holes[holeKey(holeNumber) as keyof typeof holes] };
}

/**
 * The OpenStreetMap centerline for a hole, tee first and green last.
 *
 * These are map-derived route points, not surveyed positions — the last one is
 * near the middle of the green rather than at a pin.
 */
export function holeCenterline(holeNumber: number): LatLon[] {
  const points = sources.centerlines.holes[
    holeKey(holeNumber) as keyof typeof sources.centerlines.holes
  ] as number[][];
  return points.map(([lat, lon]) => ({ lat, lon }));
}

export function holeTee(holeNumber: number): LatLon {
  return holeCenterline(holeNumber)[0];
}

export function holeGreen(holeNumber: number): LatLon {
  const points = holeCenterline(holeNumber);
  return points[points.length - 1];
}

/**
 * The mapped outline of a hole's putting surface.
 *
 * Unlike `holeGreen()` — a single point taken from the end of a centerline —
 * this is the real ring OpenStreetMap maps, which is what front and back
 * yardages need. The two coexist: the centerline point still orients the card.
 */
export function holeGreenPolygon(holeNumber: number): GreenPolygon {
  const green = sources.greens.holes[holeKey(holeNumber) as keyof typeof sources.greens.holes];
  return (green.points as number[][]).map(([lat, lon]) => ({ lat, lon }));
}

/**
 * May yardages be read off this hole's illustrated card?
 *
 * True only when the shipped illustration is a geometry-locked repaint AND
 * this hole's measured drift passed the 5-yard bar recorded by the generator.
 * Freehand art, a missing measurement, or a failed hole all answer no — the
 * guide then keeps the aerial as the measuring surface for that hole.
 */
export function holeIllustrationLocked(holeNumber: number): boolean {
  const info = sources.illustrations as {
    geometryLocked?: boolean;
    drift?: Record<string, { pass?: boolean }>;
  };
  if (!info.geometryLocked) return false;
  return Boolean(info.drift?.[holeKey(holeNumber)]?.pass);
}

/**
 * How far the matched green's middle sits from where the centerline ended.
 *
 * Written by the generator as the evidence the pairing is right. Exposed so a
 * test can assert it rather than trusting the match blindly.
 */
export function holeGreenMatchOffsetYards(holeNumber: number): number {
  return sources.greens.holes[holeKey(holeNumber) as keyof typeof sources.greens.holes]
    .offsetYards;
}
