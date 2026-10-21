"""Private experimental vector/reference exports; never called by the application."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from shapely.geometry import LineString
from svgpathtools import parse_path

from wraplab.svg import convert

from .core import (
    BASELINE,
    WARNING,
    check_membership,
    experimental_svg,
    geometry_signature,
    source_rings,
    source_samples,
    split_global_svg,
    target_points,
    vector_audit,
)
from .independent import Fit, Profile

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def root_svg(width, height, title):
    r = ET.Element(
        f"{{{NS}}}svg",
        {
            "width": f"{width:.6f}mm",
            "height": f"{height:.6f}mm",
            "viewBox": f"0 0 {width:.6f} {height:.6f}",
            "version": "1.1",
        },
    )
    ET.SubElement(r, "title").text = title
    return r


def save_svg(root, path):
    ET.indent(root, space="  ")
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    )


def label(root, x, y, text, size=3):
    n = ET.SubElement(
        root,
        "text",
        {
            "x": str(x),
            "y": str(y),
            "font-size": str(size),
            "font-family": "sans-serif",
            "fill": "#152d40",
        },
    )
    n.text = text


def line(root, x1, y1, x2, y2, color="#47718d", width=0.2):
    ET.SubElement(
        root,
        "line",
        {
            "x1": str(x1),
            "y1": str(y1),
            "x2": str(x2),
            "y2": str(y2),
            "stroke": color,
            "stroke-width": str(width),
        },
    )


def reference_sheet(cutting_text, anchors, path, title):
    source = ET.fromstring(cutting_text)
    w, h = float(source.get("width")[:-2]), float(source.get("height")[:-2])
    coords = np.array([a["cut_page_xy_mm"] for a in anchors])
    left = min(0, float(coords[:, 0].min())) - 15
    top = min(0, float(coords[:, 1].min())) - 18
    right = max(w, float(coords[:, 0].max())) + 15
    bottom = max(h, float(coords[:, 1].max())) + 15
    width = max(140, right - left)
    height = max(150, bottom - top + 15)
    r = root_svg(width, height, "REFERENCE ONLY — DO NOT CUT — " + title)
    g = deepcopy(source.find("{*}g"))
    g.set("transform", f"translate({-left} {-top})")
    g.set("opacity", ".35")
    r.append(g)
    for a in anchors:
        x, y = np.array(a["cut_page_xy_mm"]) - [left, top]
        line(r, x - 2, y, x + 2, y, "#be3c29")
        line(r, x, y - 2, x, y + 2, "#be3c29")
        label(r, x + 2.5, y - 1, a["id"], 2.5)
    label(r, 4, 5, "REFERENCE ONLY — DO NOT CUT", 3)
    label(r, 4, 10, title, 2.5)
    # Independent horizontal and vertical 100-mm calibration references.
    line(r, 15, height - 8, 115, height - 8, "#000000")
    label(r, 45, height - 10, "100 mm X", 2.5)
    line(r, width - 6, 20, width - 6, 120, "#000000")
    label(r, width - 25, 18, "100 mm Y", 2.5)
    ET.SubElement(r, "metadata").text = json.dumps(
        {
            "warning": "REFERENCE ONLY — DO NOT CUT",
            "cut_page_to_reference_page_translation_mm": [-left, -top],
            "cut_svg_page_mm": [w, h],
            "anchors": anchors,
            "application_baseline": BASELINE,
        }
    )
    save_svg(r, path)


def registration(project, fit, text, name, config):
    p = project.placement
    targets = [
        ("L", p.x - 0.35 * p.width, p.z + p.height / 2),
        ("R", p.x + 0.35 * p.width, p.z + p.height / 2),
        ("TOP", p.x, p.z),
    ]
    root = ET.fromstring(text)
    origin = np.array(json.loads(root.find("{*}metadata").text)["page_origin_mm"])
    result = []
    for ident, x, z in targets:
        flat = fit.mapping(np.array([[x, z]]))[0]
        radius = float(fit.profile.radius(z))
        result.append(
            {
                "id": name + "-" + ident,
                "global_front_x_mm": x,
                "app_z_down_mm": z,
                "physical_height_above_bottom_in": float(config["physical_top_height_in"])
                - z / 25.4,
                "surface_arc_from_front_meridian_mm": radius * math.asin(x / radius),
                "theta_degrees": math.degrees(math.asin(x / radius)),
                "flat_xy_before_page_trim_mm": flat.tolist(),
                "cut_page_xy_mm": (flat - origin).tolist(),
                "role": "Reference mark on separate paper/carrier; not a cutting contour",
            }
        )
    return result


def inverse_vector_check(text, ref, group_art, whole_art, global_project):
    root = ET.fromstring(text)
    origin = np.array(json.loads(root.find("{*}metadata").text)["page_origin_mm"])
    rings = []
    for element in root.findall(".//{*}path"):
        for sub in parse_path(element.get("d")).continuous_subpaths():
            rings.append(np.array([[s.start.real, s.start.imag] for s in sub]) + origin)
    flat = np.vstack(rings)
    front, residual = ref.inverse(flat)
    expected = [
        target_points(points, whole_art.visible_frame, global_project)
        for per_shape in source_rings(group_art, 129)
        for points in per_shape
    ]
    assert len(rings) == len(expected)
    start = 0
    distances = []
    for ring, target in zip(rings, expected, strict=True):
        actual = front[start : start + len(ring)]
        start += len(ring)
        a = audit_line(actual)
        b = audit_line(target)
        with np.errstate(invalid="raise"):
            distance = a.hausdorff_distance(b)
        assert math.isfinite(distance)
        distances.append(distance)
    assert max(distances) < global_project.export_tolerance_mm + 0.001
    # Independent source-point correspondence check, without converter/mapper reuse.
    source = source_samples(group_art, 5)
    desired = target_points(source, whole_art.visible_frame, global_project)
    derived = ref.mapping(desired)
    back, error = ref.inverse(derived, flat_residual_limit_mm=1e-7)
    assert np.max(np.linalg.norm(back - desired, axis=1)) < 1e-7
    return {
        "serialized_vertices_inverted": len(flat),
        "inverse_forward_residual_mm": residual,
        "sampled_max_inverse_front_contour_hausdorff_mm": max(distances),
        "source_reference_sampling": "129 parameter samples per original segment; not certified global curve bound",
        "audit_only_cleanup": "Consecutive points within 1e-10 mm removed from audit polylines to avoid degenerate source closure segments; cutting/source geometry unchanged",
        "direct_correspondence_samples": len(source),
        "independent_roundtrip_front_error_mm": float(
            np.max(np.linalg.norm(back - desired, axis=1))
        ),
        "independent_roundtrip_flat_residual_mm": error,
        "rounding_policy": "Inverse stays within measured domain; forward residual must fit 3e-6 mm serialization audit budget. Production guards unchanged.",
    }


def audit_line(points):
    """Suppress only subnanometer duplicate audit samples, never alter export paths."""
    points = np.asarray(points)
    assert np.isfinite(points).all()
    kept = [points[0]]
    for point in points[1:]:
        if np.linalg.norm(point - kept[-1]) > 1e-10:
            kept.append(point)
    if np.linalg.norm(kept[-1] - kept[0]) <= 1e-10:
        kept.pop()
    assert len(kept) >= 3
    return LineString(np.vstack([kept, kept[0]]))


def build(output, config, art, group_art, global_project, local_projects, nominal, baseline_models):
    output = Path(output)
    cuts = output / "EXPERIMENTAL_ARTWORK_ONLY"
    references = output / "REFERENCE_ONLY_DO_NOT_CUT"
    cuts.mkdir()
    references.mkdir()
    metadata = {
        "source_sha256": config["source_sha256"],
        "frame": "visible",
        "input_status": config["input_status"],
        "global_placement": vars(global_project.placement),
        "stations_z_circumference_mm": global_project.object.points,
        "physical_top_height_above_common_bottom_in": config["physical_top_height_in"],
        "view": "upright distant horizontal frontal orthographic; x=0 front center; z down from labelled top",
        "actual_saved_windows_project": False,
        "group_membership": config["groups"],
    }
    print("Converting A whole layout", flush=True)
    a_conversion = convert(art, global_project)
    a_text = experimental_svg(
        a_conversion, global_project, {"condition": "A", "group": "whole_layout", **metadata}
    )
    (cuts / "EXPERIMENTAL_NOT_APPROVED_A_whole_layout.svg").write_text(a_text)
    source_audit = vector_audit(a_text)
    check_membership(source_audit, config["groups"])
    assert sum(x["contours"] for x in source_audit) == 44
    assert sum(x["openings"] for x in source_audit) == 12
    b_root = ET.fromstring(a_text)
    node = b_root.find("{*}metadata")
    data = json.loads(node.text)
    data["research"]["condition"] = "B"
    data["research"]["carrier_hypothesis"] = (
        "Separate four carriers; identical A contours and deformation field"
    )
    node.text = json.dumps(data, sort_keys=True)
    b_text = ET.tostring(b_root, encoding="unicode") + "\n"
    assert geometry_signature(a_text) == geometry_signature(b_text)
    (cuts / "EXPERIMENTAL_NOT_APPROVED_B_identical_global_contours.svg").write_text(b_text)
    result = {
        "A": {
            "nodes": a_conversion.node_count,
            "audit": source_audit,
            "flat_svg_mm": [
                ET.fromstring(a_text).get("width"),
                ET.fromstring(a_text).get("height"),
            ],
        },
        "B": {"A_geometry_identical": True, "same_mathematical_strain_field": True},
        "groups": {},
    }
    whole_anchors = registration(
        global_project, baseline_models["A"]["fit"], a_text, "whole", config
    )
    reference_sheet(
        a_text,
        whole_anchors,
        references / "REFERENCE_ONLY_A_whole_layout.svg",
        "A — intact whole-layout carrier concept",
    )
    result["A"]["registration"] = whole_anchors
    global_profile = Profile(global_project.object.surface().points)
    whole_ref = Fit(
        global_profile,
        nominal["fits"]["A"]["support_front_xz_mm"],
        production_parameters=nominal["fits"]["A"]["production_metadata"],
    )
    for definition in config["groups"]:
        name = definition["id"]
        g = group_art[name]
        p = local_projects[name]
        print("Converting and independently auditing", name, flush=True)
        b_group = split_global_svg(a_text, definition)
        b_audit = vector_audit(b_group)
        b_bounds = parse_path(ET.fromstring(b_group).find(".//{*}path").get("d")).bbox()
        # Exact serialized numeric tokens are copied, not recalculated.
        a_element = ET.fromstring(a_text).findall(".//{*}path")[definition["shape"]]
        a_tokens = ["M" + x for x in a_element.get("d").split("M")[1:]]
        b_tokens = [
            "M" + x for x in ET.fromstring(b_group).find(".//{*}path").get("d").split("M")[1:]
        ]
        assert [a_tokens[i].strip() for i in definition["contours"]] == [
            x.strip() for x in b_tokens
        ]
        (cuts / f"EXPERIMENTAL_NOT_APPROVED_B_{name}_A_COORDINATES.svg").write_text(b_group)
        converted = convert(g, p)
        c_text = experimental_svg(
            converted,
            p,
            {"condition": "C", "group": name, **metadata, "local_fit": nominal["fits"][name]},
        )
        assert vector_audit(c_text) == b_audit
        (cuts / f"EXPERIMENTAL_NOT_APPROVED_C_{name}.svg").write_text(c_text)
        c_ref = Fit(
            Profile(p.object.surface().points),
            nominal["fits"][name]["support_front_xz_mm"],
            production_parameters=nominal["fits"][name]["production_metadata"],
        )
        b_anchors = registration(p, whole_ref, b_group, name, config)
        c_anchors = registration(p, c_ref, c_text, name, config)
        assert [[a["global_front_x_mm"], a["app_z_down_mm"]] for a in b_anchors] == [
            [a["global_front_x_mm"], a["app_z_down_mm"]] for a in c_anchors
        ]
        reference_sheet(
            b_group,
            b_anchors,
            references / f"REFERENCE_ONLY_B_{name}.svg",
            f"B {name} — original global geometry",
        )
        reference_sheet(
            c_text,
            c_anchors,
            references / f"REFERENCE_ONLY_C_{name}.svg",
            f"C {name} — independent fit, shared bell targets",
        )
        c_root = ET.fromstring(c_text)
        result["groups"][name] = {
            "membership": definition,
            "source_frame_mm": vars(g.visible_frame),
            "target_placement_mm": vars(p.placement),
            "audit": b_audit,
            "C_nodes": converted.node_count,
            "C_flat_svg_mm": [float(c_root.get("width")[:-2]), float(c_root.get("height")[:-2])],
            "B_exact_A_coordinate_tokens": True,
            "B_artwork_width_height_mm": [b_bounds[1] - b_bounds[0], b_bounds[3] - b_bounds[2]],
            "B_contour_bounds_on_A_page_mm": list(b_bounds),
            "B_registration": b_anchors,
            "C_registration": c_anchors,
            "B_inverse_audit": inverse_vector_check(b_group, whole_ref, g, art, global_project),
            "C_inverse_audit": inverse_vector_check(c_text, c_ref, g, art, global_project),
        }
    (output / "nominal-vector-and-registration-audit.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result


def bind_manifest(output, config, source, code_fingerprint):
    files = {
        str(p.relative_to(output)): {
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(output.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    manifest = {
        "warning": WARNING,
        "baseline_commit": BASELINE,
        "research_code_fingerprint": code_fingerprint,
        "source_sha256": config["source_sha256"],
        "original_source_preserved": hashlib.sha256(source.read_bytes()).hexdigest()
        == config["source_sha256"],
        "inputs": config,
        "files": files,
        "native_windows_coreldraw_cutter_physical_tests": "NOT PERFORMED",
        "no_production_acceptance": True,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
