import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from wraplab.domain import Project
from wraplab.svg import convert, export_svg, import_svg
from wraplab.svg.importer import class_rules
from wraplab.svg.transform import closure_samples, validate_contours


def svg(body, style='', attributes=''):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" '
            f'viewBox="0 0 40 20" style="{style}" {attributes}>{body}</svg>')


COMPOUND = 'M2 2H18V18H2Z M6 6V14H14V6Z'


def test_corel_class_cascade_preserves_curves_counters_and_mm():
    hinted = svg('<defs><style type="text/css"><![CDATA['
                 '.fil0 {fill:black;fill-rule:nonzero}]]></style></defs>'
                 f'<path class="fil0" d="{COMPOUND}"/>',
                 'shape-rendering:geometricPrecision;text-rendering:geometricPrecision;'
                 'image-rendering:optimizeQuality;fill-rule:evenodd;clip-rule:evenodd')
    direct = svg(f'<path fill="black" fill-rule="nonzero" d="{COMPOUND}"/>')
    styled, plain = import_svg(hinted), import_svg(direct)
    assert styled.source == hinted
    assert [s.style for s in styled.shapes] == [s.style for s in plain.shapes]
    assert styled.shapes[0].subpaths == plain.shapes[0].subpaths
    assert len(styled.shapes[0].subpaths) == 2
    project = Project()
    project.placement.width, project.placement.height = 30, 15
    project.center_artwork()
    a, b = [convert(art, project) for art in (styled, plain)]
    assert a.paths == b.paths
    roots = [ET.fromstring(export_svg(result, project)) for result in (a, b)]
    assert roots[0].attrib == roots[1].attrib
    assert [p.attrib for p in roots[0].findall('.//{*}path')] == [
        p.attrib for p in roots[1].findall('.//{*}path')]
    assert a.paths[0].fill_rule == 'nonzero'


@pytest.mark.parametrize('path_attributes,expected', [
    ('fill-rule="evenodd"', 'nonzero'),
    ('fill-rule="nonzero" style="fill-rule:evenodd"', 'evenodd'),
])
def test_class_overrides_presentation_attribute_inline_overrides_class(path_attributes, expected):
    art = import_svg(svg('<style>.paint{fill-rule:nonzero;fill:black}</style>'
                         f'<path class="paint" {path_attributes} d="{COMPOUND}"/>',
                         'fill-rule:evenodd'))
    assert art.shapes[0].style['fill-rule'] == expected


def test_inherit_uses_parent_rule_not_overridden_local_presentation_rule():
    art = import_svg(svg('<style>.paint{fill-rule:inherit}</style>'
                         f'<path class="paint" fill-rule="nonzero" d="{COMPOUND}"/>',
                         'fill-rule:evenodd'))
    assert art.shapes[0].style['fill-rule'] == 'evenodd'


@pytest.mark.parametrize('classes', ['first second', 'second first'])
def test_equal_specificity_uses_stylesheet_order_not_class_attribute_order(classes):
    art = import_svg(svg('<style>.second{fill:red}.first{fill:blue}</style>'
                         f'<path class="{classes}" d="{COMPOUND}"/>'))
    assert art.shapes[0].style['fill'] == 'blue'


def test_group_class_inheritance_and_multiple_stylesheets():
    art = import_svg(svg('<defs><style>.a,.b{fill:red;fill-rule:evenodd}</style></defs>'
                         '<style>.a{fill:blue}</style>'
                         f'<g class="a"><path d="{COMPOUND}"/></g>'))
    assert art.shapes[0].style['fill'] == 'blue'
    assert art.shapes[0].style['fill-rule'] == 'evenodd'


@pytest.mark.parametrize('paint_attributes,css', [
    ('color="currentColor" fill="currentColor" stroke="currentColor"', ''),
    ('style="color:currentColor;fill:currentColor;stroke:currentColor"', ''),
    ('class="paint"', '.paint{color:currentColor;fill:currentColor;stroke:currentColor}'),
])
def test_currentcolor_color_inherits_parent_before_resolving_fill_and_stroke(paint_attributes, css):
    art = import_svg(svg(f'<style>{css}</style><g color="red">'
                         f'<path {paint_attributes} d="{COMPOUND}"/></g>', 'color:blue'))
    assert {key: art.shapes[0].style[key] for key in ('color', 'fill', 'stroke')} == {
        'color': 'red', 'fill': 'red', 'stroke': 'red'}


def test_currentcolor_root_uses_initial_color_and_child_override_is_resolved_first():
    art = import_svg(svg('<style>.paint{color:blue;fill:currentColor}</style>'
                         f'<g color="red"><path class="paint" d="{COMPOUND}"/></g>',
                         'color:currentColor'))
    assert art.shapes[0].style['color'] == 'blue'
    assert art.shapes[0].style['fill'] == 'blue'
    initial = import_svg(svg(f'<path fill="currentColor" d="{COMPOUND}"/>',
                             'color:currentColor'))
    assert initial.shapes[0].style['color'] == '#000000'
    assert initial.shapes[0].style['fill'] == '#000000'


def parse_stylesheet(text):
    root = ET.Element('svg')
    ET.SubElement(root, 'style').text = text
    return class_rules(root)


def test_css_comments_whitespace_and_empty_bodies_preserve_cascade():
    rules = parse_stylesheet('/* { ignored } */ .a/* selector */,.b {fill:/* paint */red}'
                             '\n .a{} /* between */ .a{fill:blue} /* tail */')
    assert rules == [(frozenset({'a', 'b'}), {'fill': 'red'}),
                     (frozenset({'a'}), {}), (frozenset({'a'}), {'fill': 'blue'})]


@pytest.mark.parametrize('text', [
    '.a{fill:red} trailing', '.a{fill:red}}', '{fill:red}', '.a{{fill:red}}',
    '.a{fill:red', '/* no end', '/*/*/*', '.a{fill:red} /* no end',
])
def test_flat_css_parser_rejects_malformed_blocks_and_unterminated_comments(text):
    with pytest.raises(ValueError, match='Unsupported SVG element <style>'):
        parse_stylesheet(text)


def test_css_size_limit_is_checked_before_comment_removal():
    valid = '.a{fill:red}'
    assert parse_stylesheet(valid + ' ' * (1_000_000 - len(valid))) == [
        (frozenset({'a'}), {'fill': 'red'})]
    with pytest.raises(ValueError, match='size limit'):
        parse_stylesheet('/*' + 'x' * 999_998 + '*/')


def test_css_rule_limit_is_aggregate_across_stylesheets():
    assert len(parse_stylesheet('.a{}' * 1024)) == 1024
    root = ET.Element('svg')
    ET.SubElement(root, 'style').text = '.a{}' * 1024
    ET.SubElement(root, 'style').text = '.b{}'
    with pytest.raises(ValueError, match='rule limit'):
        class_rules(root)


@pytest.mark.parametrize('kind', ['brace-free', 'unterminated-comments'])
def test_maximum_malformed_stylesheet_rejects_with_bounded_runtime(kind):
    # A process timeout bounds the test itself if either former quadratic regex returns.
    code = '''
import json, sys, time
import xml.etree.ElementTree as ET
sys.path.insert(0, sys.argv[1] + '/src')
from wraplab.svg.importer import class_rules
root = ET.Element('svg')
ET.SubElement(root, 'style').text = ('x' * 1_000_000 if sys.argv[2] == 'brace-free'
                                    else '/*x' * 333_333 + 'x')
start = time.perf_counter()
try:
    class_rules(root)
except ValueError:
    print(json.dumps({'rejected': True, 'seconds': time.perf_counter() - start}))
else:
    raise AssertionError('Malformed stylesheet was accepted')
'''
    result = subprocess.run([sys.executable, '-I', '-c', code,
                             str(Path(__file__).resolve().parents[1]), kind],
                            capture_output=True, text=True, timeout=10, check=True)
    import json
    evidence = json.loads(result.stdout)
    assert evidence['rejected']
    assert evidence['seconds'] < 2


@pytest.mark.parametrize('style', [
    '.a{fill:url(https://example.invalid/a)}', '.a{fill:url(#paint)}',
    '@import "https://example.invalid/style.css";', '@media print{.a{fill:red}}',
    '.a:hover{fill:red}', '#id{fill:red}', 'path{fill:red}', '.a .b{fill:red}',
    '.a.b{fill:red}', '.a{fill:red!important}', '.a{filter:none}',
    '.a{clip-path:url(#clip)}', '.a{opacity:.5}', '.a{display:none}',
    '.a{fill}', '.a{fill:}', '.a{unknown:black}', '.a{fill:var(--paint)}',
    '.a{fill:blue', '.a{fill:bl\\75 e}', '.a{stroke-width:-1}',
])
def test_unsupported_css_is_rejected_even_when_unused(style):
    with pytest.raises(ValueError):
        import_svg(svg(f'<defs><style>{style}</style></defs><path d="{COMPOUND}"/>'))


@pytest.mark.parametrize('content', [
    '<style href="https://example.invalid/css">.a{fill:black}</style>',
    '<style media="print">.a{fill:black}</style>',
    '<defs><style>.a{fill:black}</style><script/></defs>',
    '<style>.a{fill:black}</style><path class="a" onclick="x()" d="M1 1H2V2Z"/>',
    '<style>.a{fill:black}</style><path class="a" clip-path="url(#clip)" d="M1 1H2V2Z"/>',
    '<style>.a{fill:black}</style><image class="a" href="secret.png"/>',
    '<style>.a{fill:black}</style><use class="a" href="#shape"/>',
    '<style>.a{fill:black}</style><text class="a">live</text>',
])
def test_class_support_does_not_enable_unsafe_or_unsupported_svg(content):
    with pytest.raises(ValueError):
        import_svg(svg(content))


@pytest.mark.parametrize('key,value', [
    ('shape-rendering', 'madeUp'), ('text-rendering', 'url(#font)'),
    ('image-rendering', 'url(https://example.invalid/a)'), ('clip-rule', 'invalid'),
])
@pytest.mark.parametrize('presentation', [False, True])
def test_hint_and_clip_rule_values_are_validated(key, value, presentation):
    with pytest.raises(ValueError):
        import_svg(svg(f'<path d="{COMPOUND}"/>',
                       '' if presentation else f'{key}:{value}',
                       f'{key}="{value}"' if presentation else ''))


def test_relative_decimal_closure_converts_without_false_intersection():
    art = import_svg(svg('<path d="M10.1 10.2 l4.3 0 -2.1 -3.2 -2.2 3.2 z"/>'))
    project = Project()
    project.placement.width, project.placement.height = 30, 15
    project.center_artwork()
    for preview in (True, False):
        result = convert(art, project, preview=preview)
        assert len(result.paths) == 1
        assert len(result.paths[0].contours) == 1
        ET.fromstring(export_svg(result, project))


@pytest.mark.parametrize('origin', [1.0, 100.0, 10000.0])
def test_only_terminal_ulp_duplicate_is_ignored_and_input_is_unchanged(origin):
    first = complex(origin, origin)
    points = [first, first+2, first+2+2j, first+2j,
              complex(math.nextafter(origin, math.inf), origin)]
    original = list(points)
    assert closure_samples(points) == points[:-1]
    validate_contours([points], [points], 'synthetic rectangle')
    assert points == original
    interior_duplicate = [first, complex(math.nextafter(origin, math.inf), origin),
                          first+2, first+2+2j, first+2j]
    assert closure_samples(interior_duplicate) is interior_duplicate


def test_closure_bound_is_capped_and_visible_closing_edges_are_not_removed():
    first = complex(1e8, 1e8)
    points = [first, first+2, first+2+2j, complex(math.nextafter(1e8, math.inf), 1e8)]
    assert closure_samples(points) is points
    small = [1+1j, 3+1j, 3+3j, 1+3j, 1.0000001+1j]
    assert closure_samples(small) is small


def test_genuine_crossing_and_touching_counters_remain_rejected():
    crossing = [1+1j, 4+4j, 1+4j, 4+1j]
    with pytest.raises(ValueError, match='self-intersecting'):
        validate_contours([crossing], [crossing], 'crossing')
    outer = [1+1j, 5+1j, 5+5j, 1+5j]
    touching = [1+2j, 2+2j, 2+3j, 1+3j]
    with pytest.raises(ValueError, match='intersect/touch'):
        validate_contours([outer, touching], [outer, touching], 'touching')


def test_valid_svg_with_overlapping_triangle_contours_still_blocks_cutting_export():
    # Synthetic compound outlines: legal SVG fill semantics, unsupported cutting topology.
    art = import_svg(svg('<defs><style>.paint{fill:black;fill-rule:nonzero}</style></defs>'
                         '<path class="paint" d="M5 14H25L15 2Z M5 6H25L15 18Z"/>'))
    project = Project()
    project.placement.width, project.placement.height = 30, 15
    project.center_artwork()
    with pytest.raises(ValueError, match='compound contours intersect/touch'):
        convert(art, project)
