"""Recolor a hole's pond to clear blue in the conditioning aerial.

The 2022 NAIP aerial shows the hole 2 pond as it actually was that July:
dark, algae-edged, with a tree canopy smearing into it. Prompt language
alone cannot fix that — at any conditioning scale worth keeping, the
ControlNet pins the murky source pixels (verified 2026-07-28, see
x2-test-2026-07-28/water-fix). So the water gets recolored in the *input*:
the model is handed blue water as ground truth and paints it convincingly,
while banks, rocks, and trees keep their real positions.

Water pixels are found inside a per-hole bounding box (dark, blue channel
not dominated by green — canopy is dark green, scum is yellow-green, rocks
are bright grey), then restricted to the components reachable from per-hole
seed points so tree shadows elsewhere in the box are never touched.

Output feeds generate_locked_card.py via --aerial. Drift is still measured
against the ORIGINAL aerial; the recolor changed hole 2 by 0.00 yd
(photo 2x: 0.09 max, painted 2x: 0.16 — identical to unrecolored runs).
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# Per-hole water regions: bbox (l, t, r, b) and seed points (x, y), all in
# 900x1200 card space. Only holes with a pond need an entry.
# rock_polygon: Mario's ground-truth correction (2026-07-28) — the grey spit
# the 2022 aerial shows inside the hole 2 pond is drought-era exposed bottom
# and is underwater today. Grey low-saturation pixels inside this polygon get
# recolored along with the water. A polygon, not a color-reachability rule:
# the spit's grey continues seamlessly into the dry waste area, so any
# flood-fill escapes the pond (tried, spectacular).
WATER_REGIONS = {
    2: {
        "bbox": (330, 880, 660, 1150),
        "seeds": [(430, 950), (480, 920), (500, 1010), (507, 1047), (525, 1057), (520, 1035)],
        "rock_polygon": [
            (467, 963), (545, 970), (543, 1015), (530, 1055),
            (498, 1072), (480, 1030), (473, 990),
        ],
    },
}

# Clear lake blue, modulated by local luminance so ripples survive.
TARGET_RGB = np.array([70.0, 130.0, 185.0])
BLEND = 0.85


def water_mask(
    a: np.ndarray, bbox: tuple[int, int, int, int], seeds, rock_polygon=None
) -> Image.Image:
    x0, y0, x1, y1 = bbox
    sub = a[y0:y1, x0:x1]
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    v = sub.max(axis=-1)
    cand = (v < 95) & (b >= g - 5) & (r < 80)

    H, W = cand.shape
    seen = np.zeros_like(cand)
    dq = deque()
    for cx, cy in seeds:
        s = (cy - y0, cx - x0)
        if 0 <= s[0] < H and 0 <= s[1] < W and cand[s] and not seen[s]:
            seen[s] = True
            dq.append(s)
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and cand[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                dq.append((ny, nx))

    mask = np.zeros(a.shape[:2], dtype=np.uint8)
    mask[y0:y1, x0:x1] = seen.astype(np.uint8) * 255

    if rock_polygon:
        poly = Image.new("L", (a.shape[1], a.shape[0]), 0)
        ImageDraw.Draw(poly).polygon(rock_polygon, fill=255)
        inside = np.asarray(poly) > 0
        sat = v - sub.min(axis=-1)
        grey = (sat < 35) & (v > 80) & (np.abs(r - b) < 25)
        rocks = np.zeros(a.shape[:2], dtype=bool)
        rocks[y0:y1, x0:x1] = grey
        mask[inside & rocks] = 255

    m = Image.fromarray(mask)
    # bridge scum flecks, then feather so the repaint has no hard seam
    m = m.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(5))
    return m.filter(ImageFilter.GaussianBlur(1.5))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hole", type=int, required=True, choices=sorted(WATER_REGIONS))
    parser.add_argument(
        "--aerial",
        type=Path,
        help="source aerial card; defaults to the repo's hole-NN.webp",
    )
    parser.add_argument("--out", type=Path, required=True, help="recolored aerial PNG")
    args = parser.parse_args()

    aerial_path = args.aerial or Path(f"public/course/peach-tree/hole-{args.hole:02d}.webp")
    aerial = Image.open(aerial_path).convert("RGB")
    a = np.asarray(aerial).astype(np.float32)

    region = WATER_REGIONS[args.hole]
    m = water_mask(a, region["bbox"], region["seeds"], region.get("rock_polygon"))
    mf = np.asarray(m).astype(np.float32)[..., None] / 255.0

    # upper clip keeps bright rock pixels from turning neon — over water the
    # luminance only carries ripple texture, not identity
    lum = (a.mean(axis=-1, keepdims=True) / 255.0).clip(0.25, 0.75)
    target = TARGET_RGB * (0.6 + 0.8 * lum)
    out = a * (1 - BLEND * mf) + target * (BLEND * mf)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(args.out)
    print(f"{args.out} ({int((np.asarray(m) > 127).sum())} water px recolored)")


if __name__ == "__main__":
    main()
