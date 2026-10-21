"""Independent physical references for explicit source frames (synthetic artwork only)."""

from copy import deepcopy
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from wraplab.domain import ObjectSpec, Project
from wraplab.persistence import load_project, save_project
from wraplab.svg import convert, export_svg, import_svg
from wraplab.svg.exporter import ideal_front_svg


MARGINS = (
    '<svg width="100mm" height="80mm" viewBox="0 0 100 80">'
    '<path fill-rule="evenodd" d="M20 10H80V50H20Z M30 20V40H50V20Z"/></svg>'
)


def placed(frame="visible", mode="cylinder"):
    p = Project(
        object=ObjectSpec(
            mode=mode,
            diameter=200,
            height=200,
            top_diameter=180,
            bottom_diameter=220,
            points=[(0, 180), (100, 200), (200, 220)],
        ),
        artwork_frame=frame,
    )
    p.placement.width, p.placement.height = 30, 20
    p.placement.x, p.placement.z = 3, 25
    return p


def points(result):
    return [p for path in result.paths for c in path.contours for p in c.points]


def test_bounds_keep_document_page_and_source_vectors_separate():
    art = import_svg(MARGINS)
    assert (art.page_frame.width, art.page_frame.height) == (100, 80)
    assert (
        art.visible_frame.left,
        art.visible_frame.top,
        art.visible_frame.width,
        art.visible_frame.height,
    ) == (20, 10, 60, 40)
    assert art.source == MARGINS
    assert art.shapes[0].subpaths[0].segments[0].start == 20 + 10j


def test_transformed_class_fills_extrema_hidden_shapes_and_holes():
    source = (
        '<svg width="100mm" height="80mm" viewBox="0 0 100 80">'
        "<style>.solid{fill:currentColor;fill-rule:evenodd}</style>"
        '<g color="blue" transform="translate(80 10)"><g transform="scale(-2 3)">'
        '<path class="solid" d="M5 2H25V12H5Z M10 5V9H20V5Z"/>'
        '</g></g><rect width="100" height="80" opacity="0"/>'
        '<rect width="99" height="79" visibility="hidden"/>'
        '<path d="M0 0L100 80" fill="black"/></svg>'
    )
    art = import_svg(source)
    b = art.visible_frame
    assert (b.left, b.top, b.width, b.height) == pytest.approx((30, 16, 40, 30))


def test_cubic_and_transformed_ellipse_bounds_use_interior_extrema():
    art = import_svg(
        '<svg width="100mm" height="80mm" viewBox="0 0 100 80">'
        '<path d="M10 10 C10 50 50 50 50 10 Z"/></svg>'
    )
    assert (art.visible_frame.width, art.visible_frame.height) == pytest.approx((40, 30))
    ellipse = import_svg(
        '<svg width="100mm" height="80mm" viewBox="0 0 100 80">'
        '<ellipse cx="0" cy="0" rx="10" ry="4" '
        'transform="translate(40 30) rotate(30)"/></svg>'
    )
    b = ellipse.visible_frame
    assert (b.width, b.height) == pytest.approx(
        (2 * math.sqrt(100 * 0.75 + 16 * 0.25), 2 * math.sqrt(100 * 0.25 + 16 * 0.75)), abs=1e-10
    )


@pytest.mark.parametrize("cap,expected", [("butt", (10, 18, 20, 4)), ("square", (6, 18, 28, 4))])
def test_stroke_expanded_bounds_with_caps_and_nonuniform_group_transform(cap, expected):
    art = import_svg(
        '<svg width="100mm" height="80mm" viewBox="0 0 100 80">'
        '<g transform="translate(0 10) scale(2 1)">'
        '<path d="M5 10H15" fill="none" stroke="black" stroke-width="4" '
        f'stroke-linecap="{cap}"/></g></svg>'
    )
    b = art.visible_frame
    assert (b.left, b.top, b.width, b.height) == pytest.approx(expected)


def test_round_stroke_bounds_have_an_explicit_small_numerical_envelope():
    art = import_svg(
        '<svg width="40mm" height="40mm" viewBox="0 0 40 40">'
        '<circle cx="20" cy="20" r="10" fill="none" stroke="black" '
        'stroke-width="2" stroke-linejoin="round"/></svg>'
    )
    b = art.visible_frame
    assert b.accuracy_mm == 0.00001
    assert (b.left, b.top, b.width, b.height) == pytest.approx((9, 9, 22, 22), abs=4e-5)


@pytest.mark.parametrize(
    "attributes",
    ['filter="url(#f)"', 'clip-path="url(#f)"', 'mask="url(#f)"', 'stroke-dasharray="2 2"'],
)
def test_unsupported_appearance_cannot_supply_guessed_bounds(attributes):
    with pytest.raises(ValueError, match="Unsupported SVG"):
        import_svg(MARGINS.replace('fill-rule="evenodd"', attributes))


def test_source_crossings_and_page_overflow_cannot_be_bypassed_by_visible_framing():
    for data in ("M10 10L60 60L10 60L60 10Z", "M-2 5H40V30H-2Z"):
        art = import_svg(
            f'<svg width="80mm" height="80mm" viewBox="0 0 80 80"><path d="{data}"/></svg>'
        )
        assert art.bounds_result.frame is None
        with pytest.raises(ValueError, match="Visible artwork bounds unavailable"):
            convert(art, placed())


def test_visible_cylinder_matches_analytical_positions_and_page_mode_keeps_margins():
    art = import_svg(MARGINS)
    p = placed()
    target = points(convert(art, p))
    # Independent inverse orthographic projection, not Project.mapper.
    assert min(v.real for v in target) == pytest.approx(100 * math.asin((3 - 15) / 100), abs=1e-10)
    assert max(v.real for v in target) == pytest.approx(100 * math.asin((3 + 15) / 100), abs=1e-10)
    assert (min(v.imag for v in target), max(v.imag for v in target)) == (25, 45)
    p.artwork_frame = "page"
    target = points(convert(art, p))
    assert (min(v.imag for v in target), max(v.imag for v in target)) == (27.5, 37.5)
    assert min(v.real for v in target) == pytest.approx(100 * math.asin(-6 / 100), abs=1e-10)


def test_synthetic_thirteen_by_eleven_reference_sizes_visible_not_blank_margins():
    art = import_svg(
        '<svg width="13in" height="11in" viewBox="0 0 330.2 279.4">'
        '<rect x="12.7" y="40" width="304.7996" height="200.575"/></svg>'
    )
    p = Project(object=ObjectSpec(diameter=500, height=240), artwork_frame="visible")
    frame = p.source_frame(art)
    p.placement.height = 4 * 25.4
    p.placement.width = p.placement.height * frame.width / frame.height
    p.placement.z = 30
    assert (art.width_mm / 25.4, art.height_mm / 25.4) == pytest.approx((13, 11))
    assert p.placement.width / 25.4 == pytest.approx(6.0785163, abs=1e-7)
    target = points(convert(art, p))
    assert min(v.imag for v in target) == 30
    assert max(v.imag for v in target) - min(v.imag for v in target) == pytest.approx(101.6)
    p.artwork_frame = "page"
    p.placement.width = p.placement.height * art.width_mm / art.height_mm
    target = points(convert(art, p))
    assert (max(v.imag for v in target) - min(v.imag for v in target)) / 25.4 == pytest.approx(
        2.87151, abs=1e-5
    )


@pytest.mark.parametrize("mode", ["cylinder", "frustum", "measured"])
def test_frame_persistence_units_preview_and_domain_safeguards(mode, tmp_path):
    art = import_svg(MARGINS)
    p = placed(mode=mode)
    p.source_svg = MARGINS
    path = tmp_path / "visible.wraplab"
    save_project(path, p)
    before = path.read_bytes()
    loaded = load_project(path)
    expected = export_svg(convert(art, p), p)
    assert export_svg(convert(art, loaded), loaded) == expected
    loaded.units = "in"
    result = convert(art, loaded)
    assert result.paths == convert(art, p).paths
    assert len(result.paths[0].contours) == 2
    assert [g.get("id") for g in ET.fromstring(expected).findall("{*}g")] == ["Artwork"]
    assert path.read_bytes() == before
    assert ET.fromstring(ideal_front_svg(art, p)).findall(".//{*}path")
    assert convert(art, p, preview=True).paths[0].contours[0].points[0] == pytest.approx(
        result.paths[0].contours[0].points[0]
    )
    p.placement.z = 195
    with pytest.raises(ValueError, match="outside"):
        convert(art, p)


def test_legacy_open_does_not_rewrite_and_requires_explicit_frame_for_version_two(tmp_path):
    cases = json.loads((Path(__file__).parent / "fixtures/legacy-page-projects.json").read_text())[
        "cases"
    ]
    for case in cases:
        path = tmp_path / (case["name"] + ".wraplab")
        path.write_text(json.dumps(case["project"]))
        before = path.read_bytes()
        p = load_project(path)
        assert p.artwork_frame == "page" and p.schema_version == 2
        root = ET.fromstring(export_svg(convert(import_svg(p.source_svg), p), p))
        assert [v.attrib for v in root.findall(".//{*}path")] == case["expected_paths"]
        assert path.read_bytes() == before
    bad = deepcopy(p.to_dict())
    del bad["artwork_frame"]
    with pytest.raises(ValueError, match="explicit artwork frame"):
        Project.from_dict(bad)
    bad = p.to_dict()
    bad["artwork_frame"] = "guess"
    with pytest.raises(ValueError, match="Unsupported project"):
        Project.from_dict(bad)


@pytest.mark.parametrize("top,bottom", [(180, 220), (220, 180), (200, 200.000000001)])
def test_visible_frustum_corners_match_independent_exact_development(top, bottom):
    p = placed(mode="frustum")
    p.object.top_diameter, p.object.bottom_diameter = top, bottom
    result = convert(import_svg(MARGINS), p)
    h = p.object.height
    dr = (bottom - top) / 2
    slant = math.hypot(h, dr)
    k = dr / slant
    for expected_x, z in [(-12, 25), (18, 25), (18, 45), (-12, 45)]:
        radius = top / 2 + dr * z / h
        theta = math.asin(expected_x / radius)
        # Stable independent formulas for each corner, with axial direction down.
        x = radius * math.sin(k * theta) / k
        y = z * slant / h - 2 * radius * math.sin(k * theta / 2) ** 2 / k
        # Corners are guaranteed vertices; subdivision counts are intentionally irrelevant.
        assert min(abs(v - complex(x, y)) for v in result.paths[0].contours[0].points) < 1e-10


def test_curved_stroke_outline_remains_inside_full_height_selected_frame():
    art = import_svg(
        '<svg width="40mm" height="40mm" viewBox="0 0 40 40">'
        '<circle cx="20" cy="20" r="10" fill="none" stroke="black" '
        'stroke-width="2"/></svg>'
    )
    h = 8.5 * 25.4
    p = Project(object=ObjectSpec(diameter=1000, height=h), artwork_frame="visible")
    p.placement.width = p.placement.height = h
    p.placement.z = 0
    result = convert(art, p)
    assert all(0 <= v.imag <= h for v in points(result))
    p.object.height = p.object.diameter = 1e6
    p.placement.width = p.placement.height = 1e5
    with pytest.raises(ValueError, match="bounds are too approximate"):
        convert(art, p)


def test_target_frame_and_flat_dimensions_remain_distinct_in_production_output():
    p = placed(mode="measured")
    result = convert(import_svg(MARGINS), p)
    root = ET.fromstring(export_svg(result, p))
    metadata = json.loads(root.find("{*}metadata").text)
    actual = points(result)
    flat_height = max(v.imag for v in actual) - min(v.imag for v in actual)
    assert metadata["artwork_frame"] == "visible"
    assert metadata["target_frame_dimensions_mm"] == [30, 20]
    assert metadata["flat_artwork_dimensions_mm"][1] == flat_height
    assert abs(flat_height - 20) > 0.01
    assert float(root.get("height")[:-2]) == pytest.approx(flat_height, abs=1e-6)
