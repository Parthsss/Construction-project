"""Orchestrates stages 0-4 for one CRN, and the CLI entry point for the whole run.

    python pipeline.py test-plans/CRN574114/first_floor_plan.pdf CRN574114 output/CRN574114
    python pipeline.py --all test-plans output

Each stage lives in its own module (stage0_extract.py .. stage4_render.py);
this file's only job is to pass one stage's output into the next one and to
write down, in one place, the assumptions and known limitations that apply
to the run as a whole rather than to a single function.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from geometry_types import FramingResult
from stage0_extract import extract_page_data
from stage1_boundary import compute_boundary
from stage2_columns import compute_columns
from stage3_beams import compute_beams
from stage4_render import write_outputs

_MAX_SPAN_FT = 15.0
_MIN_WALL_COVERAGE_RATIO = 0.8


def _build_assumptions() -> list[str]:
    return [
        "Boundary = outer face of the exterior walls, taken from filled black wall "
        "polygons in the PDF; the dash-dot plot/setback line is a stroked path and is "
        "structurally incapable of being picked up (see stage1_boundary.py).",
        "Door/window openings are bridged with a morphological closing whose radius is "
        "derived from this plan's own room sizes and door/window schedule, not a fixed "
        "constant (see stage1_boundary.choose_closing_radius_ft).",
        "A balcony or slab projection is included in the boundary whenever it is enclosed "
        "by wall material that survives the closing step; when the sheet states balcony "
        "area separately, it is added to the stated built-up area for the area-match check.",
        "Columns are proposed at every boundary corner, every wall-to-wall junction, and at "
        f"evenly spaced points wherever a straight run exceeds {_MAX_SPAN_FT:g} ft "
        "(see stage2_columns.py).",
        "Interior beams are only proposed where the straight line between two columns is at "
        f"least {_MIN_WALL_COVERAGE_RATIO:.0%} covered by wall material -- a beam is never "
        "inferred across a span with no wall behind it (see stage3_beams.interior_wall_beams).",
    ]


def _build_known_problems(framing_without_problems: FramingResult, isolated_column_ids: list[int]) -> list[str]:
    problems = [
        "The closing radius that reconnects wall fragments and bridges openings (stage 1) "
        "also smooths over real concave notches narrower than the radius -- visible on the "
        "drawing as a gentle curve where the source plan actually has a sharp step.",
        "A beam is only proposed where a wall is drawn between two aligned columns; a span "
        "that is genuinely open (e.g. a stair void open to a passage on one side) gets no "
        "beam there, which can leave one edge of a slab panel unsupported in the output.",
    ]
    if isolated_column_ids:
        problems.append(
            f"Column id(s) {isolated_column_ids} had no wall-backed beam candidate on either "
            "side (both neighbouring wall runs were interrupted by a doorway) and were "
            "connected to their nearest neighbouring column as a fallback, not because a wall "
            "was confirmed between them -- see stage3_beams.connect_isolated_columns."
        )
    if framing_without_problems.boundary.area_match_pct is not None:
        match = framing_without_problems.boundary.area_match_pct
        if abs(match - 100) > 15:
            problems.append(
                f"Computed boundary area is {match:g}% of the sheet's stated built-up area -- "
                "outside the +/-15% band we treat as a good match; worth a manual look before "
                "trusting this CRN's boundary."
            )
    return problems


def build_framing_result(pdf_path: str, crn: str) -> FramingResult:
    """Run stages 0-3 for one plan and assemble the full result."""
    page_data = extract_page_data(pdf_path, crn)
    boundary = compute_boundary(page_data)
    columns = compute_columns(page_data, boundary)
    beams, isolated_column_ids = compute_beams(columns, boundary, page_data.wall_union_ft)

    framing = FramingResult(
        crn=crn,
        page=page_data,
        boundary=boundary,
        columns=columns,
        beams=beams,
        assumptions=_build_assumptions(),
    )
    framing.known_problems = _build_known_problems(framing, isolated_column_ids)
    return framing


def run_for_crn(pdf_path: str, crn: str, output_dir: str) -> FramingResult:
    """Stages 0-4 for one CRN: build the result and write layout.html / layout.json."""
    framing = build_framing_result(pdf_path, crn)
    write_outputs(framing, output_dir)
    return framing


def discover_test_plans(test_plans_dir: str) -> list[tuple[str, str]]:
    """Find every `<crn>/first_floor_plan.pdf` under `test_plans_dir`, sorted by CRN."""
    root = Path(test_plans_dir)
    found = []
    for pdf_path in sorted(root.glob("*/first_floor_plan.pdf")):
        crn = pdf_path.parent.name
        found.append((crn, str(pdf_path)))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute a structural layout grid from a first floor plan PDF.")
    parser.add_argument("pdf_path", nargs="?", help="Path to a single first_floor_plan.pdf")
    parser.add_argument("crn", nargs="?", help="CRN label for that plan")
    parser.add_argument("output_dir", nargs="?", default="output", help="Where to write layout.html/.json")
    parser.add_argument("--all", metavar="TEST_PLANS_DIR", help="Run every <crn>/first_floor_plan.pdf under this directory")
    args = parser.parse_args(argv)

    if args.all:
        for crn, pdf_path in discover_test_plans(args.all):
            framing = run_for_crn(pdf_path, crn, str(Path(args.output_dir) / crn))
            match = framing.boundary.area_match_pct
            match_str = f"{match:g}%" if match is not None else "n/a"
            print(f"{crn}: {len(framing.columns)} columns, {len(framing.beams)} beams, area match {match_str}")
        return 0

    if not args.pdf_path or not args.crn:
        parser.error("either pass pdf_path and crn, or use --all TEST_PLANS_DIR")

    framing = run_for_crn(args.pdf_path, args.crn, args.output_dir)
    match = framing.boundary.area_match_pct
    match_str = f"{match:g}%" if match is not None else "n/a"
    print(f"{framing.crn}: {len(framing.columns)} columns, {len(framing.beams)} beams, area match {match_str}")
    print(f"wrote {args.output_dir}/layout.html and {args.output_dir}/layout.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
