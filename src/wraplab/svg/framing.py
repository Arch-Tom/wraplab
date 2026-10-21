"""Source frames in canonical page mm; source vectors are never cropped or rewritten."""

from dataclasses import dataclass

from svgpathtools import Line

from .model import Frame
from .transform import convert_artwork
from .importer import length

# Much smaller than the minimum 0.001 mm production tolerance. Curved stroke
# envelopes use the same certified flattening/outline machinery as compensation.
BOUNDS_TOLERANCE_MM = 0.00001


@dataclass(frozen=True)
class BoundsResult:
    frame: Frame | None
    error: str = ""


def visible_bounds(artwork):
    def identity(point):
        return point

    identity.derivative_bounds = (1, 0)
    identity.placement_affine = (1, 1)
    try:
        approximate_stroke = False
        max_miter = 1
        for shape in artwork.shapes:
            style = shape.style
            if (
                style["stroke"] not in {"none", "transparent"}
                and float(style["opacity"]) * float(style["stroke-opacity"]) > 0
                and length(style["stroke-width"]) > 0
            ):
                approximate_stroke |= (
                    style["stroke-linecap"] == "round"
                    or style["stroke-linejoin"] == "round"
                    or any(not isinstance(s, Line) for sub in shape.subpaths for s in sub.segments)
                )
                max_miter = max(max_miter, float(style["stroke-miterlimit"]))
        # Fill extrema are explicitly retained by curve_breakpoints before sampling.
        # Stroke bounds include an outward numerical envelope, with a tighter local
        # budget for miter amplification. Keep the source page and topology guards.
        tolerance = BOUNDS_TOLERANCE_MM / max_miter if approximate_stroke else 0.01
        result = convert_artwork(artwork, identity, tolerance)
        points = [p for path in result.paths for contour in path.contours for p in contour.points]
        error = BOUNDS_TOLERANCE_MM if approximate_stroke else 0
        left, right = min(p.real for p in points) - error, max(p.real for p in points) + error
        top, bottom = min(p.imag for p in points) - error, max(p.imag for p in points) + error
        if right <= left or bottom <= top:
            raise ValueError("Visible artwork has no positive two-dimensional extent.")
        return BoundsResult(Frame(left, top, right - left, bottom - top, error,
                                  tolerance if approximate_stroke else None))
    except ValueError as exc:
        return BoundsResult(None, str(exc))
