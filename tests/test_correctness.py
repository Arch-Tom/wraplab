"""SVG 2 path state and physical endpoint regressions; fixtures are synthetic."""

import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from shapely.geometry import Polygon

from wraplab.domain import ObjectSpec, Project
from wraplab.geometry.surfaces import MeasuredProfile
from wraplab.svg import convert, export_svg, import_svg
from wraplab.svg.importer import parse_subpaths
from wraplab.svg.transform import convert_artwork


@pytest.mark.parametrize("data", [
    "M10 10 m5 5 h10 v10 h-10 z",
    "M1 2 m9 8 m5 5 h10 v10 h-10 z",
    "M10 10Z m5 5 h10 v10 h-10 z",
])
def test_moveto_only_sections_retain_current_point(data):
    # SVG 2 paths: relative moveto uses the current point, even without drawing.
    subs = parse_subpaths(data)
    assert len(subs) == 1 and subs[0].closed
    assert [s.start for s in subs[0].segments] == [15+15j, 25+15j, 25+25j, 15+25j]


def test_closepath_starts_an_independent_open_stroke():
    data = "M10 10H20V20H10Z L30 30"
    subs = parse_subpaths(data)
    assert [s.closed for s in subs] == [True, False]
    assert subs[1].segments[0].start == 10+10j
    assert subs[1].segments[0].end == 30+30j
    art = import_svg('<svg width="40mm" height="40mm" viewBox="0 0 40 40">'
                     f'<path d="{data}" fill="none" stroke="black" stroke-width="2" '
                     'stroke-linecap="butt" stroke-linejoin="miter"/></svg>')
    result = convert_artwork(art, lambda p: p, .001)
    # Independent analytical outline: square annulus plus butt-capped diagonal.
    q = 1 / math.sqrt(2)
    square = Polygon([(9,9),(21,9),(21,21),(9,21)],
                     [[(11,11),(11,19),(19,19),(19,11)]])
    diagonal = Polygon([(10-q,10+q),(30-q,30+q),(30+q,30-q),(10+q,10-q)])
    rings = result.paths[0].contours
    polygons = [Polygon([(p.real,p.imag) for p in c.points]) for c in rings]
    actual = max(polygons, key=lambda p:p.area)
    for hole in polygons:
        if hole != actual and actual.contains(hole):
            actual = actual.difference(hole)
    assert actual.bounds[:2] == pytest.approx((9,9), abs=1e-12)
    assert actual.symmetric_difference(square.union(diagonal)).area < 1e-10


@pytest.mark.parametrize('data', ['M1 1Z 2 2', 'M1 1L2 1L2 2Z 3 3'])
def test_closepath_requires_an_explicit_following_command(data):
    with pytest.raises(ValueError, match='Malformed SVG path'):
        parse_subpaths(data)


@pytest.mark.parametrize("mode", ["cylinder", "frustum", "measured"])
def test_exact_source_frame_endpoint_maps_to_exact_physical_endpoint(mode):
    h = 8.5 * 25.4
    project = Project(object=ObjectSpec(mode=mode, height=h,
                                      points=[(0,80),(h/2,90),(h,100)]))
    project.placement.width, project.placement.height, project.placement.z = 10, h, 0
    mapping = project.mapper(20,20)
    assert math.isfinite(mapping(10+20j).imag)
    assert math.isfinite(mapping(10+0j).imag)
    with pytest.raises(ValueError, match="outside"):
        mapping(10+20.000001j)
    surface = project.object.surface()
    with pytest.raises(ValueError, match="outside"):
        surface.radius(math.nextafter(h, math.inf))


@pytest.mark.parametrize("z", [0, 1e-11, -1e-11, 1e-10, -1e-10])
def test_accepted_near_zero_first_station_has_a_canonical_domain(z):
    surface = MeasuredProfile([(z,80),(50,90),(100,100)])
    assert surface.points[0] == (0,80)
    assert surface.radius(0) == 40
    assert surface.distance(0) == 0


@pytest.mark.parametrize("z", [math.nextafter(1e-10, math.inf), -1.00001e-10, .001])
def test_meaningfully_nonzero_first_station_is_rejected(z):
    with pytest.raises(ValueError, match="first measured height must be zero"):
        MeasuredProfile([(z,80),(50,90),(100,100)])


def test_legacy_export_geometry_matches_captured_prechange_output():
    fixtures = json.loads((Path(__file__).parent / 'fixtures/legacy-page-projects.json').read_text())
    for case in fixtures['cases']:
        project = Project.from_dict(case['project'])
        art = import_svg(project.source_svg)
        root = ET.fromstring(export_svg(convert(art, project), project))
        assert root.attrib == case['expected_svg_attributes'], case['name']
        assert [p.attrib for p in root.findall('.//{*}path')] == case['expected_paths'], case['name']
        metadata = json.loads(root.find('{*}metadata').text)
        assert metadata['page_origin_mm'] == case['expected_origin_mm'], case['name']
