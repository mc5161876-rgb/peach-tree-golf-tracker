"""Checks the drift measurement before it is trusted to judge anything.

A measurement tool that silently under-reports would hand back a PASS on art
that is 20 yards wrong, which is worse than having no tool. So the two cases
that matter are pinned: an image against itself must read zero, and an image
against a known shift of itself must read that shift back.

Run from the repo root:

    <venv>\\Scripts\\python.exe -m unittest discover -s scripts/imagery -v
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from measure_drift import (
    card_point_to_lat_lon,
    distance_yards,
    load_geometry,
    measure,
    phase_shift,
    yards_per_card_pixel,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES = REPO_ROOT / "public" / "course" / "peach-tree" / "sources.json"
AERIAL = REPO_ROOT / "public" / "course" / "peach-tree" / "hole-07.webp"


class YardConversion(unittest.TestCase):
    def test_matches_the_transform_for_every_hole(self):
        """The pixel-to-yard number has to come from the hole's own geometry."""
        for hole in range(1, 19):
            geometry = load_geometry(SOURCES, hole)
            across, along = yards_per_card_pixel(geometry)

            # Walking 100 pixels should cost 100 times one pixel, or the
            # conversion is not linear and the whole measure is suspect.
            origin = card_point_to_lat_lon(0.0, 0.0, geometry)
            far = card_point_to_lat_lon(100.0, 0.0, geometry)
            self.assertAlmostEqual(
                distance_yards(origin, far) / 100.0, across, places=4,
                msg=f"hole {hole} across-axis conversion is not linear",
            )

            # Scale is source pixels per card pixel, and the source raster is
            # about half a metre a pixel, so a card pixel lands near
            # scale * 0.55 yards. Wide of that means the geometry was misread.
            self.assertGreater(across, 0.3 * geometry["scale"])
            self.assertLess(along, 1.2 * geometry["scale"])

    def test_five_yards_is_a_different_pixel_count_per_hole(self):
        """The reason a fixed pixel threshold would be wrong."""
        _, along_two = yards_per_card_pixel(load_geometry(SOURCES, 2))
        _, along_seventeen = yards_per_card_pixel(load_geometry(SOURCES, 17))
        pixels_two = 5.0 / along_two
        pixels_seventeen = 5.0 / along_seventeen
        self.assertLess(pixels_two, pixels_seventeen)
        self.assertGreater(pixels_seventeen / pixels_two, 1.5)


class PhaseShift(unittest.TestCase):
    def test_reads_back_a_known_shift(self):
        rng = np.random.default_rng(7)
        base = rng.normal(128, 40, (150, 150))
        for expected_x, expected_y in [(0, 0), (3, 0), (0, -4), (5, 7), (-6, 2)]:
            shifted = np.roll(np.roll(base, expected_y, axis=0), expected_x, axis=1)
            shift_x, shift_y, ratio = phase_shift(base, shifted)
            self.assertAlmostEqual(shift_x, -expected_x, delta=0.3)
            self.assertAlmostEqual(shift_y, -expected_y, delta=0.3)
            self.assertGreater(ratio, 3.0)


class MeasureAgainstRealCards(unittest.TestCase):
    def setUp(self):
        self.geometry = load_geometry(SOURCES, 7)

    def test_an_aerial_against_itself_reads_zero(self):
        result = measure(AERIAL, AERIAL, self.geometry)
        self.assertLess(
            result["maxYards"], 0.01,
            "a card compared with itself must not report drift",
        )
        self.assertGreater(result["tilesMeasured"], 20)

    def test_a_known_shift_reads_back_in_yards(self):
        """Shift the aerial by a known number of pixels and demand it back."""
        card_size = (self.geometry["card"]["width"], self.geometry["card"]["height"])
        _, yards_along = yards_per_card_pixel(self.geometry)
        offset_pixels = 12
        expected_yards = offset_pixels * yards_along

        image = Image.open(AERIAL).convert("RGB").resize(card_size, Image.LANCZOS)
        shifted = Image.fromarray(
            np.roll(np.asarray(image), offset_pixels, axis=0)
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shifted.png"
            shifted.save(path)
            result = measure(AERIAL, path, self.geometry)

        self.assertAlmostEqual(
            result["medianYards"], expected_yards, delta=0.5,
            msg=(
                f"a {offset_pixels}px shift should read as "
                f"{expected_yards:.2f} yards, got {result['medianYards']:.2f}"
            ),
        )

    def test_a_shift_beyond_tolerance_fails_the_bar(self):
        """The tool has to be able to say no, not only yes.

        Shifted across rather than along, so this also pins that the two card
        axes are converted with their own yards-per-pixel — they differ by
        about a quarter, and using one for the other silently under-reports.
        """
        card_size = (self.geometry["card"]["width"], self.geometry["card"]["height"])
        yards_across, _ = yards_per_card_pixel(self.geometry)
        offset_pixels = int(math.ceil(6.0 / yards_across))

        image = Image.open(AERIAL).convert("RGB").resize(card_size, Image.LANCZOS)
        shifted = Image.fromarray(np.roll(np.asarray(image), offset_pixels, axis=1))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shifted.png"
            shifted.save(path)
            result = measure(AERIAL, path, self.geometry)

        self.assertGreater(result["maxYards"], 5.0)


if __name__ == "__main__":
    unittest.main()
