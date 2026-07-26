"""Build the sheet Mario actually judges the art on.

The comparison that matters is not new-versus-aerial. He already knows the
aerials are fuzzy; that is why the illustrated set exists. The real question is
whether a geometry-locked repaint looks as good as the art he likes but is
allowed to carry numbers — so every panel sits beside the current illustrated
card, and each one is captioned with its measured drift in yards.

Sized to be read on a phone rather than a desktop, since that is where the
decision gets made.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PANEL_WIDTH = 420
CAPTION_HEIGHT = 96
GAP = 12
BACKGROUND = (14, 26, 20)
TEXT = (255, 253, 244)
MUTED = (150, 178, 160)
PASS_COLOUR = (128, 214, 160)
FAIL_COLOUR = (239, 138, 128)


def load_font(size: int, bold: bool = False):
    for name in (["seguisb.ttf", "segoeuib.ttf"] if bold else ["segoeui.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def panel(image_path: Path, title: str, lines: list[tuple[str, tuple[int, int, int]]]):
    image = Image.open(image_path).convert("RGB")
    height = round(image.height * (PANEL_WIDTH / image.width))
    image = image.resize((PANEL_WIDTH, height), Image.LANCZOS)

    canvas = Image.new("RGB", (PANEL_WIDTH, height + CAPTION_HEIGHT), BACKGROUND)
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)

    draw.text((14, height + 12), title, font=load_font(19, bold=True), fill=TEXT)
    offset = height + 40
    for text, colour in lines:
        draw.text((14, offset), text, font=load_font(15), fill=colour)
        offset += 21

    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hole", type=int, required=True)
    parser.add_argument("--aerial", type=Path, required=True)
    parser.add_argument("--illustrated", type=Path, required=True)
    parser.add_argument(
        "--generated",
        type=Path,
        nargs="+",
        required=True,
        help="generated cards, in the order they should appear",
    )
    parser.add_argument(
        "--drift",
        type=Path,
        help="JSON from measure_drift.py, to caption each panel with its yards",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    drift_by_name: dict[str, dict] = {}
    if args.drift and args.drift.exists():
        for entry in json.loads(args.drift.read_text(encoding="utf-8")):
            drift_by_name[entry["candidate"]] = entry

    def drift_lines(path: Path) -> list[tuple[str, tuple[int, int, int]]]:
        entry = drift_by_name.get(path.name)
        if not entry:
            return [("drift not measured", MUTED)]
        verdict = "PASS at 5 yd" if entry["maxYards"] <= 5.0 else "FAIL at 5 yd"
        colour = PASS_COLOUR if entry["maxYards"] <= 5.0 else FAIL_COLOUR
        return [
            (f"max {entry['maxYards']:.1f} yd · median {entry['medianYards']:.1f} yd", MUTED),
            (verdict, colour),
        ]

    panels = [
        panel(
            args.aerial,
            "Real aerial",
            [("2022 NAIP · the ground truth", MUTED), ("0.0 yd by definition", PASS_COLOUR)],
        ),
        panel(args.illustrated, "Current art", drift_lines(args.illustrated)),
    ]

    for generated in args.generated:
        settings = generated.with_suffix(".json")
        strength = "?"
        if settings.exists():
            strength = f"{json.loads(settings.read_text(encoding='utf-8'))['strength']:.2f}"
        panels.append(panel(generated, f"Locked · strength {strength}", drift_lines(generated)))

    width = len(panels) * PANEL_WIDTH + (len(panels) + 1) * GAP
    height = max(item.height for item in panels) + 2 * GAP
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    for index, item in enumerate(panels):
        sheet.paste(item, (GAP + index * (PANEL_WIDTH + GAP), GAP))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(f"Wrote {args.out} ({sheet.width}x{sheet.height}, {len(panels)} panels)")


if __name__ == "__main__":
    main()
