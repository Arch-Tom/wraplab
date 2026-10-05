import hashlib
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from shapely.geometry import LineString, Point

from wraplab.domain import ObjectSpec, Project
from wraplab.svg import convert, export_svg, import_svg
from wraplab.svg.adaptive import flatten
from wraplab.svg.exporter import write_export
from wraplab.svg.importer import parse_transform

FIXTURES = Path(__file__).parent / "fixtures"


def svg(content, width=50, height=30):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">{content}</svg>'


def project_for(artwork, mode="cylinder"):
    project = Project(object=ObjectSpec(mode=mode), physical_model="surface-template")
    project.placement.width = artwork.width_mm
    project.placement.height = artwork.height_mm
    project.center_artwork()
    return project


@pytest.mark.parametrize("fixture", ["lettering.svg", "calibration.svg", "primitives.svg"])
@pytest.mark.parametrize("mode", ["cylinder", "frustum", "measured"])
def test_real_fixture_conversion_physical_svg_topology(fixture, mode):
    art = import_svg((FIXTURES / fixture).read_text())
    project = project_for(art, mode)
    result = convert(art, project)
    assert 20 < result.node_count < 20_000
    text = export_svg(result, project)
    root = ET.fromstring(text)
    assert root.get("width").endswith("mm")
    assert root.get("height").endswith("mm")
    assert not root.findall(".//*[@transform]")
    assert not root.findall(".//*[@stroke-width]")
    for path in root.findall(".//{*}path"):
        assert path.get("d").endswith("Z")
    assert (
        hashlib.sha256(text.encode()).hexdigest()
        == hashlib.sha256(export_svg(convert(art, project), project).encode()).hexdigest()
    )
    if fixture == "lettering.svg":
        assert [len(p.contours) for p in result.paths] == [2, 2, 3, 2]
        assert all(p.fill_rule == "evenodd" for p in result.paths)


def test_physical_rectangle_output_is_true_size():
    art = import_svg(svg('<rect width="50" height="30"/>'))
    project = project_for(art)
    root = ET.fromstring(export_svg(convert(art, project), project))
    assert root.get("width") == "50mm"
    assert root.get("height") == "30mm"
    project.units = "in"
    assert ET.fromstring(export_svg(convert(art, project), project)).get("width") == "50mm"


def test_affine_order_viewbox_offsets_and_aspect_ratio():
    assert parse_transform("translate(10 20) scale(2) rotate(90)")(1 + 2j) == pytest.approx(6 + 22j)
    art = import_svg(
        '<svg width="2in" height="1in" viewBox="10 20 100 50"><rect x="10" y="20" width="100" height="50"/></svg>'
    )
    shape = art.shapes[0]
    assert shape.transform(10 + 20j) == pytest.approx(0j)
    assert shape.transform(110 + 70j) == pytest.approx(50.8 + 25.4j)


def test_relative_moves_preserve_subpaths():
    art = import_svg(svg('<path fill-rule="evenodd" d="M2 2 h20 v20 h-20 z m5 5 h10 v10 h-10 z"/>'))
    assert art.shapes[0].subpaths[1].segments[0].start == 7 + 7j
    assert len(convert(art, project_for(art)).paths[0].contours) == 2


@pytest.mark.parametrize(
    "content",
    [
        "<text>x</text>",
        '<image href="secret.png"/>',
        '<use href="#a"/>',
        '<rect width="2" height="2" fill="url(#paint)"/>',
        "<style>path { fill:red }</style>",
        '<path d="M0 0 L1 1" style="filter:url(#a)"/>',
        '<rect width="2" height="2" clip-path="url(#clip)"/>',
        "<script/>",
        '<path d="M0 0 L1 1" stroke-dasharray="1 2"/>',
        '<g opacity=".5"><rect width="3" height="3"/></g>',
        '<path d="M0 0 Q"/>',
    ],
)
def test_unsupported_svg_rejected(content):
    with pytest.raises(ValueError):
        import_svg(svg(content))


def test_entities_external_resources_rejected():
    with pytest.raises(ValueError):
        import_svg(
            '<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg width="1mm" height="1mm">&x;</svg>'
        )


def test_self_intersections_and_offpage_artwork_block_export():
    for content in [
        '<path d="M2 2 L20 20 L20 2 L2 20 Z"/>',
        '<rect x="-1" width="10" height="10"/>',
    ]:
        art = import_svg(svg(content))
        with pytest.raises(ValueError):
            convert(art, project_for(art))


def test_production_tolerance_against_dense_independent_curve_samples():
    art = import_svg(svg('<path d="M2 20 C3 1 40 1 45 20 L45 25 L2 25 Z"/>'))
    project = project_for(art, "frustum")
    project.object.top_diameter = 20
    project.object.bottom_diameter = 140
    project.object.height = 50
    project.center_artwork()
    mapping = project.mapper(art.width_mm, art.height_mm)
    shape = art.shapes[0]
    curve = shape.subpaths[0].segments[0]
    points = flatten(lambda t: mapping(shape.transform(curve.point(t))), 0.01)
    polyline = LineString([(p.real, p.imag) for p in points])
    error = max(
        polyline.distance(Point(p.real, p.imag))
        for p in [mapping(shape.transform(curve.point(t))) for t in np.linspace(0, 1, 10001)]
    )
    assert error <= 0.01
    assert len(points) < 1000


def test_closed_stroke_preserves_hole_and_expands_before_nonlinear_mapping():
    art = import_svg(
        svg('<circle cx="20" cy="15" r="8" fill="none" stroke="black" stroke-width="1"/>')
    )
    result = convert(art, project_for(art, "frustum"))
    assert len(result.paths) == 1
    assert len(result.paths[0].contours) == 2
    assert any("outlines" in w for w in result.warnings)


def test_guides_separate_and_source_not_overwritten(tmp_path):
    art = import_svg(svg('<rect width="50" height="30"/>'))
    project = project_for(art)
    text = export_svg(convert(art, project), project, "guides")
    root = ET.fromstring(text)
    assert {g.get("id") for g in root.findall("{*}g")} == {"Artwork", "Guides"}
    source = tmp_path / "source.svg"
    source.write_text(art.source)
    with pytest.raises(ValueError):
        write_export(source, text, source)
    assert source.read_text() == art.source


def test_adaptive_detects_collinear_backtracking_and_hard_budget():
    points = flatten(lambda t: complex(math.sin(2 * math.pi * t), 0), 0.001)
    assert len(points) > 2
    with pytest.raises(ValueError):
        flatten(lambda t: complex(t, t * t), 1e-12, max_depth=2)
