/**
 * The yardage tool's decisions, kept out of the component so they can be tested.
 *
 * Two things matter here and neither is about drawing. First, which point a
 * carry is measured *from* — the player's real position when there is a
 * trustworthy one, the tee otherwise — because a number whose reference is
 * ambiguous is worse than no number. Second, turning a tap on a cropped image
 * back into a place on the hole.
 */

// Explicit extension so the Node test runner resolves this without a loader;
// the bundler is happy either way.
import { cardPointToLatLon, distanceYards, greenDistances } from "./course-geometry.ts";
import type { CardGeometry, CardPoint, GreenPolygon, LatLon } from "./course-geometry";
import type { CourseBounds } from "./course-atlas";

/** What the yardages were measured from. */
export type MeasureReference = "position" | "tee";

export type MeasureReadout = {
  reference: MeasureReference;
  /** Reference point to the nearest edge of the green, whole yards. */
  frontYards: number;
  /** Reference point to the crosshair — the pin, wherever it was dragged. */
  middleYards: number;
  /** Reference point to the farthest edge of the green, whole yards. */
  backYards: number;
};

export type Size = { width: number; height: number };

/**
 * Is a reported position actually on this course?
 *
 * A fix from the other side of the county is not a useful "you are here" — it
 * is a wrong one, and it would silently poison every carry. Anything outside
 * the imagery's own bounding box is treated as no fix at all.
 */
export function isWithinCourse(position: LatLon, bounds: CourseBounds): boolean {
  return (
    position.lat >= bounds.minLat &&
    position.lat <= bounds.maxLat &&
    position.lon >= bounds.minLon &&
    position.lon <= bounds.maxLon
  );
}

/**
 * Which point carries are measured from, and whether it is the player's own.
 *
 * `position` is null when geolocation is unavailable, was denied, or has not
 * returned a fix yet. All three collapse to the same honest answer: measure
 * from the tee and say so.
 */
export function measureOrigin(
  position: LatLon | null,
  tee: LatLon,
  bounds: CourseBounds,
): { point: LatLon; reference: MeasureReference } {
  if (position && isWithinCourse(position, bounds)) {
    return { point: position, reference: "position" };
  }
  return { point: tee, reference: "tee" };
}

/**
 * The three numbers in the yardage band.
 *
 * Front and back are locked to the mapped edges of the putting surface; only
 * the middle follows the crosshair, so dragging the pin around never moves
 * the edges it sits between.
 */
export function measureCrosshair(options: {
  crosshair: LatLon;
  tee: LatLon;
  green: GreenPolygon;
  position: LatLon | null;
  bounds: CourseBounds;
}): MeasureReadout {
  const { point, reference } = measureOrigin(options.position, options.tee, options.bounds);
  const edges = greenDistances(point, options.green);
  return {
    reference,
    frontYards: Math.round(edges.frontYards),
    middleYards: Math.round(distanceYards(point, options.crosshair)),
    backYards: Math.round(edges.backYards),
  };
}

/**
 * Where a pointer landed, in card pixels.
 *
 * The hole image is rendered with `object-fit: cover`, so the card is scaled to
 * fill the box and the overflowing axis is cropped evenly at both ends. Reading
 * the pointer as a plain percentage of the box would be wrong by however much
 * was cropped — tens of yards near the edges.
 */
export function coverPointToCard(
  pointer: { x: number; y: number },
  container: Size,
  card: Size,
): CardPoint {
  const scale = Math.max(container.width / card.width, container.height / card.height);
  const offsetX = (container.width - card.width * scale) / 2;
  const offsetY = (container.height - card.height * scale) / 2;

  return {
    x: (pointer.x - offsetX) / scale,
    y: (pointer.y - offsetY) / scale,
  };
}

/** Inverse of `coverPointToCard`, for drawing a coordinate back onto the box. */
export function cardPointToCover(
  point: CardPoint,
  container: Size,
  card: Size,
): { x: number; y: number } {
  const scale = Math.max(container.width / card.width, container.height / card.height);
  return {
    x: point.x * scale + (container.width - card.width * scale) / 2,
    y: point.y * scale + (container.height - card.height * scale) / 2,
  };
}

/** Convenience for the component: pointer in the box straight to a coordinate. */
export function coverPointToLatLon(
  pointer: { x: number; y: number },
  container: Size,
  geometry: CardGeometry,
): LatLon {
  return cardPointToLatLon(coverPointToCard(pointer, container, geometry.card), geometry);
}
