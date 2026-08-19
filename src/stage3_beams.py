"""Stage 3 -- connect columns with beams so every slab region is bounded.

Two rules, each its own function:

1. `perimeter_beams` -- walk the boundary ring and connect every column that
   sits on it, in order. This guarantees the whole perimeter is a single
   closed loop of beams with no gap, regardless of how many span-fill or
   junction columns ended up on any one edge.
2. `interior_wall_beams` -- for every pair of columns that share an X or a Y
   coordinate (columns "line up into rows and columns", per the assignment),
   connect the two if they are *adjacent* along that line (no closer column
   in between) and a wall actually runs between them. This is what turns a
   T-junction column into a beam run through the middle of the building,
   and is also what places a beam on each side of an opening that has walls
   on at least two aligned edges (e.g. a stair void flanked by partition
   walls) -- see the module-level note on openings below.

Both rules only ever propose straight lines between two *existing* columns
(never new points), so every beam in the output traces back to a concrete
pair of Stage 2 columns.

Known limitation, stated plainly rather than papered over: a void that is
open on one side (no wall drawn there at all, e.g. a stairwell open to a
passage) gets beams only on the sides that do have wall material backing
them. A fully engineered opening would get a beam on all four sides
regardless of whether a wall happens to be drawn there; closing that gap
generically would need void detection this pipeline does not attempt. It is
listed in `known_problems` in the Stage 4 output rather than silently
assumed away.
"""

from __future__ import annotations

import math

from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

from geometry_types import BoundaryResult, Beam, Column

_BOUNDARY_SNAP_TOLERANCE_FT = 1.0
_AXIS_ALIGNMENT_TOLERANCE_FT = 0.75
_WALL_COVERAGE_CORRIDOR_FT = 0.3
_MIN_WALL_COVERAGE_RATIO = 0.8


def order_boundary_columns(columns: list[Column], boundary: BoundaryResult) -> list[Column]:
    """Return the columns that sit on the boundary ring, in ring-walk order.

    "On the ring" means within `_BOUNDARY_SNAP_TOLERANCE_FT` of the boundary
    polygon's edge -- generous enough to catch a wall-junction column stage 1's
    closing radius nudged a few inches off the exact simplified ring.
    """
    ring = boundary.as_polygon().exterior
    points = {column.id: Point(column.x_ft, column.y_ft) for column in columns}
    on_ring = [c for c in columns if ring.distance(points[c.id]) <= _BOUNDARY_SNAP_TOLERANCE_FT]
    on_ring.sort(key=lambda c: ring.project(points[c.id]))
    return on_ring


def perimeter_beams(columns: list[Column], boundary: BoundaryResult) -> list[tuple[Column, Column]]:
    """Connect consecutive boundary columns all the way around the ring."""
    ordered = order_boundary_columns(columns, boundary)
    if len(ordered) < 2:
        return []
    return [(ordered[i], ordered[(i + 1) % len(ordered)]) for i in range(len(ordered))]


def _wall_coverage_ratio(a: Column, b: Column, wall_union_ft: BaseGeometry) -> float:
    """Fraction of the straight line from a to b that runs through wall material.

    Measured as length-along-the-line, not area: a corridor-area comparison
    would always read low here because interior walls (4"-6" thick) are
    narrower than any reasonable search corridor, so no wall could ever
    "fill" it. Buffering the wall union by a small epsilon before
    intersecting with the bare line sidesteps that and gives a ratio that
    reaches 1.0 for a fully wall-backed span regardless of wall thickness.
    """
    segment = LineString([(a.x_ft, a.y_ft), (b.x_ft, b.y_ft)])
    if segment.length == 0:
        return 0.0
    wall_corridor = wall_union_ft.buffer(_WALL_COVERAGE_CORRIDOR_FT)
    covered = segment.intersection(wall_corridor)
    return covered.length / segment.length


def interior_wall_beams(columns: list[Column], wall_union_ft: BaseGeometry) -> list[tuple[Column, Column]]:
    """Connect axis-aligned, wall-backed, mutually-nearest column pairs.

    Grouping columns that share an X (or Y) coordinate and connecting only
    *adjacent* ones (sorted along that shared line) prevents a beam from
    skipping over an intermediate column -- exactly the "columns line up
    into rows and columns" structure the assignment describes.
    """
    beams: set[tuple[int, int]] = set()
    pairs: list[tuple[Column, Column]] = []

    for axis in ("x", "y"):
        groups: dict[float, list[Column]] = {}
        for column in columns:
            key_value = column.x_ft if axis == "x" else column.y_ft
            matched_key = next(
                (k for k in groups if abs(k - key_value) <= _AXIS_ALIGNMENT_TOLERANCE_FT), None
            )
            groups.setdefault(matched_key if matched_key is not None else key_value, []).append(column)

        for group in groups.values():
            if len(group) < 2:
                continue
            ordered = sorted(group, key=lambda c: c.y_ft if axis == "x" else c.x_ft)
            for i in range(len(ordered) - 1):
                a, b = ordered[i], ordered[i + 1]
                pair_key = tuple(sorted((a.id, b.id)))
                if pair_key in beams:
                    continue
                if _wall_coverage_ratio(a, b, wall_union_ft) >= _MIN_WALL_COVERAGE_RATIO:
                    beams.add(pair_key)
                    pairs.append((a, b))
    return pairs


def _dedupe_and_build(pairs: list[tuple[Column, Column]]) -> list[Beam]:
    seen: set[tuple[int, int]] = set()
    result: list[Beam] = []
    for a, b in pairs:
        key = tuple(sorted((a.id, b.id)))
        if key in seen or a.id == b.id:
            continue
        seen.add(key)
        length_ft = round(math.dist((a.x_ft, a.y_ft), (b.x_ft, b.y_ft)), 2)
        if length_ft == 0:
            continue
        result.append(Beam(id=len(result), from_column=a.id, to_column=b.id, length_ft=length_ft))
    return result


def connect_isolated_columns(columns: list[Column], beams: list[Beam]) -> tuple[list[Beam], list[int]]:
    """Give every column at least one beam.

    A column can end up with no beam at all if it sits between two doorways
    on the same wall run (both adjacent wall-coverage checks fail) and isn't
    on the boundary ring either. Rather than ship a structurally nonsensical
    free-floating column, connect it to its nearest other column by straight
    -line distance -- not backed by a confirmed wall, so every such fallback
    beam is reported back (second return value) for `known_problems`.
    """
    connected_ids = {c for beam in beams for c in (beam.from_column, beam.to_column)}
    isolated = [c for c in columns if c.id not in connected_ids]
    if not isolated:
        return beams, []

    new_beams = list(beams)
    forced_ids: list[int] = []
    next_id = max((b.id for b in beams), default=-1) + 1
    for column in isolated:
        nearest = min(
            (c for c in columns if c.id != column.id),
            key=lambda c: math.dist((column.x_ft, column.y_ft), (c.x_ft, c.y_ft)),
        )
        length_ft = round(math.dist((column.x_ft, column.y_ft), (nearest.x_ft, nearest.y_ft)), 2)
        new_beams.append(Beam(id=next_id, from_column=column.id, to_column=nearest.id, length_ft=length_ft))
        forced_ids.append(column.id)
        next_id += 1
    return new_beams, forced_ids


def compute_beams(
    columns: list[Column], boundary: BoundaryResult, wall_union_ft: BaseGeometry
) -> tuple[list[Beam], list[int]]:
    """Stage 3 entry point: columns + boundary + wall geometry in, beam list out.

    Returns `(beams, isolated_column_ids)` -- the second element lists any
    column that needed `connect_isolated_columns`'s nearest-neighbour
    fallback, so callers can surface it as a known limitation instead of
    silently presenting a guessed beam as equivalent to a wall-backed one.
    """
    all_pairs = perimeter_beams(columns, boundary) + interior_wall_beams(columns, wall_union_ft)
    beams = _dedupe_and_build(all_pairs)
    return connect_isolated_columns(columns, beams)
