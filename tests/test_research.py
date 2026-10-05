"""Independent numeric and analytic research oracles, separate from implementation formulas."""

import math
import json
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import LineString, Point

from wraplab.domain import ObjectSpec, Project
from wraplab.geometry.conformal import ConformalDevelopment
from wraplab.geometry.exact import development_bounds, front_derivative_bounds, inverse_develop
from wraplab.geometry.surfaces import Frustum, MeasuredProfile, develop, principal_stretches
from wraplab.svg import convert, import_svg
from wraplab.svg.adaptive import certificate, flatten
from wraplab.svg.exporter import guides
from wraplab.svg.model import Affine


CORPUS = json.loads((Path(__file__).parent / "fixtures" / "packet-a.json").read_text())


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda c: c["id"])
def test_complete_independent_packet_a_corpus(case):
    factor = 25.4 if case["unit"] == "in" else 1
    r0, r1, h = (float(case[key]) * factor for key in ("r0", "r1", "h"))
    surface = Frustum(2 * r1, 2 * r0, h)
    for sample in case["samples"]:
        z = float(sample.get("source_z", sample.get("z"))) * factor
        theta = float(sample["theta_rad"])
        if "source_x" in case:
            x = float(case["source_x"]) * factor
            assert math.asin(x / surface.radius(z)) == pytest.approx(theta, abs=1e-12)
            magnification = surface.slant_height / h / math.cos(theta)
            assert magnification == pytest.approx(
                float(sample["max_projection_magnification"]), abs=1e-12
            )
        expected = tuple(float(sample[key]) * factor for key in ("X", "Y"))
        assert develop(surface, theta, z) == pytest.approx(expected, abs=1e-9, rel=0)
    if "bbox_xyxy" in case:
        span = float(case["wrap_degrees"])
        assert development_bounds(surface, span) == pytest.approx(
            [float(v) * factor for v in case["bbox_xyxy"]], abs=1e-9, rel=0
        )
        assert surface.slant_height == pytest.approx(float(case["L"]) * factor, abs=1e-9)
        area = math.radians(span) * surface.slant_height * (r0 + r1) / 2
        assert area == pytest.approx(float(case["area"]) * factor**2, abs=1e-8)


@pytest.mark.parametrize(
    "r0,r1,h,x,z,expected",
    [
        (50, 50, 100, 25, 50, (26.17993877991494, 50)),
        (40, 50, 100, 20, 0, (20.93447722220821, -0.5454667887420361)),
        (40, 50, 100, 20, 50, (20.71767632067926, 49.77458224252874)),
        (40, 50, 100, 20, 100, (20.57009288614111, 100.0775508637521)),
        (50, 40, 100, 20, 0, (20.57009288614111, 0.4212053474568143)),
    ],
)
def test_packet_a_front_numeric_oracles(r0, r1, h, x, z, expected):
    surface = Frustum(2 * r1, 2 * r0, h)
    theta = math.asin(x / surface.radius(z))
    assert develop(surface, theta, z) == pytest.approx(expected, abs=1e-9)
    assert develop(surface, -theta, z) == pytest.approx((-expected[0], expected[1]), abs=1e-9)
    angle, height = inverse_develop(surface, complex(*expected))
    assert height == pytest.approx(z, abs=1e-9)
    assert surface.radius(height) * math.sin(angle) == pytest.approx(x, abs=1e-9)


def test_packet_a_near_cylinder_oracle():
    surface = Frustum(100.000002, 100, 100)
    assert develop(surface, math.pi, 0) == pytest.approx(
        (157.07963267948964, -0.0000024674011002723393), abs=1e-9
    )
    assert develop(surface, math.pi, 100) == pytest.approx(
        (157.0796358210823, 99.99999753259886), abs=1e-9
    )


def test_aggressive_boundary_oracle_includes_noncorner_extrema():
    surface = Frustum(160, 40, 40)
    expected = (-96.14803401237305, -107.1091965119846, 96.14803401237305, 72.11102550927979)
    assert development_bounds(surface) == pytest.approx(expected, abs=1e-9)
    project = Project(
        object=ObjectSpec(mode="frustum", top_diameter=40, bottom_diameter=160, height=40),
        wrap_degrees=360,
        physical_model="surface-template",
    )
    points = guides(project)[0].contours[0].points
    assert (
        min(p.real for p in points),
        min(p.imag for p in points),
        max(p.real for p in points),
        max(p.imag for p in points),
    ) == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("r0,r1", [(40, 50), (50, 40), (20, 80), (50, 50), (50, 50.0000000001)])
def test_exact_inverse_and_magnification_are_distinct_from_material_strain(r0, r1):
    surface = Frustum(r1 * 2, r0 * 2, 100)
    for z in np.linspace(0, 100, 7):
        for theta in np.linspace(-math.pi, math.pi, 11):
            assert inverse_develop(surface, complex(*develop(surface, theta, z))) == pytest.approx(
                (theta, z), abs=1e-9
            )
    z, x = 50, surface.radius(50) * 0.5
    epsilon = 1e-4

    def mapping(x, z):
        return np.array(develop(surface, math.asin(x / surface.radius(z)), z))

    jac = np.column_stack(
        (
            (mapping(x + epsilon, z) - mapping(x - epsilon, z)) / (2 * epsilon),
            (mapping(x, z + epsilon) - mapping(x, z - epsilon)) / (2 * epsilon),
        )
    )
    singular = np.linalg.svd(jac, compute_uv=False)
    assert singular[1] == pytest.approx(1, abs=1e-8)
    assert singular[0] == pytest.approx(
        surface.slant_height / surface.height / math.sqrt(0.75), abs=1e-8
    )
    assert principal_stretches(surface, math.asin(x / surface.radius(z)), z) == pytest.approx(
        (1, 1)
    )


def test_certified_transformed_closing_edge():
    art = import_svg(
        '<svg width="50mm" height="30mm" viewBox="0 0 50 30"><path d="M2 2L48 2L48 28Z"/></svg>'
    )
    project = Project(object=ObjectSpec(mode="frustum", top_diameter=65, bottom_diameter=110))
    project.placement.width, project.placement.height = 50, 30
    project.center_artwork()
    result = convert(art, project)
    closing = art.shapes[0].subpaths[0].segments[-1]
    mapper = project.mapper(50, 30)
    bound = certificate(closing, Affine(), mapper)
    assert bound is not None and bound(0, 1) > project.export_tolerance_mm
    assert len(flatten(lambda t: mapper(closing.point(t)), 0.01, error_bound=bound)) > 2
    ring = result.paths[0].contours[0].points
    line = LineString([(p.real, p.imag) for p in ring + [ring[0]]])
    assert (
        max(
            line.distance(Point(p.real, p.imag))
            for p in (mapper(closing.point(t)) for t in np.linspace(0, 1, 10001))
        )
        < 0.01
    )


def test_front_hessian_bound_dominates_numerical_second_derivatives():
    surface = Frustum(100, 80, 100)
    j, h = front_derivative_bounds(surface, 25, 10, 90)
    assert j > 1 and h > 0

    def mapping(x, z):
        return np.array(develop(surface, math.asin(x / surface.radius(z)), z))

    epsilon = 0.001
    for x, z in [(0, 50), (20, 20), (-20, 80)]:
        for angle in np.linspace(0, math.pi, 11):
            v = np.array([math.cos(angle), math.sin(angle)])
            second = (
                mapping(x + epsilon * v[0], z + epsilon * v[1])
                - 2 * mapping(x, z)
                + mapping(x - epsilon * v[0], z - epsilon * v[1])
            ) / epsilon**2
            assert np.linalg.norm(second) <= h + 1e-6


class AnalyticBelt:
    """Independent sphere/catenoid functions from Packet B; no PCHIP/production quadrature."""

    height = 20

    def __init__(self, mode):
        self.mode = mode
        self.points = [(z, 2 * self.radius(z)) for z in [0, 10, 20]]

    def radius(self, z):
        t = (z - 10) / 50
        return 50 * math.sqrt(1 - t * t) if self.mode == "sphere" else 50 * math.cosh(t)

    def radial_derivative(self, z):
        t = (z - 10) / 50
        return -t / math.sqrt(1 - t * t) if self.mode == "sphere" else math.sinh(t)

    def slope(self, z):
        d = self.radial_derivative(z)
        return d / math.hypot(1, d)


@pytest.mark.parametrize(
    "mode,expected_strain", [("sphere", -0.0202041028867288), ("catenoid", 0.0200667556190758)]
)
def test_packet_b_analytic_belts_and_required_application_strain(mode, expected_strain):
    model = ConformalDevelopment(AnalyticBelt(mode), 0, 20, -15, 15)
    assert model.k == pytest.approx(0, abs=1e-12)
    for z in np.linspace(0, 20, 11):
        t = (z - 10) / 50
        expected = math.atanh(t) if mode == "sphere" else t
        assert model.coordinate(z) == pytest.approx(expected, abs=1e-11)
    assert model.application_strain(0) == pytest.approx(expected_strain, abs=1e-10)
    assert model.application_strain(20) == pytest.approx(expected_strain, abs=1e-10)


@pytest.mark.parametrize("mode", ["sphere", "catenoid"])
def test_pchip_sampling_converges_separately_from_quadrature(mode):
    truth = AnalyticBelt(mode)
    errors = []
    for count in [3, 7, 15, 29]:
        points = [(float(z), truth.radius(z) * 2) for z in np.linspace(0, 20, count)]
        model = ConformalDevelopment(MeasuredProfile(points), 0, 20, -15, 15)
        errors.append(
            max(
                abs(
                    model.coordinate(z)
                    - (math.atanh((z - 10) / 50) if mode == "sphere" else (z - 10) / 50)
                )
                for z in np.linspace(0, 20, 101)
            )
        )
        assert model.application_strain(0) == pytest.approx(truth.radius(0) / 50 - 1, abs=1e-10)
    # Three symmetric points have fortuitous near-quadratic accuracy; more knots are not
    # monotonically better at every location. Check withheld positions, not just endpoints.
    assert errors[-1] < errors[1] / 20
    assert errors[-1] < 1e-6


def test_fit_once_over_carrier_and_measured_derivative_bounds():
    project = Project(object=ObjectSpec(mode="measured"))
    project.placement.width, project.placement.height = 30, 12
    project.center_artwork()
    a = project.development()
    b = project.development()
    assert a is b
    assert a.metadata()["support_front_x_mm"] == [-15, 15]
    mapper = project.mapper(30, 12)
    assert mapper.derivative_bounds[0] > 0
    assert mapper.derivative_bounds[1] > 0
    assert "numerical-profile" in mapper.certificate_level
    low, high = a.strain_extrema()
    assert all(
        low - 1e-12 <= a.application_strain(z) <= high + 1e-12
        for z in np.linspace(a.z_min, a.z_max, 501)
    )


def test_source_height_domain_never_clamps():
    for surface in [Frustum(100, 80, 100), MeasuredProfile([(0, 80), (50, 90), (100, 100)])]:
        for z in [-1e-12, 100 + 1e-12]:
            with pytest.raises(ValueError, match="outside"):
                develop(surface, 0.1, z)
