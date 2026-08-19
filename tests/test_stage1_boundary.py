"""Unit tests for Stage 1's boundary-closing and area-matching functions."""

from __future__ import annotations

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from geometry_types import RoomLabel
from stage1_boundary import (
    _MAX_CLOSING_RADIUS_FT,
    _MIN_CLOSING_RADIUS_FT,
    area_match_percent,
    choose_closing_radius_ft,
    close_wall_gaps,
    polygon_to_point_list,
    select_largest_shell,
    simplify_boundary,
)


def test_choose_closing_radius_uses_largest_room_half_span():
    labels = [RoomLabel("10' - 0\" X 20' - 0\"", 10.0, 20.0, (0, 0))]
    # Half of the largest room dimension (20ft) is 10ft, bigger than any
    # opening, so that should win.
    assert choose_closing_radius_ft(labels, opening_widths_ft=[3.0]) == 10.0


def test_choose_closing_radius_respects_floor_and_ceiling():
    assert choose_closing_radius_ft([], []) == _MIN_CLOSING_RADIUS_FT
    huge = [RoomLabel("1' - 0\" X 100' - 0\"", 1.0, 100.0, (0, 0))]
    assert choose_closing_radius_ft(huge, []) == _MAX_CLOSING_RADIUS_FT


def test_close_wall_gaps_reconnects_two_nearby_fragments():
    # Two 8ft-thick blocks 4ft apart -- a closing radius of 3ft (bridges any
    # gap under 6ft) should merge them into one polygon. Blocks are made
    # thicker than 2x the radius so the erosion half of the closing doesn't
    # also eat the blocks themselves, isolating the "does it bridge the gap"
    # behaviour from the separate "radius vs. material thickness" concern.
    left = box(0, 0, 10, 8)
    right = box(14, 0, 24, 8)
    fragments = unary_union([left, right])
    assert fragments.geom_type == "MultiPolygon"

    closed = close_wall_gaps(fragments, closing_radius_ft=3.0)
    assert closed.geom_type == "Polygon"


def test_select_largest_shell_drops_holes_and_picks_biggest():
    with_hole = box(0, 0, 10, 10).difference(box(4, 4, 6, 6))
    tiny = box(20, 20, 21, 21)
    from shapely.geometry import MultiPolygon

    multi = MultiPolygon([with_hole, tiny])
    shell = select_largest_shell(multi)
    assert shell.area == 100.0  # hole dropped, tiny fragment ignored
    assert len(shell.interiors) == 0


def test_simplify_boundary_keeps_real_skewed_corners():
    # A quadrilateral with a genuinely non-90-degree corner should survive
    # the small simplification tolerance used for display.
    skewed = Polygon([(0, 0), (10, 0.5), (10, 10), (0, 10)])
    simplified = simplify_boundary(skewed, tolerance_ft=0.05)
    assert len(list(simplified.exterior.coords)) - 1 == 4


def test_polygon_to_point_list_drops_repeated_closing_point():
    square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    points = polygon_to_point_list(square)
    assert len(points) == 4
    assert points[0] != points[-1]


def test_area_match_percent_handles_missing_stated_area():
    assert area_match_percent(100.0, None) is None
    assert area_match_percent(100.0, 0) is None


def test_area_match_percent_computes_ratio():
    assert area_match_percent(65.0, 100.0) == 65.0
