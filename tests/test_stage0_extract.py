"""Unit tests for Stage 0's text-parsing and scale-derivation functions."""

from __future__ import annotations

from shapely.geometry import box

from geometry_types import RoomLabel
from stage0_extract import (
    _TextLine,
    derive_scale_from_room_labels,
    derive_scale_from_wall_thickness,
    parse_opening_widths_ft,
    parse_room_labels,
    parse_stated_area_sqft as parse_area_statement,
    parse_wall_thickness_inches,
)


def test_parse_room_labels_extracts_feet_inches():
    lines = [_TextLine("12' - 0\" X 11' - 0\"", (0, 0, 10, 10))]
    labels = parse_room_labels(lines)
    assert len(labels) == 1
    assert labels[0].width_ft == 12.0
    assert labels[0].depth_ft == 11.0


def test_parse_room_labels_ignores_non_matching_text():
    lines = [_TextLine("BEDROOM", (0, 0, 10, 10)), _TextLine("UP", (0, 0, 5, 5))]
    assert parse_room_labels(lines) == []


def test_parse_wall_thickness_inches_defaults_when_absent():
    assert parse_wall_thickness_inches("no note here") == 6.0


def test_parse_wall_thickness_inches_reads_note():
    text = "NOTES\nEXTERNAL WALL-6\" BLOCK WORK\nINTERNAL WALL-4\" BLOCK WORK"
    assert parse_wall_thickness_inches(text) == 6.0


def test_parse_opening_widths_ft_reads_schedule_rows():
    text = "D1  3' - 0\"  7' - 0\"  2  42 SF\nD2  2' - 6\"  7' - 0\"  2  35 SF"
    widths = parse_opening_widths_ft(text)
    assert widths == [3.0, 2.5]


def test_parse_stated_area_sqft_first_floor_only():
    text = (
        "BUILTUP AREA  627 SF\nPARKING 132 SF\n"
        "FIRST FLOOR LEVEL\nBUILTUP AREA  649 SF"
    )
    built_up, balcony = parse_area_statement(text)
    assert built_up == 649.0
    assert balcony is None


def test_parse_stated_area_sqft_with_balcony():
    text = "FIRST FLOOR LEVEL\nBUILT UP AREA  877 SF\nBALCONY  110 SF"
    built_up, balcony = parse_area_statement(text)
    assert built_up == 877.0
    assert balcony == 110.0


def test_derive_scale_from_wall_thickness_uses_modal_measurement():
    # Ten 6pt x 60pt strips (a wall run) plus one unrelated 1pt x 1pt speck.
    strips = [box(i * 70, 0, i * 70 + 60, 6) for i in range(10)]
    speck = box(1000, 1000, 1001, 1001)
    result = derive_scale_from_wall_thickness(strips + [speck], external_wall_inches=6.0)
    assert result is not None
    # 6pt drawn thickness for a 6" (0.5ft) wall => 12 points per foot.
    assert result.points_per_foot == 12.0
    assert result.source == "wall_thickness_note"


def test_derive_scale_from_room_labels_matches_consistent_clear_span():
    # A wall frame around a 100x40pt clear hole. Ray-casting from the centre
    # finds that inner face, so a 10ft x 4ft label is consistent both axes
    # at 10 pt/ft.
    room = box(0, 0, 120, 60).difference(box(10, 10, 110, 50))
    label = RoomLabel("10' - 0\" X 4' - 0\"", width_ft=10.0, depth_ft=4.0, center_pt=(60, 30))
    result = derive_scale_from_room_labels(room, [label])
    assert result is not None
    assert abs(result.points_per_foot - 10.0) < 0.5


def test_derive_scale_from_room_labels_rejects_inconsistent_axes():
    # Same clear hole, but a label whose width:depth ratio doesn't match the
    # measured 100:40 shape -- x/y implied scales disagree by more than the
    # tolerance, so no sample should be trusted.
    room = box(0, 0, 120, 60).difference(box(10, 10, 110, 50))
    label = RoomLabel("12' - 0\" X 6' - 0\"", width_ft=12.0, depth_ft=6.0, center_pt=(60, 30))
    result = derive_scale_from_room_labels(room, [label])
    assert result is None
