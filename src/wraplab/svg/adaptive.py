"""Adaptive polyline approximation in final physical coordinates, with explicit budgets."""

import math
import time

import numpy as np
from svgpathtools import Arc

MAX_NODES = 200_000


def segment_distance(point, a, b):
    vector = b - a
    if abs(vector) < 1e-14:
        return abs(point - a)
    t = max(
        0,
        min(
            1, ((point - a).real * vector.real + (point - a).imag * vector.imag) / abs(vector) ** 2
        ),
    )
    return abs(point - (a + t * vector))


def flatten(evaluate, tolerance: float, max_depth=20, breakpoints=(), error_bound=None):
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Curve tolerance must be positive.")
    result = [evaluate(0)]
    evaluations = {0.0: result[0], 1.0: evaluate(1)}
    deadline = time.monotonic() + 30

    def at(t):
        if t not in evaluations:
            evaluations[t] = evaluate(t)
        point = evaluations[t]
        if not math.isfinite(point.real) or not math.isfinite(point.imag) or abs(point) > 1e8:
            raise ValueError("Transformation generated invalid or excessive coordinates.")
        return point

    def recurse(start, end, depth):
        if time.monotonic() > deadline:
            raise ValueError(
                "Curve processing exceeded 30 seconds. Simplify artwork or reduce coverage."
            )
        a, b = at(start), at(end)
        samples = [at(start + (end - start) * i / 8) for i in range(1, 8)]
        error = max(segment_distance(p, a, b) for p in samples)
        # A second criterion prevents backtracking on apparently collinear loops/cusps.
        chain = [a, *samples, b]
        excess = sum(abs(y - x) for x, y in zip(chain, chain[1:], strict=False)) - abs(b - a)
        bounded = error_bound is None or error_bound(start, end) <= tolerance / 2
        if bounded and error <= tolerance / 2 and excess <= tolerance / 2:
            result.append(b)
            if len(result) > MAX_NODES:
                raise ValueError(
                    "Curve exceeds the node budget. Use simpler artwork or a larger tolerance."
                )
            return
        if depth >= max_depth:
            raise ValueError("Unable to meet curve tolerance; export was stopped.")
        mid = (start + end) / 2
        recurse(start, mid, depth + 1)
        recurse(mid, end, depth + 1)

    cuts = [0, *sorted(set(t for t in breakpoints if 1e-12 < t < 1 - 1e-12)), 1]
    for start, end in zip(cuts, cuts[1:], strict=False):
        recurse(start, end, 0)
    return result


def certificate(segment, affine, mapper):
    """Bound second derivative of the composed exact map using Packet A's Hessian.

    Bézier derivatives use convex-hull bounds; ellipse derivatives use their operator norm.
    Measured-profile derivatives use numerical quadrature, not interval certification.
    """
    bounds = getattr(mapper, "derivative_bounds", None)
    if bounds is None:
        return None
    j, h = bounds
    sx, sy = mapper.placement_affine

    def vector(p):
        return complex(
            sx * (affine.a * p.real + affine.c * p.imag),
            sy * (affine.b * p.real + affine.d * p.imag),
        )

    def error(start, end):
        leaf = segment.cropped(start, end)
        if isinstance(leaf, Arc):
            rotation = complex(
                math.cos(math.radians(leaf.rotation)), math.sin(math.radians(leaf.rotation))
            )
            a, b = vector(rotation * leaf.radius.real), vector(rotation * 1j * leaf.radius.imag)
            norm = np.linalg.svd([[a.real, b.real], [a.imag, b.imag]], compute_uv=False)[0]
            delta = abs(math.radians(leaf.delta))
            first, second = norm * delta, norm * delta**2
        else:
            points = [vector(p) for p in leaf.bpoints()]
            degree = len(points) - 1
            first = max(
                (abs(degree * (b - a)) for a, b in zip(points, points[1:], strict=False)), default=0
            )
            second = max(
                (
                    abs(degree * (degree - 1) * (points[i + 2] - 2 * points[i + 1] + points[i]))
                    for i in range(len(points) - 2)
                ),
                default=0,
            )
        return (h * first * first + j * second) / 8

    return error


def curve_breakpoints(segment, affine, profile_y=()):
    """Split at exact coordinate extrema and every measured-height crossing.

    This prevents a short high-curvature measured interval from hiding between adaptive samples.
    """
    points = []
    if isinstance(segment, Arc):
        rotation = complex(
            math.cos(math.radians(segment.rotation)), math.sin(math.radians(segment.rotation))
        )
        center = affine(segment.center)
        cos_point = affine(segment.center + rotation * segment.radius.real) - center
        sin_point = affine(segment.center + rotation * 1j * segment.radius.imag) - center
        start, delta = math.radians(segment.theta), math.radians(segment.delta)
        for component, levels in [("real", []), ("imag", profile_y)]:
            a, b, c = (
                getattr(cos_point, component),
                getattr(sin_point, component),
                getattr(center, component),
            )
            phase = math.atan2(b, a)
            angles = [phase, phase + math.pi]
            amplitude = math.hypot(a, b)
            for level in levels:
                if amplitude > 1e-14 and abs((level - c) / amplitude) <= 1:
                    angle = math.acos((level - c) / amplitude)
                    angles.extend([phase + angle, phase - angle])
            for angle in angles:
                for turn in range(-3, 4):
                    t = (angle + turn * 2 * math.pi - start) / delta
                    if 0 < t < 1:
                        points.append(t)
    else:
        coefficients = segment.poly().coeffs
        x = np.array([affine.a * p.real + affine.c * p.imag for p in coefficients])
        y = np.array([affine.b * p.real + affine.d * p.imag for p in coefficients])
        x[-1] += affine.e
        y[-1] += affine.f
        equations = [np.polyder(x), np.polyder(y)]
        for level in profile_y:
            equation = y.copy()
            equation[-1] -= level
            equations.append(equation)
        for equation in equations:
            for root in np.roots(equation):
                if abs(root.imag) < 1e-9 and 0 < root.real < 1:
                    points.append(float(root.real))
    return points
