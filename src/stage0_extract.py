"""Stage 0 -- pull raw geometry, text and a feet-per-point scale out of a PDF.

Everything downstream (boundary, columns, beams) works in feet. This module
is the only place that touches PyMuPDF or reasons about PDF points, fill
colours, or the specific text layout of a Brick & Bolt drawing sheet.

Key discovery this module encodes: in these drawings walls are drawn as
*filled* black polygons (PDF "f" paint operations, kind "re"/"qu"/"l"
sub-paths), while the plot boundary, dimension chains, grid lines, hatching
and text underlines are all *stroked* ("s") paths. Filtering on fill colour
alone -- before we know anything about position -- already separates "wall
material" from everything else on the sheet. That separation is what lets
stage 1 avoid the "outermost shape on the page" and "assume a rectangle"
traps the assignment calls out.
"""

from __future__ import annotations

import math
import re
import statistics
import warnings
from dataclasses import dataclass

import pymupdf
from shapely.affinity import scale as shapely_scale
from shapely.geometry import LineString, Point as ShapelyPoint, Polygon
from shapely.ops import unary_union

from geometry_types import PageData, RoomLabel, ScaleResult, WallShape

# A wall-fill polygon is "dark" if its RGB channels sum below this. Distinct
# from room-tint fills (light pastels) and pure white hatch backgrounds.
_DARK_FILL_SUM_THRESHOLD = 0.6

# Room-size labels look like  12' - 0" X 11' - 0"
_ROOM_SIZE_RE = re.compile(r"(\d+)'\s*-\s*(\d+)\"\s*[Xx]\s*(\d+)'\s*-\s*(\d+)\"")

# Door/window schedule rows: MARK  W'-I"  H'-I"  COUNT  AREA SF
_SCHEDULE_ROW_RE = re.compile(
    r"\b([A-Z]{1,4}\d?)\s+(\d+)'\s*-\s*(\d+)\"\s+(\d+)'\s*-\s*(\d+)\"\s+(\d+)\s+(\d+)\s*SF"
)

# "EXTERNAL WALL-6" BLOCK WORK" / "EXTERNAL WALL- 6" BLOCK WORK" style notes.
_WALL_THICKNESS_RE = re.compile(r"EXTERNAL\s*WALL\D{0,8}?(\d+)\s*\"", re.IGNORECASE)

# "FIRST FLOOR LEVEL ... BUILT(-| )?UP AREA ... 649 SF"
_STATED_AREA_RE = re.compile(
    r"FIRST FLOOR LEVEL\s*.*?BUILT\s*[- ]?UP\s+AREA\D*([\d,]+(?:\.\d+)?)\s*SF",
    re.IGNORECASE | re.DOTALL,
)
_BALCONY_AREA_RE = re.compile(r"BALCONY\D*([\d,]+(?:\.\d+)?)\s*SF", re.IGNORECASE)

_DEFAULT_EXTERNAL_WALL_INCHES = 6.0
_MIN_WALL_ASPECT_RATIO = 3.0  # long-side / short-side, to call a fill "wall-like"
_ROOM_LABEL_SCALE_CONSISTENCY_TOL = 0.15  # max relative gap between sx and sy


@dataclass
class _TextLine:
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1


def load_first_page(pdf_path: str) -> pymupdf.Page:
    """Open a single-page plan PDF and return its (only) page."""
    document = pymupdf.open(pdf_path)
    return document[0]


def extract_wall_shapes_pt(page: pymupdf.Page) -> list[Polygon]:
    """Return every filled, near-black polygon on the page, in PDF points.

    Each returned polygon is one "ring" from one PDF fill path -- typically
    a whole straight wall run (which may already have door/window notches
    baked into its outline). A single drawing command can contain several
    disjoint rings (e.g. a wall split by a full window opening); each ring
    becomes its own polygon here, so a wall broken by an opening never gets
    silently welded back together at this stage.
    """
    polygons: list[Polygon] = []
    for drawing in page.get_drawings():
        if drawing["type"] != "f":
            continue
        fill = drawing.get("fill")
        if fill is None or sum(fill) >= _DARK_FILL_SUM_THRESHOLD:
            continue
        for ring in _rings_from_drawing_items(drawing["items"]):
            if len(ring) < 3:
                continue
            polygon = Polygon(ring)
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            if polygon.area > 0:
                polygons.append(polygon)
    return polygons


def _rings_from_drawing_items(items: list[tuple]) -> list[list[tuple[float, float]]]:
    """Turn a PyMuPDF drawing 'items' list into closed point rings.

    PyMuPDF represents one fill path as a sequence of segments of kind
    'l' (line, needs joining into a ring), 're' (axis-aligned rectangle,
    already a ring) or 'qu' (quad, already a ring). A new 'l' segment that
    doesn't continue from the previous point starts a new ring -- this is
    how one drawing command can hold several disjoint wall pieces.
    """
    rings: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    def flush() -> None:
        if current:
            rings.append(list(current))
            current.clear()

    for item in items:
        kind = item[0]
        if kind == "l":
            start, end = item[1], item[2]
            if not current:
                current.extend([(start.x, start.y), (end.x, end.y)])
            elif abs(current[-1][0] - start.x) > 1e-4 or abs(current[-1][1] - start.y) > 1e-4:
                flush()
                current.extend([(start.x, start.y), (end.x, end.y)])
            else:
                current.append((end.x, end.y))
        elif kind == "re":
            flush()
            rect = item[1]
            rings.append(
                [(rect.x0, rect.y0), (rect.x1, rect.y0), (rect.x1, rect.y1), (rect.x0, rect.y1)]
            )
        elif kind == "qu":
            flush()
            quad = item[1]
            rings.append(
                [
                    (quad.ul.x, quad.ul.y),
                    (quad.ur.x, quad.ur.y),
                    (quad.lr.x, quad.lr.y),
                    (quad.ll.x, quad.ll.y),
                ]
            )
        # Curves ('c') do not occur in wall fills in the sampled drawings;
        # any such item is intentionally skipped rather than approximated.
    flush()
    return rings


def extract_text_lines(page: pymupdf.Page) -> list[_TextLine]:
    """Merge per-span text into per-line text.

    PyMuPDF sometimes splits a single label (e.g. "17' - 11\" X 10' - 5\"")
    across several spans within one line because of a font change at the
    apostrophe glyph. Regexing span-by-span misses these; merging first
    fixes it once for every downstream text parser.
    """
    lines: list[_TextLine] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            merged_text = "".join(span["text"] for span in spans)
            x0 = min(span["bbox"][0] for span in spans)
            y0 = min(span["bbox"][1] for span in spans)
            x1 = max(span["bbox"][2] for span in spans)
            y1 = max(span["bbox"][3] for span in spans)
            lines.append(_TextLine(merged_text, (x0, y0, x1, y1)))
    return lines


def parse_room_labels(lines: list[_TextLine]) -> list[RoomLabel]:
    """Find every 'W\\' - I" X W\\' - I"' room clear-dimension label."""
    labels: list[RoomLabel] = []
    for line in lines:
        match = _ROOM_SIZE_RE.search(line.text)
        if not match:
            continue
        width_ft = int(match.group(1)) + int(match.group(2)) / 12.0
        depth_ft = int(match.group(3)) + int(match.group(4)) / 12.0
        x0, y0, x1, y1 = line.bbox
        center = ((x0 + x1) / 2, (y0 + y1) / 2)
        labels.append(RoomLabel(match.group(0), width_ft, depth_ft, center))
    return labels


def parse_wall_thickness_inches(full_text: str) -> float:
    """Return the external wall thickness in inches, defaulting to 6"."""
    match = _WALL_THICKNESS_RE.search(full_text)
    if match:
        return float(match.group(1))
    return _DEFAULT_EXTERNAL_WALL_INCHES


def parse_opening_widths_ft(full_text: str) -> list[float]:
    """Return door/window schedule widths in feet, if a schedule is present."""
    widths = []
    for row in _SCHEDULE_ROW_RE.finditer(full_text):
        width_ft = int(row.group(2)) + int(row.group(3)) / 12.0
        widths.append(width_ft)
    return widths


def parse_stated_area_sqft(full_text: str) -> tuple[float | None, float | None]:
    """Return (first-floor built-up area, balcony area) in square feet, if stated."""
    built_up = None
    match = _STATED_AREA_RE.search(full_text)
    if match:
        built_up = float(match.group(1).replace(",", ""))
    balcony_match = _BALCONY_AREA_RE.search(full_text)
    balcony = float(balcony_match.group(1).replace(",", "")) if balcony_match else None
    return built_up, balcony


def _nearest_wall_entry_point(
    wall_union_pt, origin: tuple[float, float], direction: tuple[float, float], ray_length: float
) -> ShapelyPoint | None:
    """Cast a ray from `origin` and return the closest point where it enters wall material."""
    dx, dy = direction
    ray = LineString([origin, (origin[0] + dx * ray_length, origin[1] + dy * ray_length)])
    intersection = wall_union_pt.intersection(ray)
    if intersection.is_empty:
        return None
    coords: list[tuple[float, float]] = []
    if intersection.geom_type == "LineString":
        coords = list(intersection.coords)
    elif hasattr(intersection, "geoms"):
        for geom in intersection.geoms:
            if hasattr(geom, "coords"):
                coords.extend(list(geom.coords))
    if not coords:
        return None
    origin_point = ShapelyPoint(origin)
    return ShapelyPoint(min(coords, key=lambda c: origin_point.distance(ShapelyPoint(c))))


def derive_scale_from_room_labels(
    wall_union_pt, room_labels: list[RoomLabel]
) -> ScaleResult | None:
    """Estimate points-per-foot by matching a room's stated clear size to its
    measured clear span between walls (ray-cast from the label to the
    nearest wall material in all four directions).

    A sample is only trusted when the independently measured X and Y scales
    agree within `_ROOM_LABEL_SCALE_CONSISTENCY_TOL` -- this automatically
    rejects rooms that are open on one side (no wall to ray-cast against),
    which would otherwise silently give a wildly wrong scale in that axis.
    """
    ray_length = 5000.0
    consistent_samples: list[float] = []
    for label in room_labels:
        cx, cy = label.center_pt
        left = _nearest_wall_entry_point(wall_union_pt, (cx, cy), (-1, 0), ray_length)
        right = _nearest_wall_entry_point(wall_union_pt, (cx, cy), (1, 0), ray_length)
        up = _nearest_wall_entry_point(wall_union_pt, (cx, cy), (0, -1), ray_length)
        down = _nearest_wall_entry_point(wall_union_pt, (cx, cy), (0, 1), ray_length)
        if None in (left, right, up, down):
            continue
        width_pt = right.x - left.x
        depth_pt = down.y - up.y
        if width_pt <= 0 or depth_pt <= 0:
            continue
        scale_x = width_pt / label.width_ft
        scale_y = depth_pt / label.depth_ft
        if abs(scale_x - scale_y) / max(scale_x, scale_y) > _ROOM_LABEL_SCALE_CONSISTENCY_TOL:
            continue
        consistent_samples.extend([scale_x, scale_y])

    if len(consistent_samples) < 2:
        return None
    return ScaleResult(
        points_per_foot=statistics.median(consistent_samples),
        source="room_label_geometry",
        sample_count=len(consistent_samples) // 2,
        detail="median of consistent width/depth ray-casts against room-size labels",
    )


def derive_scale_from_wall_thickness(
    wall_polygons_pt: list[Polygon], external_wall_inches: float
) -> ScaleResult | None:
    """Estimate points-per-foot from the drawn thickness of exterior wall fills.

    Falls back for plans where every room touches an opening or an
    unenclosed void (e.g. CRN642050's central skylight), which starves the
    room-label method of consistent samples. Uses the *modal* measured
    thickness across every elongated wall-fill polygon, so a handful of
    unrelated dark glyphs elsewhere on the sheet (legend ticks, bullets)
    can't skew the estimate -- true wall segments vastly outnumber them.
    """
    thickness_samples: list[float] = []
    for polygon in wall_polygons_pt:
        coords = _minimum_rotated_rectangle_coords(polygon)
        if coords is None:
            continue
        side_lengths = sorted(
            ShapelyPoint(coords[i]).distance(ShapelyPoint(coords[i + 1]))
            for i in range(len(coords) - 1)
        )
        minor, major = side_lengths[0], side_lengths[-1]
        if minor <= 0 or major / minor < _MIN_WALL_ASPECT_RATIO:
            continue
        thickness_samples.append(round(minor, 1))

    if not thickness_samples:
        return None
    modal_thickness_pt = statistics.mode(thickness_samples)
    external_wall_ft = external_wall_inches / 12.0
    return ScaleResult(
        points_per_foot=modal_thickness_pt / external_wall_ft,
        source="wall_thickness_note",
        sample_count=thickness_samples.count(modal_thickness_pt),
        detail=(
            f"modal drawn wall thickness ({modal_thickness_pt}pt) vs "
            f"{external_wall_inches:g}\" external wall note"
        ),
    )


def derive_scale(
    wall_union_pt,
    wall_polygons_pt: list[Polygon],
    room_labels: list[RoomLabel],
    external_wall_inches: float,
) -> ScaleResult:
    """Pick the best available scale estimate.

    Room-label ray-casting is preferred (it ties directly to a printed
    dimension the way the assignment asks for); wall-thickness is the
    fallback for plans where too few rooms are fully enclosed to trust that
    method. Raises if neither source produces an estimate -- silently
    guessing a scale is worse than failing loudly.
    """
    from_labels = derive_scale_from_room_labels(wall_union_pt, room_labels)
    from_thickness = derive_scale_from_wall_thickness(wall_polygons_pt, external_wall_inches)

    if from_labels is not None and from_labels.sample_count >= 2:
        return from_labels
    if from_thickness is not None:
        return from_thickness
    if from_labels is not None:
        return from_labels
    raise ValueError("Could not derive a scale from either room labels or wall thickness")


def extract_page_data(pdf_path: str, crn: str) -> PageData:
    """Stage 0 entry point: PDF path in, fully-parsed PageData (in feet) out."""
    page = load_first_page(pdf_path)
    full_text = page.get_text()

    wall_polygons_pt = extract_wall_shapes_pt(page)
    wall_union_pt = unary_union(wall_polygons_pt)

    text_lines = extract_text_lines(page)
    room_labels = parse_room_labels(text_lines)

    external_wall_inches = parse_wall_thickness_inches(full_text)
    scale = derive_scale(wall_union_pt, wall_polygons_pt, room_labels, external_wall_inches)
    points_per_foot = scale.points_per_foot

    def to_feet(geom):
        return shapely_scale(geom, xfact=1 / points_per_foot, yfact=1 / points_per_foot, origin=(0, 0))

    wall_shapes = [
        WallShape(
            polygon_ft=to_feet(polygon),
            thickness_ft=_estimate_thickness_ft(polygon, points_per_foot),
        )
        for polygon in wall_polygons_pt
    ]
    wall_union_ft = to_feet(wall_union_pt)

    stated_area, balcony_area = parse_stated_area_sqft(full_text)
    if balcony_area:
        stated_area_total = (stated_area or 0.0) + balcony_area
    else:
        stated_area_total = stated_area

    page_rect = page.rect
    return PageData(
        crn=crn,
        source_pdf=pdf_path,
        page_width_ft=page_rect.width / points_per_foot,
        page_height_ft=page_rect.height / points_per_foot,
        scale=scale,
        wall_shapes=wall_shapes,
        wall_union_ft=wall_union_ft,
        room_labels=room_labels,
        opening_widths_ft=parse_opening_widths_ft(full_text),
        stated_area_sqft=stated_area_total,
        raw_text=full_text,
    )


def _minimum_rotated_rectangle_coords(polygon: Polygon) -> list[tuple[float, float]] | None:
    """Safe wrapper around shapely's minimum_rotated_rectangle.

    GEOS can produce a NaN-coordinate result (with a RuntimeWarning) for
    near-degenerate slivers even when `polygon.area` reads as positive.
    Detecting NaN after the fact is simpler and more reliable than trying
    to pre-filter every pathological input shape.
    """
    if polygon.area <= 1e-6:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        min_rect = polygon.minimum_rotated_rectangle
    if min_rect.geom_type != "Polygon":
        return None
    coords = list(min_rect.exterior.coords)
    if len(coords) < 4 or any(math.isnan(c[0]) or math.isnan(c[1]) for c in coords):
        return None
    return coords


def _estimate_thickness_ft(polygon: Polygon, points_per_foot: float) -> float:
    coords = _minimum_rotated_rectangle_coords(polygon)
    if coords is None:
        return 0.0
    side_lengths = sorted(
        ShapelyPoint(coords[i]).distance(ShapelyPoint(coords[i + 1])) for i in range(len(coords) - 1)
    )
    return side_lengths[0] / points_per_foot
