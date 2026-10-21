import math

import numpy as np
import pytest

from wraplab.geometry.conformal import fit_profile
from wraplab.geometry.surfaces import MeasuredProfile

from wraplab.svg import import_svg

from research.four_group.core import (
    alignment_difference,
    check_membership,
    group_project,
    groups,
    make_global,
    source_samples,
    split_global_svg,
    target_points,
    vector_audit,
)
from research.four_group.independent import Fit, Profile


@pytest.mark.parametrize("dr", [0, 12.5, -12.5, 1e-8, -1e-8])
def test_reference_recovers_exact_cylinder_and_both_frustum_directions(dr):
    h, r0 = 100.0, 40.0
    points = [(z, 2 * (r0 + dr * z / h)) for z in [0, 25, 70, 100]]
    fit = Fit(Profile(points), [-10, 15, 10, 90])
    k = dr / math.hypot(h, dr)
    assert fit.k == pytest.approx(k, abs=1e-14)
    targets = np.array([[x, z] for x in [-10, -3, 0, 7, 10] for z in [15, 33, 65, 90]])
    out = fit.mapping(targets)
    for (x, z), mapped in zip(targets, out, strict=True):
        r = r0 + dr * z / h
        theta = math.asin(x / r)
        expected_x = r * theta if k == 0 else r * math.sin(k * theta) / k
        expected_y = z * math.hypot(h, dr) / h - (
            0 if k == 0 else 2 * r * math.sin(k * theta / 2) ** 2 / k
        )
        assert mapped == pytest.approx([expected_x, expected_y], abs=2e-11)
    assert max(abs(fit.extrema()[key]) for key in ["extension", "compression"]) < 1e-13
    inverted, residual = fit.inverse(out)
    assert np.max(np.linalg.norm(inverted - targets, axis=1)) < 1e-9
    assert residual < 1e-9


def test_independent_hermite_and_legendre_agree_with_separate_production_implementation():
    points = [(0, 80), (21, 90), (57, 130), (100, 150)]
    profile = Profile(points)
    production = MeasuredProfile(points)
    zs = np.linspace(0, 100, 501)
    assert np.max(abs(profile.radius(zs) - [production.radius(z) for z in zs])) < 1e-12
    assert (
        np.max(abs(profile.derivative(zs) - [production.radial_derivative(z) for z in zs])) < 1e-13
    )
    fitted = fit_profile(tuple(points), 15, 95, -10, 15)
    ref = Fit(profile, [-10, 15, 15, 95])
    tight = Fit(profile, [-10, 15, 15, 95], order=96)
    assert ref.k == pytest.approx(fitted.k, abs=1e-12)
    assert tight.k == pytest.approx(ref.k, abs=1e-13)
    samples = np.array([[x, z] for x in [-10, 0, 15] for z in [15, 40, 70, 95]])
    prod = np.array([fitted.develop(math.asin(x / production.radius(z)), z) for x, z in samples])
    assert np.max(abs(ref.mapping(samples) - prod)) < 1e-10
    assert ref.extrema()["maximum_signed"] == pytest.approx(fitted.strain_extrema()[1], abs=1e-12)


def test_genuine_domain_and_edge_violations_remain_errors():
    profile = Profile([(0, 80), (50, 90), (100, 120)])
    with pytest.raises(ValueError, match="domain"):
        Fit(profile, [-5, 10, 5, 101])
    with pytest.raises(ValueError, match="margin"):
        Fit(profile, [-40, 0, 40, 90])
    with pytest.raises(ValueError, match="domain"):
        profile.radius(math.nextafter(100, math.inf))


def test_group_partition_cannot_separate_a_counter_from_its_outer_contour():
    audit = [{"parents": [[], [0], []]}]
    with pytest.raises(ValueError, match="glyph/counter"):
        check_membership(
            audit,
            [{"id": "a", "shape": 0, "contours": [0]}, {"id": "b", "shape": 0, "contours": [1, 2]}],
        )
    check_membership(
        audit,
        [{"id": "a", "shape": 0, "contours": [0, 1]}, {"id": "b", "shape": 0, "contours": [2]}],
    )


def test_translation_comparison_does_not_hide_shape_change_or_recenter_targets():
    a = np.array([[0, 0], [1, 0], [1, 2], [0, 2]], dtype=float)
    b = a + [100, 200]
    assert alignment_difference(a, b)["sampled_max_difference_mm"] < 1e-12
    b[0, 0] += 0.4
    assert alignment_difference(a, b)["sampled_max_difference_mm"] > 0.29


def test_group_targets_share_global_composition_and_exact_measured_endpoint():
    art = import_svg(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="80mm" viewBox="0 0 100 80">'
        '<path d="M10 10H40V30H10Z M15 15V25H30V15Z"/>'
        '<path d="M20 50H90V70H20Z"/></svg>'
    )
    config = {
        "physical_top_height_in": "9.75",
        "stations_physical_height_and_circumference_in": [
            ("9.75", "17.125"),
            ("6.30", "25.1875"),
            ("3.80", "36.125"),
        ],
        "production_tolerance_mm": 0.01,
        "visible_height_in": "4.0",
        "visible_bottom_physical_height_in": "3.80",
    }
    definitions = [
        {"id": "upper", "shape": 0, "contours": [0, 1]},
        {"id": "lower", "shape": 1, "contours": [0]},
    ]
    global_project = make_global(art, config)
    selected = groups(art, definitions)
    for name, group in selected.items():
        p = group_project(group, art, global_project)
        raw = source_samples(group, 3)
        direct = target_points(raw, art.visible_frame, global_project)
        local = target_points(raw, group.visible_frame, p)
        assert np.max(abs(direct - local)) < 1e-12
        assert p.placement.x != 0  # Their original offsets survive grouping.
        if name == "lower":
            assert p.placement.z + p.placement.height == p.object.surface().height
    with pytest.raises(ValueError, match="duplicate"):
        groups(art, definitions + [definitions[0]])
    with pytest.raises(ValueError, match="every"):
        groups(art, definitions[:1])


def test_separate_carrier_subset_keeps_exact_numbers_winding_and_page_origin():
    import xml.etree.ElementTree as ET

    text = '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100"><metadata>{"research": {}, "page_origin_mm": [-11.234567, 20.123456]}</metadata><g id="Artwork"><path fill-rule="nonzero" stroke="none" d="M10.123456 10L40 10L40 30L10.123456 30Z M15 15L15 25L30 25L30 15Z"/><path fill-rule="nonzero" stroke="none" d="M20 50L90 50L90 70L20 70Z"/></g></svg>'
    subset = split_global_svg(text, {"id": "compound", "shape": 0, "contours": [0, 1]})
    source_root, result_root = ET.fromstring(text), ET.fromstring(subset)
    assert source_root.attrib == result_root.attrib
    assert source_root.find(".//{*}path").attrib == result_root.find(".//{*}path").attrib
    audit = vector_audit(subset)
    assert audit[0]["contours"] == 2 and audit[0]["openings"] == 1
