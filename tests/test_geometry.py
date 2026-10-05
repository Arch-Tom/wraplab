import math

import numpy as np
import pytest
from scipy.integrate import quad

from wraplab.domain import ObjectSpec, Project
from wraplab.geometry.surfaces import (
    Cylinder,
    Frustum,
    MeasuredProfile,
    develop,
    principal_stretches,
)
from wraplab.geometry.units import Unit


def test_units_are_exact_and_no_model_drift():
    assert Unit.INCH.to_mm(1) == 25.4
    assert Unit.MM.from_mm(25.4) == 25.4
    project = Project()
    before = project.to_dict()
    for _ in range(1000):
        Unit.INCH.from_mm(project.object.diameter)
        project.units = "in"
        project.units = "mm"
    assert project.to_dict() == before


@pytest.mark.parametrize("diameter", [25.4, 80, 1000])
@pytest.mark.parametrize("wrap", [30, 180, 360])
def test_cylinder_circumference_and_placement(diameter, wrap):
    project = Project(
        object=ObjectSpec(diameter=diameter), wrap_degrees=wrap, physical_model="surface-template"
    )
    assert project.wrap_width() == pytest.approx(math.pi * diameter * wrap / 360)
    project.placement.width = project.wrap_width() / 2
    project.placement.height = 30
    project.center_artwork()
    mapping = project.mapper(project.placement.width, 30)
    a, b, c = mapping(0j), mapping(complex(project.placement.width, 0)), mapping(30j)
    assert b - a == pytest.approx(complex(project.placement.width, 0))
    assert c - a == pytest.approx(30j)
    assert a.real == pytest.approx(-project.placement.width / 2)


@pytest.mark.parametrize(
    "bottom,top,height",
    [(100, 80, 120), (80, 100, 120), (200, 20, 15), (20, 200, 15), (80, 80, 100)],
)
@pytest.mark.parametrize("wrap", [45, 180, 360])
def test_frustum_truth_and_isometry(bottom, top, height, wrap):
    surface = Frustum(bottom, top, height)
    slant = math.sqrt(height**2 + ((top - bottom) / 2) ** 2)
    assert surface.slant_height == pytest.approx(slant)
    if bottom != top:
        k = abs((top - bottom) / (2 * slant))
        assert surface.developed_radii == pytest.approx((top / (2 * k), bottom / (2 * k)))
        assert surface.sector_angle(wrap) == pytest.approx(k * math.radians(wrap))
    # Independent surface metric: circumference lengths and meridional lengths.
    for z in [0, height / 3, height]:
        theta = math.radians(wrap) / 2
        assert principal_stretches(surface, theta, z) == pytest.approx((1, 1), abs=1e-12)
        dt = 1e-6
        a, b = complex(*develop(surface, theta - dt, z)), complex(*develop(surface, theta + dt, z))
        assert abs(b - a) / (2 * dt) == pytest.approx(surface.radius(z), rel=1e-8)
    theta = math.radians(wrap) / 3
    assert math.dist(develop(surface, theta, 0), develop(surface, theta, height)) == pytest.approx(
        slant
    )


@pytest.mark.parametrize("delta", [0, 1e-3, 1e-8, 1e-12, -1e-12])
def test_near_cylinder_has_stable_limit(delta):
    frustum, cylinder = Frustum(80, 80 + delta, 100), Cylinder(80, 100)
    for z in [0, 23, 100]:
        for angle in [-math.pi, -0.2, 0, math.pi]:
            assert develop(frustum, angle, z) == pytest.approx(
                develop(cylinder, angle, z), abs=max(1e-9, 10 * abs(delta))
            )


@pytest.mark.parametrize("diameters", [(80, 80), (100, 50), (50, 100)])
def test_measured_profile_matches_exact_truth(diameters):
    bottom, top = diameters
    measured = MeasuredProfile([(z, top + (bottom - top) * z / 100) for z in [0, 10, 30, 75, 100]])
    exact = Frustum(bottom, top, 100)
    for z in np.linspace(0, 100, 19):
        for angle in np.linspace(-math.pi, math.pi, 9):
            assert develop(measured, angle, z) == pytest.approx(develop(exact, angle, z), abs=1e-8)


@pytest.mark.parametrize(
    "points",
    [
        [(0, 80), (10, 75), (30, 40), (50, 35)],
        [(0, 30), (10, 45), (30, 70), (50, 75)],
        [(0, 70), (10, 45), (30, 40), (50, 70)],
    ],
)
def test_measured_shape_preservation_distance_continuity(points):
    profile = MeasuredProfile(points)
    for (a, da), (b, db) in zip(points, points[1:], strict=False):
        for z in np.linspace(a, b, 51):
            assert min(da, db) / 2 - 1e-10 <= profile.radius(z) <= max(da, db) / 2 + 1e-10
    expected, _ = quad(
        lambda z: math.sqrt(1 + float(profile._dr(z)) ** 2),
        0,
        profile.height,
        points=[p[0] for p in points],
        epsabs=1e-8,
    )
    assert profile.distance(profile.height) == pytest.approx(expected, abs=1e-7)
    for z, _ in points[1:-1]:
        assert profile.distance(z + 1e-7) - profile.distance(z - 1e-7) < 1e-5


def test_equivalent_inch_mm_profiles():
    inches = [(0, 3.25), (0.5, 3.08), (1, 2.65), (1.875, 1.5)]
    mm = [(Unit.INCH.to_mm(z), Unit.INCH.to_mm(d)) for z, d in inches]
    a = MeasuredProfile(mm)
    b = MeasuredProfile([(z * 25.4, d * 25.4) for z, d in inches])
    assert develop(a, 0.7, 25.4) == develop(b, 0.7, 25.4)


@pytest.mark.parametrize(
    "points",
    [
        [],
        [(0, 1), (1, 1)],
        [(0, 1), (0, 2), (1, 3)],
        [(1, 1), (2, 2), (3, 3)],
        [(0, 1), (1, -2), (2, 3)],
        [(0, 1), (2, 2), (1, 3)],
        [(0, 1), (1, float("nan")), (2, 3)],
    ],
)
def test_invalid_profiles(points):
    with pytest.raises(ValueError):
        MeasuredProfile(points)


def test_experimental_distortion_is_visible_and_folds_blocked():
    project = Project(object=ObjectSpec(mode="measured"))
    assert any("application strain" in w for w in project.profile_warnings())
    profile = MeasuredProfile([(0, 100), (1, 20), (2, 100)])
    assert principal_stretches(profile, 2, 0) != pytest.approx((1, 1))


@pytest.mark.parametrize(
    "surface",
    [lambda: Cylinder(0, 1), lambda: Frustum(1, -1, 1), lambda: Cylinder(1, float("inf"))],
)
def test_invalid_exact_geometry(surface):
    with pytest.raises(ValueError):
        surface()
