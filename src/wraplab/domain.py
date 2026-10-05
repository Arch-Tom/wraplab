"""Versioned, canonical-mm data. No Qt or SVG dependencies."""

from dataclasses import asdict, dataclass, field
import math

from .geometry.surfaces import Cylinder, Frustum, MeasuredProfile, develop
from .geometry.conformal import fit_profile
from .geometry.units import Unit, finite, positive
from .geometry.exact import front_derivative_bounds, intrinsic_derivative_bounds


@dataclass
class ObjectSpec:
    mode: str = "cylinder"
    name: str = "Custom Cylinder"
    diameter: float = 80.0
    bottom_diameter: float = 90.0
    top_diameter: float = 65.0
    height: float = 100.0
    points: list[tuple[float, float]] = field(
        default_factory=lambda: [
            (0, 38.1),
            (9.525, 50.8),
            (15.875, 59.69),
            (22.225, 67.31),
            (28.575, 73.66),
            (34.925, 78.232),
            (41.275, 81.534),
            (47.625, 82.55),
        ]
    )
    algorithm_version: str = "z-down-surface-v1"
    interpolation_version: str = "pchip-v1"
    profile_algorithm_version: str = "conformal-support-v1"
    measurement_type: str = "diameter"
    measurement_uncertainty: float | None = None
    notes: str = ""

    def surface(self):
        if self.algorithm_version != "z-down-surface-v1":
            raise ValueError("This object uses an unsupported geometry version.")
        if (
            self.interpolation_version != "pchip-v1"
            or self.profile_algorithm_version != "conformal-support-v1"
        ):
            raise ValueError("Unsupported profile algorithm version.")
        if self.measurement_type not in {"diameter", "circumference"}:
            raise ValueError("Measurement type must be diameter or circumference.")
        if self.measurement_uncertainty is not None:
            positive(self.measurement_uncertainty, "Measurement uncertainty")
        if not isinstance(self.notes, str) or len(self.notes) > 4096:
            raise ValueError("Measurement notes must be text, up to 4096 characters.")
        if self.mode == "cylinder":
            return Cylinder(self.diameter, self.height)
        if self.mode == "frustum":
            return Frustum(self.bottom_diameter, self.top_diameter, self.height)
        if self.mode == "measured":
            return MeasuredProfile(
                [
                    (z, value / math.pi if self.measurement_type == "circumference" else value)
                    for z, value in self.points
                ]
            )
        raise ValueError("Unknown object mode.")


@dataclass
class Placement:
    width: float = 40.0
    height: float = 20.0
    x: float = 0.0  # front-view center offset; surface-wrap: arc distance from left seam
    z: float = 10.0  # artwork TOP height down from labelled object top
    lock_aspect: bool = True

    def validate(
        self, surface, wrap_degrees: float, physical_model="surface-template", margin=0.95
    ):
        positive(self.width, "Artwork width")
        positive(self.height, "Artwork height")
        finite(self.x, "Artwork horizontal position")
        finite(self.z, "Artwork top height")
        circumference = 2 * math.pi * surface.radius(surface.height / 2)
        extent = circumference * wrap_degrees / 360
        if physical_model == "surface-template" and (
            self.x < -1e-8 or self.x + self.width > extent + 1e-8
        ):
            raise ValueError(
                "Artwork crosses a seam. Reduce width or move it inside the wrap region."
            )
        if self.z < -1e-8 or self.z + self.height > surface.height + 1e-8:
            raise ValueError(
                "Artwork lies outside the object height. Reduce height or move it up/down."
            )
        if physical_model == "front-view-vinyl":
            zs = [self.z, self.z + self.height]
            if isinstance(surface, MeasuredProfile):
                zs += [z for z, _ in surface.points if self.z < z < self.z + self.height]
            radius = min(surface.radius(z) for z in zs)
            limit = min(margin, math.sin(min(math.pi / 2, math.radians(wrap_degrees) / 2)))
            if abs(self.x) + self.width / 2 >= radius * limit:
                raise ValueError(
                    "Artwork is too close to the visible edge or outside coverage. Reduce width or center it."
                )


@dataclass
class Project:
    object: ObjectSpec = field(default_factory=ObjectSpec)
    placement: Placement = field(default_factory=Placement)
    units: str = "mm"
    wrap_degrees: float = 180.0
    rotation_degrees: float = 0.0
    export_tolerance_mm: float = 0.01
    source_svg: str | None = None
    source_name: str = ""
    schema_version: int = 1
    physical_model: str = "front-view-vinyl"
    front_margin: float = 0.95

    def validate(self, artwork: bool = True):
        if self.schema_version != 1 or self.physical_model not in {
            "surface-template",
            "front-view-vinyl",
        }:
            raise ValueError("Unsupported project version or physical model.")
        Unit(self.units)
        surface = self.object.surface()
        if not 0 < finite(self.wrap_degrees) <= 360:
            raise ValueError("Wrap coverage must be greater than 0 and at most 360 degrees.")
        finite(self.rotation_degrees, "Template rotation")
        if not 0.5 <= finite(self.front_margin) <= 0.98:
            raise ValueError("Visible-edge margin must be between 0.50 and 0.98 of the radius.")
        if not 0.001 <= finite(self.export_tolerance_mm) <= 0.25:
            raise ValueError("Production tolerance must be 0.001–0.25 mm.")
        if artwork:
            self.placement.validate(
                surface, self.wrap_degrees, self.physical_model, self.front_margin
            )
        return surface

    def wrap_width(self):
        surface = self.validate(False)
        return surface.radius(surface.height / 2) * math.radians(self.wrap_degrees)

    def mapper(self, canvas_width: float, canvas_height: float):
        surface = self.validate()
        development = self.development(surface)
        p = self.placement
        reference_radius = surface.radius(surface.height / 2)
        center = math.radians(self.wrap_degrees) / 2
        rotation = complex(
            math.cos(math.radians(self.rotation_degrees)),
            math.sin(math.radians(self.rotation_degrees)),
        )

        def mapping(point: complex) -> complex:
            z = p.z + p.height * point.imag / canvas_height
            if self.physical_model == "front-view-vinyl":
                x_front = p.x + p.width * (point.real / canvas_width - 0.5)
                ratio = x_front / surface.radius(z)
                if abs(ratio) >= self.front_margin:
                    raise ValueError(
                        "Artwork reaches the visible edge. Reduce width; edge coordinates are never clamped."
                    )
                theta = math.asin(ratio)
                if abs(theta) > center + 1e-10:
                    raise ValueError(
                        "Front-view artwork crosses a seam. Increase coverage or reduce width."
                    )
            else:
                u = p.x + point.real * p.width / canvas_width
                theta = u / reference_radius - center
            x, y = develop(development, theta, z)
            return complex(x, y) * rotation

        mapping.profile_y = (
            [(z - p.z) * canvas_height / p.height for z, _ in surface.points]
            if isinstance(surface, MeasuredProfile)
            else []
        )
        mapping.derivative_bounds = self.mapping_derivative_bounds(surface)
        mapping.placement_affine = (p.width / canvas_width, p.height / canvas_height)
        mapping.certificate_level = (
            "analytical-exact-surface"
            if not isinstance(surface, MeasuredProfile)
            else "analytical-derivatives-numerical-profile-quadrature"
        )
        return mapping

    def development(self, surface=None):
        surface = surface or self.validate(False)
        if not isinstance(surface, MeasuredProfile):
            return surface
        self.placement.validate(surface, self.wrap_degrees, self.physical_model, self.front_margin)
        p = self.placement
        if self.physical_model == "front-view-vinyl":
            return fit_profile(
                surface.points, p.z, p.z + p.height, p.x - p.width / 2, p.x + p.width / 2
            )
        return fit_profile(
            surface.points, p.z, p.z + p.height, angular_width=math.radians(self.wrap_degrees)
        )

    def center_artwork(self):
        surface = self.validate(False)
        self.placement.x = (
            0
            if self.physical_model == "front-view-vinyl"
            else (self.wrap_width() - self.placement.width) / 2
        )
        self.placement.z = (surface.height - self.placement.height) / 2

    def mapping_scale_bound(self):
        """Conservative amplification of this support patch, used by stroke budgets."""
        return self.mapping_derivative_bounds()[0]

    def mapping_derivative_bounds(self, surface=None):
        surface = surface or self.validate()
        p = self.placement
        if isinstance(surface, MeasuredProfile):
            return self.development(surface).derivative_bounds(
                self.physical_model, abs(p.x) + p.width / 2, surface.radius(surface.height / 2)
            )
        if self.physical_model == "front-view-vinyl":
            return front_derivative_bounds(surface, abs(p.x) + p.width / 2, p.z, p.z + p.height)
        return intrinsic_derivative_bounds(
            surface, surface.radius(surface.height / 2), p.z, p.z + p.height
        )

    def profile_warnings(self):
        surface = self.validate(False)
        if not isinstance(surface, MeasuredProfile):
            return []
        warnings = [
            "Experimental profile: curvature requires distortion. Test a paper template first."
        ]
        if len(surface.points) < 6:
            warnings.append("Sparse measurements: add points where the wall bends most.")
        if self.wrap_degrees > 180:
            warnings.append("Coverage exceeds 180°; consider narrower panels to reduce distortion.")
        development = self.development(surface)
        low, high = development.strain_extrema()
        warnings.append(
            f"Required application strain over carrier: extension up to {max(0, high):.2%}; compression up to {max(0, -low):.2%}. No material limit has been validated."
        )
        warnings.append(
            "Carrier assumption: the entire artwork rectangle. Separate letters may behave differently."
        )
        return warnings

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Unsupported WrapLab project format.")
        try:
            values = dict(data)
            values["object"] = ObjectSpec(**values["object"])
            values["placement"] = Placement(**values["placement"])
            project = cls(**values)
            project.validate(False)
            if project.source_svg is not None and not isinstance(project.source_svg, str):
                raise ValueError("Project artwork must be SVG text.")
            return project
        except (TypeError, KeyError) as exc:
            raise ValueError("Malformed WrapLab project.") from exc
