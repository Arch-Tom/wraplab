"""Three carriers, two explicit mapping methods, and common on-object references."""

from copy import deepcopy
from dataclasses import dataclass, fields, replace
import hashlib
import json
import math
from shapely.geometry import GeometryCollection, Polygon, box

from ..domain import Project
from ..geometry.conformal import fit_profile
from ..geometry.surfaces import MeasuredProfile, develop
from ..svg import convert
from ..svg.adaptive import flatten
from ..svg.model import Artwork, Conversion
from .model import validate_assignment


@dataclass(frozen=True)
class FrameSubset(Artwork):
    fixed_frame: object = None

    @property
    def visible_frame(self):
        return self.fixed_frame


def subset(art, group, frame=None):
    shapes = tuple(replace(art.shapes[si], subpaths=tuple(art.shapes[si].subpaths[i] for i in indices))
                   for si, indices in group.selections)
    if frame is None:
        return replace(art, shapes=shapes)
    return FrameSubset(art.width_mm, art.height_mm, shapes, art.source, art.warnings, frame)


def selected_conversion(conversion, group):
    # Exact contour objects from the existing global conversion, without refitting,
    # recentering, resampling or independent transformation of Hebrew rows.
    return Conversion([replace(conversion.paths[si], contours=[conversion.paths[si].contours[i]
                      for i in indices]) for si, indices in group.selections],
                      list(conversion.warnings), conversion.tolerance_mm)


@dataclass
class SupportedProject(Project):
    """Preview/planning adapter: same solver and source placement, explicit local support."""
    support_bounds: tuple = ()

    def development(self, surface=None):
        surface = surface or self.validate(False)
        if not isinstance(surface, MeasuredProfile):
            return super().development(surface)
        left, top, right, bottom = self.support_bounds
        return fit_profile(surface.points, top, bottom, left, right)

    def mapping_derivative_bounds(self, surface=None):
        surface = surface or self.validate()
        if not isinstance(surface, MeasuredProfile):
            return super().mapping_derivative_bounds(surface)
        left, _, right, _ = self.support_bounds
        return self.development(surface).derivative_bounds(
            self.physical_model, max(abs(left), abs(right)), surface.radius(surface.height / 2))


@dataclass
class Mask:
    id: str
    conversion: object
    original: object
    mapping_project: Project
    support: tuple
    carrier_flat: list[complex]
    references: list[dict]
    flat_reference_points: list[complex]
    original_reference_points: list[complex]
    strain: tuple
    warnings: list[str]


@dataclass
class Plan:
    method: str
    masks: list[Mask]
    source_sha256: str
    profile_sha256: str
    topology: dict
    global_strain: tuple
    warnings: list[str]


def object_reference(project, x, z):
    surface = project.object.surface()
    radius = surface.radius(z)  # Strict measured domain; no extrapolation.
    if project.physical_model != "front-view-vinyl":
        raise ValueError("Mask registration currently requires front-view artwork.")
    if abs(x) >= project.front_margin * radius:
        raise ValueError("Carrier or registration reaches the visible edge. Reduce its margin or width.")
    angle = math.asin(x / radius)
    if abs(angle)>math.radians(project.wrap_degrees)/2+1e-10:
        raise ValueError("Carrier or registration crosses the selected coverage seam. Reduce margins or increase coverage.")
    datum=project.preview_options.get("physical_top_datum_mm")
    return {"front_x_mm": x, "z_down_mm": z, "height_above_measured_bottom_mm": surface.height - z,
            "physical_height_above_operator_datum_mm": None if datum is None else datum-z,
            "theta_radians": angle, "signed_front_arc_mm": radius * angle,
            "xyz_mm": [radius * math.sin(angle), surface.height / 2 - z, radius * math.cos(angle)]}


def plan_masks(artwork, project, assignment, method="global-split", margins=(0, 0, 0, 0), preview=False):
    """Margins L/R/T/B in the front reference plane, not assumed flat tape distances."""
    if method not in {"global-split", "independent"}:
        raise ValueError("Unknown mask compensation method.")
    if len(margins) != 4 or any(not math.isfinite(v) or not 0 <= v <= 50 for v in margins):
        raise ValueError("Handling margins must be finite, nonnegative and at most 50 mm.")
    if project.physical_model != "front-view-vinyl":
        raise ValueError("Mask planning uses front-view targets. Ordinary surface-wrap export remains available.")
    topology = validate_assignment(assignment, artwork, project)
    original_all = topology.pop("_original")
    global_all = convert(artwork, project, preview=preview)
    frame, placement = project.source_frame(artwork), project.placement
    surface, global_development = project.validate(), project.development()
    global_strain = global_development.strain_extrema() if isinstance(surface, MeasuredProfile) else (0., 0.)
    masks, warnings = [], ["Planning only: no CorelDRAW, cutter or material approval.",
        "Carrier edges and registration are reference-only; artwork SVGs contain no added trim cuts."]
    if isinstance(surface, MeasuredProfile):
        warnings.append("Only the measured band is modeled; no neck, crown or lower skirt is extrapolated.")
    for group in assignment.groups:
        group_art = subset(artwork, group)
        g = group_art.visible_frame
        left = placement.x + placement.width * ((g.left - frame.left) / frame.width - .5)
        right = placement.x + placement.width * ((g.left + g.width - frame.left) / frame.width - .5)
        top = placement.z if g.top == frame.top else placement.z + placement.height * (g.top - frame.top) / frame.height
        bottom = (placement.z + placement.height if g.top + g.height == frame.top + frame.height else
                  placement.z + placement.height * (g.top + g.height - frame.top) / frame.height)
        support = (left - margins[0], top - margins[2], right + margins[1], bottom + margins[3])
        left_edge, top_edge, right_edge, bottom_edge = support
        if not 0 <= top_edge < bottom_edge <= surface.height:
            raise ValueError(f"{group.id}: handling margin leaves the measured height. Reduce TOP/BOTTOM margins or add real stations; no extrapolation.")
        references = [dict(label=label, **object_reference(project, x, z))
                      for label, x, z in (("L", left_edge, (top_edge + bottom_edge) / 2),
                                          ("R", right_edge, (top_edge + bottom_edge) / 2),
                                          ("TOP", (left_edge + right_edge) / 2, top_edge))]
        mapped_project = project
        if method == "independent":
            mapped_project = SupportedProject(**{f.name: deepcopy(getattr(project, f.name)) for f in fields(Project)},
                                             support_bounds=support)
        development = mapped_project.development()
        if isinstance(surface, MeasuredProfile):
            stations = [top_edge,bottom_edge]+[z for z in development.diagnostic_stations()
                                              if top_edge <= z <= bottom_edge]
            strains = [development.application_strain(z) for z in stations]
            strain = (min(strains),max(strains))
        else:
            strain = (0.,0.)
        selected = subset(artwork, group, frame)
        conversion = (selected_conversion(global_all, group) if method == "global-split" else
                      convert(selected, mapped_project, preview=preview))
        original = selected_conversion(original_all, group)
        rotation = complex(math.cos(math.radians(project.rotation_degrees)),
                           math.sin(math.radians(project.rotation_degrees)))

        def boundary_point(x, z, development=development, rotation=rotation):
            ref = object_reference(project, x, z)
            xy = develop(development, ref["theta_radians"], z)
            return complex(*xy) * rotation

        carrier = []
        corners = [(left_edge,top_edge),(right_edge,top_edge),(right_edge,bottom_edge),(left_edge,bottom_edge)]
        for (x0, z0), (x1, z1) in zip(corners, corners[1:] + corners[:1], strict=False):
            def edge(u, x0=x0, x1=x1, z0=z0, z1=z1, point=boundary_point):
                return point(x0+(x1-x0)*u, z0 if u==0 else z1 if u==1 else z0+(z1-z0)*u)
            carrier += flatten(edge, .05)[:-1]
        group_warnings = (["Global mapping preserved; separating carriers does not reduce modeled strain."]
                          if method == "global-split" else
                          ["EXPERIMENTAL independent fit; use object-space references, never old flat gaps."])
        masks.append(Mask(group.id, conversion, original, mapped_project, support, carrier,
                          references, [boundary_point(ref["front_x_mm"],ref["z_down_mm"]) for ref in references],
                          [complex(ref["front_x_mm"]-placement.x+placement.width/2,
                                   ref["z_down_mm"]-placement.z) for ref in references],
                          strain, group_warnings))
    # Conservative rectangular carriers may not contain any other mask's ink.
    # Resolve a conflict deliberately by changing membership/margins; never slice letters.
    shift=complex(placement.x-placement.width/2,placement.z)
    painted={}
    for mask in masks:
        geometry=GeometryCollection()
        for path in mask.original.paths:
            path_geometry=GeometryCollection()
            polygons=[Polygon([(q.real+shift.real,q.imag+shift.imag) for q in c.points]) for c in path.contours]
            winding=[1 if polygon.exterior.is_ccw else -1 for polygon in polygons]
            for i in sorted(range(len(polygons)),key=lambda i:polygons[i].area,reverse=True):
                parents=[j for j,other in enumerate(polygons) if i!=j and other.contains(polygons[i])]
                fill=(len(parents)%2==0 if path.fill_rule=="evenodd" else
                      sum(winding[j] for j in parents)+winding[i]!=0)
                path_geometry=path_geometry.union(polygons[i]) if fill else path_geometry.difference(polygons[i])
            geometry=geometry.union(path_geometry)
        painted[mask.id]=geometry
    for mask in masks:
        carrier=box(*mask.support)
        for other_id,geometry in painted.items():
            if other_id!=mask.id and carrier.intersection(geometry).area>1e-8:
                raise ValueError(f"{mask.id}: carrier overlaps {other_id} artwork. Reduce margins or deliberately revise the component assignment; automatic cuts through artwork are forbidden.")
    profile = json.dumps(project.to_dict()["object"], sort_keys=True, separators=(",", ":"))
    return Plan(method, masks, assignment.source_sha256, hashlib.sha256(profile.encode()).hexdigest(),
                {k: v for k, v in topology.items() if k != "membership"}, global_strain, warnings)
