"""Colour-grade a painted card toward a reference illustration — deterministic, geometry-free.

Reinhard-style statistics transfer in Lab (per-channel mean/std), blended by --amount, then an
optional saturation and contrast lift. Pixels do not move, so drift is untouched; only the
palette, warmth and punch change. Cheapest possible lever for "make it look like the
originals" and fully reversible.

Usage:
  python grade_card.py --ref refs/hole-07-original.png --card out/x.png --out graded/x.png [--amount 0.8] [--sat 1.15] [--contrast 1.08]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def lab_stats(img: np.ndarray):
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(np.float32)
    return lab, lab.reshape(-1, 3).mean(0), lab.reshape(-1, 3).std(0) + 1e-6


def grade(card: np.ndarray, ref: np.ndarray, amount: float, sat: float, contrast: float, protect_mask: np.ndarray | None = None) -> np.ndarray:
    lab, m_c, s_c = lab_stats(card)
    _, m_r, s_r = lab_stats(ref)
    out = (lab - m_c) / s_c * s_r + m_r
    out = lab + amount * (out - lab)
    out = np.clip(out, 0, 255).astype(np.uint8)
    rgb = cv2.cvtColor(out, cv2.COLOR_LAB2RGB)
    if sat != 1.0 or contrast != 1.0:
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
        hsv[..., 1] = np.clip(hsv[..., 1] * sat, 0, 255)
        rgb = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)
        rgb = np.clip((rgb - 128) * contrast + 128, 0, 255).astype(np.uint8)
    if protect_mask is not None:
        rgb[protect_mask] = card[protect_mask]
    return rgb


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", type=Path, required=True)
    ap.add_argument("--card", type=Path, required=True, nargs="+")
    ap.add_argument("--out", type=Path, required=True, help="output dir")
    ap.add_argument("--amount", type=float, default=0.8)
    ap.add_argument("--sat", type=float, default=1.12)
    ap.add_argument("--contrast", type=float, default=1.06)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    ref = np.array(Image.open(args.ref).convert("RGB"))
    for c in args.card:
        card = np.array(Image.open(c).convert("RGB"))
        g = grade(card, ref, args.amount, args.sat, args.contrast)
        out = args.out / (c.stem + f"-graded-a{args.amount:.2f}.png".replace(".", "_", 1) if False else c.stem + "-graded.png")
        Image.fromarray(g).save(out)
        print("graded ->", out)


if __name__ == "__main__":
    main()
