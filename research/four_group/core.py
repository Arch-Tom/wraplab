"""Research-only adapters around the unchanged WrapLab solver and converter."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import math
import xml.etree.ElementTree as ET

import numpy as np
from shapely.geometry import Polygon
from svgpathtools import parse_path

from wraplab.domain import ObjectSpec, Project
from wraplab.geometry.conformal import fit_profile
from wraplab.svg import import_svg
from wraplab.svg.exporter import export_svg, validate_serialized

BASELINE = "23181d3672dc11abc548412eb4d8316cf9bae422"
WARNING = "EXPERIMENTAL — NOT PRODUCTION APPROVED"


def mm(value):
    return float(Decimal(str(value)) * Decimal("25.4"))


def nominal_points(config):
    top = Decimal(config["physical_top_height_in"])
    return [
        (mm(top - Decimal(z)), mm(c))
        for z, c in config["stations_physical_height_and_circumference_in"]
    ]


def make_object(points):
    return ObjectSpec(
        mode="measured",
        name=WARNING + " — reconstructed nominal bell",
        measurement_type="circumference",
        points=points,
        notes="User-supplied nominal research measurements; not reconfirmed physical data.",
    )


def make_global(art, config, points=None, bottom_physical_in=None):
    obj = make_object(points if points is not None else nominal_points(config))
    p = Project(
        object=obj,
        artwork_frame="visible",
        source_svg=art.source,
        source_name="authenticated-uncompensated-research-source.svg",
        export_tolerance_mm=config["production_tolerance_mm"],
    )
    p.placement.height = mm(config["visible_height_in"])
    p.placement.width = p.placement.height * art.visible_frame.width / art.visible_frame.height
    bottom = Decimal(config["physical_top_height_in"]) - Decimal(
        str(
            bottom_physical_in
            if bottom_physical_in is not None
            else config["visible_bottom_physical_height_in"]
        )
    )
    p.placement.z = mm(bottom) - p.placement.height
    p.placement.x = config.get("global_front_center_mm", 0)
    return p


def groups(art, definitions):
    used = set()
    result = {}
    for definition in definitions:
        shape_index = definition["shape"]
        shape = art.shapes[shape_index]
        indices = definition["contours"]
        keys = [(shape_index, i) for i in indices]
        if len(set(keys)) != len(keys) or any(k in used for k in keys):
            raise ValueError("Missing or duplicate contour membership")
        used.update(keys)
        selected = replace(shape, subpaths=tuple(shape.subpaths[i] for i in indices))
        result[definition["id"]] = replace(art, shapes=(selected,))
    expected = {
        (si, ci) for si, shape in enumerate(art.shapes) for ci in range(len(shape.subpaths))
    }
    if used != expected:
        raise ValueError("Groups must partition every source contour exactly once")
    return result


def target_points(points, frame, global_project):
    points = np.asarray(points)
    p = global_project.placement
    x = p.x + p.width * ((points[:, 0] - frame.left) / frame.width - 0.5)
    z = p.z + p.height * (points[:, 1] - frame.top) / frame.height
    # The same exact intended endpoints used by the corrected production mapper.
    z = np.where(points[:, 1] == frame.top, p.z, z)
    z = np.where(points[:, 1] == frame.top + frame.height, p.z + p.height, z)
    return np.column_stack([x, z])


def group_project(group_art, whole_art, global_project):
    f = group_art.visible_frame
    corners = target_points(
        [[f.left, f.top], [f.left + f.width, f.top + f.height]],
        whole_art.visible_frame,
        global_project,
    )
    p = deepcopy(global_project)
    p.placement.x = float((corners[0, 0] + corners[1, 0]) / 2)
    p.placement.width = float(corners[1, 0] - corners[0, 0])
    p.placement.z = float(corners[0, 1])
    p.placement.height = float(corners[1, 1] - corners[0, 1])
    bottom = float(corners[1, 1])
    # Encode shared endpoints consistently, without relaxing any surface guard.
    for _ in range(2):
        if p.placement.z + p.placement.height == bottom:
            break
        p.placement.height = math.nextafter(
            p.placement.height,
            math.inf if p.placement.z + p.placement.height < bottom else -math.inf,
        )
    assert abs(p.placement.height - (corners[1, 1] - corners[0, 1])) < 1e-12
    return p


def support(project):
    p = project.placement
    return [p.x - p.width / 2, p.z, p.x + p.width / 2, p.z + p.height]


def production_fit(obj, bounds):
    left, top, right, bottom = bounds
    profile = obj.surface()
    if not 0 <= top < bottom <= profile.height:
        raise ValueError("Support outside measured domain; no extrapolation")
    zs = [top, bottom] + [z for z, _ in profile.points if top < z < bottom]
    if max(abs(left), abs(right)) >= 0.95 * min(profile.radius(z) for z in zs):
        raise ValueError("Support crosses visible-edge margin")
    return fit_profile(profile.points, top, bottom, left, right)


def source_samples(art, per_segment=9):
    values = []
    for shape in art.shapes:
        for sub in shape.subpaths:
            for segment in sub.segments:
                for t in np.linspace(0, 1, per_segment):
                    p = shape.transform(segment.point(t))
                    values.append((p.real, p.imag))
    return np.array(values)


def source_rings(art, per_segment=65):
    result = []
    for shape in art.shapes:
        rings = []
        for sub in shape.subpaths:
            values = []
            for segment in sub.segments:
                values.extend(
                    shape.transform(segment.point(t))
                    for t in np.linspace(0, 1, per_segment, endpoint=False)
                )
            rings.append(np.array([[p.real, p.imag] for p in values]))
        result.append(rings)
    return result


def vector_audit(text):
    root = ET.fromstring(text)
    assert root.get("width").endswith("mm") and root.get("height").endswith("mm")
    assert not root.findall(".//{*}image") and not root.findall(".//{*}text")
    assert [g.get("id") for g in root.findall("{*}g")] == ["Artwork"]
    all_keys = set()
    rows = []
    for element in root.findall(".//{*}path"):
        assert element.get("fill-rule") == "nonzero" and element.get("stroke") == "none"
        parts = parse_path(element.get("d")).continuous_subpaths()
        assert all(p.isclosed() for p in parts)
        polygons = [Polygon([(s.start.real, s.start.imag) for s in p]) for p in parts]
        assert all(p.is_valid and p.area > 0 for p in polygons)
        for p in polygons:
            key = p.normalize().wkb
            assert key not in all_keys
            all_keys.add(key)
        parents = [
            [j for j, outer in enumerate(polygons) if i != j and outer.contains(p)]
            for i, p in enumerate(polygons)
        ]
        winding = [1 if p.exterior.is_ccw else -1 for p in polygons]
        holes = [
            i
            for i, ancestors in enumerate(parents)
            if sum(winding[j] for j in ancestors) != 0
            and sum(winding[j] for j in ancestors) + winding[i] == 0
        ]
        rows.append(
            {
                "contours": len(polygons),
                "parents": parents,
                "winding": winding,
                "openings": len(holes),
            }
        )
    return rows


def check_membership(audit, definitions):
    membership = {(d["shape"], i): d["id"] for d in definitions for i in d["contours"]}
    for si, shape in enumerate(audit):
        for ci, parents in enumerate(shape["parents"]):
            for parent in parents:
                if membership[si, ci] != membership[si, parent]:
                    raise ValueError("Group selection splits a glyph/counter containment relation")


def experimental_svg(conversion, project, metadata):
    text = export_svg(conversion, project, "artwork", project.source_name)
    root = ET.fromstring(text)
    node = root.find("{*}metadata")
    data = json.loads(node.text)
    data["research"] = {"warning": WARNING, "baseline_commit": BASELINE, **metadata}
    node.text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    root.find("{*}title").text = WARNING
    ET.indent(root, space="  ")
    text = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    validate_serialized(text, conversion.paths, complex(*data["page_origin_mm"]))
    return text


def geometry_signature(text):
    r = ET.fromstring(text)
    return (r.attrib, [e.attrib for e in r.findall(".//{*}path")])


def split_global_svg(text, definition, condition="B"):
    # Reuse A's serialized tokens and common page. Do not round/translate/refit.
    root = ET.fromstring(text)
    group = root.find("{*}g")
    paths = list(group)
    selected = deepcopy(paths[definition["shape"]])
    tokens = ["M" + t for t in selected.get("d").split("M")[1:]]
    selected.set("d", "".join(tokens[i] for i in definition["contours"]).rstrip())
    for element in list(group):
        group.remove(element)
    group.append(selected)
    meta = root.find("{*}metadata")
    data = json.loads(meta.text)
    data["research"].update(
        condition=condition,
        group=definition["id"],
        geometry="Exact subset of A serialized coordinates; common A canvas retained",
    )
    meta.text = json.dumps(data, sort_keys=True)
    return ET.tostring(root, encoding="unicode") + "\n"


def alignment_difference(a, b):
    a, b = np.asarray(a), np.asarray(b)
    translation = np.mean(b - a, axis=0)
    differences = b - translation - a
    A, B = a - a.mean(axis=0), b - b.mean(axis=0)
    u, _, vt = np.linalg.svd(B.T @ A)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        u[:, -1] *= -1
        rotation = u @ vt
    residual = B @ rotation - A
    bbox_translation = (b.max(axis=0) + b.min(axis=0) - a.max(axis=0) - a.min(axis=0)) / 2
    return {
        "translation_only_mm": translation.tolist(),
        "rotation_removed_degrees": 0,
        "sampled_max_difference_mm": float(np.max(np.linalg.norm(differences, axis=1))),
        "sampled_rms_difference_mm": float(np.sqrt(np.mean(np.sum(differences**2, axis=1)))),
        "bbox_center_translation_max_difference_mm": float(
            np.max(np.linalg.norm(b - bbox_translation - a, axis=1))
        ),
        "separate_best_rigid_rotation_degrees": float(
            math.degrees(math.atan2(rotation[0, 1], rotation[0, 0]))
        ),
        "separate_best_rigid_sampled_max_mm": float(np.max(np.linalg.norm(residual, axis=1))),
        "sampling": "uniform samples per original segment; maxima are sampled, not certified",
    }


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_input(config_path):
    config = json.loads(config_path.read_text())
    from pathlib import Path

    source = Path(config["source_svg"])
    assert sha256(source) == config["source_sha256"]
    assert config["baseline_commit"] == BASELINE and config["frame"] == "visible"
    return config, source, import_svg(source.read_bytes().decode("utf-8-sig"))


def raw_source_audit(source, art):
    """Independent whole-path bounds for the authenticated untransformed mm source.

    Deliberately scoped to this experiment; transformed or page-scaled input needs
    a new explicit audit rather than silently applying this simple reference.
    """
    from defusedxml.ElementTree import fromstring

    root = fromstring(source.read_bytes())
    assert not any(e.get("transform") for e in root.iter())
    assert root.get("width").endswith("mm") and root.get("height").endswith("mm")
    page = [float(root.get(k)[:-2]) for k in ["width", "height"]]
    assert [float(x) for x in root.get("viewBox").split()] == [0, 0, *page]
    paths = [parse_path(e.get("d")) for e in root.findall(".//{*}path")]
    bounds = [p.bbox() for p in paths]
    left, right = min(b[0] for b in bounds), max(b[1] for b in bounds)
    top, bottom = min(b[2] for b in bounds), max(b[3] for b in bounds)
    actual = [left, top, right - left, bottom - top]
    frame = art.visible_frame
    discrepancy = max(
        abs(a - b)
        for a, b in zip(actual, [frame.left, frame.top, frame.width, frame.height], strict=True)
    )
    assert discrepancy < 1e-10
    return {
        "raw_svg_page_mm": page,
        "independent_whole_path_visible_frame_mm": actual,
        "import_frame_max_difference_mm": discrepancy,
        "raw_path_bounds_xmin_xmax_ymin_ymax_mm": bounds,
        "closed_contours_per_path": [
            sum(s.isclosed() for s in p.continuous_subpaths()) for p in paths
        ],
        "raw_source_segments": sum(len(p) for p in paths),
        "source_not_transformed_or_cropped": True,
        "shared_library": "svgpathtools curve parsing/bbox; whole paths independent of importer subpath splitting",
    }
