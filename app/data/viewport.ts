/**
 * The hole card's pinch-zoom viewport, kept out of the component so the
 * gesture math can be tested without a browser.
 *
 * A view is `screen = content * z + t` with the origin at the box's top-left.
 * Content coordinates are box pixels at rest (zoom 1), which is what the
 * existing cover math consumes — so the whole zoom feature composes with the
 * measuring pipeline instead of reimplementing any of it: pointer → content
 * (here) → card pixels → coordinates (measure.ts). Distances never touch the
 * zoom; only where a finger lands does.
 */

export type ViewTransform = {
  /** Zoom factor. 1 shows the whole card exactly as before. */
  z: number;
  /** Translation of the content's top-left, in box pixels. Never positive. */
  tx: number;
  ty: number;
};

export type Box = { width: number; height: number };

export const IDENTITY_VIEW: ViewTransform = { z: 1, tx: 0, ty: 0 };

/** 1x is the whole card; 4x is about a green-and-its-bunkers close-up. */
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 4;

/**
 * Force a view into legality: zoom inside its limits, and the card always
 * filling the box. Scaled content spans `box * z`, so a translation is legal
 * between `box * (1 - z)` (bottom/right edge flush) and 0 (top/left flush) —
 * there is never a gap at any edge, matching how map apps feel.
 */
export function clampView(view: ViewTransform, box: Box): ViewTransform {
  const z = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.z));
  return {
    z,
    tx: Math.min(0, Math.max(box.width * (1 - z), view.tx)),
    ty: Math.min(0, Math.max(box.height * (1 - z), view.ty)),
  };
}

/**
 * Zoom by a factor while keeping the content under `focal` stationary on
 * screen — the spot between two pinching fingers, or under the cursor on a
 * wheel. Clamping can still slide the result at the zoom limits or the card
 * edges; that is the intended feel, not an error.
 */
export function zoomAt(
  view: ViewTransform,
  focal: { x: number; y: number },
  factor: number,
  box: Box,
): ViewTransform {
  const z = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.z * factor));
  const applied = z / view.z;
  return clampView(
    {
      z,
      tx: focal.x - (focal.x - view.tx) * applied,
      ty: focal.y - (focal.y - view.ty) * applied,
    },
    box,
  );
}

/** Slide the content by a screen-pixel delta, staying inside the card. */
export function panBy(
  view: ViewTransform,
  delta: { x: number; y: number },
  box: Box,
): ViewTransform {
  return clampView({ z: view.z, tx: view.tx + delta.x, ty: view.ty + delta.y }, box);
}

/** Where a screen point sits in resting box pixels — the cover math's input. */
export function screenToContent(
  point: { x: number; y: number },
  view: ViewTransform,
): { x: number; y: number } {
  return { x: (point.x - view.tx) / view.z, y: (point.y - view.ty) / view.z };
}

/** Where a resting box pixel lands on screen — for drawing overlays. */
export function contentToScreen(
  point: { x: number; y: number },
  view: ViewTransform,
): { x: number; y: number } {
  return { x: point.x * view.z + view.tx, y: point.y * view.z + view.ty };
}
