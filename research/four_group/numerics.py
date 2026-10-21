"""Nominal and hypothetical scenario calculations; no experimental export on failure."""

from copy import deepcopy
from decimal import Decimal
import math

import numpy as np

from .core import (
    alignment_difference,
    group_project,
    make_global,
    nominal_points,
    production_fit,
    source_samples,
    support,
    target_points,
    mm,
)
from .independent import Fit, Profile


def fit_record(obj, bounds, kind="pchip"):
    production = production_fit(obj, bounds) if kind == "pchip" else None
    profile = Profile(obj.surface().points, kind)
    ref = Fit(profile, bounds, production_parameters=production.metadata() if production else None)
    extrema = ref.extrema()
    data = {
        "support_front_xz_mm": bounds,
        "support_width_height_mm": [bounds[2] - bounds[0], bounds[3] - bounds[1]],
        "k": ref.k,
        "reference_z_mm": ref.z_ref,
        "reference_radius_mm": ref.r_ref,
        "top_center_origin_translation_mm": ref.origin_y,
        "strain": extrema,
        "independent_k_difference": ref.independent_k - ref.k,
        "interpolation": kind,
        "solver": "unchanged production conformal fit"
        if production
        else "independent research-only interpolation comparison",
    }
    if production:
        low, high = production.strain_extrema()
        assert abs(extrema["minimum_signed"] - low) < 1e-10
        assert abs(extrema["maximum_signed"] - high) < 1e-10
        data["production_metadata"] = production.metadata()
    return data, ref


def restricted_strain(fit, bounds):
    left, top, right, bottom = bounds
    z = [top, bottom] + [
        z for z in fit.profile.stationary(fit.k / math.sqrt(1 - fit.k**2)) if top < z < bottom
    ]
    values = fit.strain(np.array(z))
    return {
        "extension": max(0.0, float(np.max(values))),
        "compression": max(0.0, -float(np.min(values))),
        "note": "Same A/B field restricted to the group vertical band; no carrier-separation strain benefit assigned",
    }


def scenario_list(config):
    rows = [{"id": "nominal", "category": "nominal"}]
    for delta in [-0.125, -0.05, 0.05, 0.125]:
        rows.append(
            {
                "id": f"lowest_height_{delta:+.3f}in",
                "category": "station-height",
                "height_change": (3, delta),
            }
        )
    for delta in [-0.25, -0.125, 0.125, 0.25]:
        rows.append(
            {
                "id": f"6.30_height_{delta:+.3f}in",
                "category": "station-height",
                "height_change": (2, delta),
            }
        )
    for i in range(4):
        for delta in [-0.125, 0.125]:
            rows.append(
                {
                    "id": f"circumference_station_{i}_{delta:+.3f}in",
                    "category": "circumference",
                    "circumference_change": (i, delta),
                }
            )
    for delta in [-0.125, 0.125]:
        rows.append(
            {
                "id": f"all_circumferences_{delta:+.3f}in",
                "category": "circumference",
                "all_circumferences_change": delta,
            }
        )
    for delta in [-0.25, 0, 0.25]:
        rows.append(
            {
                "id": f"extra_5.05in_C_{delta:+.2f}in",
                "category": "extra-station",
                "extra_station_change": delta,
            }
        )
    for interpolation in ["linear", "natural-cubic"]:
        rows.append(
            {
                "id": f"interpolation_{interpolation}",
                "category": "interpolation",
                "interpolation": interpolation,
            }
        )
    for delta in [-0.125, -0.05, 0.05, 0.125]:
        rows.append(
            {
                "id": f"artwork_bottom_{delta:+.3f}in",
                "category": "placement",
                "placement_change": delta,
            }
        )
    for margin in [1.0, 3.0, 5.0]:
        rows.append(
            {
                "id": f"all_support_margins_{margin:g}mm",
                "category": "support-margin",
                "margin_mm": margin,
            }
        )
        rows.append(
            {
                "id": f"side_support_margins_{margin:g}mm",
                "category": "support-margin",
                "side_margin_mm": margin,
            }
        )
    for shrink in [1.0, 3.0]:
        rows.append(
            {
                "id": f"support_inset_{shrink:g}mm_REJECT",
                "category": "support-size",
                "inset_mm": shrink,
            }
        )
    return rows


def evaluate(config, art, group_art, scenarios=None):
    nominal_global = make_global(art, config)
    nominal_group = {name: group_project(g, art, nominal_global) for name, g in group_art.items()}
    samples = {name: source_samples(g, 9) for name, g in group_art.items()}
    nominal_targets = {
        name: target_points(v, art.visible_frame, nominal_global) for name, v in samples.items()
    }
    baseline = {}
    rows = []
    for scenario in scenarios or scenario_list(config):
        print("scenario", scenario["id"], flush=True)
        points = nominal_points(config)
        stations = deepcopy(config["stations_physical_height_and_circumference_in"])
        top_datum = Decimal(config["physical_top_height_in"])
        if "height_change" in scenario:
            i, delta = scenario["height_change"]
            stations[i][0] = str(Decimal(stations[i][0]) + Decimal(str(delta)))
        if "circumference_change" in scenario:
            i, delta = scenario["circumference_change"]
            stations[i][1] = str(Decimal(stations[i][1]) + Decimal(str(delta)))
        if "all_circumferences_change" in scenario:
            for station in stations:
                station[1] = str(
                    Decimal(station[1]) + Decimal(str(scenario["all_circumferences_change"]))
                )
        if "extra_station_change" in scenario:
            nominal_profile = Profile([(z, c / math.pi) for z, c in points])
            extra_z = mm(top_datum - Decimal("5.05"))
            c = float(nominal_profile.radius(extra_z)) * 2 * math.pi + mm(
                scenario["extra_station_change"]
            )
            stations.append(["5.05", str(c / 25.4)])
            stations.sort(key=lambda row: -float(row[0]))
        points = [(mm(top_datum - Decimal(z)), mm(c)) for z, c in stations]
        bottom = Decimal(config["visible_bottom_physical_height_in"]) + Decimal(
            str(scenario.get("placement_change", 0))
        )
        project = make_global(art, config, points, str(bottom))
        local_projects = {name: group_project(g, art, project) for name, g in group_art.items()}
        kind = scenario.get("interpolation", "pchip")
        row = {
            "scenario": scenario,
            "input_status": "nominal reconstruction"
            if scenario["id"] == "nominal"
            else "hypothetical deterministic variation, not a measured distribution",
            "stations_z_circumference_mm": points,
            "interpolation": kind,
            "artwork_bottom_physical_in": float(bottom),
            "fits": {},
        }
        models = {}
        for name, p in [("A", project), *local_projects.items()]:
            actual = support(p)
            bounds = actual.copy()
            margin = scenario.get("margin_mm", 0)
            side = scenario.get("side_margin_mm", 0)
            bounds = [
                bounds[0] - margin - side,
                bounds[1] - margin,
                bounds[2] + margin + side,
                bounds[3] + margin,
            ]
            try:
                if "inset_mm" in scenario:
                    raise ValueError("Rejected: proposed support would exclude visible artwork")
                data, ref = fit_record(p.object, bounds, kind)
                if name == "A":
                    source = np.vstack(list(samples.values()))
                else:
                    source = samples[name]
                targets = target_points(source, art.visible_frame, project)
                flat = ref.mapping(targets)
                data["valid"] = True
                data["sampled_flat_bounds_mm"] = [
                    *flat.min(axis=0).tolist(),
                    *flat.max(axis=0).tolist(),
                ]
                data["sampled_flat_width_height_mm"] = (
                    flat.max(axis=0) - flat.min(axis=0)
                ).tolist()
                data["geometry_measurement"] = (
                    "Sampled original curves (9 per segment); not production export bounds or certified extrema"
                )
                data["registration_target_center_mm"] = [
                    p.placement.x,
                    p.placement.z + p.placement.height / 2,
                ]
                if scenario["id"] == "nominal":
                    baseline[name] = {"flat": flat, "fit": ref, "targets": targets}
                else:
                    compare = alignment_difference(baseline[name]["flat"], flat)
                    data["change_from_nominal"] = compare
                    data["nominal_registration_origin_shift_mm"] = (
                        ref.mapping(np.array([data["registration_target_center_mm"]]))[0]
                        - baseline[name]["fit"].mapping(
                            np.array(
                                [
                                    [
                                        p.placement.x,
                                        nominal_group[name].placement.z
                                        + nominal_group[name].placement.height / 2,
                                    ]
                                    if name != "A"
                                    else [
                                        0,
                                        nominal_global.placement.z
                                        + nominal_global.placement.height / 2,
                                    ]
                                ]
                            )
                        )[0]
                    ).tolist()
                models[name] = ref
            except ValueError as exc:
                data = {
                    "valid": False,
                    "rejection": str(exc),
                    "attempted_support_front_xz_mm": bounds,
                }
            row["fits"][name] = data
        row["complete_layout_valid"] = all(v["valid"] for v in row["fits"].values())
        if row["fits"]["A"]["valid"]:
            for name, p in local_projects.items():
                if row["fits"][name]["valid"]:
                    ab = restricted_strain(models["A"], support(p))
                    row["fits"][name]["A_and_B_same_field_over_group_band"] = ab
                    local = row["fits"][name]["strain"]
                    denominator = max(ab["extension"], ab["compression"])
                    row["fits"][name]["C_to_AB_max_abs_strain_ratio"] = (
                        max(local["extension"], local["compression"]) / denominator
                    )
            if scenario["id"] == "nominal":
                for name, targets in nominal_targets.items():
                    original = models["A"].mapping(targets)
                    local = models[name].mapping(targets)
                    comparison = alignment_difference(original, local)
                    center = np.array(
                        [
                            [
                                local_projects[name].placement.x,
                                local_projects[name].placement.z
                                + local_projects[name].placement.height / 2,
                            ]
                        ]
                    )
                    shift = (models[name].mapping(center) - models["A"].mapping(center))[0]
                    comparison["target_center_anchor_alignment_max_mm"] = float(
                        np.max(np.linalg.norm(local - shift - original, axis=1))
                    )
                    row["fits"][name]["difference_from_A"] = comparison
        rows.append(row)
    return rows, baseline, nominal_global, nominal_group
