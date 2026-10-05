"""One support-patch conformal near-cone fit (Mote Packet B); no material simulation."""

from functools import lru_cache
import math

from scipy.integrate import quad

from .surfaces import MeasuredProfile, sinc
from .units import finite


def exprel(t):
    if abs(t) < 1e-5:
        return 1 + t / 2 + t * t / 6 + t**3 / 24 + t**4 / 120
    return math.expm1(t) / t


class ConformalDevelopment:
    status = "Best-Fit / Experimental"
    algorithm = "pchip-conformal-support-fit-v1"

    def __init__(self, profile, z_min, z_max, x_left=None, x_right=None, angular_width=math.pi):
        self.profile = profile
        self.height = profile.height
        self.z_min, self.z_max = finite(z_min), finite(z_max)
        if not 0 <= z_min < z_max <= self.height:
            raise ValueError(
                "Conformal support must be inside the measured height with positive extent."
            )
        self.z_ref = (z_min + z_max) / 2
        self.r_ref = profile.radius(self.z_ref)
        self.x_left, self.x_right = x_left, x_right
        self.angular_width = angular_width
        self._u_cache = {}
        self._u_cumulative = [0.0]
        for (a, _), (b, _) in zip(profile.points, profile.points[1:], strict=False):
            result, _ = quad(self._density, a, b, epsabs=1e-12, epsrel=1e-10)
            self._u_cumulative.append(self._u_cumulative[-1] + result)
        self._u_ref = self._absolute_u(self.z_ref)
        stations = [z_min] + [z for z, _ in profile.points if z_min < z < z_max] + [z_max]

        def denominator(z):
            u = self.coordinate(z)
            return self.support_width(z) * math.hypot(1, profile.radial_derivative(z)) * u * u

        def numerator(z):
            r = profile.radius(z)
            u = self.coordinate(z)
            return (
                self.support_width(z)
                * math.hypot(1, profile.radial_derivative(z))
                * u
                * math.log1p((r - self.r_ref) / self.r_ref)
            )

        # Scale absolute quadrature tolerance to the dimensionful integral, not a universal cutoff.
        scale = (
            self.support_width(self.z_ref)
            * (z_max - z_min)
            * max(abs(self.coordinate(z_min)), abs(self.coordinate(z_max))) ** 2
        )
        eps = max(1e-300, scale * 1e-11)
        den = math.fsum(
            quad(denominator, a, b, epsabs=eps, epsrel=1e-10)[0]
            for a, b in zip(stations, stations[1:], strict=False)
        )
        num = math.fsum(
            quad(numerator, a, b, epsabs=eps, epsrel=1e-10)[0]
            for a, b in zip(stations, stations[1:], strict=False)
        )
        self.fallback = den <= 1e-290
        self.k = profile.slope(self.z_ref) if self.fallback else num / den
        if not math.isfinite(self.k) or abs(self.k) > 1 + 1e-9:
            raise ValueError(
                "Conformal fit produced an invalid slope; inspect the measured profile."
            )
        # Packet B uses the artwork reference anchor. Translate only, to top-center Y=0.
        u_top = self.coordinate(0)
        self.origin_y = self.r_ref * u_top * exprel(self.k * u_top)

    @property
    def fan_slope(self):
        return self.k

    def radius(self, z):
        return self.profile.radius(z)

    def distance(self, z):
        return self.profile.distance(z)

    def slope(self, z):
        return self.profile.slope(z)

    def support_width(self, z):
        r = self.radius(z)
        if self.x_left is None:
            return r * self.angular_width
        if not self.x_left < self.x_right or max(abs(self.x_left), abs(self.x_right)) >= r:
            raise ValueError("The carrier/support rectangle crosses the visible edge.")
        return r * (math.asin(self.x_right / r) - math.asin(self.x_left / r))

    def _density(self, z):
        return math.hypot(1, self.profile.radial_derivative(z)) / self.radius(z)

    def _absolute_u(self, z):
        self.radius(z)  # no extrapolation
        if z in self._u_cache:
            return self._u_cache[z]
        index = 0
        for i, (height, _) in enumerate(self.profile.points):
            if height <= z:
                index = i
        if index == len(self.profile.points) - 1:
            return self._u_cumulative[-1]
        value = (
            self._u_cumulative[index]
            + quad(self._density, self.profile.points[index][0], z, epsabs=1e-12, epsrel=1e-10)[0]
        )
        if len(self._u_cache) > 32768:
            self._u_cache.clear()
        self._u_cache[z] = value
        return value

    def coordinate(self, z):
        value = self._absolute_u(z) - self._u_ref
        if abs(value) < 1e-8:
            value = quad(self._density, self.z_ref, z, epsabs=1e-14, epsrel=1e-10)[0]
        return value

    def log_scale(self, z):
        r = self.radius(z)
        return self.k * self.coordinate(z) - math.log1p((r - self.r_ref) / self.r_ref)

    def scale(self, z):
        return math.exp(self.log_scale(z))

    def application_strain(self, z):
        return math.expm1(-self.log_scale(z))

    def develop(self, theta, z):
        u = self.coordinate(z)
        ku = self.k * u
        if abs(ku) > 100:
            raise ValueError("Conformal pattern has excessive scale; reduce the support region.")
        r = self.r_ref * math.exp(ku)
        angle = self.k * finite(theta)
        return (
            r * theta * sinc(angle),
            self.r_ref * u * exprel(ku)
            - r * self.k * theta**2 / 2 * sinc(angle / 2) ** 2
            - self.origin_y,
        )

    def diagnostic_stations(self):
        zs = [self.z_min, self.z_max, self.z_ref]
        zs += [z for z, _ in self.profile.points if self.z_min <= z <= self.z_max]
        if abs(self.k) < 1 and isinstance(self.profile, MeasuredProfile):
            target = self.k / math.sqrt(1 - self.k * self.k)
            zs += [
                float(z)
                for z in self.profile._dr.solve(target, extrapolate=False)
                if math.isfinite(z) and self.z_min <= z <= self.z_max
            ]
        else:
            zs += [self.z_min + (self.z_max - self.z_min) * i / 128 for i in range(129)]
        return sorted(set(zs))

    def strain_extrema(self):
        strains = [self.application_strain(z) for z in self.diagnostic_stations()]
        return min(strains), max(strains)

    def derivative_bounds(self, physical_model, x_max=0, reference_radius=1):
        """Analytical PCHIP derivative bounds, with numerical u/k rather than intervals."""
        p = self.profile
        stations = [self.z_min, self.z_max] + [
            z for z, _ in p.points if self.z_min < z < self.z_max
        ]
        stations += [
            float(z)
            for z in p._dr.derivative().roots(extrapolate=False)
            if math.isfinite(z) and self.z_min <= z <= self.z_max
        ]
        r_min = min(p.radius(z) for z in stations)
        a = max(abs(p.radial_derivative(z)) for z in stations)
        b = 0
        for i, (z, _) in enumerate(p.points[:-1]):
            end = p.points[i + 1][0]
            if end >= self.z_min and z <= self.z_max:
                b = max(
                    b,
                    abs(2 * p._dr.c[0, i] * (max(z, self.z_min) - z) + p._dr.c[1, i]),
                    abs(2 * p._dr.c[0, i] * (min(end, self.z_max) - z) + p._dr.c[1, i]),
                )
        q = math.hypot(1, a)
        uz = q / r_min
        uzz = a * b / r_min + q * a / r_min**2
        r_flat = max(
            self.r_ref * math.exp(self.k * self.coordinate(z)) for z in [self.z_min, self.z_max]
        )
        if physical_model == "front-view-vinyl":
            eta = abs(x_max) / r_min
            if eta >= 1:
                raise ValueError("Front support lies outside the visible surface.")
            c = math.sqrt(1 - eta * eta)
            tx = 1 / (r_min * c)
            tz = eta * a / (r_min * c)
            txx = eta / (r_min * r_min * c**3)
            txz = a / (r_min * r_min * c**3)
            tzz = (
                eta * b / (r_min * c)
                + 2 * eta * a * a / (r_min * r_min * c)
                + eta**3 * a * a / (r_min * r_min * c**3)
            )
            tgrad = math.hypot(tx, tz)
            thess = txx + 2 * txz + tzz
        else:
            tgrad = 1 / reference_radius
            thess = 0
        return (
            r_flat * math.hypot(uz, tgrad),
            r_flat * (abs(self.k) * (uz + tgrad) ** 2 + uzz + thess),
        )

    def metadata(self):
        low, high = self.strain_extrema()
        return {
            "algorithm": self.algorithm,
            "k": self.k,
            "reference_z_mm": self.z_ref,
            "reference_radius_mm": self.r_ref,
            "support_z_mm": [self.z_min, self.z_max],
            "support_front_x_mm": None if self.x_left is None else [self.x_left, self.x_right],
            "anchor": "top-center-translation",
            "reference_anchor_y_mm": -self.origin_y,
            "application_strain_min": low,
            "application_strain_max": high,
            "local_fit_fallback": self.fallback,
        }


@lru_cache(maxsize=32)
def fit_profile(points, z_min, z_max, x_left=None, x_right=None, angular_width=math.pi):
    return ConformalDevelopment(
        MeasuredProfile(points), z_min, z_max, x_left, x_right, angular_width
    )
