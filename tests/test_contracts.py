from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from wraplab.domain import ObjectSpec, Project
from wraplab.svg import convert, export_svg, import_svg
from wraplab.svg.model import Contour, Conversion, VectorPath


@pytest.mark.parametrize(
    "units,size,physical", [("mm", 100, 100), ("in", 1, 25.4), ("mm", 25.4, 25.4)]
)
def test_corel_true_size_reference_squares(units, size, physical):
    art = import_svg(
        f'<svg width="{size}{units}" height="{size}{units}" viewBox="0 0 1 1"><rect width="1" height="1"/></svg>'
    )
    project = Project(
        object=ObjectSpec(diameter=100, height=200), physical_model="surface-template"
    )
    project.placement.width = project.placement.height = physical
    project.center_artwork()
    root = ET.fromstring(export_svg(convert(art, project), project))
    assert root.get("width") == f"{physical:g}mm"
    assert root.get("height") == f"{physical:g}mm"


def test_mirrored_nested_affine_and_immutable_original():
    text = '<svg width="30mm" height="20mm" viewBox="0 0 30 20"><g transform="translate(30 0)"><g transform="scale(-1 1)"><path d="M2 2L10 2L2 15Z"/></g></g></svg>'
    art = import_svg(text)
    project = Project(physical_model="surface-template")
    project.placement.width, project.placement.height = 30, 20
    project.center_artwork()
    source = art.shapes[0].subpaths[0].segments[0].start
    result = convert(art, project)
    xs = [p.real for p in result.paths[0].contours[0].points]
    assert min(xs) == pytest.approx(5) and max(xs) == pytest.approx(13)
    assert art.source == text and art.shapes[0].subpaths[0].segments[0].start == source


def test_serialization_cannot_silently_close_thin_counter():
    outer = [0j, 10 + 0j, 10 + 10j, 10j]
    hole = [0.0000002 + 2j, 3 + 2j, 3 + 8j, 0.0000002 + 8j]
    conversion = Conversion(
        [VectorPath([Contour(outer), Contour(hole)], fill_rule="evenodd")], [], 0.01
    )
    with pytest.raises(ValueError, match="Serialized output"):
        export_svg(conversion, Project())


def test_deep_xml_and_foreign_rendering_namespaces_rejected():
    for inner in [
        "<g>" * 65 + '<rect width="1" height="1"/>' + "</g>" * 65,
        '<bad:rect xmlns:bad="urn:not-svg" width="1" height="1"/>',
    ]:
        with pytest.raises(ValueError):
            import_svg('<svg width="10mm" height="10mm">' + inner + "</svg>")


def test_guides_do_not_leak_into_primary_production_artwork():
    art = import_svg((Path(__file__).parent / "fixtures" / "lettering.svg").read_text())
    project = Project()
    project.placement.width, project.placement.height = 50, 25 * 50 / 60
    project.center_artwork()
    result = convert(art, project)
    production = ET.fromstring(export_svg(result, project, "artwork"))
    assert [g.get("id") for g in production.findall("{*}g")] == ["Artwork"]
    assert not production.findall(".//*[@stroke-width]")


def test_path_converted_hebrew_like_geometry_keeps_source_order():
    text = (Path(__file__).parent / "fixtures" / "hebrew-paths.svg").read_text()
    art = import_svg(text)
    project = Project()
    project.placement.width, project.placement.height = 40, 16
    project.center_artwork()
    result = convert(art, project)
    centers = [
        sum(p.real for p in path.contours[0].points) / len(path.contours[0].points)
        for path in result.paths
    ]
    assert len(result.paths) == 5
    assert min(centers[:3]) > centers[3] > centers[4]
    assert art.source == text
    export_svg(result, project)


def test_two_counters_and_shared_endpoints_preserved():
    text = (Path(__file__).parent / "fixtures" / "eight.svg").read_text()
    art = import_svg(text)
    project = Project()
    project.placement.width, project.placement.height = 20, 30
    project.center_artwork()
    result = convert(art, project)
    assert len(result.paths[0].contours) == 3
    export_svg(result, project)
    art = import_svg(
        '<svg width="20mm" height="30mm" viewBox="0 0 20 30"><path d="M10 15L2 2L18 2Z"/><path d="M10 15L18 28L2 28Z"/></svg>'
    )
    result = convert(art, project)
    assert result.paths[0].contours[0].points[0] == result.paths[1].contours[0].points[0]


def test_script_in_unused_definitions_is_rejected():
    with pytest.raises(ValueError, match="scripted"):
        import_svg(
            '<svg width="10mm" height="10mm"><defs><script/></defs><rect width="5" height="5"/></svg>'
        )
