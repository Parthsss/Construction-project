"""Stage 4 -- draw the result and write it to disk.

Produces, per CRN:
- `layout.html` -- the original architectural plan next to a plain line
  drawing of the computed boundary/columns/beams. Deliberately styled like
  a printed technical sheet (white background, black rules, one accent
  colour per element type) rather than a web dashboard: no gradients, no
  card shadows, no interactive chrome. This is a drawing, not an app.
- `layout.json` -- the same geometry as data, in the shape sketched in the
  assignment brief, for anyone who wants to check numbers without opening
  the drawing.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pymupdf

from geometry_types import FramingResult

_PIXELS_PER_FOOT = 11
_PAGE_PADDING_FT = 4
_COLUMN_MARKER_PX = 5

_SOURCE_LABEL = {
    "boundary_corner": "boundary corner",
    "wall_junction": "wall junction",
    "span_fill": "span fill (>15 ft gap)",
}


def render_original_plan_data_uri(pdf_path: str) -> str:
    """Rasterize the source PDF's first page to a PNG data URI for embedding."""
    document = pymupdf.open(pdf_path)
    pixmap = document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2))
    encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_framing_svg(framing: FramingResult, pixels_per_foot: float = _PIXELS_PER_FOOT) -> str:
    """Draw the boundary polygon, columns and beams as a plain-line SVG in real-world proportions."""
    boundary = framing.boundary
    xs = [x for x, _ in boundary.polygon_ft]
    ys = [y for _, y in boundary.polygon_ft]
    min_x, max_x = min(xs) - _PAGE_PADDING_FT, max(xs) + _PAGE_PADDING_FT
    min_y, max_y = min(ys) - _PAGE_PADDING_FT, max(ys) + _PAGE_PADDING_FT
    width = (max_x - min_x) * pixels_per_foot
    height = (max_y - min_y) * pixels_per_foot

    def to_px(x_ft: float, y_ft: float) -> tuple[float, float]:
        return (x_ft - min_x) * pixels_per_foot, (y_ft - min_y) * pixels_per_foot

    columns_by_id = {c.id: c for c in framing.columns}

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" font-family="Helvetica, Arial, sans-serif">',
        f'<rect x="0" y="0" width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>',
    ]

    boundary_points = " ".join(f"{x:.1f},{y:.1f}" for x, y in (to_px(x, y) for x, y in boundary.polygon_ft))
    parts.append(f'<polygon points="{boundary_points}" fill="none" stroke="#111111" stroke-width="2"/>')

    for beam in framing.beams:
        a = columns_by_id[beam.from_column]
        b = columns_by_id[beam.to_column]
        ax, ay = to_px(a.x_ft, a.y_ft)
        bx, by = to_px(b.x_ft, b.y_ft)
        parts.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#2b6cb0" stroke-width="2.5"/>')

    for column in framing.columns:
        cx, cy = to_px(column.x_ft, column.y_ft)
        half = _COLUMN_MARKER_PX
        parts.append(
            f'<rect x="{cx - half:.1f}" y="{cy - half:.1f}" width="{2 * half}" height="{2 * half}" '
            f'fill="#8a1f1f" stroke="#111111" stroke-width="0.5"/>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _stat_rows(framing: FramingResult) -> str:
    boundary = framing.boundary
    stated = f"{boundary.stated_area_sqft:g} SF" if boundary.stated_area_sqft else "not stated on sheet"
    match = f"{boundary.area_match_pct:g}%" if boundary.area_match_pct is not None else "n/a"
    rows = [
        ("CRN", framing.crn),
        ("Scale derived", f"{framing.page.scale.points_per_foot:.2f} pt/ft ({framing.page.scale.source}: {framing.page.scale.detail})"),
        ("Boundary area (computed)", f"{boundary.area_sqft:g} SF"),
        ("Boundary area (stated on sheet)", stated),
        ("Match", match),
        ("Closing radius used", f"{boundary.closing_radius_ft:g} ft"),
        ("Columns", str(len(framing.columns))),
        ("Beams", str(len(framing.beams))),
    ]
    return "\n".join(f"<tr><th>{label}</th><td>{value}</td></tr>" for label, value in rows)


def _list_block(title: str, items: list[str]) -> str:
    if not items:
        return ""
    list_items = "\n".join(f"<li>{item}</li>" for item in items)
    return f"<h3>{title}</h3><ul>{list_items}</ul>"


def build_comparison_html(framing: FramingResult) -> str:
    """The full layout.html page: original plan beside the computed framing drawing."""
    original_data_uri = render_original_plan_data_uri(framing.page.source_pdf)
    framing_svg = build_framing_svg(framing)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{framing.crn} -- layout grid</title>
<style>
  body {{ font-family: Helvetica, Arial, sans-serif; margin: 24px; color: #111111; background: #ffffff; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  h2 {{ font-size: 15px; margin: 0 0 12px 0; color: #444444; font-weight: normal; }}
  h3 {{ font-size: 14px; margin: 18px 0 6px 0; }}
  .panels {{ display: flex; gap: 24px; flex-wrap: wrap; align-items: flex-start; }}
  .panel {{ border: 1px solid #cccccc; padding: 12px; }}
  .panel h4 {{ margin: 0 0 8px 0; font-size: 13px; font-weight: bold; color: #333333; }}
  .panel img, .panel svg {{ max-width: 640px; height: auto; display: block; }}
  table {{ border-collapse: collapse; margin-top: 12px; font-size: 13px; }}
  th, td {{ text-align: left; padding: 3px 10px 3px 0; vertical-align: top; }}
  th {{ color: #555555; font-weight: normal; white-space: nowrap; }}
  ul {{ font-size: 13px; margin: 4px 0; padding-left: 20px; }}
  .legend {{ font-size: 12px; color: #555555; margin-top: 8px; }}
  .legend span {{ display: inline-block; width: 12px; height: 12px; margin-right: 4px; vertical-align: middle; }}
</style>
</head>
<body>
<h1>{framing.crn} -- structural layout grid</h1>
<h2>Boundary, columns and beams computed from the first-floor plan (Stages 0-3)</h2>

<div class="panels">
  <div class="panel">
    <h4>INPUT -- architect's first floor plan</h4>
    <img src="{original_data_uri}" alt="Original first floor plan for {framing.crn}">
  </div>
  <div class="panel">
    <h4>COMPUTED -- boundary / columns / beams</h4>
    {framing_svg}
    <div class="legend">
      <span style="background:#111111"></span>boundary&nbsp;&nbsp;
      <span style="background:#2b6cb0"></span>beam&nbsp;&nbsp;
      <span style="background:#8a1f1f"></span>column
    </div>
  </div>
</div>

<table>
{_stat_rows(framing)}
</table>

{_list_block("Assumptions", framing.assumptions)}
{_list_block("Known problems", framing.known_problems)}

</body>
</html>
"""


def build_output_json(framing: FramingResult) -> dict:
    """The machine-readable geometry, in the shape the assignment brief sketches."""
    boundary = framing.boundary
    return {
        "crn": framing.crn,
        "units": "feet",
        "scale_source": f"{framing.page.scale.source}: {framing.page.scale.detail}",
        "boundary": [[x, y] for x, y in boundary.polygon_ft],
        "boundary_area_sqft": boundary.area_sqft,
        "stated_area_sqft": boundary.stated_area_sqft,
        "area_match_pct": boundary.area_match_pct,
        "columns": [
            {"id": c.id, "x": c.x_ft, "y": c.y_ft, "source": _SOURCE_LABEL.get(c.source, c.source)}
            for c in framing.columns
        ],
        "beams": [
            {"id": b.id, "from": b.from_column, "to": b.to_column, "length_ft": b.length_ft}
            for b in framing.beams
        ],
        "assumptions": framing.assumptions,
        "known_problems": framing.known_problems,
    }


def write_outputs(framing: FramingResult, output_dir: str) -> tuple[Path, Path]:
    """Stage 4 entry point: write layout.html and layout.json for one CRN, return their paths."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    html_path = directory / "layout.html"
    html_path.write_text(build_comparison_html(framing), encoding="utf-8")

    json_path = directory / "layout.json"
    json_path.write_text(json.dumps(build_output_json(framing), indent=2), encoding="utf-8")

    return html_path, json_path
