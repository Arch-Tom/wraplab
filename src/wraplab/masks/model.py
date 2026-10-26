"""Source-bound component membership. Indices are never inferred for unknown artwork."""

from dataclasses import dataclass
import hashlib
import re

from shapely.geometry import Polygon

from ..svg import convert


@dataclass(frozen=True)
class MaskGroup:
    id: str
    selections: tuple[tuple[int, tuple[int, ...]], ...]


@dataclass(frozen=True)
class Assignment:
    source_sha256: str
    groups: tuple[MaskGroup, ...]

    def to_dict(self):
        return {"source_sha256": self.source_sha256, "groups": [
            {"id": g.id, "selections": [{"shape": si, "contours": list(indices)}
             for si, indices in g.selections]} for g in self.groups]}


def source_identity(artwork):
    return hashlib.sha256(artwork.source.encode("utf-8")).hexdigest()


def assignment_from_dict(data):
    try:
        digest, groups = data["source_sha256"], data["groups"]
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not 1 <= len(groups) <= 16:
            raise ValueError("Invalid source identity or mask count.")
        result = []
        for group in groups:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", group["id"]):
                raise ValueError("Mask names must use uppercase letters, digits and underscores.")
            selections = []
            for row in group["selections"]:
                si, indices = row["shape"], row["contours"]
                if type(si) is not int or si < 0 or not isinstance(indices, (list, tuple)) or not indices:
                    raise ValueError("Each mask needs explicit shape and contour membership.")
                if len(indices) > 200_000 or any(type(i) is not int or i < 0 for i in indices):
                    raise ValueError("Invalid contour selection.")
                selections.append((si, tuple(indices)))
            if not selections:
                raise ValueError("An empty physical mask cannot be exported.")
            result.append(MaskGroup(group["id"], tuple(selections)))
        if len({g.id for g in result}) != len(result):
            raise ValueError("Mask names must be unique.")
        return Assignment(digest, tuple(result))
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid mask assignment document.") from exc


def cantor_assignment(artwork):
    # Verified user-supplied corrected source. This is a recipe for this identity only.
    digest = "c391a63dd7fb654872d6154ae4677650543c83167a1843970389e9195c76bf79"
    if source_identity(artwork) != digest or [len(s.subpaths) for s in artwork.shapes] != [22, 8, 14]:
        raise ValueError("This artwork does not match the verified CantorLand source. Load an explicit assignment.")
    return Assignment(digest, (
        MaskGroup("STAR", ((1, tuple(range(8))),)),
        MaskGroup("HEBREW", ((0, tuple(range(22))),)),
        MaskGroup("CANTORLAND", ((2, tuple(range(14))),)),
    ))


def cantor_trial(artwork):
    """Explicit operator action only; never silently replace a current object's measurements."""
    from decimal import Decimal
    from ..domain import ObjectSpec, Project

    assignment = cantor_assignment(artwork)
    def mm(value):
        return float(Decimal(str(value))*Decimal("25.4"))
    project = Project(object=ObjectSpec(mode="measured", name="CantorLand — HISTORICAL TRIAL",
        measurement_type="circumference", points=[(mm(z),mm(c)) for z,c in
            ((0,17.125),(1.5,20.125),(3.45,25.1875),(5.95,36.125))],
        notes="Historical nominal stations: measured TOP at physical 9.75 inches above the common historical datum; last station at 3.80 inches. Not reconfirmed. Last station is the lower artwork boundary."),
        artwork_frame="visible", source_svg=artwork.source, source_name="CantorLand.svg")
    project.placement.height = 101.6
    project.placement.width = 101.6*artwork.visible_frame.width/artwork.visible_frame.height
    project.placement.z = 49.53
    project.preview_options = {"assignment":assignment.to_dict(), "physical_top_datum_mm":247.65}
    return project


def validate_assignment(assignment, artwork, project):
    assignment_from_dict(assignment.to_dict())
    if assignment.source_sha256 != source_identity(artwork):
        raise ValueError("Mask assignment belongs to a different SVG. Reassign its components.")
    expected = {(si, ci) for si, shape in enumerate(artwork.shapes)
                for ci in range(len(shape.subpaths))}
    membership = {}
    for group in assignment.groups:
        for si, indices in group.selections:
            for ci in indices:
                if (si, ci) not in expected or (si, ci) in membership:
                    raise ValueError("Masks must contain each source contour exactly once, without duplicates.")
                membership[si, ci] = group.id
    if membership.keys() != expected:
        raise ValueError("Mask selection leaves source contours unassigned.")
    # First release deliberately excludes ambiguous open/stroked/translucent masks.
    # Such SVGs still work in ordinary export and the 3D preview.
    for shape in artwork.shapes:
        style = shape.style
        if (style["stroke"] not in {"none", "transparent"} or style["fill"] in {"none", "transparent"}
                or float(style["opacity"]) != 1 or float(style["fill-opacity"]) != 1
                or any(not sub.closed for sub in shape.subpaths)):
            raise ValueError("Mask planning requires closed, opaque filled contours. Outline strokes and resolve transparency in the source editor.")
    original = convert(artwork, project, original=True)
    if len(original.paths) != len(artwork.shapes):
        raise ValueError("Source paint membership is ambiguous; preserve ordinary export and simplify the source.")
    holes = 0
    for si, path in enumerate(original.paths):
        polygons = [Polygon([(p.real, p.imag) for p in c.points]) for c in path.contours]
        winding = [1 if poly.exterior.is_ccw else -1 for poly in polygons]
        for ci, polygon in enumerate(polygons):
            parents = [i for i, outer in enumerate(polygons) if i != ci and outer.contains(polygon)]
            if any(membership[si, ci] != membership[si, parent] for parent in parents):
                raise ValueError("A mask assignment separates a contour from its opening or containing shape.")
            holes += ((len(parents) % 2 == 1) if path.fill_rule == "evenodd" else
                      (sum(winding[i] for i in parents) != 0 and
                       sum(winding[i] for i in parents) + winding[ci] == 0))
    if assignment.source_sha256 == "c391a63dd7fb654872d6154ae4677650543c83167a1843970389e9195c76bf79":
        if len(expected) != 44 or holes != 12:
            raise ValueError("CantorLand topology differs from its verified 44 contours / 12 openings.")
    return {"contours": len(expected), "openings": int(holes), "membership": membership,
            "_original": original}
