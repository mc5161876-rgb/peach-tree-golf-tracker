"""Generate Roundwell's Peach Tree hole atlas from real aerial imagery.

The base raster is public-domain 2022 USDA NAIP imagery served by USGS.
Hole centerlines are read from OpenStreetMap ways and used only to orient and
crop each real aerial. The generated cards are illustrative planning aids, not
GPS products.
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps


COURSE_BBOX = (-121.553, 39.135, -121.530, 39.152)
NAIP_URL = (
    "https://imagery.nationalmap.gov/arcgis/rest/services/"
    "USGSNAIPImagery/ImageServer/exportImage"
    "?bbox=-121.553,39.135,-121.530,39.152"
    "&bboxSR=4326&size=4000,2957&imageSR=4326&format=jpg&f=image"
)

# OpenStreetMap hole centerline ways, refs 1 through 18.
OSM_HOLE_WAYS = [
    1426341377,
    1426341375,
    1426341376,
    1426341378,
    1426341379,
    1426341380,
    1426341381,
    1426341382,
    1426341383,
    1426341384,
    1426341385,
    1426341386,
    1426341387,
    1426341388,
    1426341389,
    1426341390,
    1426341391,
    1426341392,
]

USER_AGENT = "RoundwellPrototype/2.0 (local course-atlas generator)"


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def download_naip(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(request_bytes(NAIP_URL))
    return destination


def fetch_centerlines() -> dict[int, list[tuple[float, float]]]:
    centerlines: dict[int, list[tuple[float, float]]] = {}
    for way_id in OSM_HOLE_WAYS:
        payload = json.loads(
            request_bytes(
                f"https://api.openstreetmap.org/api/0.6/way/{way_id}/full.json"
            )
        )
        nodes = {
            item["id"]: (item["lat"], item["lon"])
            for item in payload["elements"]
            if item["type"] == "node"
        }
        way = next(item for item in payload["elements"] if item["type"] == "way")
        hole_number = int(way["tags"]["ref"])
        centerlines[hole_number] = [nodes[node_id] for node_id in way["nodes"]]
    return centerlines


def color_grade(image: Image.Image) -> Image.Image:
    image = ImageOps.autocontrast(image.convert("RGB"), cutoff=0.6)
    image = ImageEnhance.Color(image).enhance(1.14)
    image = ImageEnhance.Contrast(image).enhance(1.12)
    image = ImageEnhance.Brightness(image).enhance(0.93)
    image = ImageEnhance.Sharpness(image).enhance(1.22)
    forest = Image.new("RGB", image.size, (10, 41, 29))
    return Image.blend(image, forest, 0.08)


def add_vignette(image: Image.Image, strength: int = 105) -> Image.Image:
    width, height = image.size
    mask = Image.new("L", (width, height), 0)
    pixels = mask.load()
    for y in range(height):
        ny = (y - height / 2) / (height / 2)
        for x in range(width):
            nx = (x - width / 2) / (width / 2)
            radius = min(1.0, math.sqrt(nx * nx + ny * ny))
            pixels[x, y] = int(max(0, radius - 0.28) / 0.72 * strength)
    overlay = Image.new("RGBA", image.size, (2, 13, 9, 0))
    overlay.putalpha(mask.filter(ImageFilter.GaussianBlur(radius=18)))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def geo_to_pixel(
    lat: float, lon: float, width: int, height: int
) -> tuple[float, float]:
    min_lon, min_lat, max_lon, max_lat = COURSE_BBOX
    x = (lon - min_lon) / (max_lon - min_lon) * width
    y = (max_lat - lat) / (max_lat - min_lat) * height
    return x, y


def atlas_card(
    source: Image.Image, points_geo: list[tuple[float, float]], size=(900, 1200)
) -> Image.Image:
    source_width, source_height = source.size
    points = [
        geo_to_pixel(lat, lon, source_width, source_height)
        for lat, lon in points_geo
    ]
    tee_x, tee_y = points[0]
    green_x, green_y = points[-1]
    vector_x = green_x - tee_x
    vector_y = green_y - tee_y
    vector_length = math.hypot(vector_x, vector_y)
    unit_x, unit_y = vector_x / vector_length, vector_y / vector_length
    perp_x, perp_y = -unit_y, unit_x
    center_x = sum(point[0] for point in points) / len(points)
    center_y = sum(point[1] for point in points) / len(points)

    along = [
        (x - center_x) * unit_x + (y - center_y) * unit_y for x, y in points
    ]
    across = [
        (x - center_x) * perp_x + (y - center_y) * perp_y for x, y in points
    ]
    output_width, output_height = size
    scale = max(
        (max(along) - min(along) + 310) / output_height,
        (max(across) - min(across) + 360) / output_width,
    )

    a = scale * perp_x
    b = -scale * unit_x
    c = center_x - a * output_width / 2 - b * output_height / 2
    d = scale * perp_y
    e = -scale * unit_y
    f = center_y - d * output_width / 2 - e * output_height / 2
    card = source.transform(
        size,
        Image.Transform.AFFINE,
        (a, b, c, d, e, f),
        resample=Image.Resampling.BICUBIC,
        fillcolor=(5, 23, 16),
    )
    card = color_grade(card)

    def to_card(point: tuple[float, float]) -> tuple[float, float]:
        offset_x = point[0] - center_x
        offset_y = point[1] - center_y
        x = output_width / 2 + (offset_x * perp_x + offset_y * perp_y) / scale
        y = output_height / 2 - (offset_x * unit_x + offset_y * unit_y) / scale
        return x, y

    route = [to_card(point) for point in points]
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.line(route, fill=(5, 20, 14, 155), width=17, joint="curve")
    draw.line(route, fill=(224, 190, 105, 225), width=5, joint="curve")

    for index, point in enumerate((route[0], route[-1])):
        radius = 16 if index == 0 else 19
        x, y = point
        draw.ellipse(
            (x - radius - 5, y - radius - 5, x + radius + 5, y + radius + 5),
            fill=(4, 19, 13, 150),
        )
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            outline=(249, 230, 174, 240),
            width=5,
        )
        draw.ellipse(
            (x - 4, y - 4, x + 4, y + 4), fill=(249, 230, 174, 255)
        )

    card = Image.alpha_composite(card.convert("RGBA"), overlay)
    card = add_vignette(card.convert("RGB"), strength=122)

    shade = Image.new("RGBA", size, (0, 0, 0, 0))
    shade_pixels = shade.load()
    for y in range(output_height):
        edge = max(0.0, (y / output_height - 0.67) / 0.33)
        top = max(0.0, (0.22 - y / output_height) / 0.22)
        alpha = int(115 * edge + 70 * top)
        for x in range(output_width):
            shade_pixels[x, y] = (3, 17, 12, min(170, alpha))
    return Image.alpha_composite(card.convert("RGBA"), shade).convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public/course/peach-tree"),
    )
    args = parser.parse_args()

    source_path = args.source or Path("tmp/imagegen/peach-tree-naip-source.jpg")
    if not source_path.exists():
        download_naip(source_path)

    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    source = Image.open(source_path).convert("RGB")
    centerlines = fetch_centerlines()

    overview = add_vignette(color_grade(source.resize((1600, 1183))))
    overview.save(output / "course-aerial.webp", "WEBP", quality=84, method=6)

    for hole_number in range(1, 19):
        card = atlas_card(source, centerlines[hole_number])
        card.save(
            output / f"hole-{hole_number:02d}.webp",
            "WEBP",
            quality=84,
            method=6,
        )

    geometry = {
        "course": "Peach Tree Golf & Country Club",
        "imagery": {
            "source": "USDA NAIP via USGS The National Map",
            "acquired": "2022-07-09",
            "publicDomain": True,
            "url": NAIP_URL,
        },
        "centerlines": {
            "source": "OpenStreetMap contributors",
            "license": "ODbL",
            "url": "https://www.openstreetmap.org/way/1426341377",
            "holes": {
                str(number): centerlines[number] for number in range(1, 19)
            },
        },
    }
    (output / "sources.json").write_text(
        json.dumps(geometry, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Generated 18 hole cards and course overview in {output.resolve()}")


if __name__ == "__main__":
    main()
