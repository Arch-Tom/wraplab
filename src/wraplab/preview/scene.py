"""Version 1 scene contract. Python owns geometry; the viewer only projects triangles.

World axes: X right, Y up about measured-band midpoint, Z toward the front viewer.
All coordinates are millimeters; measured surfaces end exactly at their last station.
"""

from dataclasses import dataclass
import math
import xml.etree.ElementTree as ET

from ..geometry.surfaces import MeasuredProfile
from ..svg import convert
from ..svg.exporter import number, path_data
from ..masks.model import source_identity


@dataclass(frozen=True)
class Scene:
    version: int
    extent_mm: float
    height_mm: float
    body: tuple
    artwork_mesh: tuple
    textures: dict
    lines: tuple
    references: tuple
    warnings: tuple
    identity: dict


def surface_vertex(surface, theta, z, uv=(0, 0), lift=0):
    radius = surface.radius(z)
    slope = surface.slope(z)
    radial = slope / math.sqrt(max(1e-30, 1 - slope * slope))
    norm = math.sqrt(1 + radial * radial)
    s, c = math.sin(theta), math.cos(theta)
    return ((radius + lift) * s, surface.height / 2 - z, (radius + lift) * c,
            s / norm, radial / norm, c / norm, *uv)


def triangles(grid):
    result = []
    for a, b in zip(grid, grid[1:], strict=False):
        for i in range(len(a) - 1):
            result.extend((a[i], b[i], a[i + 1], a[i + 1], b[i], b[i + 1]))
    return tuple(result)


def texture_svg(conversion, width, height, highlight=False):
    """Only regenerated, validated vectors reach Qt. No imported SVG document/assets."""
    root = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
                      width=f"{number(width)}mm", height=f"{number(height)}mm",
                      viewBox=f"0 0 {number(width)} {number(height)}")
    parent, current = root, None
    for path in conversion.paths:
        if path.opacity_group is None:
            parent, current = root, None
        elif current != path.opacity_group:
            current = path.opacity_group
            parent = ET.SubElement(root, "g", opacity=number(current[1]))
        ET.SubElement(parent, "path", d=path_data(path, 0j),
                      fill="#df8d28" if highlight else path.fill,
                      **{"fill-rule": path.fill_rule, "opacity": number(path.opacity),
                         "stroke": path.stroke, "stroke-width": number(path.stroke_width)})
    return ET.tostring(root, encoding="unicode")


def build_scene(project, artwork=None, original=None, plan=None):
    surface = project.validate(bool(artwork))
    zs = sorted(set([surface.height * (i / 48) for i in range(48)] + [surface.height]
                    + ([z for z, _ in surface.points] if isinstance(surface, MeasuredProfile) else [])))
    grid = [[surface_vertex(surface, -math.pi + 2 * math.pi * i / 96, z)
             for i in range(97)] for z in zs]
    body = triangles(grid)
    extent = max(surface.height, max(surface.radius(z) * 2 for z in zs))
    lift = max(.005, extent * .0001)
    lines, references, warnings = [], [], []
    for theta in (-math.radians(project.wrap_degrees) / 2, math.radians(project.wrap_degrees) / 2):
        lines.append(("seam", "all", tuple(surface_vertex(surface, theta, z, lift=2*lift)[:3] for z in zs)))
    for z in (0., surface.height):
        lines.append(("bounds", "all", tuple(surface_vertex(surface, 2*math.pi*i/128, z, lift=lift)[:3]
                                               for i in range(129))))
    lines.append(("registration", "all", tuple(surface_vertex(surface, 0, z, lift=2*lift)[:3] for z in zs)))
    mesh, textures = (), {}
    if isinstance(surface, MeasuredProfile):
        warnings.append("Measured band only · open ends are measurement limits, not a reconstructed complete bell.")
    if artwork:
        original = original or convert(artwork, project, preview=True, original=True)
        p = project.placement
        locate = project.surface_mapper(p.width, p.height)

        def point(x, y, u=0, v=0):
            theta, z = locate(complex(x, y))
            return surface_vertex(surface, theta, z, (u, v), lift)

        grid = [[point(p.width if u==64 else p.width*(u/64),
                       p.height if v==48 else p.height*(v/48), u / 64, v / 48)
                 for u in range(65)] for v in range(49)]
        mesh = triangles(grid)
        textures["all"] = texture_svg(original, p.width, p.height)
        for mask_id, paths in [("all", original.paths)] + (
                [(m.id, m.original.paths) for m in plan.masks] if plan else []):
            for path in paths:
                for contour in path.contours:
                    positions = [point(q.real, q.imag)[:3] for q in contour.points]
                    if contour.closed and positions:
                        positions.append(positions[0])
                    lines.append(("cut_paths", mask_id, tuple(positions)))
        if plan:
            for mask in plan.masks:
                textures[mask.id] = texture_svg(mask.original, p.width, p.height)
                textures[mask.id + ":highlight"] = texture_svg(mask.original, p.width, p.height, True)
                left, top, right, bottom = mask.support
                def reference_vertex(x, z):
                    radius = surface.radius(z)
                    theta = math.asin(x / radius)
                    return surface_vertex(surface, theta, z, lift=2*lift)[:3]
                border = []
                corners = [(left,top), (right,top), (right,bottom), (left,bottom)]
                for (x0,z0), (x1,z1) in zip(corners,corners[1:]+corners[:1], strict=False):
                    for i in range(33):
                        u = i/32
                        z = z0 if i == 0 else z1 if i == 32 else z0+(z1-z0)*u
                        border.append(reference_vertex(x0+(x1-x0)*u,z))
                lines.append(("carriers", mask.id, tuple(border)))
                for reference in mask.references:
                    references.append(dict(reference, mask=mask.id))
    return Scene(1, extent, surface.height, body,
                 mesh, textures, tuple(lines), tuple(references), tuple(warnings),
                 {"source_sha256": source_identity(artwork) if artwork else None,
                  "units": "mm", "coordinates": "x-right-y-up-z-front",
                  "physical_model": project.physical_model, "preview_only": True,
                  "display_decal_lift_mm": lift,
                  "mesh_is_approximate": True, "export_uses_original_vector_engine": True})
