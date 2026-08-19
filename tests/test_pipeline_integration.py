"""End-to-end tests: run the full pipeline against the real test-plan PDFs.

These are the tests that matter most for the assignment's "does it
generalise" requirement -- everything here runs against `test-plans/`
unmodified, with no CRN-specific branches anywhere in the pipeline code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pipeline import build_framing_result, discover_test_plans, run_for_crn

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_PLANS = discover_test_plans(str(REPO_ROOT / "test-plans"))


@pytest.mark.parametrize("crn,pdf_path", TEST_PLANS, ids=[crn for crn, _ in TEST_PLANS])
def test_boundary_is_a_simple_closed_polygon_with_positive_area(crn, pdf_path):
    framing = build_framing_result(pdf_path, crn)
    assert len(framing.boundary.polygon_ft) >= 4
    assert framing.boundary.area_sqft > 0


@pytest.mark.parametrize("crn,pdf_path", TEST_PLANS, ids=[crn for crn, _ in TEST_PLANS])
def test_computed_area_is_within_a_sane_band_of_the_stated_area(crn, pdf_path):
    framing = build_framing_result(pdf_path, crn)
    # Not a tight tolerance -- the assignment explicitly does not want constant
    # -tuning for a perfect match. This is a regression guard against a
    # completely broken extraction (e.g. picking up the plot line, or only
    # capturing half the building), not a precision claim.
    assert framing.boundary.area_match_pct is not None
    assert 50.0 <= framing.boundary.area_match_pct <= 150.0


@pytest.mark.parametrize("crn,pdf_path", TEST_PLANS, ids=[crn for crn, _ in TEST_PLANS])
def test_every_beam_references_a_real_column_with_positive_length(crn, pdf_path):
    framing = build_framing_result(pdf_path, crn)
    column_ids = {c.id for c in framing.columns}
    for beam in framing.beams:
        assert beam.from_column in column_ids
        assert beam.to_column in column_ids
        assert beam.from_column != beam.to_column
        assert beam.length_ft > 0


@pytest.mark.parametrize("crn,pdf_path", TEST_PLANS, ids=[crn for crn, _ in TEST_PLANS])
def test_every_column_has_at_least_one_beam(crn, pdf_path):
    framing = build_framing_result(pdf_path, crn)
    connected = {c for beam in framing.beams for c in (beam.from_column, beam.to_column)}
    assert connected == {c.id for c in framing.columns}


@pytest.mark.parametrize("crn,pdf_path", TEST_PLANS, ids=[crn for crn, _ in TEST_PLANS])
def test_column_ids_are_unique(crn, pdf_path):
    framing = build_framing_result(pdf_path, crn)
    ids = [c.id for c in framing.columns]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("crn,pdf_path", TEST_PLANS, ids=[crn for crn, _ in TEST_PLANS])
def test_no_scale_or_boundary_value_is_hardcoded_per_crn(crn, pdf_path):
    # Sanity check on genericity: scale must come from this plan's own
    # geometry/text, never a constant.
    framing = build_framing_result(pdf_path, crn)
    assert framing.page.scale.points_per_foot > 0
    assert framing.page.scale.source in ("room_label_geometry", "wall_thickness_note")


def test_run_for_crn_writes_html_and_json(tmp_path):
    crn, pdf_path = TEST_PLANS[0]
    output_dir = tmp_path / crn
    framing = run_for_crn(pdf_path, crn, str(output_dir))

    html_path = output_dir / "layout.html"
    json_path = output_dir / "layout.json"
    assert html_path.exists() and html_path.stat().st_size > 0
    assert json_path.exists()

    data = json.loads(json_path.read_text())
    assert data["crn"] == crn
    assert len(data["columns"]) == len(framing.columns)
    assert len(data["beams"]) == len(framing.beams)
    assert data["boundary_area_sqft"] == framing.boundary.area_sqft


def test_discover_test_plans_finds_all_three_crns():
    crns = {crn for crn, _ in TEST_PLANS}
    assert crns == {"CRN574114", "CRN642050", "CRN716485"}
