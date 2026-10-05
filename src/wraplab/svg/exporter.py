"""Canonical, deterministic, physical-mm SVG. No live text, resources, or transforms."""

import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from .. import __version__
from ..geometry.surfaces import develop
from ..persistence import atomic_write
from .adaptive import flatten
from .model import Contour, VectorPath
from .transform import convert_artwork, validate_contours

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def convert(artwork, project, preview=False, original=False):
    project.validate()
    tolerance = max(0.08, project.export_tolerance_mm) if preview else project.export_tolerance_mm
    scale = max(
        project.placement.width / artwork.width_mm, project.placement.height / artwork.height_mm
    )
    mapper = (
        (
            lambda p: complex(
                p.real * project.placement.width / artwork.width_mm,
                p.imag * project.placement.height / artwork.height_mm,
            )
        )
        if original
        else project.mapper(artwork.width_mm, artwork.height_mm)
    )
    if original:
        mapper.derivative_bounds = (1, 0)
        mapper.placement_affine = (
            project.placement.width / artwork.width_mm,
            project.placement.height / artwork.height_mm,
        )
    amplification = 1 if original else project.mapping_scale_bound()
    conversion = convert_artwork(artwork, mapper, tolerance, scale * amplification)
    if not original:
        conversion.warnings += project.profile_warnings()
    return conversion


def guides(project, tolerance=0.02):
    surface = project.validate(False)
    development = project.development(surface)
    extent = math.radians(project.wrap_degrees) / 2
    rotation = complex(
        math.cos(math.radians(project.rotation_degrees)),
        math.sin(math.radians(project.rotation_degrees)),
    )

    def point(theta, z):
        x, y = develop(development, theta, z)
        return complex(x, y) * rotation

    edges = [
        lambda t: point(-extent + 2 * extent * t, 0),
        lambda t: point(extent, surface.height * t),
        lambda t: point(extent - 2 * extent * t, surface.height),
        lambda t: point(-extent, surface.height * (1 - t)),
    ]
    boundary = []
    for edge in edges:
        boundary.extend(flatten(edge, tolerance)[:-1])
    # Exact row extrema must belong to the boundary, including aggressive sectors > pi.
    if development.fan_slope:
        k = development.fan_slope
        cuts = [
            (i * math.pi / (2 * k) + extent) / (2 * extent)
            for i in range(-2, 3)
            if -extent < i * math.pi / (2 * k) < extent
        ]
        boundary = []
        for index, edge in enumerate(edges):
            boundary.extend(
                flatten(
                    edge,
                    tolerance,
                    breakpoints=cuts if index == 0 else [1 - t for t in cuts] if index == 2 else [],
                )[:-1]
            )
    center = flatten(lambda t: point(0, surface.height * t), tolerance)
    midline = flatten(lambda t: point(-extent + 2 * extent * t, surface.height / 2), tolerance)
    return [
        VectorPath([Contour(boundary)], "none", stroke="#4b8295", stroke_width=0.15),
        VectorPath(
            [Contour(center, False), Contour(midline, False)],
            "none",
            stroke="#94a3b8",
            stroke_width=0.1,
        ),
    ]


def number(value):
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def path_data(path, offset):
    commands = []
    for contour in path.contours:
        if not contour.points:
            continue
        for i, point in enumerate(contour.points):
            p = point - offset
            commands.append(f"{'M' if i == 0 else 'L'}{number(p.real)} {number(p.imag)}")
        if contour.closed:
            commands.append("Z")
    return " ".join(commands)


def export_svg(conversion, project, mode="artwork", source_name=""):
    if mode not in {"artwork", "guides", "template", "original"}:
        raise ValueError("Unknown SVG export mode.")
    if mode in {"artwork", "guides", "original"} and conversion is None:
        raise ValueError("Import and compensate artwork before exporting.")
    artwork = conversion.paths if conversion is not None and mode != "template" else []
    guide_paths = (
        guides(project, project.export_tolerance_mm) if mode in {"guides", "template"} else []
    )
    all_paths = artwork + guide_paths
    points = [v for path in all_paths for c in path.contours for v in c.points]
    if not points:
        raise ValueError("Nothing to export.")
    # Allow guide strokes to remain inside the SVG viewport; production art gets no padding.
    padding = 0.15 if guide_paths else 0
    left, top = min(p.real for p in points) - padding, min(p.imag for p in points) - padding
    width = max(p.real for p in points) - left + padding
    height = max(p.imag for p in points) - top + padding
    if width <= 0 or height <= 0:
        raise ValueError("Export has degenerate bounds.")
    root = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "version": "1.1",
            "width": number(width) + "mm",
            "height": number(height) + "mm",
            "viewBox": f"0 0 {number(width)} {number(height)}",
        },
    )
    surface = project.validate(False)
    development = project.development(surface)
    ET.SubElement(root, f"{{{SVG_NS}}}title").text = "WrapLab — " + project.object.name
    ET.SubElement(root, f"{{{SVG_NS}}}metadata").text = json.dumps(
        {
            "wraplab_version": __version__,
            "physical_model": project.physical_model,
            "mode": "uncompensated" if mode == "original" else project.object.mode,
            "status": "Uncompensated" if mode == "original" else surface.status,
            "algorithm": development.algorithm,
            "development": development.metadata()
            if hasattr(development, "metadata")
            else {"application_strain": 0},
            "profile_name": project.object.name,
            "units": "mm",
            "display_units": project.units,
            "wrap_degrees": project.wrap_degrees,
            "reference_height_mm": surface.height / 2,
            "placement": vars(project.placement),
            "axial_direction": "down-from-labelled-top",
            "front_margin": project.front_margin,
            "view_assumption": "upright-object-horizontal-distant-orthographic"
            if project.physical_model == "front-view-vinyl"
            else "surface-wrap",
            "page_origin_mm": [left, top],
            "source_name": source_name,
            "tolerance_mm": project.export_tolerance_mm,
            "certificate_level": "analytical-affine"
            if mode == "original"
            else "analytical-derivatives-numerical-profile-quadrature"
            if project.object.mode == "measured"
            else "analytical-exact-surface",
            "warnings": (conversion.warnings if conversion else project.profile_warnings())
            + (
                ["Guide paths may cut; this group is not automatically noncutting."]
                if guide_paths
                else []
            ),
            "coreldraw_2019_verified": False,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    for group_name, paths in [("Artwork", artwork), ("Guides", guide_paths)]:
        if not paths:
            continue
        group = ET.SubElement(root, f"{{{SVG_NS}}}g", {"id": group_name})
        for i, path in enumerate(paths):
            attrs = {
                "id": f"{group_name}-{i + 1}",
                "d": path_data(path, complex(left, top)),
                "fill": path.fill,
                "fill-rule": path.fill_rule,
                "stroke": path.stroke,
            }
            if path.opacity != 1:
                attrs["opacity"] = number(path.opacity)
            if path.stroke != "none":
                attrs["stroke-width"] = number(path.stroke_width)
            ET.SubElement(group, f"{{{SVG_NS}}}path", attrs)
    ET.indent(root, space="  ")
    text = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    validate_serialized(text, all_paths, complex(left, top))
    return text


def validate_serialized(text, paths, offset):
    """Check rounded production outlines and dimensions; never repair changed topology."""
    from .importer import parse_subpaths

    root = ET.fromstring(text)
    w, h = float(root.get("width")[:-2]), float(root.get("height")[:-2])
    if [float(n) for n in root.get("viewBox").split()] != [0, 0, w, h] or w <= 0 or h <= 0:
        raise ValueError("Serialized SVG physical size is invalid.")
    elements = root.findall(".//{*}path")
    if len(elements) != len(paths):
        raise ValueError("Serialized SVG lost vector paths.")
    for element, path in zip(elements, paths, strict=True):
        parsed = parse_subpaths(element.get("d"), segment_limit=200_000)
        if len(parsed) != len(path.contours):
            raise ValueError("Serialized SVG lost compound contours.")
        before, after = [], []
        for sub, contour in zip(parsed, path.contours, strict=True):
            points = [segment.start for segment in sub.segments]
            if not contour.closed:
                points.append(sub.segments[-1].end)
            if not all(math.isfinite(p.real) and math.isfinite(p.imag) for p in points):
                raise ValueError("Serialized SVG has invalid coordinates.")
            if contour.closed and path.fill != "none":
                before.append([p - offset for p in contour.points])
                after.append(points)
        if before:
            validate_contours(before, after, "Serialized output")


def ideal_front_svg(artwork, project, preview=True):
    """Ideal orthographic view, not a simulation of material strain or actual application."""
    from .model import Conversion

    original = convert(artwork, project, preview=preview, original=True)
    surface = project.validate()
    outline = [
        complex(-surface.radius(surface.height * i / 160), surface.height * i / 160)
        for i in range(161)
    ]
    outline += [
        complex(surface.radius(surface.height * i / 160), surface.height * i / 160)
        for i in range(160, -1, -1)
    ]
    silhouette = VectorPath([Contour(outline)], "#e2ebef")
    shift = complex(project.placement.x - project.placement.width / 2, project.placement.z)
    paths = [silhouette]
    for path in original.paths:
        paths.append(
            VectorPath(
                [Contour([p + shift for p in c.points]) for c in path.contours],
                path.fill,
                path.fill_rule,
                path.opacity,
            )
        )
    return export_svg(Conversion(paths, [], original.tolerance_mm), project, "original")


def write_export(path: Path, text: str, source_path: Path | None = None):
    if source_path is not None and Path(path).resolve() == Path(source_path).resolve():
        raise ValueError("Choose a new filename. The imported source must remain untouched.")
    atomic_write(path, text)
