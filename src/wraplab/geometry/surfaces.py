"""Surface development, not a laser/rotary projection model. z is DOWN from labelled top."""

from dataclasses import dataclass
import math
from typing import Protocol

import numpy as np
from scipy.integrate import quad
from scipy.interpolate import PchipInterpolator

from .units import finite, positive


class Surface(Protocol):
    height: float
    status: str
    algorithm: str

    def radius(self, z: float) -> float: ...
    def distance(self, z: float) -> float: ...
    def slope(self, z: float) -> float: ...

    @property
    def fan_slope(self) -> float: ...


def _check_z(z: float, height: float) -> float:
    z = finite(z, "Axial position")
    if z < 0 or z > height:
        raise ValueError("Artwork lies outside the measured object height.")
    return z


@dataclass(frozen=True)
class Cylinder:
    diameter: float = 80.0
    height: float = 100.0
    status = "Exact"
    algorithm = "cylinder-development-v1"

    def __post_init__(self):
        positive(self.diameter, "Diameter")
        positive(self.height, "Axial height")

    def radius(self, z: float) -> float:
        _check_z(z, self.height)
        return self.diameter / 2

    def distance(self, z: float) -> float:
        return _check_z(z, self.height)

    def slope(self, z: float) -> float:
        _check_z(z, self.height)
        return 0.0

    @property
    def fan_slope(self):
        return 0.0


@dataclass(frozen=True)
class Frustum:
    bottom_diameter: float = 90.0
    top_diameter: float = 65.0
    height: float = 100.0
    status = "Exact"
    algorithm = "frustum-development-v1"

    def __post_init__(self):
        positive(self.bottom_diameter, "Bottom diameter")
        positive(self.top_diameter, "Top diameter")
        positive(self.height, "Axial height")

    @property
    def dr(self):
        return (self.bottom_diameter - self.top_diameter) / 2

    @property
    def slant_height(self):
        return math.hypot(self.height, self.dr)

    @property
    def fan_slope(self):
        return self.dr / self.slant_height

    @property
    def developed_radii(self) -> tuple[float, float] | None:
        if self.dr == 0:
            return None
        return tuple(
            d / (2 * abs(self.fan_slope)) for d in (self.top_diameter, self.bottom_diameter)
        )

    def sector_angle(self, wrap_degrees: float = 360.0):
        return abs(self.fan_slope) * math.radians(wrap_degrees)

    def radius(self, z: float):
        return self.top_diameter / 2 + self.dr * _check_z(z, self.height) / self.height

    def distance(self, z: float):
        return _check_z(z, self.height) * self.slant_height / self.height

    def slope(self, z: float):
        _check_z(z, self.height)
        return self.fan_slope


class MeasuredProfile:
    """PCHIP meridian; conformal support fit. Exact only for cylinder/straight truth cases."""

    status = "Best-Fit / Experimental"
    algorithm = "pchip-conformal-support-fit-v1"

    def __init__(self, points: tuple[tuple[float, float], ...] | list[tuple[float, float]]):
        if not 3 <= len(points) <= 30:
            raise ValueError("Enter 3–30 measured height/diameter points.")
        self.points = tuple((finite(z, "Height"), positive(d, "Diameter")) for z, d in points)
        zs = [p[0] for p in self.points]
        if abs(zs[0]) > 1e-10:
            raise ValueError("The first measured height must be zero (the labelled top).")
        if any(b - a < 1e-5 for a, b in zip(zs, zs[1:], strict=False)):
            raise ValueError("Heights must increase without duplicates; sort the table if needed.")
        self.height = positive(zs[-1], "Profile height")
        self._r = PchipInterpolator(zs, [p[1] / 2 for p in self.points], extrapolate=False)
        self._dr = self._r.derivative()
        self._cumulative = [0.0]
        for a, b in zip(zs, zs[1:], strict=False):
            length, _ = quad(self._speed, a, b, epsabs=1e-9, epsrel=1e-10)
            self._cumulative.append(self._cumulative[-1] + length)
        self._length = self._cumulative[-1]
        self._distance_cache = {}

    def _speed(self, z):
        return math.hypot(1, float(self._dr(z)))

    def radius(self, z: float):
        return float(self._r(_check_z(z, self.height)))

    def distance(self, z: float):
        z = _check_z(z, self.height)
        if z in self._distance_cache:
            return self._distance_cache[z]
        index = int(np.searchsorted([p[0] for p in self.points], z, side="right")) - 1
        if index >= len(self.points) - 1:
            return self._length
        partial, _ = quad(self._speed, self.points[index][0], z, epsabs=1e-9, epsrel=1e-10)
        value = self._cumulative[index] + partial
        if len(self._distance_cache) >= 32768:
            self._distance_cache.clear()
        self._distance_cache[z] = value
        return value

    def slope(self, z: float):
        derivative = float(self._dr(_check_z(z, self.height)))
        return derivative / math.hypot(1, derivative)

    def radial_derivative(self, z):
        return float(self._dr(_check_z(z, self.height)))

    def default_development(self):
        from .conformal import fit_profile

        return fit_profile(self.points, 0, self.height, angular_width=2 * math.pi)

    @property
    def fan_slope(self):
        return self.default_development().k


def sinc(x: float):
    if abs(x) < 1e-4:
        x2 = x * x
        return 1 - x2 / 6 + x2 * x2 / 120
    return math.sin(x) / x


def develop(surface: Surface, theta: float, z: float) -> tuple[float, float]:
    """Cancellation-free fan, translated to the central meridian. SVG y and z are down.

    X = r sin(k theta)/k; Y = s - r(1-cos(k theta))/k.
    k = dr/ds for a cone, 0 for a cylinder. Measured profiles delegate to their support fit.
    """
    if isinstance(surface, MeasuredProfile):
        return surface.default_development().develop(theta, z)
    if hasattr(surface, "develop"):
        return surface.develop(theta, z)
    r, s, k = surface.radius(z), surface.distance(z), surface.fan_slope
    angle = k * finite(theta, "Wrap angle")
    return (r * theta * sinc(angle), s - r * k * theta**2 / 2 * sinc(angle / 2) ** 2)


def principal_stretches(surface: Surface, theta: float, z: float) -> tuple[float, float]:
    """Singular values relative to the surface metric (r dtheta, ds). 1 = undistorted."""
    if isinstance(surface, MeasuredProfile):
        value = surface.default_development().scale(z)
        return value, value
    if hasattr(surface, "scale"):
        value = surface.scale(z)
        return value, value
    k, q = surface.fan_slope, surface.slope(z)
    angle = k * theta
    a = np.array(
        [
            [math.cos(angle), q * theta * sinc(angle)],
            [math.sin(angle), -1 + q * k * theta**2 / 2 * sinc(angle / 2) ** 2],
        ]
    )
    values = np.linalg.svd(a, compute_uv=False)
    return float(values[-1]), float(values[0])
