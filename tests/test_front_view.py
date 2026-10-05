import math

import numpy as np
import pytest

from wraplab.domain import ObjectSpec, Project
from wraplab.geometry.surfaces import develop
from wraplab.svg import convert, import_svg


@pytest.mark.parametrize("mode", ["cylinder", "frustum", "measured"])
def test_front_projection_roundtrip_and_level_baseline(mode):
    project = Project(object=ObjectSpec(mode=mode))
    project.placement.width = 25
    project.placement.height = 12
    project.center_artwork()
    surface = project.object.surface()
    mapper = project.mapper(25, 12)
    for x in np.linspace(0, 25, 13):
        y = 6
        desired_x = x - 12.5
        z = project.placement.z + y
        theta = math.asin(desired_x / surface.radius(z))
        assert surface.radius(z) * math.sin(theta) == pytest.approx(desired_x)
        assert mapper(complex(x, y)) == pytest.approx(
            complex(*develop(project.development(surface), theta, z))
        )
        assert z == project.placement.z + 6  # baseline sits at constant axial height


def test_cylinder_front_width_is_inverse_projection_not_arc_width():
    project = Project(object=ObjectSpec(diameter=80, height=100))
    project.placement.width, project.placement.height = 40, 20
    project.center_artwork()
    mapping = project.mapper(40, 20)
    width = (mapping(40 + 0j) - mapping(0j)).real
    assert width == pytest.approx(2 * 40 * math.asin(40 / (2 * 40)))
    assert width > 40
    assert mapping(20j).imag - mapping(0j).imag == pytest.approx(20)


def test_frustum_radius_and_axial_direction_are_from_labelled_top():
    project = Project(
        object=ObjectSpec(mode="frustum", top_diameter=30, bottom_diameter=80, height=50)
    )
    surface = project.object.surface()
    assert surface.radius(0) == 15
    assert surface.radius(50) == 40
    assert develop(surface, 0, 50)[1] > develop(surface, 0, 0)[1]


@pytest.mark.parametrize("x,width", [(0, 76), (40, 1), (-40, 1), (0, 100)])
def test_visible_edge_margin_rejects_instead_of_clamping(x, width):
    project = Project(object=ObjectSpec(diameter=80))
    project.placement.x, project.placement.width = x, width
    with pytest.raises(ValueError, match="visible edge"):
        project.mapper(width, 20)


def test_every_mapped_point_is_checked_even_outside_canvas():
    project = Project()
    project.center_artwork()
    mapping = project.mapper(40, 20)
    with pytest.raises(ValueError, match="never clamped"):
        mapping(100 + 10j)


def test_front_view_vinyl_conversion_retains_counters_and_reports_bell_strain():
    art = import_svg(
        '<svg width="25mm" height="12mm" viewBox="0 0 25 12"><path fill-rule="evenodd" d="M1 1H24V11H1Z M5 4H20V8H5Z"/></svg>'
    )
    project = Project(object=ObjectSpec(mode="measured"))
    project.placement.width, project.placement.height = 25, 12
    project.center_artwork()
    result = convert(art, project)
    assert len(result.paths[0].contours) == 2
    assert any("application strain" in w for w in result.warnings)
