"""Drift measurement that knows what it is looking at.

Same tiles, same phase correlation, same confidence gate as the repo's measure_drift.py —
but each tile is also labelled by the dominant class in the base map's classes.png, and the
verdict separates two different things the plain measure lumps together:

  * LAND tiles (rough, fairway, trees, sand, green, tee, path): did the painter move anything?
    This is the accuracy gate — max over land tiles must stay under the tolerance.
  * WATER tiles: the base map paints water where OpenStreetMap (and Mario) say water is
    *today*; the 2022 aerial shows drought-era shorelines and exposed bed. Where they
    disagree, the card follows the map by design, so those tiles are reported separately
    ("shoreline differs from 2022 aerial by N yd") instead of failing the painter for it.

Usage:
  python measure_drift_classed.py --hole 7 --card out/x.png [--classes cond/hole-07-classes.png] [--tile 150]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path.home() / "rex/peach-tree-golf-tracker"
sys.path.insert(0, str(REPO / "scripts" / "imagery"))
import measure_drift as md  # noqa: E402

WATER_CLASS = 8


def measure_classed(hole: int, card: Path, classes_path: Path, tile: int = 150, tolerance: float = 5.0,
                    reference: Path | None = None) -> dict:
    geometry = md.load_geometry(REPO / "public/course/peach-tree/sources.json", hole)
    reference = reference or REPO / f"public/course/peach-tree/hole-{hole:02d}.webp"
    card_size = (geometry["card"]["width"], geometry["card"]["height"])
    ref = md.load_card(reference, card_size)
    cand = md.load_card(card, card_size)
    classes = np.array(Image.open(classes_path).convert("L").resize(card_size, Image.NEAREST))
    ypx = md.yards_per_card_pixel(geometry)
    land, water, dropped = [], [], 0
    for top in range(0, card_size[1] - tile + 1, tile):
        for left in range(0, card_size[0] - tile + 1, tile):
            r = ref[top:top + tile, left:left + tile]
            c = cand[top:top + tile, left:left + tile]
            if r.std() < 1.0 or c.std() < 1.0:
                dropped += 1
                continue
            dx, dy, ratio = md.phase_shift(r, c)
            if ratio < md.MIN_PEAK_RATIO:
                dropped += 1
                continue
            yards = float(np.hypot(dx * ypx[0], dy * ypx[1]))
            cls_tile = classes[top:top + tile, left:left + tile]
            water_frac = float((cls_tile == WATER_CLASS).mean())
            entry = {"x": left + tile // 2, "y": top + tile // 2, "yards": round(yards, 2), "waterFrac": round(water_frac, 2)}
            (water if water_frac >= 0.3 else land).append(entry)
    land_max = max((t["yards"] for t in land), default=0.0)
    land_med = float(np.median([t["yards"] for t in land])) if land else 0.0
    water_max = max((t["yards"] for t in water), default=0.0)
    all_yards = [t["yards"] for t in land + water]
    return {
        "hole": hole,
        "card": str(card),
        "tile": tile,
        "tilesLand": len(land),
        "tilesWater": len(water),
        "tilesDropped": dropped,
        "landMaxYards": round(land_max, 2),
        "landMedianYards": round(land_med, 2),
        "waterMaxYards": round(water_max, 2),
        "overallMaxYards": round(max(all_yards, default=0.0), 2),
        "overallMedianYards": round(float(np.median(all_yards)), 2) if all_yards else 0.0,
        "worstLandTile": max(land, key=lambda t: t["yards"]) if land else None,
        "pass": land_max <= tolerance,
        "note": "water tiles follow the OSM/today shoreline by design; their offset vs the 2022 aerial is reported, not judged",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hole", type=int, required=True)
    ap.add_argument("--card", type=Path, required=True, nargs="+")
    ap.add_argument("--classes", type=Path)
    ap.add_argument("--tile", type=int, default=150)
    ap.add_argument("--tolerance", type=float, default=5.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    classes = args.classes or Path(f"cond/hole-{args.hole:02d}-classes.png")
    for card in args.card:
        r = measure_classed(args.hole, card, classes, args.tile, args.tolerance)
        if args.json:
            print(json.dumps(r))
        else:
            print(f"{card.name}: LAND max {r['landMaxYards']:.2f} yd median {r['landMedianYards']:.2f} yd "
                  f"({r['tilesLand']} tiles) {'PASS' if r['pass'] else 'FAIL'} | water tiles {r['tilesWater']} "
                  f"shoreline offset up to {r['waterMaxYards']:.2f} yd | overall max {r['overallMaxYards']:.2f}")


if __name__ == "__main__":
    main()
