"""Unit tests for Stage 2's column-proposal functions."""

from __future__ import annotations

import math

from geometry_types import BoundaryResult, WallShape
from shapely.geometry import box
from stage2_columns import (
    boundary_corner_columns,
    merge_nearby_columns,
    span_fill_columns,
    wall_junction_columns,
)


def _boundary(polygon_ft: list[tuple[float, float]]) -> BoundaryResult:
    return BoundaryResult(
        polygon_ft=polygon_ft,
        area_sqft=0.0,
        stated_area_sqft=None,
        area_match_pct=None,
        closing_radius_ft=3.0,
    )


def test_boundary_corner_columns_returns_one_point_per_corner():
    square = _boundary([(0, 0), (20, 0), (20, 10), (0, 10)])
    corners = boundary_corner_columns(square)
    assert len(corners) == 4


def test_span_fill_columns_inserts_midpoint_on_long_edge():
    # A rectangle with two 30ft edges (top and bottom) and two 10ft edges:
    # each 30ft edge needs one intermediate column to keep every span under
    # 15ft; the 10ft edges need none.
    corners = [(0, 0), (30, 0), (30, 10), (0, 10)]
    inserted = span_fill_columns(corners, max_span_ft=15.0)
    assert len(inserted) == 2
    assert (15.0, 0.0) in inserted
    assert (15.0, 10.0) in inserted


def test_span_fill_columns_skips_short_edges():
    corners = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert span_fill_columns(corners, max_span_ft=15.0) == []


def test_wall_junction_columns_finds_t_junction():
    exterior = WallShape(polygon_ft=box(0, 0, 20, 1), thickness_ft=1.0)
    partition = WallShape(polygon_ft=box(9.5, 0, 10.5, 8), thickness_ft=1.0)
    junctions = wall_junction_columns([exterior, partition])
    assert len(junctions) == 1
    x, y = junctions[0]
    assert math.isclose(x, 10.0, abs_tol=0.5)
    assert math.isclose(y, 0.5, abs_tol=0.5)


def test_wall_junction_columns_ignores_walls_that_never_touch():
    a = WallShape(polygon_ft=box(0, 0, 5, 1), thickness_ft=1.0)
    b = WallShape(polygon_ft=box(50, 50, 55, 51), thickness_ft=1.0)
    assert wall_junction_columns([a, b]) == []


def test_merge_nearby_columns_collapses_close_points_and_prefers_corner_source():
    candidates = [
        ((10.0, 10.0), "wall_junction"),
        ((10.3, 9.9), "boundary_corner"),  # within tolerance of the point above
        ((40.0, 40.0), "span_fill"),  # far away, stays separate
    ]
    columns = merge_nearby_columns(candidates, tolerance_ft=2.0)
    assert len(columns) == 2
    merged = next(c for c in columns if c.source == "boundary_corner")
    assert 10.0 <= merged.x_ft <= 10.3
