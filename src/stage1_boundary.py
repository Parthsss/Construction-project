"""Stage 1 -- find the outline of the built floor area.

Definition used here: **the boundary is the outer face of the exterior
walls** at this floor level, including any balcony whose slab sits within
(or projects past) that wall line. Explicitly excluded: the plot / setback
line, dimension chains, grid lines, hatching, text and the title block --
none of those are filled wall material, so they can never appear in
`wall_union_ft` (Stage 0 only fills that from *filled* black polygons; the
plot boundary and every one of those other things is drawn as a *stroked*
path). That single fact is what keeps this stage from falling into the two
traps the assignment sets up: "take the bounding box of the page" and
"assume the outermost closed shape on the page is the building".

The one real difficulty: `wall_union_ft` is the *exterior and interior*
walls together, still exactly as thin as they are drawn (4"-6" wide). Two
problems follow directly from that:

1. Interior partition walls poke into the union from the exterior walls
   without enclosing anything on their own. Tracing the outer ring of that
   raw union follows every partition wall's face in and back out again,
   like tracing the outline of a comb -- correct topologically, useless as
   a "building outline" (confirmed by hand: it produces a ~500-vertex
   polygon covering under half the stated area).
2. Door, window and balcony openings are real gaps in the wall fill, so the
   raw union is not even a single connected shape -- some plans split into
   6-8 disjoint wall islands.

Both are solved by the same operation: a large-radius morphological closing
(dilate by R, then erode by R). Dilating by a radius bigger than half of
any room's smaller side swallows every room and every interior partition
into one solid mass; eroding back by the same R removes the dilation's
outward bulge but -- because no interior cavity was ever wider than 2R --
leaves the interior filled solid. The same R, sized against the largest
opening on the sheet, also bridges door/window gaps and (usually) open
balcony edges. What is left after eroding is a single solid blob whose
outer ring is the building footprint directly -- no separate room/void
classification needed.

The trade-off, stated plainly: any real concave notch in the true outline
that is narrower than 2R gets smoothed over along with the door gaps. This
is visible on the rendered output as gentle curves where the drawing has a
sharp step (e.g. a recessed balcony corner) -- see the README's known
limitations.
"""

from __future__ import annotations

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from geometry_types import BoundaryResult, PageData, RoomLabel

_MIN_CLOSING_RADIUS_FT = 4.0
_MAX_CLOSING_RADIUS_FT = 15.0
_SIMPLIFY_TOLERANCE_FT = 0.05


def choose_closing_radius_ft(room_labels: list[RoomLabel], opening_widths_ft: list[float]) -> float:
    """Pick a closing radius large enough to swallow the biggest room and
    bridge the widest scheduled opening, so the closing operation in
    `close_wall_gaps` produces one solid mass rather than a comb-shaped mesh.

    Sized from this plan's own rooms and openings (never a fixed constant),
    clamped to a sane range so a plan with no parseable rooms/openings still
    gets a usable default, and a plan with one huge room doesn't get an
    absurdly large radius that would erase real boundary steps.
    """
    room_half_spans = [max(label.width_ft, label.depth_ft) / 2.0 for label in room_labels]
    candidates = room_half_spans + [w / 2.0 for w in opening_widths_ft]
    radius = max(candidates, default=_MIN_CLOSING_RADIUS_FT)
    return min(max(radius, _MIN_CLOSING_RADIUS_FT), _MAX_CLOSING_RADIUS_FT)


def close_wall_gaps(wall_union_ft: BaseGeometry, closing_radius_ft: float) -> BaseGeometry:
    """Dilate then erode by `closing_radius_ft` to turn the wall network into
    one solid mass (see module docstring for why this works)."""
    dilated = wall_union_ft.buffer(closing_radius_ft, join_style=1)
    return dilated.buffer(-closing_radius_ft, join_style=1)


def select_largest_shell(closed_geometry: BaseGeometry) -> Polygon:
    """Return the single largest component's outer ring, discarding any holes.

    A hole here would mean a courtyard/light-well fully enclosed by wall on
    every side and wider than the closing radius; we treat the plan-level
    structural boundary as following the outer wall line regardless (the
    roof/slab still spans to that line even where there's an opening below
    it), so holes are dropped rather than subtracted.
    """
    if closed_geometry.geom_type == "MultiPolygon":
        largest = max(closed_geometry.geoms, key=lambda g: g.area)
    elif closed_geometry.geom_type == "Polygon":
        largest = closed_geometry
    else:
        raise ValueError(f"Unexpected geometry type after closing: {closed_geometry.geom_type}")
    return Polygon(largest.exterior)


def simplify_boundary(polygon: Polygon, tolerance_ft: float = _SIMPLIFY_TOLERANCE_FT) -> Polygon:
    """Remove the small jagged vertices buffering introduces.

    `tolerance_ft` is deliberately tiny (well under an inch) -- it cleans up
    buffering noise without straightening real geometry, so a genuinely
    skewed plot (CRN574114's 91/88/87/93 degree corners) is preserved.
    """
    return polygon.simplify(tolerance_ft, preserve_topology=True)


def polygon_to_point_list(polygon: Polygon) -> list[tuple[float, float]]:
    """Convert a shapely polygon's exterior ring to an ordered, non-repeating point list."""
    coords = list(polygon.exterior.coords)
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]
    return [(round(x, 2), round(y, 2)) for x, y in coords]


def area_match_percent(computed_area_sqft: float, stated_area_sqft: float | None) -> float | None:
    """How close the computed boundary area is to the sheet's own area statement."""
    if not stated_area_sqft:
        return None
    return round(100.0 * computed_area_sqft / stated_area_sqft, 1)


def compute_boundary(page_data: PageData) -> BoundaryResult:
    """Stage 1 entry point: PageData in, the boundary polygon (in feet) out."""
    closing_radius_ft = choose_closing_radius_ft(page_data.room_labels, page_data.opening_widths_ft)
    closed = close_wall_gaps(page_data.wall_union_ft, closing_radius_ft)
    shell = select_largest_shell(closed)
    simplified = simplify_boundary(shell)

    area_sqft = round(simplified.area, 1)
    return BoundaryResult(
        polygon_ft=polygon_to_point_list(simplified),
        area_sqft=area_sqft,
        stated_area_sqft=page_data.stated_area_sqft,
        area_match_pct=area_match_percent(area_sqft, page_data.stated_area_sqft),
        closing_radius_ft=closing_radius_ft,
    )
