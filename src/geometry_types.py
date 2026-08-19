"""Shared data structures passed between pipeline stages.

Every stage module (stage0_extract.py .. stage4_render.py) reads and writes
these plain dataclasses. Keeping them in one place means a stage never has
to know how an earlier stage built its inputs -- only what shape they are.

Coordinate convention: all "_ft" fields are real-world feet, in the same
X-right / Y-down orientation as the source PDF page (PDF points also use
Y-down in PyMuPDF, and so does SVG, so nothing is flipped anywhere in the
pipeline).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

Point = tuple[float, float]

WallRole = Literal["exterior", "interior", "unknown"]
ColumnSource = Literal["boundary_corner", "wall_junction", "span_fill"]
ScaleMethod = Literal["room_label_geometry", "wall_thickness_note", "manual_override"]


@dataclass
class ScaleResult:
    """How many PDF points equal one real-world foot, and how we know it."""

    points_per_foot: float
    source: ScaleMethod
    sample_count: int
    detail: str


@dataclass
class RoomLabel:
    """A parsed 'W\' - I" X W\' - I"' room-size label and where it sits on the page."""

    raw_text: str
    width_ft: float
    depth_ft: float
    center_pt: Point


@dataclass
class WallShape:
    """One filled black polygon extracted from the PDF, already converted to feet.

    A single "wall run" in the source drawing (e.g. one exterior wall with two
    door notches) can still be one WallShape -- the polygon is whatever ring
    PyMuPDF drew, not one physical brick-length. `role` is filled in by
    stage 2's wall classifier, not stage 0.
    """

    polygon_ft: Polygon
    thickness_ft: float
    role: WallRole = "unknown"


@dataclass
class PageData:
    """Everything Stage 0 extracts from a single first-floor-plan PDF."""

    crn: str
    source_pdf: str
    page_width_ft: float
    page_height_ft: float
    scale: ScaleResult
    wall_shapes: list[WallShape]
    wall_union_ft: BaseGeometry
    room_labels: list[RoomLabel]
    opening_widths_ft: list[float]
    stated_area_sqft: Optional[float]
    raw_text: str


@dataclass
class BoundaryResult:
    """Stage 1 output: the outline of the built floor area."""

    polygon_ft: list[Point]
    area_sqft: float
    stated_area_sqft: Optional[float]
    area_match_pct: Optional[float]
    closing_radius_ft: float

    def as_polygon(self) -> Polygon:
        return Polygon(self.polygon_ft)


@dataclass
class Column:
    id: int
    x_ft: float
    y_ft: float
    source: ColumnSource


@dataclass
class Beam:
    id: int
    from_column: int
    to_column: int
    length_ft: float


@dataclass
class FramingResult:
    """Everything downstream consumers (Stage 4, tests) need for one CRN."""

    crn: str
    page: PageData
    boundary: BoundaryResult
    columns: list[Column]
    beams: list[Beam]
    assumptions: list[str] = field(default_factory=list)
    known_problems: list[str] = field(default_factory=list)
