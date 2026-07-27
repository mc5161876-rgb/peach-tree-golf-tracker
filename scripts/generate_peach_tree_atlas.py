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
import urllib.parse
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
CARD_SIZE = (900, 1200)

# How much taller the card is than the hole it shows.
#
# The old crop padded a fixed 310x360 source pixels regardless of hole length,
# which framed the average hole at 1.78x its own length and the short par 3s at
# up to 2.56x — enough that hole 7's card showed holes 5 and 8 as well. Scaling
# the frame to the hole instead keeps every hole filling its card the same way.
TARGET_FRAME_RATIO = 1.25

# Absolute floor on the breathing room at each end, whichever way the ratio
# works out. Twenty yards is about the width of a green: a shot that misses by
# a green's width is still on the card rather than cropped off it. On the
# shortest hole (3, at 162 yards) the 1.25 ratio already yields just over this,
# so the floor almost never binds — it exists so a very short hole cannot crop
# to nothing.
MIN_MARGIN_YARDS = 20.0


def naip_source_size() -> tuple[int, int]:
    """The raster dimensions NAIP_URL asks for, read from the URL itself.

    The card transform is expressed in source-raster pixels, so the geometry
    export needs these numbers even when no raster is on disk. Parsing the URL
    keeps them from drifting away from what the download actually requests.
    """
    for parameter in NAIP_URL.split("?", 1)[1].split("&"):
        key, _, value = parameter.partition("=")
        if key == "size":
            width, _, height = value.partition(",")
            return int(width), int(height)
    raise ValueError("NAIP_URL has no size parameter")

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

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

EARTH_RADIUS_METRES = 6_371_000
YARDS_PER_METRE = 1.0936132983377078

# How far a matched green's centroid may sit from the centerline's last point
# before the match is treated as wrong rather than merely imprecise. The
# centerline ends near the middle of the green by construction, so a good match
# lands within a couple of yards; anything approaching this means the pairing
# picked up a different green.
GREEN_MATCH_TOLERANCE_YARDS = 10.0


def request_bytes(url: str, data: bytes | None = None) -> bytes:
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def distance_yards(
    first: tuple[float, float], second: tuple[float, float]
) -> float:
    """Great-circle distance in yards. Mirrors `distanceYards` in the app."""
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


def source_metres_per_pixel(source_size: tuple[int, int]) -> tuple[float, float]:
    """Ground distance covered by one source-raster pixel, along each axis.

    The raster is stored in degrees, so a pixel is wider in latitude than in
    longitude at this latitude. Uses the same earth radius as `distance_yards`
    so a frame solved here cannot disagree with a yardage measured there.
    """
    min_lon, min_lat, max_lon, max_lat = COURSE_BBOX
    source_width, source_height = source_size
    mid_lat = math.radians((min_lat + max_lat) / 2)
    metres_per_degree = math.radians(1.0) * EARTH_RADIUS_METRES
    return (
        (max_lon - min_lon) / source_width * metres_per_degree * math.cos(mid_lat),
        (max_lat - min_lat) / source_height * metres_per_degree,
    )


def polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Mean of the ring's vertices.

    Not the area centroid: OpenStreetMap green rings are sampled densely and
    fairly evenly, so the vertex mean lands within a yard or two of the middle
    of the putting surface, which is all "middle of the green" needs to mean.
    """
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


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


def fetch_greens() -> list[dict]:
    """Every `golf=green` polygon inside the course bounding box.

    Unlike the hole centerlines these carry no `ref` tag, so they arrive
    unlabelled and have to be matched to holes geometrically. The course also
    has practice greens inside the same box, which is why this returns
    everything it finds and leaves the sorting to `match_greens_to_holes`.
    """
    min_lon, min_lat, max_lon, max_lat = COURSE_BBOX
    query = (
        "[out:json][timeout:90];"
        f'way["golf"="green"]({min_lat},{min_lon},{max_lat},{max_lon});'
        "out geom;"
    )
    payload = json.loads(
        request_bytes(OVERPASS_URL, data=urllib.parse.urlencode({"data": query}).encode())
    )

    greens = []
    for element in payload["elements"]:
        geometry = element.get("geometry")
        if not geometry:
            continue
        points = [(node["lat"], node["lon"]) for node in geometry]
        # Overpass closes rings by repeating the first node last; carrying the
        # duplicate would weight the centroid toward that vertex.
        if len(points) > 1 and points[0] == points[-1]:
            points = points[:-1]
        greens.append({"id": element["id"], "points": points})

    if not greens:
        raise ValueError("Overpass returned no golf=green ways for the course bbox")
    return greens


def match_greens_to_holes(
    centerlines: dict[int, list[tuple[float, float]]],
    greens: list[dict],
) -> dict[int, dict]:
    """Pair each hole with its green by nearest centroid to the hole's end.

    The centerline's last point already sits on the putting surface, so the
    nearest green centroid is unambiguous — every Peach Tree hole matches
    within about two yards. Practice greens simply never win a hole.

    Every failure mode raises. A silently wrong pairing would put front and
    back yardages on the wrong green, which is worse than no yardages at all.
    """
    matches: dict[int, dict] = {}
    for hole_number in range(1, 19):
        hole_end = centerlines[hole_number][-1]
        nearest = min(
            greens,
            key=lambda green: distance_yards(hole_end, polygon_centroid(green["points"])),
        )
        centroid = polygon_centroid(nearest["points"])
        offset = distance_yards(hole_end, centroid)
        if offset > GREEN_MATCH_TOLERANCE_YARDS:
            raise ValueError(
                f"hole {hole_number}: nearest green (way {nearest['id']}) sits "
                f"{offset:.1f} yards from the centerline end, over the "
                f"{GREEN_MATCH_TOLERANCE_YARDS:.0f} yard tolerance"
            )
        matches[hole_number] = {
            "wayId": nearest["id"],
            "offsetYards": offset,
            "points": nearest["points"],
        }

    assigned = [match["wayId"] for match in matches.values()]
    duplicates = sorted({way for way in assigned if assigned.count(way) > 1})
    if duplicates:
        raise ValueError(
            "greens matched to more than one hole: "
            + ", ".join(
                f"way {way} → holes "
                + ", ".join(
                    str(number)
                    for number, match in matches.items()
                    if match["wayId"] == way
                )
                for way in duplicates
            )
        )

    missing = [number for number in range(1, 19) if number not in matches]
    if missing:
        raise ValueError(f"holes with no matched green: {missing}")

    return matches


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


def card_transform(
    points_geo: list[tuple[float, float]],
    source_size: tuple[int, int],
    size: tuple[int, int] = CARD_SIZE,
) -> dict:
    """Work out how one hole's card is cut from the source raster.

    The card is the source rotated so the hole runs bottom-to-top, then scaled
    to fit. Everything here is a pure function of the centerline, the bounding
    box, and the two image sizes — no pixel data is involved — which is why the
    same values can be exported without regenerating any imagery.
    """
    source_width, source_height = source_size
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

    # Source pixels are not square on the ground: one pixel spans a different
    # number of metres east-west than north-south, because the raster is in
    # degrees. So how many metres a pixel covers depends on which way the hole
    # runs, and the frame has to be solved in metres rather than pixels or a
    # north-south hole would end up framed differently from an east-west one.
    metres_per_pixel_x, metres_per_pixel_y = source_metres_per_pixel(source_size)
    metres_along = math.hypot(unit_x * metres_per_pixel_x, unit_y * metres_per_pixel_y)
    metres_across = math.hypot(perp_x * metres_per_pixel_x, perp_y * metres_per_pixel_y)

    hole_metres = sum(
        distance_yards(points_geo[index - 1], points_geo[index])
        for index in range(1, len(points_geo))
    ) / YARDS_PER_METRE

    # The frame we want: a fixed multiple of how long the hole actually plays.
    target = TARGET_FRAME_RATIO * hole_metres / (output_height * metres_along)

    # The frame we need: the hole itself, plus a margin at every edge. The
    # projected span is never longer than the walked path, so on a straight
    # hole this sits below the target and does nothing.
    margin = MIN_MARGIN_YARDS / YARDS_PER_METRE
    fits_along = ((max(along) - min(along)) * metres_along + 2 * margin) / (
        output_height * metres_along
    )
    fits_across = ((max(across) - min(across)) * metres_across + 2 * margin) / (
        output_width * metres_across
    )

    scale = max(target, fits_along, fits_across)

    # The card is a rotated rectangle cut from the raster, and nothing above
    # checks that the rectangle stays on it. Once the frame tightened to the
    # hole (MAR-31), a hole near the imagery's edge could poke past it — hole
    # 2's card reached ~270px beyond the southern edge and the overhang
    # rendered black. Fit first: if the card cannot fit on the raster at this
    # scale in any position, tighten the frame to the largest scale that can.
    # Then slide the centre the shortest distance that puts every corner
    # inside.
    half_extent_x = (output_width / 2) * abs(perp_x) + (output_height / 2) * abs(unit_x)
    half_extent_y = (output_width / 2) * abs(perp_y) + (output_height / 2) * abs(unit_y)
    largest_fitting = min(
        source_width / (2 * half_extent_x), source_height / (2 * half_extent_y)
    )
    if scale > largest_fitting:
        if max(fits_along, fits_across) > largest_fitting:
            raise ValueError(
                "hole card cannot fit inside the raster even at the minimum "
                "frame that still contains the hole — the raster is too small "
                "for this hole's position"
            )
        scale = largest_fitting

    center_x = min(
        max(center_x, half_extent_x * scale), source_width - half_extent_x * scale
    )
    center_y = min(
        max(center_y, half_extent_y * scale), source_height - half_extent_y * scale
    )

    # Belt and braces: a future edit to the maths above must fail loudly here
    # rather than quietly ship a black-banded card again.
    for signs in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        corner_x = center_x + signs[0] * half_extent_x * scale
        corner_y = center_y + signs[1] * half_extent_y * scale
        if not (-1e-6 <= corner_x <= source_width + 1e-6) or not (
            -1e-6 <= corner_y <= source_height + 1e-6
        ):
            raise AssertionError(
                f"card corner ({corner_x:.1f}, {corner_y:.1f}) left the "
                f"{source_width}x{source_height} raster after clamping"
            )

    return {
        "center": {"x": center_x, "y": center_y},
        "unit": {"x": unit_x, "y": unit_y},
        "perp": {"x": perp_x, "y": perp_y},
        "scale": scale,
        # How much taller the frame is than the hole, after any fit reduction.
        # Matches TARGET_FRAME_RATIO except on a hole squeezed by the raster's
        # edge, where this records what was actually achievable.
        "frameRatio": round(
            scale * output_height * metres_along / hole_metres, 4
        ),
    }


def transform_to_card(
    point: tuple[float, float], transform: dict, size: tuple[int, int] = CARD_SIZE
) -> tuple[float, float]:
    """Source-raster pixel to card pixel."""
    output_width, output_height = size
    offset_x = point[0] - transform["center"]["x"]
    offset_y = point[1] - transform["center"]["y"]
    unit, perp, scale = transform["unit"], transform["perp"], transform["scale"]
    x = output_width / 2 + (offset_x * perp["x"] + offset_y * perp["y"]) / scale
    y = output_height / 2 - (offset_x * unit["x"] + offset_y * unit["y"]) / scale
    return x, y


def atlas_card(
    source: Image.Image, points_geo: list[tuple[float, float]], size=CARD_SIZE
) -> Image.Image:
    source_width, source_height = source.size
    points = [
        geo_to_pixel(lat, lon, source_width, source_height)
        for lat, lon in points_geo
    ]
    transform = card_transform(points_geo, source.size, size)
    center_x = transform["center"]["x"]
    center_y = transform["center"]["y"]
    unit_x, unit_y = transform["unit"]["x"], transform["unit"]["y"]
    perp_x, perp_y = transform["perp"]["x"], transform["perp"]["y"]
    scale = transform["scale"]
    output_width, output_height = size

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

    route = [transform_to_card(point, transform, size) for point in points]
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


def build_card_geometry(
    centerlines: dict[int, list[tuple[float, float]]],
    source_size: tuple[int, int],
) -> dict:
    """The per-hole transforms, in the shape the app consumes.

    Values shared by every hole sit at the top; each hole carries only what is
    unique to it. Card pixels are converted to real coordinates by inverting
    these, so anything measured on a hole card depends on them being right.
    """
    min_lon, min_lat, max_lon, max_lat = COURSE_BBOX
    source_width, source_height = source_size
    card_width, card_height = CARD_SIZE
    return {
        "bbox": {
            "minLon": min_lon,
            "minLat": min_lat,
            "maxLon": max_lon,
            "maxLat": max_lat,
        },
        "source": {"width": source_width, "height": source_height},
        "card": {"width": card_width, "height": card_height},
        "holes": {
            str(number): card_transform(centerlines[number], source_size)
            for number in range(1, 19)
        },
    }


def greens_payload(greens_by_hole: dict[int, dict]) -> dict:
    """The matched greens, in the shape the app consumes.

    `offsetYards` is kept per hole because it is the evidence the match is
    right: it says how far the green's middle sits from where the centerline
    said the green was. A number that grows on a future regeneration means the
    course or the map changed.
    """
    return {
        "source": "OpenStreetMap contributors",
        "license": "ODbL",
        "url": "https://www.openstreetmap.org/",
        "matching": (
            "Each hole is paired with the golf=green way whose centroid is "
            "nearest the last point of its centerline. Practice greens inside "
            "the course bounding box are left unassigned."
        ),
        "holes": {
            str(number): {
                "wayId": greens_by_hole[number]["wayId"],
                "offsetYards": round(greens_by_hole[number]["offsetYards"], 3),
                "points": [
                    [point[0], point[1]] for point in greens_by_hole[number]["points"]
                ],
            }
            for number in range(1, 19)
        },
    }


def sources_payload(
    centerlines: dict[int, list[tuple[float, float]]],
    source_size: tuple[int, int],
    greens_by_hole: dict[int, dict],
) -> dict:
    return {
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
        "greens": greens_payload(greens_by_hole),
        "cardGeometry": build_card_geometry(centerlines, source_size),
    }


def write_sources(output: Path, payload: dict) -> None:
    (output / "sources.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public/course/peach-tree"),
    )
    parser.add_argument(
        "--geometry-only",
        action="store_true",
        help=(
            "Recompute cardGeometry from the centerlines already in "
            "sources.json and rewrite that file. Touches no imagery, downloads "
            "nothing, and leaves the centerlines and greens exactly as they are."
        ),
    )
    parser.add_argument(
        "--cards-only",
        action="store_true",
        help=(
            "Recut all 18 hole cards and the overview from the centerlines "
            "already in sources.json, and rewrite cardGeometry to match. "
            "Needs the NAIP raster and will download it if absent, but "
            "contacts OpenStreetMap for nothing: centerlines and greens are "
            "read from the file and the greens block is left untouched. This "
            "is the path for a change to how cards are framed."
        ),
    )
    parser.add_argument(
        "--greens-only",
        action="store_true",
        help=(
            "Fetch golf=green polygons from OpenStreetMap, match them to the "
            "centerlines already in sources.json, and rewrite that file. "
            "Touches no imagery and leaves centerlines and cardGeometry as "
            "they are — the NAIP raster is 4000x2957 and re-downloading it to "
            "add map data would be pure waste."
        ),
    )
    args = parser.parse_args()

    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    exclusive = [args.geometry_only, args.greens_only, args.cards_only]
    if sum(bool(flag) for flag in exclusive) > 1:
        parser.error(
            "--geometry-only, --greens-only, and --cards-only do different "
            "things; pick one"
        )

    def stored_centerlines() -> tuple[dict, dict[int, list[tuple[float, float]]]]:
        existing = json.loads((output / "sources.json").read_text(encoding="utf-8"))
        return existing, {
            number: [
                (point[0], point[1])
                for point in existing["centerlines"]["holes"][str(number)]
            ]
            for number in range(1, 19)
        }

    if args.cards_only:
        existing, centerlines = stored_centerlines()
        source_path = args.source or Path("tmp/imagegen/peach-tree-naip-source.jpg")
        if not source_path.exists():
            download_naip(source_path)
        source = Image.open(source_path).convert("RGB")

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

        existing["cardGeometry"] = build_card_geometry(centerlines, source.size)
        write_sources(output, existing)
        print(
            f"Recut 18 hole cards at {TARGET_FRAME_RATIO:.2f}x framing in "
            f"{output.resolve()}; greens and centerlines untouched"
        )
        return

    if args.greens_only:
        existing = json.loads((output / "sources.json").read_text(encoding="utf-8"))
        centerlines = {
            number: [
                (point[0], point[1])
                for point in existing["centerlines"]["holes"][str(number)]
            ]
            for number in range(1, 19)
        }
        greens_by_hole = match_greens_to_holes(centerlines, fetch_greens())
        existing["greens"] = greens_payload(greens_by_hole)
        write_sources(output, existing)
        worst = max(match["offsetYards"] for match in greens_by_hole.values())
        print(
            f"Matched 18 greens in {(output / 'sources.json').resolve()} "
            f"(worst centroid offset {worst:.1f} yards)"
        )
        return

    if args.geometry_only:
        existing = json.loads((output / "sources.json").read_text(encoding="utf-8"))
        centerlines = {
            number: [
                (point[0], point[1])
                for point in existing["centerlines"]["holes"][str(number)]
            ]
            for number in range(1, 19)
        }
        existing["cardGeometry"] = build_card_geometry(
            centerlines, naip_source_size()
        )
        write_sources(output, existing)
        print(f"Wrote cardGeometry for 18 holes to {(output / 'sources.json').resolve()}")
        return

    source_path = args.source or Path("tmp/imagegen/peach-tree-naip-source.jpg")
    if not source_path.exists():
        download_naip(source_path)

    source = Image.open(source_path).convert("RGB")
    centerlines = fetch_centerlines()
    greens_by_hole = match_greens_to_holes(centerlines, fetch_greens())

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

    write_sources(output, sources_payload(centerlines, source.size, greens_by_hole))
    print(f"Generated 18 hole cards and course overview in {output.resolve()}")


if __name__ == "__main__":
    main()
