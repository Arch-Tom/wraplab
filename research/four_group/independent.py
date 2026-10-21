"""Independent Hermite interpolation and Gauss-Legendre fit/inverse checks.

Shares the mathematical objective with WrapLab, but not its PCHIP, quadrature,
fitter, mapper, or inverse implementation. Natural-cubic sensitivity deliberately
uses SciPy CubicSpline and is identified separately from the production method.
"""

import math

import numpy as np
from numpy.polynomial.legendre import leggauss


class Profile:
    def __init__(self, points, kind="pchip"):
        self.points = tuple(points)  # z, diameter mm
        self.x = np.array([z for z, _ in points], dtype=float)
        self.r = np.array([d / 2 for _, d in points], dtype=float)
        if self.x[0] != 0 or np.any(np.diff(self.x) <= 0) or np.any(self.r <= 0):
            raise ValueError("Reference profile needs increasing stations from exact zero.")
        self.height = self.x[-1]
        self.kind = kind
        h, delta = np.diff(self.x), np.diff(self.r) / np.diff(self.x)
        if kind == "natural-cubic":
            from scipy.interpolate import CubicSpline

            self.coeff = CubicSpline(self.x, self.r, bc_type="natural").c[::-1].T
        elif kind == "linear":
            self.coeff = np.column_stack([self.r[:-1], delta, np.zeros_like(h), np.zeros_like(h)])
        elif kind == "pchip":
            slopes = np.zeros(len(self.x))
            if len(self.x) == 2:
                slopes[:] = delta[0]
            else:
                for i in range(1, len(self.x) - 1):
                    if delta[i - 1] * delta[i] > 0:
                        w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
                        slopes[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])

                def endpoint(h0, h1, d0, d1):
                    value = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
                    if value * d0 <= 0:
                        return 0.0
                    return 3 * d0 if d0 * d1 < 0 and abs(value) > abs(3 * d0) else value

                slopes[0] = endpoint(h[0], h[1], delta[0], delta[1])
                slopes[-1] = endpoint(h[-1], h[-2], delta[-1], delta[-2])
            self.coeff = np.column_stack(
                [
                    self.r[:-1],
                    slopes[:-1],
                    (3 * delta - 2 * slopes[:-1] - slopes[1:]) / h,
                    (slopes[:-1] + slopes[1:] - 2 * delta) / h**2,
                ]
            )
        else:
            raise ValueError("Unknown reference interpolation")
        if min(self.radius(z) for z in self.stationary(0, radius=True)) <= 0:
            raise ValueError("Interpolation has a nonpositive radius")

    def evaluate(self, z, derivative=False):
        z = np.asarray(z, dtype=float)
        if np.any(z < 0) or np.any(z > self.height):
            raise ValueError("Reference evaluation outside measured domain")
        index = np.minimum(np.searchsorted(self.x, z, side="right") - 1, len(self.x) - 2)
        t = z - self.x[index]
        c = self.coeff[index]
        return (
            (3 * c[..., 3] * t + 2 * c[..., 2]) * t + c[..., 1]
            if derivative
            else ((c[..., 3] * t + c[..., 2]) * t + c[..., 1]) * t + c[..., 0]
        )

    def radius(self, z):
        return self.evaluate(z)

    def derivative(self, z):
        return self.evaluate(z, True)

    def stationary(self, target, radius=False):
        # Radius extrema and log-scale extrema both solve r'(z)=a constant.
        target = 0 if radius else target
        result = list(self.x)
        for i, c in enumerate(self.coeff):
            coefficients = np.trim_zeros([3 * c[3], 2 * c[2], c[1] - target], "f")
            for root in np.roots(coefficients) if len(coefficients) > 1 else []:
                if abs(root.imag) < 1e-10 and 0 < root.real < self.x[i + 1] - self.x[i]:
                    result.append(float(self.x[i] + root.real))
        return result

    def integral_density(self, z, order=64):
        z = np.asarray(z, dtype=float)
        if np.any(z < 0) or np.any(z > self.height):
            raise ValueError("Reference integration outside measured domain")
        original_shape = z.shape
        z = z.ravel()
        result = np.zeros_like(z)
        nodes, weights = quadrature(order)
        for a, b in zip(self.x[:-1], self.x[1:], strict=True):
            lengths = np.maximum(0, np.minimum(z, b) - a)
            active = lengths > 0
            t = a + lengths[active, None] * (nodes + 1) / 2
            density = np.hypot(1, self.derivative(t)) / self.radius(t)
            result[active] += lengths[active] / 2 * (density @ weights)
        return result.reshape(original_shape)


_QUADRATURE = {}


def quadrature(order):
    if order not in _QUADRATURE:
        _QUADRATURE[order] = leggauss(order)
    return _QUADRATURE[order]


def exprel(t):
    t = np.asarray(t)
    out = np.ones_like(t, dtype=float)
    np.divide(np.expm1(t), t, out=out, where=t != 0)
    return out


class Fit:
    def __init__(self, profile, support, order=64, production_parameters=None):
        self.profile, self.support, self.order = profile, tuple(support), order
        left, top, right, bottom = self.support
        if not (0 <= top < bottom <= profile.height and left < right):
            raise ValueError("Support outside measured domain")
        radius_checks = [top, bottom] + [z for z in profile.stationary(0, True) if top < z < bottom]
        if max(abs(left), abs(right)) >= 0.95 * min(profile.radius(z) for z in radius_checks):
            raise ValueError("Support crosses the front visible-edge margin")
        self.z_ref = (top + bottom) / 2
        self.r_ref = float(profile.radius(self.z_ref))
        self.u_ref = float(profile.integral_density(self.z_ref, order))
        nodes, weights = quadrature(order)
        cuts = [top] + [z for z in profile.x if top < z < bottom] + [bottom]
        num = den = 0.0
        for a, b in zip(cuts[:-1], cuts[1:], strict=True):
            z = a + (b - a) * (nodes + 1) / 2
            r, q, u = profile.radius(z), np.hypot(1, profile.derivative(z)), self.coordinate(z)
            w = r * (np.arcsin(right / r) - np.arcsin(left / r))
            num += (b - a) / 2 * float(weights @ (w * q * u * np.log(r / self.r_ref)))
            den += (b - a) / 2 * float(weights @ (w * q * u**2))
        self.k = num / den
        if not math.isfinite(self.k) or abs(self.k) > 1 + 1e-9:
            raise ValueError("Invalid independent fit")
        u0 = float(self.coordinate(0))
        self.origin_y = float(self.r_ref * u0 * exprel(self.k * u0))
        self.independent_k = self.k
        if production_parameters is not None:
            assert abs(self.k - production_parameters["k"]) < 2e-10
            assert abs(self.r_ref - production_parameters["reference_radius_mm"]) < 1e-9
            assert abs(self.origin_y + production_parameters["reference_anchor_y_mm"]) < 1e-8
            # Sensitivity coordinates use the actual production fit parameters,
            # with independent vectorized density integration cross-checked above.
            self.k = production_parameters["k"]
            self.origin_y = -production_parameters["reference_anchor_y_mm"]

    def coordinate(self, z):
        return self.profile.integral_density(z, self.order) - self.u_ref

    def strain(self, z):
        return np.expm1(np.log(self.profile.radius(z) / self.r_ref) - self.k * self.coordinate(z))

    def extrema(self):
        _, top, _, bottom = self.support
        if abs(self.k) >= 1:
            raise ValueError("Extrema stationary formula requires |k|<1")
        target = self.k / math.sqrt(1 - self.k**2)
        z = np.array(
            sorted(
                set(
                    [top, bottom, self.z_ref]
                    + [z for z in self.profile.stationary(target) if top <= z <= bottom]
                )
            )
        )
        strains = self.strain(z)
        lo, hi = int(np.argmin(strains)), int(np.argmax(strains))
        return {
            "minimum_signed": float(strains[lo]),
            "maximum_signed": float(strains[hi]),
            "extension": max(0.0, float(strains[hi])),
            "compression": max(0.0, -float(strains[lo])),
            "min_z_mm": float(z[lo]),
            "max_z_mm": float(z[hi]),
            "stations_mm": z.tolist(),
            "method": "piecewise polynomial stationary roots and boundaries",
        }

    def mapping(self, points):
        points = np.asarray(points, dtype=float)
        x, z = points[..., 0], points[..., 1]
        r = self.profile.radius(z)
        if np.any(abs(x / r) >= 0.95):
            raise ValueError("Front sample outside visible margin")
        theta, u = np.arcsin(x / r), self.coordinate(z)
        R = self.r_ref * np.exp(self.k * u)
        angle = self.k * theta
        X = R * theta * np.sinc(angle / np.pi)
        Y = (
            self.r_ref * u * exprel(self.k * u)
            - R * self.k * theta**2 / 2 * np.sinc(angle / (2 * np.pi)) ** 2
            - self.origin_y
        )
        return np.stack([X, Y], axis=-1)

    def inverse(self, points, flat_residual_limit_mm=3e-6):
        # Audit only. Bisection stays within measured z. Endpoint ambiguity is
        # accepted only if forward residual fits the explicit SVG rounding budget.
        points = np.asarray(points, dtype=float)
        X, Y = points[:, 0], points[:, 1] + self.origin_y
        if abs(self.k) < 1e-12:
            theta, wanted_u = X / self.r_ref, Y / self.r_ref
        else:
            theta = np.arctan2(self.k * X, self.r_ref + self.k * Y) / self.k
            t = 2 * self.k * Y / self.r_ref + (self.k / self.r_ref) ** 2 * (X**2 + Y**2)
            if np.any(t <= -1):
                raise ValueError("Flat sample outside independent inverse")
            wanted_u = np.log1p(t) / (2 * self.k)
        low = np.zeros(len(X))
        high = np.full(len(X), self.profile.height)
        for _ in range(42):
            mid = (low + high) / 2
            lower = self.coordinate(mid) < wanted_u
            low = np.where(lower, mid, low)
            high = np.where(lower, high, mid)
        z = (low + high) / 2
        front = np.stack([self.profile.radius(z) * np.sin(theta), z], axis=-1)
        residual = np.linalg.norm(self.mapping(front) - points, axis=1)
        if np.max(residual) > flat_residual_limit_mm:
            raise ValueError("Inverse sample exceeds rounding budget or measured domain")
        return front, float(np.max(residual))
