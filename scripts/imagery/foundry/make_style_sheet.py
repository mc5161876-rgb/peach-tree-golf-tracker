"""Contact sheet for a styled-card sweep: aerial, style reference, then every candidate with its
settings and drift verdict, sorted best-drift first. Usage:
  python make_style_sheet.py --hole 7 --dir out/hole7 --ref refs/hole-07-original.png --out sheets/hole-07.jpg [--top 8]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Helvetica.ttc"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hole", type=int, required=True)
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--ref", type=Path, nargs="+", required=True)
    ap.add_argument("--aerial", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--width", type=int, default=360)
    ap.add_argument("--title", default="")
    ap.add_argument("--filter", default="", help="substring the filename must contain")
    args = ap.parse_args()

    repo = Path.home() / "rex/peach-tree-golf-tracker"
    aerial = args.aerial or repo / f"public/course/peach-tree/hole-{args.hole:02d}.webp"
    cards = []
    for js in sorted(args.dir.glob(f"hole-{args.hole:02d}-styled-*.json")):
        if args.filter and args.filter not in js.name:
            continue
        meta = json.loads(js.read_text())
        png = js.with_suffix(".png")
        if not png.exists():
            continue
        d = meta.get("drift", {})
        c = meta.get("driftClassed")
        s = meta.get("driftVsSkeleton")
        cards.append((s["landMaxYards"] if s else (c["landMaxYards"] if c else d.get("maxYards", 999.0)), png, meta))
    cards.sort(key=lambda c: c[0])
    cards = cards[: args.top]

    W = args.width
    H = int(W * 4 / 3)
    lab = 58
    pad = 12
    f_big = ImageFont.truetype(FONT, 18)
    f = ImageFont.truetype(FONT, 14)
    f_small = ImageFont.truetype(FONT, 12)

    tiles = [("aerial (truth)", "", Image.open(aerial).convert("RGB"), None)]
    for r in args.ref:
        tiles.append((f"style ref: {r.stem}", "", Image.open(r).convert("RGB"), None))
    for mx, png, meta in cards:
        d = meta.get("drift", {})
        t1 = f"{meta['ipMode']} ip{meta['ipScale']:.2f} s{meta['strength']:.2f} c{meta['controlnetConditioningScale']:.2f} {meta['promptFamily']} {meta.get('adapter', meta.get('ipAdapter','').split('/')[-1].replace('ip-adapter','').replace('.safetensors',''))}"
        c = meta.get("driftClassed")
        if c:
            verdict = "PASS" if c["pass"] else "FAIL"
            s = meta.get("driftVsSkeleton")
            if s:
                ok = s["landMaxYards"] <= 5.0
                t2 = (f"vs skeleton {s['landMaxYards']:.2f} max · {s['landMedianYards']:.2f} med yd · {'PASS' if ok else 'FAIL'}"
                      f" | vs aerial {c['landMaxYards']:.1f}/{c['landMedianYards']:.2f} · water≤{c['waterMaxYards']:.0f}")
                tiles.append((t1, t2, Image.open(png).convert("RGB"), ok))
            else:
                t2 = (f"LAND max {c['landMaxYards']:.2f} · med {c['landMedianYards']:.2f} yd · {verdict}"
                      f" · water {c['tilesWater']}t ≤{c['waterMaxYards']:.1f} · {meta.get('secondsTaken', 0):.0f}s")
                tiles.append((t1, t2, Image.open(png).convert("RGB"), c["pass"]))
        else:
            verdict = ("PASS" if d.get("pass") else "FAIL") if d else "unmeasured"
            t2 = f"drift max {d.get('maxYards', float('nan')):.2f} yd · median {d.get('medianYards', float('nan')):.2f} yd · {verdict} · {meta.get('secondsTaken', 0):.0f}s"
            tiles.append((t1, t2, Image.open(png).convert("RGB"), d.get("pass")))

    cols = args.cols
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (pad + cols * (W + pad), 44 + rows * (H + lab + pad)), "#14261c")
    dr = ImageDraw.Draw(sheet)
    title = args.title or f"Hole {args.hole} — style-referenced repaint under ControlNet tile (foundry, MPS). Sorted by drift."
    dr.text((pad, 12), title, fill="#f3e9d2", font=f_big)
    for i, (t1, t2, im, ok) in enumerate(tiles):
        r, c = divmod(i, cols)
        x = pad + c * (W + pad)
        y = 44 + r * (H + lab + pad)
        im = im.resize((W, H), Image.LANCZOS)
        sheet.paste(im, (x, y + lab))
        colour = "#f3e9d2" if ok is None else ("#9fe29f" if ok else "#ff9d9d")
        dr.text((x, y + 4), t1[:60], fill="#f3e9d2", font=f)
        if t2:
            dr.text((x, y + 24), t2, fill=colour, font=f_small)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out, quality=88)
    print(f"saved {args.out} ({sheet.size[0]}x{sheet.size[1]}), {len(cards)} cards")


if __name__ == "__main__":
    main()
