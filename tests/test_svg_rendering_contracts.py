"""Synthetic regressions for the October 2026 independent SVG findings."""

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

from wraplab.domain import ObjectSpec, Project
from wraplab.svg import convert, export_svg, import_svg
from wraplab.svg.exporter import ideal_front_svg
from wraplab.svg.transform import convert_artwork


def svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" '
            'viewBox="0 0 100 100">' + body + '</svg>')


SQUARE = '<rect x="10" y="10" width="10" height="10"/>'


@pytest.mark.parametrize('attribute', ['requiredExtensions', 'requiredFeatures', 'systemLanguage'])
@pytest.mark.parametrize('value', ['urn:wraplab:unsupported', ''])
@pytest.mark.parametrize('context', ['shape', 'group', 'root', 'hidden', 'defs'])
def test_conditional_processing_is_rejected_before_visibility_or_defs_skips(
    attribute, value, context
):
    condition = f'{attribute}="{value}"'
    conditional = f'<rect x="40" y="40" width="50" height="50" {condition}/>'
    if context == 'group':
        conditional = f'<g><g {condition}>{SQUARE}</g></g>'
    elif context == 'hidden':
        conditional = f'<g display="none">{conditional}</g>'
    elif context == 'defs':
        conditional = f'<defs><g id="unused">{conditional}</g></defs>'
    source = svg(SQUARE + conditional)
    if context == 'root':
        source = svg(SQUARE).replace('<svg ', f'<svg {condition} ', 1)
    with pytest.raises(ValueError, match=f'{attribute}.*plain.*SVG'):
        import_svg(source)


def test_plain_visible_frame_and_export_keep_requested_size():
    art = import_svg(svg(SQUARE + '<g display="none"><rect width="90" height="90"/></g>'))
    f = art.visible_frame
    assert (f.left, f.top, f.width, f.height) == pytest.approx((10, 10, 10, 10))
    project = Project(object=ObjectSpec(diameter=300, height=100), artwork_frame='visible')
    project.placement.width = project.placement.height = 10
    project.placement.z = 20
    root = ET.fromstring(export_svg(convert(art, project), project))
    assert root.get('height') == '10mm'
    assert len(root.findall('.//{*}path')) == 1


@pytest.mark.parametrize('position', ['before', 'inside', 'after', 'metadata'])
@pytest.mark.parametrize('href', ['appearance.css', 'https://invalid.example/style.css'])
def test_stylesheet_processing_instructions_are_rejected(position, href):
    pi = f'<?xml-stylesheet type="text/css" href="{href}"?>'
    source = svg(SQUARE)
    if position == 'before':
        source = pi + source
    elif position == 'after':
        source += pi
    elif position == 'inside':
        source = svg(pi + SQUARE)
    else:
        source = svg('<metadata>' + pi + '</metadata>' + SQUARE)
    with pytest.raises(ValueError, match='stylesheet.*self-contained'):
        import_svg(source)


def test_stylesheet_like_comments_metadata_and_ordinary_pi_are_safe():
    source = (
        '<?xml version="1.0"?><?shop-note sheet="one"?>' + svg(
            '<!-- <?xml-stylesheet href="not-a-resource.css"?> -->'
            '<metadata><![CDATA[<?xml-stylesheet href="literal.css"?>]]></metadata>'
            '<desc>requiredExtensions and systemLanguage are explanatory text.</desc>' + SQUARE
        )
    )
    assert len(import_svg(source).shapes) == 1


def opacity_fixture(paints='fill="red" stroke="black" stroke-width="20"', opacity='.5'):
    return svg(f'<rect x="20" y="20" width="60" height="60" {paints} opacity="{opacity}"/>')


def project():
    p = Project(object=ObjectSpec(diameter=300, height=150, top_diameter=280,
                                 bottom_diameter=320,
                                 points=[(0, 280), (75, 300), (150, 340)]))
    p.placement.width = p.placement.height = 100
    p.placement.z = 20
    return p


def test_element_opacity_applies_once_after_fill_and_stroke_painting():
    source = opacity_fixture()  # Expected overlap: black at alpha .5, not red/black at .75.
    result = convert_artwork(import_svg(source), lambda p: p, .001)
    root = ET.fromstring(export_svg(result, project(), 'original'))
    element_group = root.find('.//{*}g[@opacity="0.5"]')
    assert element_group is not None
    paints = element_group.findall('{*}path')
    assert len(paints) == 2
    assert all(p.get('opacity', '1') == '1' for p in paints)
    assert [p.get('fill') for p in paints] == ['red', 'black']


def test_paint_opacity_is_kept_distinct_and_neighbor_elements_are_not_grouped():
    source = svg(
        '<rect x="20" y="20" width="60" height="60" fill="red" fill-opacity=".4" '
        'stroke="black" stroke-width="10" stroke-opacity=".6" opacity=".5"/>'
        '<rect x="5" y="5" width="5" height="5" fill="blue" opacity=".3"/>'
    )
    result = convert_artwork(import_svg(source), lambda p: p, .001)
    root = ET.fromstring(export_svg(result, project(), 'original'))
    group = root.find('.//{*}g[@opacity="0.5"]')
    assert group is not None
    assert [p.get('opacity') for p in group.findall('{*}path')] == ['0.4', '0.6']
    blue = root.find('.//{*}path[@fill="blue"]')
    assert blue.get('opacity') == '0.3'
    assert blue not in list(group)


def test_adjacent_half_opacity_elements_have_separate_compositing_groups():
    body = ('<rect x="20" y="20" width="40" height="40" fill="red" '
            'stroke="black" stroke-width="4" opacity=".5"/>')
    source = svg(body + body.replace('x="20"', 'x="40"'))
    result = convert_artwork(import_svg(source), lambda p: p, .001)
    root = ET.fromstring(export_svg(result, project(), 'original'))
    groups = root.findall('.//{*}g[@opacity="0.5"]')
    assert len(groups) == 2
    assert [len(g.findall('{*}path')) for g in groups] == [2, 2]
    assert result.paths[0].opacity_group != result.paths[2].opacity_group


@pytest.mark.parametrize('mode', ['cylinder', 'frustum', 'measured'])
def test_compositing_does_not_change_compensated_contours_or_dimensions(mode):
    p = project()
    p.object.mode = mode
    art = import_svg(opacity_fixture())
    opaque = import_svg(opacity_fixture(opacity='1'))
    result, expected = convert(art, p), convert(opaque, p)
    assert len(result.paths) == len(expected.paths) == 2
    for a, b in zip(result.paths, expected.paths, strict=True):
        assert a.contours == b.contours
        assert a.fill_rule == b.fill_rule
    actual_xml = ET.fromstring(export_svg(result, p))
    expected_xml = ET.fromstring(export_svg(expected, p))
    assert actual_xml.get('viewBox') == expected_xml.get('viewBox')
    assert [e.get('d') for e in actual_xml.findall('.//{*}path')] == [
        e.get('d') for e in expected_xml.findall('.//{*}path')
    ]


def test_ideal_front_preserves_element_compositing():
    art = import_svg(opacity_fixture())
    root = ET.fromstring(ideal_front_svg(art, project()))
    group = root.find('.//{*}g[@opacity="0.5"]')
    assert group is not None and len(group.findall('{*}path')) == 2


@pytest.mark.parametrize('paints', [
    'fill="red"',
    'fill="none" stroke="black" stroke-width="20"',
    'fill="red" stroke="black" stroke-width="20" stroke-opacity="0"',
])
def test_single_paint_half_opacity_keeps_existing_path_semantics(paints):
    result = convert_artwork(import_svg(opacity_fixture(paints)), lambda p: p, .001)
    root = ET.fromstring(export_svg(result, project(), 'original'))
    assert len(result.paths) == 1
    assert root.find('.//{*}path').get('opacity') == '0.5'
    assert root.find('.//{*}g[@opacity]') is None


@pytest.mark.parametrize('opacity', ['.5', '1'])
@pytest.mark.parametrize('paints', [
    'fill="red" stroke="black" stroke-width="20"',
    'fill="red"',
    'fill="none" stroke="black" stroke-width="20"',
    'fill="red" fill-opacity=".4" stroke="black" stroke-width="20" stroke-opacity=".6"',
])
def test_independent_renderer_matches_source_paint_samples(tmp_path, opacity, paints):
    inkscape = shutil.which('inkscape')
    if inkscape is None:
        pytest.skip('Independent rendering requires optional Inkscape CLI.')
    # PNG reading uses Qt, already a runtime dependency; rendering uses independent Inkscape.
    from PySide6.QtGui import QImage

    source = opacity_fixture(paints, opacity)
    art = import_svg(source)
    result = convert_artwork(art, lambda p: p, .001)
    p = project()
    output = export_svg(result, p, 'original')
    points = [q for path in result.paths for c in path.contours for q in c.points]
    left, top = min(q.real for q in points), min(q.imag for q in points)
    images = []
    for name, text in [('source', source), ('export', output)]:
        svg_path, png_path = tmp_path / f'{name}.svg', tmp_path / f'{name}.png'
        svg_path.write_text(text)
        env = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path / 'config'),
                   XDG_CACHE_HOME=str(tmp_path / 'cache'))
        subprocess.run([inkscape, str(svg_path), '--export-dpi=254',
                        f'--export-filename={png_path}'], env=env,
                       capture_output=True, check=True, timeout=30)
        image = QImage(str(png_path))
        assert not image.isNull()
        images.append(image)
    # Interior fill, fill/stroke overlap, stroke-only band. Avoid antialias boundaries.
    for x, y in [(50, 50), (22, 50), (15, 50)]:
        a = images[0].pixelColor(round(x * 10), round(y * 10)).getRgb()
        px, py = round((x - left) * 10), round((y - top) * 10)
        b = (images[1].pixelColor(px, py).getRgb()
             if 0 <= px < images[1].width() and 0 <= py < images[1].height()
             else (0, 0, 0, 0))
        if a[3] == 0:
            assert b[3] == 0  # RGB is immaterial where the paint is fully transparent.
        else:
            assert a == b
