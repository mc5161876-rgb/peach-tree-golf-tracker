/**
 * Converting between a point on a hole card and a real-world coordinate.
 *
 * Each hole card is a rotated, scaled crop of one geo-referenced aerial
 * raster. `scripts/generate_peach_tree_atlas.py` knows the transform it used
 * and writes it into `public/course/peach-tree/sources.json` under
 * `cardGeometry`; these functions invert it.
 *
 * Nothing here knows which course it is working on — the geometry is passed
 * in. Distances are honest about their limits: the "green" in the underlying
 * data is the last point of an OpenStreetMap centerline, not a surveyed pin,
 * so anything measured to it is good to roughly ten yards.
 */

export type LatLon = {
  lat: number;
  lon: number;
};

/** A position on a hole card, in card pixels from the top-left. */
export type CardPoint = {
  x: number;
  y: number;
};

export type CardGeometry = {
  /** The geographic extent of the source raster. */
  bbox: { minLon: number; minLat: number; maxLon: number; maxLat: number };
  /** Dimensions of the source raster, in pixels. */
  source: { width: number; height: number };
  /** Dimensions of the produced card, in pixels. */
  card: { width: number; height: number };
  /** Card centre, in source-raster pixels. */
  center: { x: number; y: number };
  /** Unit vector along the hole, tee to green, in source-raster pixel space. */
  unit: { x: number; y: number };
  /** Unit vector perpendicular to `unit`. */
  perp: { x: number; y: number };
  /** Source-raster pixels per card pixel. */
  scale: number;
};

const EARTH_RADIUS_METRES = 6_371_000;
const YARDS_PER_METRE = 1.0936132983377078;

const toRadians = (degrees: number) => (degrees * Math.PI) / 180;

/** Source-raster pixel for a coordinate. Mirrors `geo_to_pixel` in the generator. */
function latLonToSourcePixel(position: LatLon, geometry: CardGeometry): CardPoint {
  const { bbox, source } = geometry;
  return {
    x: ((position.lon - bbox.minLon) / (bbox.maxLon - bbox.minLon)) * source.width,
    y: ((bbox.maxLat - position.lat) / (bbox.maxLat - bbox.minLat)) * source.height,
  };
}

function sourcePixelToLatLon(pixel: CardPoint, geometry: CardGeometry): LatLon {
  const { bbox, source } = geometry;
  return {
    lat: bbox.maxLat - (pixel.y / source.height) * (bbox.maxLat - bbox.minLat),
    lon: bbox.minLon + (pixel.x / source.width) * (bbox.maxLon - bbox.minLon),
  };
}

/**
 * Where on Earth a point on the hole card is.
 *
 * The card is the source rotated so the hole runs bottom-to-top, so this
 * undoes the rotation before converting pixels to degrees. `unit` and `perp`
 * are orthonormal, which makes the rotation its own inverse to transpose.
 */
export function cardPointToLatLon(point: CardPoint, geometry: CardGeometry): LatLon {
  const { card, center, unit, perp, scale } = geometry;
  const across = (point.x - card.width / 2) * scale;
  const along = -(point.y - card.height / 2) * scale;

  return sourcePixelToLatLon(
    {
      x: center.x + along * unit.x + across * perp.x,
      y: center.y + along * unit.y + across * perp.y,
    },
    geometry,
  );
}

/**
 * Where a coordinate falls on the hole card.
 *
 * The result is not clamped: a position off the edge of the crop returns
 * coordinates outside the card, which is how a caller can tell it is off-card.
 */
export function latLonToCardPoint(position: LatLon, geometry: CardGeometry): CardPoint {
  const { card, center, unit, perp, scale } = geometry;
  const pixel = latLonToSourcePixel(position, geometry);
  const offsetX = pixel.x - center.x;
  const offsetY = pixel.y - center.y;

  return {
    x: card.width / 2 + (offsetX * perp.x + offsetY * perp.y) / scale,
    y: card.height / 2 - (offsetX * unit.x + offsetY * unit.y) / scale,
  };
}

/** Great-circle distance in yards. */
export function distanceYards(from: LatLon, to: LatLon): number {
  const deltaLat = toRadians(to.lat - from.lat);
  const deltaLon = toRadians(to.lon - from.lon);
  const a =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(toRadians(from.lat)) *
      Math.cos(toRadians(to.lat)) *
      Math.sin(deltaLon / 2) ** 2;

  return 2 * EARTH_RADIUS_METRES * Math.asin(Math.sqrt(a)) * YARDS_PER_METRE;
}
