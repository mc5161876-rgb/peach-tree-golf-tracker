"""Register an original (free-form) AI hole illustration onto the current aerial card's
geometry, so the pretty art can carry the yardage overlay.

Steps
  A. old aerial -> new aerial: global similarity (SIFT + RANSAC). Same raster, so this is tight.
  B. apply A to the old illustration -> illustration in the new card frame (900x1200).
  C. dense residual registration of the illustration onto the new aerial: coarse-to-fine
     tile phase correlation on gradient images, smoothed displacement field, cv2.remap.
  D. report drift (reusing the repo's measure_drift.py) before and after, plus overlays.

Usage:
  python register_art.py --hole 7 --repo ~/rex/peach-tree-golf-tracker --orig orig --cur cur --out out
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, median_filter


def to_gray_f32(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return img.astype(np.float32)


def structure_image(gray: np.ndarray) -> np.ndarray:
    """Gradient magnitude, lightly blurred, contrast-normalised. Phase correlation on this is far
    less sensitive to the photo-vs-painting tone difference than on raw intensity."""
    g = cv2.GaussianBlur(gray, (0, 0), 1.2)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy)
    mag = cv2.GaussianBlur(mag, (0, 0), 1.0)
    mag = mag / (mag.mean() + 1e-6)
    return np.clip(mag, 0, 8).astype(np.float32)


def similarity_old_to_new(old_aerial: np.ndarray, new_aerial: np.ndarray) -> tuple[np.ndarray, int]:
    sift = cv2.SIFT_create(nfeatures=6000)
    g1 = cv2.cvtColor(old_aerial, cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(new_aerial, cv2.COLOR_RGB2GRAY)
    k1, d1 = sift.detectAndCompute(g1, None)
    k2, d2 = sift.detectAndCompute(g2, None)
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    raw = matcher.knnMatch(d1, d2, k=2)
    good = [m for m, n in raw if m.distance < 0.75 * n.distance]
    src = np.float32([k1[m.queryIdx].pt for m in good])
    dst = np.float32([k2[m.trainIdx].pt for m in good])
    M, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.0, maxIters=5000)
    n_in = int(inliers.sum()) if inliers is not None else 0
    return M, n_in


MD = None  # the repo's measure_drift module, injected by main()


def tile_displacements(ref_g: np.ndarray, cand_g: np.ndarray, tile: int, stride: int, min_ratio: float):
    """For each tile, the shift taking cand content onto ref (repo phase_shift convention).
    Confidence is the repo's peak/noise ratio, so 'aligned' means the same thing to the
    registration as it does to the measurement."""
    h, w = ref_g.shape
    pts, vecs, ratios = [], [], []
    for top in range(0, h - tile + 1, stride):
        for left in range(0, w - tile + 1, stride):
            r = ref_g[top:top + tile, left:left + tile]
            c = cand_g[top:top + tile, left:left + tile]
            if r.std() < 1.0 or c.std() < 1.0:
                continue
            # proven by isolated test: phase_shift(a, b) = a's displacement relative to b,
            # so the shift that takes c onto r is phase_shift(r, c).
            dx, dy, ratio = MD.phase_shift(r, c)
            if ratio < min_ratio or abs(dx) > tile * 0.35 or abs(dy) > tile * 0.35:
                continue
            pts.append((left + tile / 2, top + tile / 2))
            vecs.append((dx, dy))
            ratios.append(ratio)
    if not pts:
        return np.zeros((0, 2), np.float32), np.zeros((0, 2), np.float32), np.zeros((0,), np.float32)
    return np.array(pts, np.float32), np.array(vecs, np.float32), np.array(ratios, np.float32)


def field_from_samples(pts, vecs, shape, stride, sigma_px, smoothing=None):
    """Robust thin-plate-spline fit of the scattered tile vectors, with iterative outlier
    rejection (a tile that disagrees with its neighbourhood by a lot is a mismatch, not a
    real local warp). Returns a dense (2, h, w) field on the reference grid."""
    from scipy.interpolate import RBFInterpolator

    h, w = shape
    P = pts.astype(np.float64) / max(h, w)  # normalise coordinates for a well-conditioned fit
    V = vecs.astype(np.float64)
    keep = np.ones(len(P), bool)
    smooth = 1e-3 if smoothing is None else smoothing
    for _ in range(4):
        if keep.sum() < 4:
            break
        rbf = RBFInterpolator(P[keep], V[keep], kernel="thin_plate_spline", smoothing=smooth)
        pred = rbf(P)
        res = np.hypot(*(V - pred).T)
        mad = np.median(res[keep]) + 1e-6
        new_keep = res <= max(3.0, 4.0 * mad)
        if new_keep.sum() == keep.sum() and (new_keep == keep).all():
            break
        keep = new_keep
    rbf = RBFInterpolator(P[keep], V[keep], kernel="thin_plate_spline", smoothing=smooth)
    # evaluate on a coarse lattice then upsample (fast), then a light blur
    gh, gw = h // stride + 2, w // stride + 2
    gy, gx = np.mgrid[0:gh, 0:gw]
    Q = np.stack([gx.ravel() * stride, gy.ravel() * stride], 1).astype(np.float64) / max(h, w)
    G = rbf(Q).reshape(gh, gw, 2)
    up = np.stack([cv2.resize(G[..., ch].astype(np.float32), (gw * stride, gh * stride), interpolation=cv2.INTER_CUBIC)[:h, :w] for ch in range(2)])
    for ch in range(2):
        up[ch] = gaussian_filter(up[ch], sigma_px)
    return up, int(keep.sum()), int(len(keep) - keep.sum())


def apply_field(img: np.ndarray, field: np.ndarray) -> np.ndarray:
    """Output O(q) = I(q - d(q)): content at q-d in the candidate lands at q."""
    h, w = field.shape[1:]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = xs - field[0]
    map_y = ys - field[1]
    return cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def compose_fields(total: np.ndarray, delta: np.ndarray) -> np.ndarray:
    """New total so that applying it once equals applying total then delta (approximately:
    delta is sampled at q - delta which is where total's output content came from)."""
    h, w = total.shape[1:]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = xs - delta[0]
    map_y = ys - delta[1]
    t_dx = cv2.remap(total[0], map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    t_dy = cv2.remap(total[1], map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return np.stack([t_dx + delta[0], t_dy + delta[1]])


def register_dense(ref_rgb: np.ndarray, cand_rgb: np.ndarray, schedule, min_ratio=3.0, log=print):
    """Returns (warped_rgb, total_field, per-pass stats)."""
    ref_g = to_gray_f32(ref_rgb)
    h, w = ref_g.shape
    total = np.zeros((2, h, w), np.float32)
    stats = []
    for tile, stride, sigma in schedule:
        cur = apply_field(cand_rgb, total)
        cand_g = to_gray_f32(cur)
        pts, vecs, ratios = tile_displacements(ref_g, cand_g, tile, stride, min_ratio)
        if len(pts) < 4:
            log(f"  tile {tile}: too few confident tiles ({len(pts)}), skipping")
            continue
        delta, kept, dropped = field_from_samples(pts, vecs, (h, w), stride, sigma)
        total = compose_fields(total, delta)
        mag = np.hypot(vecs[:, 0], vecs[:, 1])
        stats.append({"tile": tile, "tiles": int(len(pts)), "kept": kept, "outliers": dropped,
                      "median_px": float(np.median(mag)), "max_px": float(mag.max())})
        log(f"  tile {tile:3d} stride {stride:3d}: {len(pts):3d} confident tiles ({dropped} outliers dropped), residual median {np.median(mag):5.2f}px max {mag.max():5.2f}px")
    warped = apply_field(cand_rgb, total)
    return warped, total, stats


def checkerboard(a: np.ndarray, b: np.ndarray, cell=100) -> np.ndarray:
    h, w = a.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    m = ((ys // cell + xs // cell) % 2).astype(bool)
    out = a.copy()
    out[m] = b[m]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hole", type=int, required=True)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--orig", type=Path, required=True, help="dir with old hole-XX-illustrated.png + hole-XX.webp")
    ap.add_argument("--cur", type=Path, required=True, help="dir with current hole-XX.webp (new crop)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--selftest", action="store_true", help="also register a synthetically shifted aerial to prove sign/scale")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    hh = f"{args.hole:02d}"

    sys.path.insert(0, str(args.repo / "scripts" / "imagery"))
    import measure_drift as md  # noqa: E402
    global MD
    MD = md

    geometry = md.load_geometry(args.repo / "public/course/peach-tree/sources.json", args.hole)
    ypx = md.yards_per_card_pixel(geometry)
    print(f"Hole {args.hole}: scale {geometry['scale']:.4f}; yards/px ≈ {ypx}")

    old_ill = np.array(Image.open(args.orig / f"hole-{hh}-illustrated.png").convert("RGB"))
    old_aer = np.array(Image.open(args.orig / f"hole-{hh}.webp").convert("RGB"))
    new_aer = np.array(Image.open(args.cur / f"hole-{hh}.webp").convert("RGB"))
    H, W = new_aer.shape[:2]
    print(f"old illustration {old_ill.shape[1]}x{old_ill.shape[0]}, old aerial {old_aer.shape[1]}x{old_aer.shape[0]}, new aerial {W}x{H}")

    # The old illustration may not be the old aerial's pixel size; scale it to the old aerial first.
    if old_ill.shape[:2] != old_aer.shape[:2]:
        old_ill = cv2.resize(old_ill, (old_aer.shape[1], old_aer.shape[0]), interpolation=cv2.INTER_AREA)

    # A. global similarity old aerial -> new aerial
    M, n_in = similarity_old_to_new(old_aer, new_aer)
    s = float(np.hypot(M[0, 0], M[0, 1]))
    ang = float(np.degrees(np.arctan2(M[0, 1], M[0, 0])))
    print(f"A. similarity old->new: scale {s:.4f}, rotation {ang:.2f}°, inliers {n_in}")
    old_aer_in_new = cv2.warpAffine(old_aer, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    ill_in_new = cv2.warpAffine(old_ill, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    Image.fromarray(ill_in_new).save(args.out / f"hole-{hh}-orig-art-in-new-frame.png")
    Image.fromarray(old_aer_in_new).save(args.out / f"hole-{hh}-old-aerial-in-new-frame.png")

    # sanity: old aerial mapped into the new frame should sit on the new aerial almost exactly
    r0 = md.measure(args.cur / f"hole-{hh}.webp", args.out / f"hole-{hh}-old-aerial-in-new-frame.png", geometry, 150)
    print(f"   check: old aerial vs new aerial after similarity -> max {r0['maxYards']:.2f} yd, median {r0['medianYards']:.2f} yd ({r0['tilesMeasured']} tiles)")

    # B/C. dense registration of the art onto the new aerial
    before = md.measure(args.cur / f"hole-{hh}.webp", args.out / f"hole-{hh}-orig-art-in-new-frame.png", geometry, 150)
    print(f"BEFORE dense registration: max {before['maxYards']:.2f} yd, median {before['medianYards']:.2f} yd ({before['tilesMeasured']} tiles, {before['tilesDropped']} dropped)")

    schedule = [(360, 90, 60), (240, 60, 40), (160, 40, 28), (120, 30, 22), (90, 22, 16)]
    warped, field, stats = register_dense(new_aer, ill_in_new, schedule)
    Image.fromarray(warped).save(args.out / f"hole-{hh}-art-registered.png")
    np.save(args.out / f"hole-{hh}-field.npy", field)

    after = md.measure(args.cur / f"hole-{hh}.webp", args.out / f"hole-{hh}-art-registered.png", geometry, 150)
    after_fine = md.measure(args.cur / f"hole-{hh}.webp", args.out / f"hole-{hh}-art-registered.png", geometry, 100)
    print(f"AFTER  dense registration: max {after['maxYards']:.2f} yd, median {after['medianYards']:.2f} yd ({after['tilesMeasured']} tiles, {after['tilesDropped']} dropped)  [tile 150]")
    print(f"                           max {after_fine['maxYards']:.2f} yd, median {after_fine['medianYards']:.2f} yd ({after_fine['tilesMeasured']} tiles)  [tile 100]")
    mag = np.hypot(field[0], field[1])
    print(f"   warp magnitude: median {np.median(mag):.1f}px ({np.median(mag)*ypx[0]:.1f} yd), p95 {np.percentile(mag,95):.1f}px, max {mag.max():.1f}px ({mag.max()*ypx[0]:.1f} yd)")

    # visuals
    Image.fromarray(checkerboard(new_aer, ill_in_new)).save(args.out / f"hole-{hh}-checker-before.png")
    Image.fromarray(checkerboard(new_aer, warped)).save(args.out / f"hole-{hh}-checker-after.png")
    blend = cv2.addWeighted(new_aer, 0.5, warped, 0.5, 0)
    Image.fromarray(blend).save(args.out / f"hole-{hh}-blend-after.png")

    if args.selftest:
        # shift + slightly scale the new aerial itself, then recover it; proves the sign/scale conventions
        T = np.float32([[1.01, 0.0, 9.0], [0.0, 1.01, -7.0]])
        synth = cv2.warpAffine(new_aer, T, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        Image.fromarray(synth).save(args.out / "selftest-synth.png")
        b = md.measure(args.cur / f"hole-{hh}.webp", args.out / "selftest-synth.png", geometry, 150)
        _p, _v, _r = tile_displacements(to_gray_f32(new_aer), to_gray_f32(synth), 360, 90, 3.0)
        print(f"SELFTEST tile-360 median vector {np.median(_v,0)} over {len(_v)} tiles (expect about (-13, +1))")
        w2, _, _ = register_dense(new_aer, synth, schedule, log=lambda *_: None)
        Image.fromarray(w2).save(args.out / "selftest-recovered.png")
        a = md.measure(args.cur / f"hole-{hh}.webp", args.out / "selftest-recovered.png", geometry, 150)
        print(f"SELFTEST synthetic shift: before max {b['maxYards']:.2f} yd -> after max {a['maxYards']:.2f} yd (must drop to ~0)")

    json.dump({"hole": args.hole, "similarity_inliers": n_in, "before": before, "after_150": after, "after_100": after_fine, "passes": stats},
              open(args.out / f"hole-{hh}-report.json", "w"), indent=2, default=float)


if __name__ == "__main__":
    main()
