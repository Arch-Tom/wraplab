"""Nonlinear mapping of fills and outlined strokes, with contour/topology checks."""

import math
import time

from shapely.geometry import LineString, LinearRing, Polygon
from svgpathtools import Line

from .adaptive import MAX_NODES, certificate, curve_breakpoints, flatten
from .importer import length
from .model import Affine, Contour, Conversion, VectorPath


def signed_area(points):
    return (
        sum(
            a.real * b.imag - b.real * a.imag
            for a, b in zip(points, points[1:] + points[:1], strict=False)
        )
        / 2
    )


def validate_contours(before, after, name):
    source_polys, result_polys = [], []
    for source, target in zip(before, after, strict=True):
        if len(source) < 3 or len(target) < 3:
            raise ValueError(f"{name}: degenerate closed contour.")
        for points, polygons in [(source, source_polys), (target, result_polys)]:
            coords = [(p.real, p.imag) for p in points]
            if not LinearRing(coords).is_simple:
                raise ValueError(
                    f"{name}: self-intersecting contour. Repair or simplify the source."
                )
            polygon = Polygon(coords)
            if polygon.area < 1e-10:
                raise ValueError(f"{name}: contour has negligible area.")
            polygons.append(polygon)
        if signed_area(source) * signed_area(target) <= 0:
            raise ValueError(
                f"{name}: compensation inverted a contour; reduce coverage or change region."
            )
    for i in range(len(before)):
        for j in range(i):
            s, t = source_polys[i], source_polys[j]
            a, b = result_polys[i], result_polys[j]
            if s.boundary.intersects(t.boundary) or a.boundary.intersects(b.boundary):
                raise ValueError(
                    f"{name}: compound contours intersect/touch. Simplify them before export."
                )
            if (s.contains(t), t.contains(s)) != (a.contains(b), b.contains(a)):
                raise ValueError(f"{name}: compensation changed a counter/hole relationship.")


def convert_artwork(artwork, mapper, tolerance, placement_scale=1.0):
    paths, warnings = [], list(artwork.warnings)
    deadline = time.monotonic() + 120

    def identity(point):
        return point

    identity.derivative_bounds = (1, 0)
    identity.placement_affine = (1, 1)

    def within_canvas(point):
        if time.monotonic() > deadline:
            raise ValueError("Artwork conversion exceeded two minutes; simplify the source.")
        if not (
            -1e-6 <= point.real <= artwork.width_mm + 1e-6
            and -1e-6 <= point.imag <= artwork.height_mm + 1e-6
        ):
            raise ValueError(
                "Artwork extends beyond the SVG page. Fit the page to artwork in Corel first."
            )
        return point

    def mapped(point):
        return mapper(within_canvas(point))

    for shape in artwork.shapes:
        style = shape.style
        opacity = float(style["opacity"])
        before, after = [], []
        if (
            style["fill"] not in {"none", "transparent"}
            and opacity * float(style["fill-opacity"]) > 0
        ):
            for sub in shape.subpaths:
                segments = list(sub.segments)
                if not segments:
                    continue
                # SVG fills close open subpaths implicitly; line-only paths have no fill area.
                if segments[-1].end != segments[0].start:
                    segments.append(Line(segments[-1].end, segments[0].start))
                source_points, target_points = [], []
                for segment in segments:
                    cuts = curve_breakpoints(
                        segment, shape.transform, getattr(mapper, "profile_y", [])
                    )
                    source = flatten(
                        lambda t, s=segment, a=shape.transform: within_canvas(a(s.point(t))),
                        tolerance / (8 * max(placement_scale, 1)),
                        breakpoints=cuts,
                        error_bound=certificate(segment, shape.transform, identity),
                    )
                    target = flatten(
                        lambda t, s=segment, a=shape.transform: mapped(a(s.point(t))),
                        tolerance,
                        breakpoints=cuts,
                        error_bound=certificate(segment, shape.transform, mapper),
                    )
                    source_points.extend(source[:-1])
                    target_points.extend(target[:-1])
                if len(source_points) < 3 or abs(signed_area(source_points)) < 1e-10:
                    if all(isinstance(s, Line) for s in segments) and len(segments) <= 2:
                        continue
                    raise ValueError(f"{shape.name}: filled contour has zero area.")
                before.append(source_points)
                after.append(target_points)
            if after:
                validate_contours(before, after, shape.name)
                paths.append(
                    VectorPath(
                        [Contour(p) for p in after],
                        style["fill"],
                        style["fill-rule"],
                        opacity * float(style["fill-opacity"]),
                    )
                )
        if (
            style["stroke"] not in {"none", "transparent"}
            and opacity * float(style["stroke-opacity"]) > 0
        ):
            width = length(style["stroke-width"])
            if width < 0:
                raise ValueError("SVG stroke width cannot be negative.")
            if width == 0:
                continue
            local_tol = tolerance / (4 * max(shape.transform.scale_bound * placement_scale, 1))
            outline_before, outline_after = [], []
            caps = {"round": 1, "butt": 2, "square": 3}
            joins = {"round": 1, "miter": 2, "bevel": 3}
            angle = math.acos(max(-1, 1 - min(local_tol / (width / 2), 1)))
            quads = max(8, min(2048, math.ceil(math.pi / (4 * max(angle, 1e-8)))))
            for sub in shape.subpaths:
                points = []
                for segment in sub.segments:
                    points.extend(
                        flatten(
                            segment.point,
                            local_tol,
                            breakpoints=curve_breakpoints(segment, Affine()),
                            error_bound=certificate(segment, Affine(), identity),
                        )[:-1]
                    )
                points.append(sub.segments[-1].end)
                if sub.closed and points[-1] != points[0]:
                    points.append(points[0])
                if len(set(points)) < 2:
                    raise ValueError(
                        "Zero-length stroke is unsupported; convert it to a filled path."
                    )
                geometry = LineString([(p.real, p.imag) for p in points]).buffer(
                    width / 2,
                    quad_segs=quads,
                    cap_style=caps[style["stroke-linecap"]],
                    join_style=joins[style["stroke-linejoin"]],
                    mitre_limit=float(style["stroke-miterlimit"]),
                )
                polygons = [geometry] if geometry.geom_type == "Polygon" else list(geometry.geoms)
                for polygon in polygons:
                    for ring in [polygon.exterior, *polygon.interiors]:
                        local = [complex(x, y) for x, y in ring.coords][:-1]
                        source = [within_canvas(shape.transform(p)) for p in local]
                        target = []
                        for a, b in zip(source, source[1:] + source[:1], strict=False):
                            cuts = [
                                (y - a.imag) / (b.imag - a.imag)
                                for y in getattr(mapper, "profile_y", [])
                                if abs(b.imag - a.imag) > 1e-12
                            ]
                            target.extend(
                                flatten(
                                    lambda t, a=a, b=b: mapped(a + (b - a) * t),
                                    tolerance,
                                    breakpoints=cuts,
                                    error_bound=certificate(Line(a, b), Affine(), mapper),
                                )[:-1]
                            )
                        outline_before.append(source)
                        outline_after.append(target)
            validate_contours(outline_before, outline_after, f"{shape.name} stroke")
            paths.append(
                VectorPath(
                    [Contour(p) for p in outline_after],
                    style["stroke"],
                    "nonzero",
                    opacity * float(style["stroke-opacity"]),
                )
            )
            if (
                "Strokes converted to filled outlines for physical-width compensation."
                not in warnings
            ):
                warnings.append(
                    "Strokes converted to filled outlines for physical-width compensation."
                )
        if sum(len(c.points) for p in paths for c in p.contours) > MAX_NODES:
            raise ValueError(
                "Artwork exceeds 200,000 output nodes. Simplify the source or increase tolerance."
            )
    if not paths:
        raise ValueError("SVG contains no nondegenerate visible artwork.")
    return Conversion(paths, warnings, tolerance)
