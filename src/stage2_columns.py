"""Stage 2 -- propose a column everywhere the assignment's starting rules say one is needed.

Rules encoded here, each as its own function so the debrief question "why is
there a column at (x, y)" always has a one-function answer:

1. Every corner of the boundary polygon wants a column (`boundary_corner_columns`).
2. A junction where one wall meets another wants a column (`wall_junction_columns`)
   -- this covers both internal-meets-external and internal-meets-internal
   T/L/+ junctions; the assignment names the external case but a partition
   meeting another partition is structurally the same kind of point load.
3. If two neighbouring columns end up more than `max_span_ft` apart with
   nothing between them, add evenly spaced columns so no span exceeds that
   limit (`span_fill_columns`) -- applied along the boundary perimeter,
   which is where the assignment's example shows it mattering most.

Columns produced by different rules often land within an inch or two of
each other (a wall junction sitting exactly on a boundary corner, say);
`merge_nearby_columns` collapses those into one point rather than reporting
two columns for one physical corner.
"""

from __future__ import annotations

import math

from shapely.geometry import Point, Polygon

from geometry_types import BoundaryResult, Column, ColumnSource, PageData, WallShape

_CORNER_SIMPLIFY_TOLERANCE_FT = 1.5  # collapses buffering-rounded arcs to their real corners
_JUNCTION_TOUCH_TOLERANCE_FT = 0.15  # how close two wall polygons must be to count as touching
_MERGE_TOLERANCE_FT = 2.0  # columns closer than this are treated as the same physical point
_MAX_SPAN_FT = 15.0


def boundary_corner_columns(boundary: BoundaryResult) -> list[tuple[float, float]]:
    """One column per real corner of the boundary polygon.

    The boundary polygon stored in `BoundaryResult` is only lightly
    simplified (kept detailed for accurate area/drawing). Corners of interest
    here are the *dominant* direction changes -- the large closing radius in
    stage 1 turns some real corners into gentle multi-point arcs, which would
    otherwise each contribute a spurious column. Re-simplifying with a
    coarser tolerance collapses each arc back to the single corner it stands in for.
    """
    polygon = Polygon(boundary.polygon_ft).simplify(_CORNER_SIMPLIFY_TOLERANCE_FT, preserve_topology=True)
    coords = list(polygon.exterior.coords)
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]
    return coords


def wall_junction_columns(wall_shapes: list[WallShape]) -> list[tuple[float, float]]:
    """One column at every point where two distinct wall polygons touch or overlap.

    Covers both external-meets-internal and internal-meets-internal
    junctions: any two wall pieces sharing a point are treated the same way,
    since both put a concentrated load where a column would normally go.
    """
    junctions: list[tuple[float, float]] = []
    polygons = [shape.polygon_ft.buffer(_JUNCTION_TOUCH_TOLERANCE_FT) for shape in wall_shapes]
    for i in range(len(polygons)):
        for j in range(i + 1, len(polygons)):
            if not polygons[i].intersects(polygons[j]):
                continue
            overlap = polygons[i].intersection(polygons[j])
            if overlap.is_empty:
                continue
            centroid = overlap.centroid
            junctions.append((centroid.x, centroid.y))
    return junctions


def span_fill_columns(
    ordered_corners: list[tuple[float, float]], max_span_ft: float = _MAX_SPAN_FT
) -> list[tuple[float, float]]:
    """Insert evenly spaced columns along any boundary edge longer than `max_span_ft`."""
    inserted: list[tuple[float, float]] = []
    n = len(ordered_corners)
    for i in range(n):
        start = ordered_corners[i]
        end = ordered_corners[(i + 1) % n]
        edge_length = math.dist(start, end)
        if edge_length <= max_span_ft:
            continue
        segment_count = math.ceil(edge_length / max_span_ft)
        for step in range(1, segment_count):
            t = step / segment_count
            inserted.append((start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1])))
    return inserted


def merge_nearby_columns(
    candidates: list[tuple[tuple[float, float], ColumnSource]], tolerance_ft: float = _MERGE_TOLERANCE_FT
) -> list[Column]:
    """Collapse candidate points within `tolerance_ft` of each other into one column.

    Greedy single-pass clustering: a candidate joins the nearest existing
    cluster if within tolerance, otherwise starts a new one. Source priority
    on merge is boundary_corner > wall_junction > span_fill, so a corner that
    happens to coincide with a junction is still reported as a corner.
    """
    source_priority = {"boundary_corner": 0, "wall_junction": 1, "span_fill": 2}
    clusters: list[dict] = []  # each: {"points": [...], "source": str}

    for point, source in candidates:
        best_cluster = None
        best_distance = tolerance_ft
        for cluster in clusters:
            cx, cy = cluster["centroid"]
            distance = math.dist(point, (cx, cy))
            if distance <= best_distance:
                best_distance = distance
                best_cluster = cluster
        if best_cluster is None:
            clusters.append({"points": [point], "source": source, "centroid": point})
        else:
            best_cluster["points"].append(point)
            if source_priority[source] < source_priority[best_cluster["source"]]:
                best_cluster["source"] = source
            xs = [p[0] for p in best_cluster["points"]]
            ys = [p[1] for p in best_cluster["points"]]
            best_cluster["centroid"] = (sum(xs) / len(xs), sum(ys) / len(ys))

    columns = [
        Column(id=i, x_ft=round(c["centroid"][0], 2), y_ft=round(c["centroid"][1], 2), source=c["source"])
        for i, c in enumerate(clusters)
    ]
    return columns


def compute_columns(page_data: PageData, boundary: BoundaryResult) -> list[Column]:
    """Stage 2 entry point: PageData + boundary in, the column list out."""
    corners = boundary_corner_columns(boundary)
    junctions = wall_junction_columns(page_data.wall_shapes)
    span_fill = span_fill_columns(corners)

    candidates: list[tuple[tuple[float, float], ColumnSource]] = (
        [(p, "boundary_corner") for p in corners]
        + [(p, "wall_junction") for p in junctions]
        + [(p, "span_fill") for p in span_fill]
    )
    return merge_nearby_columns(candidates)
