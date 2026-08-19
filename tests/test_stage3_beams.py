"""Unit tests for Stage 3's beam-proposal functions."""

from __future__ import annotations

from geometry_types import BoundaryResult, Column
from shapely.geometry import box
from stage3_beams import (
    _dedupe_and_build,
    connect_isolated_columns,
    interior_wall_beams,
    order_boundary_columns,
    perimeter_beams,
)


def _boundary(polygon_ft: list[tuple[float, float]]) -> BoundaryResult:
    return BoundaryResult(
        polygon_ft=polygon_ft,
        area_sqft=0.0,
        stated_area_sqft=None,
        area_match_pct=None,
        closing_radius_ft=3.0,
    )


def test_order_boundary_columns_walks_the_ring_in_order():
    square = _boundary([(0, 0), (10, 0), (10, 10), (0, 10)])
    # Deliberately listed out of ring order.
    columns = [
        Column(0, 10, 10, "boundary_corner"),
        Column(1, 0, 0, "boundary_corner"),
        Column(2, 10, 0, "boundary_corner"),
        Column(3, 0, 10, "boundary_corner"),
    ]
    ordered = order_boundary_columns(columns, square)
    assert [c.id for c in ordered] == [1, 2, 0, 3]


def test_perimeter_beams_form_a_closed_loop():
    square = _boundary([(0, 0), (10, 0), (10, 10), (0, 10)])
    columns = [
        Column(0, 0, 0, "boundary_corner"),
        Column(1, 10, 0, "boundary_corner"),
        Column(2, 10, 10, "boundary_corner"),
        Column(3, 0, 10, "boundary_corner"),
    ]
    pairs = perimeter_beams(columns, square)
    assert len(pairs) == 4  # one beam per edge, wrapping back to the start
    touched = {c.id for pair in pairs for c in pair}
    assert touched == {0, 1, 2, 3}


def test_interior_wall_beams_connects_wall_backed_aligned_columns():
    wall_union = box(0, 0, 1, 20)  # a single vertical wall run
    a = Column(0, 0.5, 0, "wall_junction")
    b = Column(1, 0.5, 20, "wall_junction")
    pairs = interior_wall_beams([a, b], wall_union)
    assert len(pairs) == 1


def test_interior_wall_beams_skips_columns_with_no_wall_between_them():
    wall_union = box(0, 0, 1, 1)  # a short stub, nowhere near either column
    a = Column(0, 0.5, 0, "wall_junction")
    b = Column(1, 0.5, 20, "wall_junction")
    assert interior_wall_beams([a, b], wall_union) == []


def test_interior_wall_beams_does_not_skip_over_an_intermediate_column():
    wall_union = box(0, 0, 1, 20)
    a = Column(0, 0.5, 0, "wall_junction")
    mid = Column(1, 0.5, 10, "wall_junction")
    b = Column(2, 0.5, 20, "wall_junction")
    pairs = interior_wall_beams([a, mid, b], wall_union)
    pair_ids = {tuple(sorted((p[0].id, p[1].id))) for p in pairs}
    assert pair_ids == {(0, 1), (1, 2)}  # not the (0, 2) shortcut


def test_connect_isolated_columns_gives_every_column_a_beam():
    columns = [
        Column(0, 0, 0, "boundary_corner"),
        Column(1, 10, 0, "boundary_corner"),
        Column(2, 5, 100, "wall_junction"),  # far away, no beam yet
    ]
    existing_beams = _dedupe_and_build([(columns[0], columns[1])])
    new_beams, forced_ids = connect_isolated_columns(columns, existing_beams)
    assert forced_ids == [2]
    assert len(new_beams) == 2
    touched = {c for beam in new_beams for c in (beam.from_column, beam.to_column)}
    assert touched == {0, 1, 2}


def test_connect_isolated_columns_is_noop_when_all_connected():
    columns = [Column(0, 0, 0, "boundary_corner"), Column(1, 10, 0, "boundary_corner")]
    beams = _dedupe_and_build([(columns[0], columns[1])])
    new_beams, forced_ids = connect_isolated_columns(columns, beams)
    assert forced_ids == []
    assert new_beams == beams
