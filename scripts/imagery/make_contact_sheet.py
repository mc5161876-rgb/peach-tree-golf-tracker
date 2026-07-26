"""Every hole, before and after a framing change, on one sheet.

A crop change is easy to verify in aggregate and easy to get wrong on one
hole — a dogleg that now runs off the edge, a green that lost its surround.
Eighteen pairs on a single sheet is the cheapest way to catch the one hole that
broke while the other seventeen improved.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PANEL_WIDTH = 132
COLUMNS = 6
CAPTION = 30
GAP = 10
BACKGROUND = (14, 26, 20)
TEXT = (255, 253, 244)
MUTED = (150, 178, 160)

EARTH_RADIUS_METRES = 6_371_000
YARDS_PER_METRE = 1.0936132983377078


def font(size: int, bold: bool = False):
    for name in (["seguisb.ttf"] if bold else ["segoeui.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def distance_yards(first, second) -> float:
    delta_lat = math.radians(second[0] - first[0])
    delta_lon = math.radians(second[1] - first[1])
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(math.radians(first[0]))
        * math.cos(math.radians(second[0]))
        * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METRES * math.asin(math.sqrt(a)) * YARDS_PER_METRE


def frame_ratio(sources: dict, hole: int) -> float:
    """Card height against hole length, the number the crop change targets."""
    card_geometry = sources["cardGeometry"]
    geometry = {
        "bbox": card_geometry["bbox"],
        "source": card_geometry["source"],
        "card": card_geometry["card"],
        **card_geometry["holes"][str(hole)],
    }
    bbox, source, card = geometry["bbox"], geometry["source"], geometry["card"]

    def card_point(x: float, y: float):
        across = (x - card["width"] / 2) * geometry["scale"]
        along = -(y - card["height"] / 2) * geometry["scale"]
        pixel_x = geometry["center"]["x"] + along * geometry["unit"]["x"] + across * geometry["perp"]["x"]
        pixel_y = geometry["center"]["y"] + along * geometry["unit"]["y"] + across * geometry["perp"]["y"]
        return (
            bbox["maxLat"] - (pixel_y / source["height"]) * (bbox["maxLat"] - bbox["minLat"]),
            bbox["minLon"] + (pixel_x / source["width"]) * (bbox["maxLon"] - bbox["minLon"]),
        )

    points = sources["centerlines"]["holes"][str(hole)]
    hole_yards = sum(
        distance_yards(points[index - 1], points[index]) for index in range(1, len(points))
    )
    card_yards = distance_yards(card_point(450, 0), card_point(450, 1200))
    return card_yards / hole_yards


def cell(before: Path, after: Path, label: str, sub: str) -> Image.Image:
    height = round(PANEL_WIDTH * 4 / 3)
    width = PANEL_WIDTH * 2 + 4
    canvas = Image.new("RGB", (width, height + CAPTION), BACKGROUND)

    for index, path in enumerate((before, after)):
        image = Image.open(path).convert("RGB").resize((PANEL_WIDTH, height), Image.LANCZOS)
        canvas.paste(image, (index * (PANEL_WIDTH + 4), 0))

    draw = ImageDraw.Draw(canvas)
    draw.text((2, height + 5), label, font=font(14, bold=True), fill=TEXT)
    draw.text((2, height + 19), sub, font=font(11), fill=MUTED)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True, help="directory of the old cards")
    parser.add_argument("--after", type=Path, required=True, help="directory of the new cards")
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("public/course/peach-tree/sources.json"),
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    sources = json.loads(args.sources.read_text(encoding="utf-8"))

    cells = []
    for hole in range(1, 19):
        name = f"hole-{hole:02d}.webp"
        cells.append(
            cell(
                args.before / name,
                args.after / name,
                f"Hole {hole}",
                f"now {frame_ratio(sources, hole):.2f}x",
            )
        )

    rows = math.ceil(len(cells) / COLUMNS)
    cell_width, cell_height = cells[0].size
    sheet = Image.new(
        "RGB",
        (
            COLUMNS * cell_width + (COLUMNS + 1) * GAP,
            rows * cell_height + (rows + 1) * GAP,
        ),
        BACKGROUND,
    )
    for index, item in enumerate(cells):
        column, row = index % COLUMNS, index // COLUMNS
        sheet.paste(
            item,
            (GAP + column * (cell_width + GAP), GAP + row * (cell_height + GAP)),
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(f"Wrote {args.out} ({sheet.width}x{sheet.height}) - each pair is before | after")


if __name__ == "__main__":
    main()
