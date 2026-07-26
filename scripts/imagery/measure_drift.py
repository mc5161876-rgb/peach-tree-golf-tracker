"""Measure how far a generated hole card has drifted off its real aerial.

The question this answers is not "do these look similar" but "if a yardage were
read off the generated card, how many yards wrong would it be". So the output
is in yards, never pixels, and the conversion uses each hole's own transform
rather than one number for the course: `cardGeometry.scale` ranges from 0.49 to
1.06 across the 18 holes, which means 5 yards is 6.8 card pixels on hole 2 and
14.6 on hole 17.

Method is phase correlation over a grid of tiles. Each tile reports how far its
content moved between the two images; a tile whose correlation peak is weak
carries no usable signal (flat grass, open water) and is dropped rather than
guessed at. What survives is a displacement field, and the honest summary of it
is the worst tile, not the average — a card can be perfect everywhere except
the green and still be useless.

Deliberately depends on numpy and Pillow only. No torch, no OpenCV: this has to
stay runnable to check any image against any other, long after the generation
pipeline has changed.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

EARTH_RADIUS_METRES = 6_371_000
YARDS_PER_METRE = 1.0936132983377078

DEFAULT_TILE = 150
DEFAULT_TOLERANCE_YARDS = 5.0
# Below this, the correlation peak is indistinguishable from the noise floor and
# the tile's reported shift is meaningless. Tuned so featureless grass and water
# drop out while fairway edges, bunkers, tree lines, and cart paths survive.
MIN_PEAK_RATIO = 3.0


def load_geometry(sources_path: Path, hole: int) -> dict:
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    card_geometry = sources["cardGeometry"]
    return {
        "bbox": card_geometry["bbox"],
        "source": card_geometry["source"],
        "card": card_geometry["card"],
        **card_geometry["holes"][str(hole)],
    }


def card_point_to_lat_lon(x: float, y: float, geometry: dict) -> tuple[float, float]:
    """Mirrors `cardPointToLatLon` in app/data/course-geometry.ts."""
    card = geometry["card"]
    center = geometry["center"]
    unit = geometry["unit"]
    perp = geometry["perp"]
    scale = geometry["scale"]
    bbox = geometry["bbox"]
    source = geometry["source"]

    across = (x - card["width"] / 2) * scale
    along = -(y - card["height"] / 2) * scale
    pixel_x = center["x"] + along * unit["x"] + across * perp["x"]
    pixel_y = center["y"] + along * unit["y"] + across * perp["y"]

    lat = bbox["maxLat"] - (pixel_y / source["height"]) * (bbox["maxLat"] - bbox["minLat"])
    lon = bbox["minLon"] + (pixel_x / source["width"]) * (bbox["maxLon"] - bbox["minLon"])
    return lat, lon


def distance_yards(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = first
    lat2, lon2 = second
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METRES * math.asin(math.sqrt(a)) * YARDS_PER_METRE


def yards_per_card_pixel(geometry: dict) -> tuple[float, float]:
    """How many yards one card pixel covers, along each card axis.

    Derived by walking one pixel through the same transform the app uses rather
    than from the bounding box directly, so this number cannot disagree with
    what a yardage read off the card would say.
    """
    origin = card_point_to_lat_lon(0.0, 0.0, geometry)
    one_across = card_point_to_lat_lon(1.0, 0.0, geometry)
    one_along = card_point_to_lat_lon(0.0, 1.0, geometry)
    return distance_yards(origin, one_across), distance_yards(origin, one_along)


def load_card(path: Path, card_size: tuple[int, int]) -> np.ndarray:
    """Greyscale float array at card resolution.

    Generated and illustrated cards are not guaranteed to arrive at 900x1200,
    so everything is resampled onto the card grid first. Comparing at different
    resolutions would report a scale difference as drift.
    """
    image = Image.open(path).convert("L")
    if image.size != card_size:
        image = image.resize(card_size, Image.LANCZOS)
    return np.asarray(image, dtype=np.float64)


def phase_shift(first: np.ndarray, second: np.ndarray) -> tuple[float, float, float]:
    """Sub-pixel shift taking `first` onto `second`, plus a confidence ratio.

    Phase correlation rather than raw cross-correlation: dividing out the
    magnitude makes the answer depend on where edges are and not on how bright
    or contrasty either tile is, which matters when one image is a painted
    reinterpretation of the other.
    """
    window = np.outer(np.hanning(first.shape[0]), np.hanning(first.shape[1]))
    a = (first - first.mean()) * window
    b = (second - second.mean()) * window

    spectrum = np.fft.fft2(a) * np.conj(np.fft.fft2(b))
    magnitude = np.abs(spectrum)
    magnitude[magnitude == 0] = 1e-12
    correlation = np.real(np.fft.ifft2(spectrum / magnitude))

    peak_index = int(np.argmax(correlation))
    peak_y, peak_x = np.unravel_index(peak_index, correlation.shape)
    peak = correlation[peak_y, peak_x]
    noise = np.abs(correlation).mean()
    ratio = float(peak / noise) if noise > 0 else 0.0

    def refine(axis_values: np.ndarray, index: int) -> float:
        """Parabolic fit through the peak and its neighbours."""
        length = len(axis_values)
        before = axis_values[(index - 1) % length]
        at = axis_values[index]
        after = axis_values[(index + 1) % length]
        denominator = before - 2 * at + after
        if denominator == 0:
            return float(index)
        return index + 0.5 * (before - after) / denominator

    refined_y = refine(correlation[:, peak_x], int(peak_y))
    refined_x = refine(correlation[peak_y, :], int(peak_x))

    height, width = correlation.shape
    shift_y = refined_y - height if refined_y > height / 2 else refined_y
    shift_x = refined_x - width if refined_x > width / 2 else refined_x
    return float(shift_x), float(shift_y), ratio


def measure(
    reference_path: Path,
    candidate_path: Path,
    geometry: dict,
    tile: int = DEFAULT_TILE,
) -> dict:
    card_size = (geometry["card"]["width"], geometry["card"]["height"])
    reference = load_card(reference_path, card_size)
    candidate = load_card(candidate_path, card_size)
    yards_x, yards_y = yards_per_card_pixel(geometry)

    displacements: list[dict] = []
    dropped = 0
    for top in range(0, card_size[1] - tile + 1, tile):
        for left in range(0, card_size[0] - tile + 1, tile):
            reference_tile = reference[top : top + tile, left : left + tile]
            candidate_tile = candidate[top : top + tile, left : left + tile]

            # A tile with no structure cannot report where anything moved.
            if reference_tile.std() < 1.0 or candidate_tile.std() < 1.0:
                dropped += 1
                continue

            shift_x, shift_y, ratio = phase_shift(reference_tile, candidate_tile)
            if ratio < MIN_PEAK_RATIO:
                dropped += 1
                continue

            displacements.append(
                {
                    "x": left + tile // 2,
                    "y": top + tile // 2,
                    "shiftX": shift_x,
                    "shiftY": shift_y,
                    "yards": math.hypot(shift_x * yards_x, shift_y * yards_y),
                    "confidence": ratio,
                }
            )

    if not displacements:
        raise ValueError(
            f"no tile in {candidate_path.name} carried enough structure to measure"
        )

    yards = sorted(item["yards"] for item in displacements)
    worst = max(displacements, key=lambda item: item["yards"])
    return {
        "candidate": candidate_path.name,
        "reference": reference_path.name,
        "tilesMeasured": len(displacements),
        "tilesDropped": dropped,
        "yardsPerPixel": {"across": yards_x, "along": yards_y},
        "maxYards": yards[-1],
        "medianYards": yards[len(yards) // 2],
        "worstTile": {"x": worst["x"], "y": worst["y"]},
    }


def format_report(result: dict, tolerance: float) -> str:
    verdict = "PASS" if result["maxYards"] <= tolerance else "FAIL"
    return (
        f"{result['candidate']:<44} "
        f"max {result['maxYards']:6.2f} yd   "
        f"median {result['medianYards']:6.2f} yd   "
        f"{result['tilesMeasured']:>3} tiles ({result['tilesDropped']} dropped)   "
        f"worst at ({result['worstTile']['x']},{result['worstTile']['y']})   "
        f"{verdict} at {tolerance:.0f} yd"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hole", type=int, required=True)
    parser.add_argument("--reference", type=Path, required=True, help="the real aerial card")
    parser.add_argument(
        "--candidate",
        type=Path,
        nargs="+",
        required=True,
        help="one or more cards to measure against the reference",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("public/course/peach-tree/sources.json"),
    )
    parser.add_argument("--tile", type=int, default=DEFAULT_TILE)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_YARDS)
    parser.add_argument("--json", type=Path, help="also write the raw results here")
    args = parser.parse_args()

    geometry = load_geometry(args.sources, args.hole)
    yards_x, yards_y = yards_per_card_pixel(geometry)
    print(
        f"Hole {args.hole}: scale {geometry['scale']:.4f}, "
        f"{yards_x:.3f} yd per pixel across / {yards_y:.3f} along, "
        f"{args.tolerance:.0f} yd = {args.tolerance / yards_y:.1f} px"
    )

    results = []
    for candidate in args.candidate:
        result = measure(args.reference, candidate, geometry, args.tile)
        result["hole"] = args.hole
        result["pass"] = result["maxYards"] <= args.tolerance
        results.append(result)
        print("  " + format_report(result, args.tolerance))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
