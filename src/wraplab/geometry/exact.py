"""Packet A derivative bounds, inverse, and exact template bounds; no Qt/SVG dependency."""

import math

from .surfaces import Cylinder, Frustum, develop
from .units import finite


def front_derivative_bounds(surface, x_max, z_min, z_max):
    if not isinstance(surface, (Cylinder, Frustum)):
        return None
    r_min = min(surface.radius(z_min), surface.radius(z_max))
    eta = abs(x_max) / r_min
    if eta >= 1:
        raise ValueError("Front artwork is outside the visible surface.")
    a = surface.dr / surface.height if isinstance(surface, Frustum) else 0
    g = math.hypot(1, a)
    k = surface.fan_slope
    j = g / math.sqrt(1 - eta**2)
    h = (
        math.sqrt(k * k + (1 - k * k) * eta * eta)
        * (1 + a * a * eta * eta)
        / (r_min * (1 - eta * eta) ** 1.5)
    )
    return j, h


def intrinsic_derivative_bounds(surface, reference_radius, z_min, z_max):
    if not isinstance(surface, (Cylinder, Frustum)):
        return None
    r_max = max(surface.radius(z_min), surface.radius(z_max))
    a = surface.dr / surface.height if isinstance(surface, Frustum) else 0
    j = max(r_max / reference_radius, math.hypot(1, a))
    h = r_max * abs(surface.fan_slope) / reference_radius**2 + 2 * abs(a) / reference_radius
    return j, h


def inverse_develop(surface, point: complex):
    """Stable inverse for the centered single-wrap exact domain, before page translation."""
    if not isinstance(surface, (Cylinder, Frustum)):
        raise ValueError(
            "An analytical inverse is available only for exact cylinder/frustum surfaces."
        )
    x, y = finite(point.real), finite(point.imag)
    r0, k = surface.radius(0), surface.fan_slope
    if k == 0:
        theta, z = x / r0, y
    else:
        r = math.hypot(k * x, r0 + k * y)
        theta = math.atan2(k * x, r0 + k * y) / k
        s = (2 * r0 * y + k * (x * x + y * y)) / (r + r0)
        z = s * surface.height / surface.slant_height
    # Undo binary64 roundoff of the inverse only; source coordinate APIs never clamp.
    error = 64 * math.ulp(max(1, surface.height, abs(y)))
    if -error <= z < 0:
        z = 0
    elif surface.height < z <= surface.height + error:
        z = surface.height
    surface.radius(z)
    if abs(theta) > math.pi + 1e-9:
        raise ValueError("Point is outside the centered single-wrap development.")
    return theta, z


def development_bounds(surface, wrap_degrees=360):
    if not isinstance(surface, (Cylinder, Frustum)):
        raise ValueError("Exact boundary bounds are available only for cylinder/frustum surfaces.")
    if not 0 < finite(wrap_degrees) <= 360:
        raise ValueError("Coverage must be greater than zero and at most 360 degrees.")
    extent, k = math.radians(wrap_degrees) / 2, surface.fan_slope
    angles = [-extent, 0, extent]
    if k:
        angles += [
            i * math.pi / (2 * k) for i in range(-2, 3) if abs(i * math.pi / (2 * k)) <= extent
        ]
    points = [develop(surface, theta, z) for theta in angles for z in [0, surface.height]]
    return (
        min(x for x, y in points),
        min(y for x, y in points),
        max(x for x, y in points),
        max(y for x, y in points),
    )
