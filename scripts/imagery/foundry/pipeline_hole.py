"""One hole, end to end: skeleton -> gpt-image-2 repaint -> snap back -> gate -> final card + sidecar.

Steps (all deterministic except the paint, which is gated afterwards):
  1. skeleton   make_base_map.render(hole, procedural, detail, dry_sigma=4)  -> cond/hole-NN-base-v6.png (+classes)
  2. frame      pad to 2:3 + thin white border                                -> cond/hole-NN-base-v6-pad23-framed.png
  3. paint      gpt_image_render.py via the Hermes venv (gpt-image-2, Codex OAuth), style ref = the hole's original art
  4. crop       detect the white frame in the output, crop to it, back to 900x1200
  5. snap       ECC global affine + gentle dense snap onto the skeleton (register_art.register_dense, coarse tiles)
  6. gate       measure_drift_classed: painted-vs-skeleton (the painter gate), skeleton-vs-aerial, painted-vs-aerial, water separately
  7. write      final/hole-NN.png + final/hole-NN.json + final/hole-NN-sheet.jpg

Usage: .venv/bin/python pipeline_hole.py --hole 7 [--skip-paint] [--attempts 2]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path.home() / "rex/peach-tree-golf-tracker/scripts/imagery"))
import measure_drift as md  # noqa: E402
import register_art as ra  # noqa: E402
import make_base_map as mbm  # noqa: E402
from measure_drift_classed import measure_classed  # noqa: E402

ra.MD = md
REPO = Path.home() / "rex/peach-tree-golf-tracker"
HERMES_PY = Path.home() / ".hermes/hermes-agent/venv/bin/python"
TOL = 5.0


def g32(a):
    return cv2.GaussianBlur(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32), (0, 0), 2.0)


def frame_and_pad(base_png: Path, out_png: Path) -> int:
    im = Image.open(base_png).convert("RGB")
    W, H = im.size
    th = int(round(W * 1.5))
    pad = (th - H) // 2
    canvas = Image.new("RGB", (W, th), (20, 38, 28))
    canvas.paste(im, (0, pad))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, W - 1, th - 1], outline=(255, 255, 255), width=6)
    canvas.save(out_png)
    return pad


def crop_to_frame(raw: np.ndarray, pad: int) -> Image.Image:
    """Find the white frame the model was asked to keep; fall back to the full image."""
    white = (raw.min(-1) > 225).astype(np.uint8)
    rows, cols = white.sum(1), white.sum(0)
    h, w = white.shape
    if rows.max() > w * 0.5 and cols.max() > h * 0.5:
        top = int(np.argmax(rows > w * 0.5))
        bot = int(len(rows) - 1 - np.argmax(rows[::-1] > w * 0.5))
        left = int(np.argmax(cols > h * 0.5))
        right = int(len(cols) - 1 - np.argmax(cols[::-1] > h * 0.5))
        inner = raw[top + 10:bot - 9, left + 10:right - 9]
        frame_found = True
    else:
        inner = raw
        frame_found = False
    im = Image.fromarray(inner).resize((900, 1350), Image.LANCZOS).crop((0, pad, 900, pad + 1200))
    return im, frame_found


def ecc_align(skel: np.ndarray, card: np.ndarray):
    warp = np.eye(2, 3, dtype=np.float32)
    cc, warp = cv2.findTransformECC(g32(skel), g32(card), warp, cv2.MOTION_AFFINE,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6), None, 5)
    out = cv2.warpAffine(card, warp, (900, 1200), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT)
    return out, warp, float(cc)


def snap(skel: np.ndarray, card: np.ndarray):
    out, field, _ = ra.register_dense(skel, card, [(300, 75, 50), (200, 50, 36), (150, 38, 28)], log=lambda *_: None)
    mag = np.hypot(field[0], field[1])
    return out, float(np.median(mag)), float(mag.max())


def sheet(hole: int, ref: Path, skel: Path, final: Path, out: Path, s: dict, a: dict) -> None:
    f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    fs = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
    ims = [("original art (style ref)", Image.open(ref).convert("RGB")), ("skeleton — exact geometry", Image.open(skel).convert("RGB")),
           ("final card", Image.open(final).convert("RGB")), ("final — green end", Image.open(final).convert("RGB").crop((250, 0, 650, 533))),
           ("final — tee end", Image.open(final).convert("RGB").crop((250, 667, 650, 1200)))]
    W, H, pad, lab = 280, 373, 10, 44
    sh = Image.new("RGB", (pad + 5 * (W + pad), 36 + H + lab + pad), "#14261c")
    d = ImageDraw.Draw(sh)
    ok = s["landMaxYards"] <= TOL
    d.text((pad, 8), f"Hole {hole} — vs skeleton max {s['landMaxYards']:.2f} yd · median {s['landMedianYards']:.2f} yd · {'PASS' if ok else 'FAIL'}"
                     f"   |   vs aerial (land) max {a['landMaxYards']:.2f} · median {a['landMedianYards']:.2f} · water tiles {a['tilesWater']} ≤{a['waterMaxYards']:.1f} yd",
           fill="#9fe29f" if ok else "#ff9d9d", font=f)
    for i, (t, im) in enumerate(ims):
        x = pad + i * (W + pad)
        d.text((x, 36 + 4), t, fill="#f3e9d2", font=fs)
        sh.paste(im.resize((W, H), Image.LANCZOS), (x, 36 + lab))
    sh.save(out, quality=90)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hole", type=int, required=True)
    ap.add_argument("--attempts", type=int, default=2, help="gpt-image-2 attempts if the gate fails")
    ap.add_argument("--skip-paint", action="store_true", help="reuse an existing raw render")
    ap.add_argument("--out", type=Path, default=Path("final"))
    args = ap.parse_args()
    h = args.hole
    hh = f"{h:02d}"
    args.out.mkdir(exist_ok=True)
    t0 = time.time()

    # 1. skeleton
    mbm.DRY_SIGMA = 4.0
    mbm.TREES_MODE = "photo"
    mbm.render(h, Path("cond/osm-course.json"), Path("cond"), False, 1.0, "-v6", True)
    skel_p = Path(f"cond/hole-{hh}-base-v6.png")
    cls_p = Path(f"cond/hole-{hh}-classes.png")
    skel = np.array(Image.open(skel_p).convert("RGB"))
    aerial_p = REPO / f"public/course/peach-tree/hole-{hh}.webp"
    g = md.load_geometry(REPO / "public/course/peach-tree/sources.json", h)
    sk_vs_aer = md.measure(aerial_p, skel_p, g, 150)
    print(f"[hole {h}] skeleton vs aerial: max {sk_vs_aer['maxYards']:.2f} yd median {sk_vs_aer['medianYards']:.2f}", flush=True)

    # 2. frame
    framed_p = Path(f"cond/hole-{hh}-base-v6-pad23-framed.png")
    pad = frame_and_pad(skel_p, framed_p)
    ref_p = Path(f"refs/hole-{hh}-original.png")

    best = None
    for attempt in range(1, args.attempts + 1):
        raw_out = Path(f"out/hole{h}-gpt")
        raw_out.mkdir(parents=True, exist_ok=True)
        tag = f"-run{attempt}"
        raw_p = raw_out / f"hole-{hh}-gptimage2{tag}-raw.png"
        # 3. paint
        if not (args.skip_paint and raw_p.exists()):
            cmd = [str(HERMES_PY), "gpt_image_render.py", "--hole", str(h), "--skeleton", str(framed_p), "--style-ref", str(ref_p),
                   "--out", str(raw_out), f"--tag={tag}", f"--prompt={FRAMED_PROMPT}"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0 or not raw_p.exists():
                print(f"[hole {h}] paint attempt {attempt} failed: {r.stdout[-400:]} {r.stderr[-400:]}", flush=True)
                continue
        raw = np.array(Image.open(raw_p).convert("RGB"))
        # 4. crop
        im, frame_found = crop_to_frame(raw, pad)
        card = np.array(im)
        # 5. snap
        try:
            aligned, warp, cc = ecc_align(skel, card)
        except cv2.error:
            aligned, warp, cc = card, np.eye(2, 3, dtype=np.float32), 0.0
        snapped, snap_med, snap_max = snap(skel, aligned)
        final_p = args.out / f"hole-{hh}.png"
        cand_p = args.out / f"hole-{hh}-attempt{attempt}.png"
        Image.fromarray(snapped).save(cand_p)
        # 6. gate
        s = measure_classed(h, cand_p, cls_p, 150, reference=skel_p)
        s100 = measure_classed(h, cand_p, cls_p, 100, reference=skel_p)
        a = measure_classed(h, cand_p, cls_p, 150)
        rec = {"attempt": attempt, "frameFound": frame_found, "eccCC": round(cc, 3), "eccAffine": np.round(warp, 4).tolist(),
               "snapMedianPx": round(snap_med, 2), "snapMaxPx": round(snap_max, 2),
               "vsSkeleton150": s, "vsSkeleton100": s100, "vsAerial150": a, "candidate": str(cand_p), "raw": str(raw_p)}
        ok = s["landMaxYards"] <= TOL  # the project standard is the 150-px tile; t100 is reported for context only
        print(f"[hole {h}] attempt {attempt}: frame={frame_found} ecc={cc:.3f} snap med {snap_med:.1f}px | vs skeleton max {s['landMaxYards']:.2f} med {s['landMedianYards']:.2f} (t100 {s100['landMaxYards']:.2f}) | vs aerial land max {a['landMaxYards']:.2f} med {a['landMedianYards']:.2f} | {'PASS' if ok else 'FAIL'}", flush=True)
        if best is None or s["landMaxYards"] < best["vsSkeleton150"]["landMaxYards"]:
            best = rec
        if ok:
            break
    if best is None:
        print(f"[hole {h}] NO RENDER", flush=True)
        sys.exit(2)
    # 7. write (+ Qwen content QA, soft)
    final_p = args.out / f"hole-{hh}.png"
    Image.open(best["candidate"]).save(final_p)
    try:
        from qa_qwen import qa as qwen_qa
        best["qwen"] = qwen_qa(skel_p, final_p)
        if best["qwen"].get("available"):
            print(f"[hole {h}] qwen QA: {'OK' if best['qwen']['pass'] else 'ISSUES ' + ','.join(best['qwen']['issues'])} ({best['qwen']['seconds']}s)", flush=True)
    except Exception as exc:
        best["qwen"] = {"available": False, "error": str(exc)[:200]}
    meta = {"hole": h, "skeletonVsAerial": {"maxYards": sk_vs_aer["maxYards"], "medianYards": sk_vs_aer["medianYards"]},
            "best": best, "pass": best["vsSkeleton150"]["landMaxYards"] <= TOL, "secondsTotal": round(time.time() - t0, 1),
            "painter": "gpt-image-2-high via Hermes openai-codex plugin", "styleRef": str(ref_p), "skeleton": str(skel_p)}
    (args.out / f"hole-{hh}.json").write_text(json.dumps(meta, indent=2, default=float) + "\n")
    sheet(h, ref_p, skel_p, final_p, args.out / f"hole-{hh}-sheet.jpg", best["vsSkeleton150"], best["vsAerial150"])
    print(f"[hole {h}] DONE {'PASS' if meta['pass'] else 'FAIL'} in {meta['secondsTotal']:.0f}s -> {final_p}", flush=True)


FRAMED_PROMPT = (
    "Repaint the FIRST image (a top-down golf hole map with a thin white border frame) as a premium photorealistic "
    "cinematic 2.5D yardage-book illustration in exactly the visual style of the SECOND image: lush manicured grass "
    "with mow stripes, individually modeled tree canopies with long warm late-afternoon shadows, clean sculpted sand "
    "bunkers, clear deep blue water, dry golden rough, rich saturated colour, crisp detail. CRITICAL: geometry is "
    "sacred. Keep the white border frame, the framing and every shape, outline, position and size EXACTLY as in the "
    "first image: fairways, greens, tees, bunkers, water, tree clusters, cart paths, the gold hole line and its two "
    "markers. Do not add, remove, move, resize or reshape anything. No text, labels, people, carts, buildings, roads "
    "or new water. Same straight-down orthographic view."
)

if __name__ == "__main__":
    main()
