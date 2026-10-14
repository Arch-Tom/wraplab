from pathlib import Path

import pytest

from wraplab.domain import Project
from wraplab.svg import convert, export_svg, import_svg

FIXTURE = Path(__file__).parent / "fixtures/corel-like-transparent.svg"


def test_transparent_root_background_preserves_compound_geometry_and_physical_output():
    source = FIXTURE.read_text(encoding="utf-8")
    normal = source.replace("background-color:transparent;", "")
    accepted, original = import_svg(source), import_svg(normal)
    assert accepted.width_mm == original.width_mm == 40
    assert accepted.height_mm == original.height_mm == 20
    assert len(accepted.shapes[0].subpaths) == 2
    assert accepted.shapes[0].style["fill-rule"] == "evenodd"
    assert accepted.shapes[0].style == original.shapes[0].style
    assert accepted.warnings == ("Ignored a transparent page background; artwork fills and strokes are unchanged.",)
    project = Project()
    project.placement.width, project.placement.height = 30, 15
    project.center_artwork()
    results = [convert(artwork, project) for artwork in (accepted, original)]
    assert results[0].paths == results[1].paths
    # Exported path data, dimensions and counters stay the same; diagnostic metadata may differ.
    import xml.etree.ElementTree as ET
    roots = [ET.fromstring(export_svg(result, project, "artwork", "compound.svg")) for result in results]
    assert roots[0].attrib == roots[1].attrib
    assert [p.attrib for p in roots[0].findall(".//{*}path")] == [
        p.attrib for p in roots[1].findall(".//{*}path")
    ]


def test_malformed_xml_reports_location_without_claiming_blocked_entities():
    with pytest.raises(ValueError) as caught:
        import_svg('<svg width="1mm" height="1mm">\n<path></svg>')
    message = str(caught.value)
    assert "malformed XML at line 2, column" in message
    assert "Export it again" in message
    assert "unsafe" not in message and "DTD" not in message


@pytest.mark.parametrize("declaration", [
    '<!DOCTYPE svg [<!ENTITY payload "expand-me">]>',
    '<!DOCTYPE svg [<!ENTITY payload SYSTEM "file:///C:/private-test-marker.txt">]>',
])
def test_entity_declarations_stay_blocked_without_exposing_resource_or_value(declaration):
    with pytest.raises(ValueError) as caught:
        import_svg(declaration + '<svg width="1mm" height="1mm">&payload;</svg>')
    assert "XML entity declarations" in str(caught.value)
    assert "private-test-marker" not in str(caught.value)
    assert "expand-me" not in str(caught.value)


@pytest.mark.parametrize("style", [
    "background-color:white", "background-color:#ffffff", "background-color:url(secret.svg)",
    "filter:none", "clip-path:url(#clip)", "stroke-dasharray:1 2", "unknown-property:value",
])
def test_unknown_or_potentially_visible_style_is_not_silently_stripped(style):
    source = FIXTURE.read_text().replace("background-color:transparent", style)
    with pytest.raises(ValueError, match="Unsupported SVG style"):
        import_svg(source)


def test_transparent_background_is_not_accepted_on_a_rendered_shape():
    source = '<svg width="2mm" height="2mm"><path style="background-color:transparent" d="M0 0H1V1H0Z"/></svg>'
    with pytest.raises(ValueError, match="background-color.*<path>"):
        import_svg(source)


@pytest.mark.parametrize("element,advice", [
    ("<text>x</text>", "Convert the text to curves"),
    ('<image href="data:image/png;base64,AA=="/>', "Replace it with vector paths"),
    ("<style>path {fill:red}</style>", "inline fill/stroke"),
])
def test_unsupported_content_retains_rejection_and_specific_guidance(element, advice):
    with pytest.raises(ValueError, match=advice):
        import_svg('<svg width="2mm" height="2mm">' + element + '</svg>')
