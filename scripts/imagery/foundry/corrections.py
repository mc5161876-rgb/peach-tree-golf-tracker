"""Mario's ground-truth corrections to the skeleton — the layer the 2022 aerial cannot supply.

corrections.json (next to this file) holds per-hole overrides in 900x1200 card pixels:

  {
    "7": {
      "clear_trees": [ [[x,y],[x,y],...], ... ],     # polygons: no canopy inside (cleared since 2022)
      "add_trees":   [ [x, y, radius_px], ... ],      # crowns to add (e.g. hole 6's big oak, hole 8's tree)
      "notes": "Mario 2026-08-23: trees along the fairway short of the green are gone"
    }
  }

Helpers turn what Mario actually says into polygons:
  cells_to_polygons(["C4","C5"])                       -> grid cells (6 cols A-F x 8 rows 1-8)
  band_to_polygon(hole, 60, 140, side="left", width=130) -> strip along the hole line from 60 to 140 yd off the tee
The mask edits happen in make_base_map.render via apply_corrections(); cleared/added areas are also
recorded so the drift report can flag 'override' tiles instead of calling them drift.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = Path.home() / "rex/peach-tree-golf-tracker"
sys.path.insert(0, str(REPO / "scripts" / "imagery"))
CARD_W, CARD_H = 900, 1200
GRID_COLS, GRID_ROWS = 6, 8


def load() -> dict:
    p = HERE / "corrections.json"
    return json.loads(p.read_text()) if p.exists() else {}


def save(data: dict) -> None:
    (HERE / "corrections.json").write_text(json.dumps(data, indent=2) + "\n")


def cells_to_polygons(cells: list[str]) -> list[list[list[float]]]:
    cw, rh = CARD_W / GRID_COLS, CARD_H / GRID_ROWS
    polys = []
    for c in cells:
        c = c.strip().upper()
        col = "ABCDEF".index(c[0])
        row = int(c[1:]) - 1
        x0, y0 = col * cw, row * rh
        polys.append([[x0, y0], [x0 + cw, y0], [x0 + cw, y0 + rh], [x0, y0 + rh]])
    return polys


def _centerline_card(hole: int):
    import measure_drift as md
    from make_base_map import lat_lon_to_card
    g = md.load_geometry(REPO / "public/course/peach-tree/sources.json", hole)
    src = json.loads((REPO / "public/course/peach-tree/sources.json").read_text())
    cl = src["centerlines"]
    holes_cl = cl.get("holes", cl)
    entry = holes_cl.get(str(hole)) or holes_cl.get(hole)
    pts = entry.get("points") if isinstance(entry, dict) else entry
    P = [((p["lat"], p["lon"]) if isinstance(p, dict) else (p[0], p[1])) for p in pts]
    cp = [lat_lon_to_card(la, lo, g) for la, lo in P]
    if cp[0][1] < cp[-1][1]:  # tee should be the lower end of the card
        P, cp = P[::-1], cp[::-1]
    cum = [0.0]
    for i in range(1, len(P)):
        cum.append(cum[-1] + md.distance_yards(P[i - 1], P[i]))
    return cp, cum


def _point_at(cp, cum, yd):
    for i in range(1, len(cum)):
        if cum[i] >= yd:
            t = (yd - cum[i - 1]) / max(1e-6, cum[i] - cum[i - 1])
            return (cp[i - 1][0] + t * (cp[i][0] - cp[i - 1][0]), cp[i - 1][1] + t * (cp[i][1] - cp[i - 1][1]))
    return cp[-1]


def band_to_polygon(hole: int, yd0: float, yd1: float, side: str = "both", width: float = 130.0, inner: float = 0.0) -> list[list[float]]:
    """Strip along the hole line between yd0 and yd1 from the tee. side: left/right/both (as the golfer
    stands on the tee looking at the green, i.e. left = -x on the card when the hole runs up the card).
    width = lateral extent in card px from the line (hole 7: 1 px ≈ 0.18 yd across, so 130 px ≈ 23 yd);
    inner = gap from the line (e.g. to keep the fairway itself untouched)."""
    cp, cum = _centerline_card(hole)
    n = 12
    ys = [yd0 + (yd1 - yd0) * i / n for i in range(n + 1)]
    pts = [_point_at(cp, cum, y) for y in ys]
    # local direction for the perpendicular
    def perp(i):
        a = pts[max(i - 1, 0)]; b = pts[min(i + 1, n)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = max(1e-6, (dx * dx + dy * dy) ** 0.5)
        return (-dy / L, dx / L)  # rotate 90°: for a hole running up the card (dy<0) this points to +x (golfer's right)
    lo = -width if side in ("left", "both") else -inner
    hi = width if side in ("right", "both") else inner
    left_edge = [(p[0] + perp(i)[0] * lo, p[1] + perp(i)[1] * lo) for i, p in enumerate(pts)]
    right_edge = [(p[0] + perp(i)[0] * hi, p[1] + perp(i)[1] * hi) for i, p in enumerate(pts)]
    poly = left_edge + right_edge[::-1]
    return [[round(x, 1), round(y, 1)] for x, y in poly]


def masks_for(hole: int, data: dict | None = None):
    """Return (clear_mask, add_list) for a hole; clear_mask is a bool HxW array."""
    data = load() if data is None else data
    entry = data.get(str(hole), {})
    clear = np.zeros((CARD_H, CARD_W), np.uint8)
    for poly in entry.get("clear_trees", []):
        cv2.fillPoly(clear, [np.array(poly, np.int32)], 1)
    return clear.astype(bool), entry.get("add_trees", [])


def apply_corrections(hole: int, tree_mask: np.ndarray, data: dict | None = None):
    """Apply Mario's overrides to the tree mask. Returns (tree_mask, override_mask)."""
    clear, adds = masks_for(hole, data)
    tm = tree_mask.copy()
    tm[clear] = False
    override = clear.copy()
    for x, y, r in adds:
        cv2.circle(tm.view(np.uint8), (int(x), int(y)), int(r), 1, -1)
        cv2.circle(override.view(np.uint8), (int(x), int(y)), int(r) + 4, 1, -1)
    # set_class polygons also count as overrides (the 2022 photo is not the truth there)
    for item in (data or load()).get(str(hole), {}).get("set_class", []):
        cv2.fillPoly(override.view(np.uint8), [np.array(item["polygon"], np.int32)], 1)
    return tm.astype(bool), override.astype(bool)


def class_overrides(hole: int, data: dict | None = None) -> list[dict]:
    """[{'class': 'fairway', 'polygon': [[x,y],...]}, ...] — ground Mario says is a different class today."""
    return (data or load()).get(str(hole), {}).get("set_class", [])


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="record a correction")
    ap.add_argument("--hole", type=int, required=True)
    ap.add_argument("--clear-cells", nargs="*", default=[])
    ap.add_argument("--clear-band", nargs=3, metavar=("YD0", "YD1", "SIDE"))
    ap.add_argument("--band-width", type=float, default=130.0)
    ap.add_argument("--band-inner", type=float, default=0.0)
    ap.add_argument("--add-tree", nargs=3, type=float, action="append", metavar=("X", "Y", "R"))
    ap.add_argument("--set-class-band", nargs=4, metavar=("CLASS", "YD0", "YD1", "SIDE"), help="e.g. fairway 25 185 both")
    ap.add_argument("--set-class-cells", nargs="+", metavar="CLASS_AND_CELLS", help="e.g. fairway C4 C5")
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    data = load()
    e = data.setdefault(str(args.hole), {"clear_trees": [], "add_trees": [], "notes": ""})
    if args.clear_cells:
        e["clear_trees"] += cells_to_polygons(args.clear_cells)
    if args.clear_band:
        y0, y1, side = float(args.clear_band[0]), float(args.clear_band[1]), args.clear_band[2]
        e["clear_trees"].append(band_to_polygon(args.hole, y0, y1, side, args.band_width, args.band_inner))
    for t in args.add_tree or []:
        e["add_trees"].append([t[0], t[1], t[2]])
    e.setdefault("set_class", [])
    if args.set_class_band:
        cls, y0, y1, side = args.set_class_band
        e["set_class"].append({"class": cls, "polygon": band_to_polygon(args.hole, float(y0), float(y1), side, args.band_width, args.band_inner)})
    if args.set_class_cells:
        cls, cells = args.set_class_cells[0], args.set_class_cells[1:]
        for poly in cells_to_polygons(cells):
            e["set_class"].append({"class": cls, "polygon": poly})
    if args.note:
        e["notes"] = (e.get("notes", "") + " | " + args.note).strip(" |")
    save(data)
    print(json.dumps(e, indent=1)[:800])
