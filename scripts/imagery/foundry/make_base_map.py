"""Render a clean 'yardage-book base map' for a hole card from real geometry.

Why: the free-form AI art Mario likes is pretty because the model was allowed to invent;
repainting the murky 0.6 m aerial keeps geometry but the look never arrives; edge-only
control brings the look back and invents lakes. This sidesteps the fight. Everything that
matters for a yardage — fairway, green, tee, bunker, water, cart path, hole line — comes from
OpenStreetMap vectors projected through the repo's own card transform, and the only thing
read off the aerial is *where the trees and the dry ground are* (colour classification,
smoothed). The model is then handed a flat, clean, already-stylised base to texture and
light, with tile ControlNet pinning it. Water can only appear where the map says water.

Outputs (900x1200 card space):
  cond/hole-NN-base.png     the flat illustration base (conditioning + img2img input)
  cond/hole-NN-classes.png  label map (one grey level per class) for invention checks

Usage: python make_base_map.py --hole 7 [--osm cond/osm-course.json] [--out cond]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

REPO = Path.home() / "rex/peach-tree-golf-tracker"
CARD = (900, 1200)
SHADOW_DX, SHADOW_DY, SHADOW_DARK = 0.9, 1.15, 0.5
DRY_SIGMA = 9.0  # smoothing of the dry-ground mask; lower hugs the aerial's real boundaries

# Illustration palette: warm late-afternoon yardage-book look.
PALETTE = {
    "ground_green": (92, 128, 58),
    "ground_dry": (178, 152, 100),
    "orchard": (66, 100, 48),
    "fairway": (120, 176, 64),
    "tee": (134, 178, 74),
    "green": (150, 206, 86),
    "bunker": (236, 220, 176),
    "water": (46, 104, 142),
    "path": (200, 186, 156),
    "tree": (42, 74, 36),
    "tree_hi": (70, 112, 52),
    "tree_shadow": (28, 44, 26),
    "route": (214, 176, 72),
    "marker": (240, 228, 196),
}
CLASS_ID = {"ground_green": 1, "ground_dry": 2, "orchard": 3, "fairway": 4, "tee": 5, "green": 6,
            "bunker": 7, "water": 8, "path": 9, "tree": 10}


def load_geometry(hole: int) -> dict:
    sys.path.insert(0, str(REPO / "scripts" / "imagery"))
    import measure_drift as md  # noqa: E402
    return md.load_geometry(REPO / "public/course/peach-tree/sources.json", hole)


def lat_lon_to_card(lat: float, lon: float, g: dict) -> tuple[float, float]:
    """Inverse of measure_drift.card_point_to_lat_lon (mirrors latLonToCardPoint in the app)."""
    bbox, src, card = g["bbox"], g["source"], g["card"]
    px = (lon - bbox["minLon"]) / (bbox["maxLon"] - bbox["minLon"]) * src["width"]
    py = (bbox["maxLat"] - lat) / (bbox["maxLat"] - bbox["minLat"]) * src["height"]
    ox, oy = px - g["center"]["x"], py - g["center"]["y"]
    unit, perp, scale = g["unit"], g["perp"], g["scale"]
    x = card["width"] / 2 + (ox * perp["x"] + oy * perp["y"]) / scale
    y = card["height"] / 2 - (ox * unit["x"] + oy * unit["y"]) / scale
    return x, y


def osm_shapes(osm: dict, g: dict):
    """Yield (kind, [rings]) with rings in card pixels. kind in PALETTE/CLASS_ID or 'hole'."""
    def ring(geom):
        return [lat_lon_to_card(p["lat"], p["lon"], g) for p in geom]

    for el in osm["elements"]:
        tags = el.get("tags", {})
        golf = tags.get("golf")
        kind = None
        is_line = False
        if golf in ("fairway", "green", "tee", "bunker"):
            kind = golf
        elif golf == "water_hazard" or tags.get("natural") == "water":
            kind = "water"
        elif golf == "hole":
            kind, is_line = "hole", True
        elif tags.get("highway") in ("service", "track", "path", "footway") and "geometry" in el:
            kind, is_line = "path", True
        elif tags.get("landuse") == "orchard":
            kind = "orchard"
        if kind is None:
            continue
        if el["type"] == "way" and "geometry" in el:
            yield kind, is_line, [ring(el["geometry"])], tags
        elif el["type"] == "relation":
            outers = [ring(m["geometry"]) for m in el.get("members", []) if m.get("role") == "outer" and "geometry" in m]
            inners = [ring(m["geometry"]) for m in el.get("members", []) if m.get("role") == "inner" and "geometry" in m]
            if outers:
                yield kind, is_line, outers, {**tags, "_inners": inners}


def classify_aerial(aerial: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (tree_mask, dry_mask) from the NAIP card, both smoothed booleans."""
    img = aerial.astype(np.float32)
    r, gch, b = img[..., 0], img[..., 1], img[..., 2]
    val = img.max(-1)
    greenness = gch - np.maximum(r, b)
    # trees: dark canopy (green-dominant, low value) or hard shadow
    # canopy: genuinely green AND dark; hard shadow only when very dark. Shadows on dry
    # ground are not green, so they stay ground. Tighter blur keeps individual crowns apart.
    tree = ((val < 78) & (greenness > 2)) | (val < 42)
    tree = cv2.GaussianBlur(tree.astype(np.float32), (0, 0), 1.8) > 0.55
    tree = cv2.morphologyEx(tree.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    # remove specks
    n, lab, stats, _ = cv2.connectedComponentsWithStats(tree.astype(np.uint8), 8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= 40
    tree = keep[lab]
    # dry ground: bright and not green
    dry = (val > 120) & (greenness < 12)
    dry = cv2.GaussianBlur(dry.astype(np.float32), (0, 0), DRY_SIGMA) > 0.5
    return tree, dry


def _noise(shape, sigma, rng):
    n = rng.standard_normal(shape).astype(np.float32)
    n = cv2.GaussianBlur(n, (0, 0), sigma)
    return n / (n.std() + 1e-6)


def procedural_surfaces(base: Image.Image, classes: Image.Image, aerial: np.ndarray, g: dict, tree_mask: np.ndarray):
    """Make the flat map look like a yardage-book page before the painter sees it:
    mow stripes on fairway/green/tee across the hole direction, grain on rough/dry/sand,
    a water gradient, and individually modeled tree crowns with long warm-light shadows."""
    rng = np.random.default_rng(20260822)
    arr = np.array(base).astype(np.float32)
    cls = np.array(classes)
    H, W = cls.shape
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)

    # hole direction in card space: the card is built so the hole runs up the card (unit
    # vector = +y up), so stripes perpendicular to play are horizontal bands; mow them at a
    # slight diagonal like a real crew does.
    ang = np.deg2rad(18.0)
    coord = xs * np.cos(ang) + ys * np.sin(ang)
    period = 16.0
    stripes = np.sin(2 * np.pi * coord / period)
    stripes = np.sign(stripes) * 0.085 + 0.02 * stripes  # crisp bands, slight softness
    for cid, amp in ((CLASS_ID["fairway"], 1.0), (CLASS_ID["green"], 0.6), (CLASS_ID["tee"], 0.6)):
        m = cls == cid
        arr[m] *= (1 + amp * stripes[m])[:, None]
    # grain
    grain_fine = _noise((H, W), 1.2, rng)
    grain_soft = _noise((H, W), 5.0, rng)
    for cid, a1, a2 in ((CLASS_ID["ground_green"], 0.05, 0.05), (CLASS_ID["ground_dry"], 0.06, 0.07),
                        (CLASS_ID["orchard"], 0.05, 0.04), (CLASS_ID["bunker"], 0.025, 0.02)):
        m = cls == cid
        arr[m] *= (1 + a1 * grain_fine[m] + a2 * grain_soft[m])[:, None]
    # water: darker toward the far bank, faint ripple
    m = cls == CLASS_ID["water"]
    if m.any():
        grad = (ys - ys[m].min()) / max(1.0, ys[m].max() - ys[m].min())
        arr[m] *= (1 - 0.18 * grad[m] + 0.02 * grain_soft[m])[:, None]
        arr[m, 2] *= 1.04
    # bunker rim: a touch darker at the edge so it reads as a lip
    bm = (cls == CLASS_ID["bunker"]).astype(np.uint8)
    rim = (bm > 0) & (cv2.erode(bm, np.ones((5, 5), np.uint8)) == 0)
    arr[rim] *= 0.92
    arr = np.clip(arr, 0, 255)

    # trees: crowns from the canopy mask. Distance-transform peaks place crowns; radius from
    # the distance value so dense masses become clusters of overlapping crowns.
    tm = tree_mask.astype(np.uint8)
    dist = cv2.distanceTransform(tm, cv2.DIST_L2, 5)
    # local maxima of the distance map, thinned
    dil = cv2.dilate(dist, np.ones((9, 9), np.uint8))
    peaks = (dist >= dil - 1e-3) & (dist >= 4.0)
    py, px = np.nonzero(peaks)
    order = np.argsort(-dist[py, px])
    taken = np.zeros((H, W), bool)
    crowns = []
    for i in order:
        y, x = int(py[i]), int(px[i])
        r = float(np.clip(dist[y, x] * 1.15 + 2.0, 5.0, 24.0))
        if taken[y, x]:
            continue
        crowns.append((x, y, r))
        cv2.circle(taken.view(np.uint8), (x, y), int(r * 0.9), 1, -1)
    # fill gaps: any canopy pixel farther than 1 radius from every crown gets a small crown
    cover = np.zeros((H, W), np.uint8)
    for x, y, r in crowns:
        cv2.circle(cover, (x, y), int(r), 1, -1)
    gap = (tm > 0) & (cover == 0)
    gd = cv2.distanceTransform(gap.astype(np.uint8), cv2.DIST_L2, 5)
    gy, gx = np.nonzero((gd >= 4) & (gd >= cv2.dilate(gd, np.ones((9, 9), np.uint8)) - 1e-3))
    for y, x in zip(gy, gx):
        crowns.append((int(x), int(y), float(np.clip(gd[y, x] * 1.2 + 2, 5.0, 14.0))))

    # draw: shadows first (long, toward lower-right = late afternoon sun from upper-left)
    shadow = np.zeros((H, W), np.float32)
    for x, y, r in crowns:
        # late-afternoon sun from the upper-left: shadows fall long toward the lower-right
        cv2.ellipse(shadow, (int(x + r * SHADOW_DX), int(y + r * SHADOW_DY)), (int(r * 1.25), int(r * 0.8)), -35, 0, 360, 1.0, -1)
    shadow = cv2.GaussianBlur(shadow, (0, 0), 3.0)
    arr *= (1 - SHADOW_DARK * np.clip(shadow, 0, 1))[..., None]
    # crowns with radial shading: lit upper-left, dark lower-right
    crown_img = np.zeros((H, W, 3), np.float32)
    crown_a = np.zeros((H, W), np.float32)
    dark = np.array(PALETTE["tree"], np.float32)
    lit = np.array(PALETTE["tree_hi"], np.float32) * 1.12
    for x, y, r in sorted(crowns, key=lambda c: c[1]):
        x0, x1 = max(0, int(x - r - 2)), min(W, int(x + r + 3))
        y0, y1 = max(0, int(y - r - 2)), min(H, int(y + r + 3))
        if x1 <= x0 or y1 <= y0:
            continue
        sub_y, sub_x = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        d = np.hypot(sub_x - x, sub_y - y) / r
        inside = d <= 1.0
        # lobed silhouette (a few big lobes + fine bumps), lit from the upper-left with a
        # bright rim and a dark core so each crown reads as a rounded 3-D canopy
        th = np.arctan2(sub_y - y, sub_x - x)
        wob = 1.0 + 0.10 * np.sin(3 * th + x * 0.37) + 0.05 * np.sin(9 * th + y * 0.23)
        inside = d <= wob
        light = ((sub_x - x) * -0.6 + (sub_y - y) * -0.8) / r          # +1 toward the sun
        shade = np.clip(0.55 - 0.45 * light, 0, 1)                       # 0 = lit, 1 = dark
        core = np.clip(1.0 - d / max(wob.mean(), 1e-3), 0, 1) ** 2       # darker toward the middle
        shade = np.clip(shade * (0.7 + 0.5 * core), 0, 1)
        rim = np.clip((d - 0.72) / 0.28, 0, 1) * np.clip(light, 0, 1)     # lit rim on the sun side
        col = lit[None, None, :] * (1 - shade[..., None]) + dark[None, None, :] * shade[..., None]
        col = col * (1 + 0.35 * rim[..., None])
        crown_img[y0:y1, x0:x1][inside] = col[inside]
        crown_a[y0:y1, x0:x1][inside] = 1.0
    crown_a = cv2.GaussianBlur(crown_a, (0, 0), 0.8)
    arr = arr * (1 - crown_a[..., None]) + crown_img * crown_a[..., None]
    cls[crown_a > 0.5] = CLASS_ID["tree"]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), Image.fromarray(cls)


def render(hole: int, osm_path: Path, out_dir: Path, no_route: bool = False, detail: float = 0.0, suffix: str = "", procedural: bool = False) -> None:
    g = load_geometry(hole)
    osm = json.loads(osm_path.read_text())
    aerial = np.array(Image.open(REPO / f"public/course/peach-tree/hole-{hole:02d}.webp").convert("RGB"))
    tree_mask, dry_mask = classify_aerial(aerial)
    # Mario's ground-truth overrides (trees cleared since 2022, trees to add): corrections.json
    try:
        from corrections import apply_corrections
        tree_mask, override_mask = apply_corrections(hole, tree_mask)
    except Exception as exc:  # corrections are optional
        override_mask = np.zeros_like(tree_mask)
        print(f"  (no corrections applied: {exc})")

    W, H = CARD
    base = Image.new("RGB", (W, H), PALETTE["ground_green"])
    classes = Image.new("L", (W, H), CLASS_ID["ground_green"])
    d = ImageDraw.Draw(base)
    dc = ImageDraw.Draw(classes)

    # ground character from the aerial: dry waste vs green rough (smoothed, no texture)
    dry_img = np.array(base).copy()
    dry_img[dry_mask] = PALETTE["ground_dry"]
    base = Image.fromarray(dry_img)
    cls = np.array(classes)
    cls[dry_mask] = CLASS_ID["ground_dry"]
    classes = Image.fromarray(cls)
    d = ImageDraw.Draw(base)
    dc = ImageDraw.Draw(classes)

    # vector layers, painted in an order where later wins
    order = {"orchard": 0, "fairway": 1, "tee": 2, "green": 3, "bunker": 4, "water": 5}
    shapes = list(osm_shapes(osm, g))
    areas = sorted([s for s in shapes if not s[1] and s[0] in order], key=lambda s: order[s[0]])
    for kind, _, rings, tags in areas:
        for rg in rings:
            if len(rg) >= 3:
                d.polygon(rg, fill=PALETTE[kind])
                dc.polygon(rg, fill=CLASS_ID[kind])
        for inner in tags.get("_inners", []):
            if len(inner) >= 3:
                d.polygon(inner, fill=PALETTE["ground_green"])
                dc.polygon(inner, fill=CLASS_ID["ground_green"])

    # Mario's class overrides (e.g. "this corridor is mown fairway today")
    try:
        from corrections import class_overrides
        for item in class_overrides(hole):
            kind = item["class"]
            if kind in PALETTE and kind in CLASS_ID:
                d.polygon([tuple(p) for p in item["polygon"]], fill=PALETTE[kind])
                dc.polygon([tuple(p) for p in item["polygon"]], fill=CLASS_ID[kind])
    except Exception as exc:
        print(f"  (class overrides skipped: {exc})")

    # trees from the aerial: shadow first, then canopy with a lit edge, on top of ground/fairway.
    # Never over water, sand, greens or tees — those shapes are surveyed-ish vectors and dark
    # water would otherwise be mis-read as canopy.
    protected = np.isin(np.array(classes), [CLASS_ID["water"], CLASS_ID["bunker"], CLASS_ID["green"], CLASS_ID["tee"]])
    protected = cv2.dilate(protected.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    tree_mask = tree_mask & ~protected
    canopy = tree_mask.astype(np.uint8) * 255
    if procedural:
        canopy = np.zeros_like(canopy)  # crowns are rendered per tree in procedural_surfaces
    shadow = np.roll(np.roll(canopy, 7, axis=0), 5, axis=1)
    arr = np.array(base)
    arr[shadow > 0] = (0.55 * arr[shadow > 0] + 0.45 * np.array(PALETTE["tree_shadow"])).astype(np.uint8)
    hi = cv2.erode(canopy, np.ones((5, 5), np.uint8))
    hi = np.roll(np.roll(hi, -3, axis=0), -3, axis=1)
    arr[canopy > 0] = PALETTE["tree"]
    lit = (canopy > 0) & (hi == 0)
    arr[lit] = PALETTE["tree_hi"]
    base = Image.fromarray(arr)
    cls = np.array(classes)
    cls[canopy > 0] = CLASS_ID["tree"]
    classes = Image.fromarray(cls)
    d = ImageDraw.Draw(base)
    dc = ImageDraw.Draw(classes)

    if procedural:
        base, classes = procedural_surfaces(base, classes, aerial, g, tree_mask)

    # cart paths on top of everything except water
    for kind, is_line, rings, tags in shapes:
        if kind == "path":
            for rg in rings:
                d.line(rg, fill=PALETTE["path"], width=4, joint="curve")
                dc.line(rg, fill=CLASS_ID["path"], width=4)

    # soften vector edges a touch so it reads as a painting base, not a GIS plot
    base = base.filter(ImageFilter.GaussianBlur(1.2))

    # optional: carry the real aerial's fine structure through as a gentle luminance high-pass,
    # so mow lines, crown shadows and real edges survive for the painter (and for drift
    # measurement) while colours/classes stay dictated by the map. Water/sand stay clean.
    if detail > 0:
        gray = cv2.cvtColor(aerial, cv2.COLOR_RGB2GRAY).astype(np.float32)
        hp = gray - cv2.GaussianBlur(gray, (0, 0), 6.0)
        hp = np.clip(hp * detail, -40, 40)
        arr = np.array(base).astype(np.float32)
        clean = np.isin(np.array(classes), [CLASS_ID["water"], CLASS_ID["bunker"]])
        hp[clean] *= 0.25
        hp[override_mask] = 0.0
        arr = np.clip(arr + hp[..., None], 0, 255).astype(np.uint8)
        base = Image.fromarray(arr)
    d = ImageDraw.Draw(base)

    # the hole route + markers, matching the aerial cards, drawn last
    if not no_route:
        for kind, is_line, rings, tags in shapes:
            if kind == "hole" and tags.get("ref") == str(hole):
                pts = rings[0]
                d.line(pts, fill=PALETTE["route"], width=5, joint="curve")
                for (x, y) in (pts[0], pts[-1]):
                    d.ellipse([x - 9, y - 9, x + 9, y + 9], outline=PALETTE["marker"], width=3)
                    d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=PALETTE["marker"])

    out_dir.mkdir(parents=True, exist_ok=True)
    base.save(out_dir / f"hole-{hole:02d}-base{suffix}.png")
    classes.save(out_dir / f"hole-{hole:02d}-classes.png")
    Image.fromarray((override_mask.astype(np.uint8) * 255)).save(out_dir / f"hole-{hole:02d}-override.png")
    counts = {k: int((np.array(classes) == v).sum()) for k, v in CLASS_ID.items()}
    print(f"hole {hole}: base + classes written; px per class: {counts}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hole", type=int, nargs="+", required=True)
    ap.add_argument("--osm", type=Path, default=Path("cond/osm-course.json"))
    ap.add_argument("--out", type=Path, default=Path("cond"))
    ap.add_argument("--no-route", action="store_true")
    ap.add_argument("--detail", type=float, default=0.0, help="strength of aerial high-pass detail blended into the base (0 = flat)")
    ap.add_argument("--suffix", default="", help="filename suffix for the base, e.g. -detail")
    ap.add_argument("--procedural", action="store_true", help="mow stripes, grain, water gradient, modeled tree crowns with shadows")
    ap.add_argument("--dry-sigma", type=float, default=9.0)
    args = ap.parse_args()
    global DRY_SIGMA
    DRY_SIGMA = args.dry_sigma
    for h in args.hole:
        render(h, args.osm, args.out, args.no_route, args.detail, args.suffix, args.procedural)


if __name__ == "__main__":
    main()
