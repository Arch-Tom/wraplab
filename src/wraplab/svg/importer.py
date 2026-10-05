"""Strict SVG subset. Reject unsupported rendering rather than dropping visible content."""

import math
import re
from types import MappingProxyType

from defusedxml import ElementTree as SafeET
from svgpathtools import parse_path

from ..geometry.units import positive
from .model import Affine, Artwork, Shape, Subpath

SVG_NS = "http://www.w3.org/2000/svg"
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
NUM_RE = re.compile(NUMBER)
LENGTH_RE = re.compile(rf"\s*({NUMBER})\s*(mm|cm|in|pt|pc|px)?\s*\Z")
STYLES = {
    "fill",
    "fill-rule",
    "fill-opacity",
    "stroke",
    "stroke-width",
    "stroke-opacity",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "opacity",
    "display",
    "visibility",
    "color",
}
DEFAULT_STYLE = {
    "fill": "#000000",
    "fill-rule": "nonzero",
    "fill-opacity": "1",
    "stroke": "none",
    "stroke-width": "1",
    "stroke-opacity": "1",
    "stroke-linecap": "butt",
    "stroke-linejoin": "miter",
    "stroke-miterlimit": "4",
    "opacity": "1",
    "display": "inline",
    "visibility": "visible",
    "color": "#000000",
}
NAMED_COLORS = {
    "black",
    "white",
    "red",
    "green",
    "blue",
    "yellow",
    "cyan",
    "magenta",
    "gray",
    "grey",
    "silver",
    "maroon",
    "purple",
    "fuchsia",
    "lime",
    "olive",
    "navy",
    "teal",
    "aqua",
    "orange",
    "pink",
    "brown",
    "transparent",
}


def numbers(text: str):
    if NUM_RE.sub("", text).strip(" ,\t\r\n"):
        raise ValueError("Invalid SVG numeric list.")
    values = [float(s) for s in NUM_RE.findall(text)]
    if any(not math.isfinite(n) or abs(n) > 1e9 for n in values):
        raise ValueError("SVG coordinates must be finite and within supported range.")
    return values


def length(text: str, physical=False):
    match = LENGTH_RE.fullmatch(str(text))
    if not match:
        raise ValueError(f"Unsupported SVG length {text!r}; percentages are not supported.")
    value = float(match[1])
    factors = {
        "mm": 1,
        "cm": 10,
        "in": 25.4,
        "pt": 25.4 / 72,
        "pc": 25.4 / 6,
        "px": 25.4 / 96,
        None: 25.4 / 96,
    }
    if not math.isfinite(value) or abs(value) > 1e9:
        raise ValueError("SVG length is out of range.")
    return value * factors[match[2]] * (1 if physical else 96 / 25.4)


def parse_transform(text: str):
    result = Affine()
    pattern = re.compile(r"([A-Za-z]+)\s*\(([^()]*)\)")
    if pattern.sub("", text).strip(" ,\t\r\n"):
        raise ValueError("Malformed SVG transform.")
    for match in pattern.finditer(text):
        name, values = match[1], numbers(match[2])
        if name == "matrix" and len(values) == 6:
            transform = Affine(*values)
        elif name == "translate" and len(values) in (1, 2):
            transform = Affine(e=values[0], f=values[1] if len(values) == 2 else 0)
        elif name == "scale" and len(values) in (1, 2):
            transform = Affine(a=values[0], d=values[-1])
        elif name == "rotate" and len(values) in (1, 3):
            angle = math.radians(values[0])
            transform = Affine(math.cos(angle), math.sin(angle), -math.sin(angle), math.cos(angle))
            if len(values) == 3:
                x, y = values[1:]
                transform = Affine(e=x, f=y) @ transform @ Affine(e=-x, f=-y)
        elif name in {"skewX", "skewY"} and len(values) == 1:
            if abs(math.cos(math.radians(values[0]))) < 1e-8:
                raise ValueError("Singular SVG skew transform.")
            t = math.tan(math.radians(values[0]))
            transform = Affine(c=t) if name == "skewX" else Affine(b=t)
        else:
            raise ValueError(f"Unsupported SVG transform {name}.")
        result = result @ transform
    if abs(result.a * result.d - result.b * result.c) < 1e-12:
        raise ValueError("SVG transform collapses artwork to a line or point.")
    return result


def color(value: str, current="black"):
    value = value.strip().lower()
    if value == "currentcolor":
        return color(current)
    if value == "none" or value in NAMED_COLORS:
        return value
    if re.fullmatch(r"#[0-9a-f]{3}(?:[0-9a-f]{3})?", value):
        return value
    match = re.fullmatch(r"rgb\(\s*([^)]*)\)", value)
    if match:
        parts = match[1].split(",")
        if len(parts) == 3:
            vals = [
                float(x.strip().rstrip("%")) * (2.55 if x.strip().endswith("%") else 1)
                for x in parts
            ]
            if all(math.isfinite(v) and 0 <= v <= 255.00001 for v in vals):
                return "#" + "".join(f"{round(v):02x}" for v in vals)
    raise ValueError(f"Unsupported SVG paint {value!r}. Use solid colors; expand gradients first.")


def style_for(element, inherited):
    style = {**inherited, "opacity": "1"}  # opacity is not inherited by the SVG specification
    for key in STYLES:
        if key in element.attrib:
            style[key] = element.attrib[key]
    for declaration in element.get("style", "").split(";"):
        if not declaration.strip():
            continue
        if ":" not in declaration:
            raise ValueError("Malformed inline SVG style.")
        key, value = (s.strip() for s in declaration.split(":", 1))
        if key not in STYLES:
            raise ValueError(f"Unsupported SVG style {key!r}; simplify the source in Corel.")
        style[key] = value
    if style["fill-rule"] not in {"nonzero", "evenodd"}:
        raise ValueError("Unsupported SVG fill rule.")
    for key in ["fill", "stroke", "color"]:
        style[key] = color(style[key], style.get("color", "black"))
    for key in ["opacity", "fill-opacity", "stroke-opacity"]:
        value = float(style[key])
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("SVG opacity must be between zero and one.")
    if style["stroke-linecap"] not in {"butt", "round", "square"} or style[
        "stroke-linejoin"
    ] not in {"miter", "round", "bevel"}:
        raise ValueError("Unsupported SVG stroke caps or joins.")
    if not 1 <= float(style["stroke-miterlimit"]) <= 100:
        raise ValueError("Stroke miter limit must be 1–100.")
    if style["display"] not in {"none", "inline"} or style["visibility"] not in {
        "hidden",
        "visible",
    }:
        raise ValueError("Unsupported SVG visibility/display value.")
    return style


def primitive_path(tag, element):
    def n(key, default="0"):
        return length(element.get(key, default))

    if tag == "path":
        return element.get("d", "")
    if tag == "line":
        return f"M {n('x1')} {n('y1')} L {n('x2')} {n('y2')}"
    if tag in {"polyline", "polygon"}:
        p = numbers(element.get("points", ""))
        if len(p) < 4 or len(p) % 2:
            raise ValueError("Polygon/polyline must contain coordinate pairs.")
        return (
            "M "
            + " L ".join(f"{x} {y}" for x, y in zip(p[::2], p[1::2], strict=False))
            + (" Z" if tag == "polygon" else "")
        )
    if tag == "rect":
        x, y, w, h = n("x"), n("y"), n("width"), n("height")
        if w < 0 or h < 0:
            raise ValueError("SVG rectangles cannot have negative dimensions.")
        if w == 0 or h == 0:
            return ""
        rx = n("rx", element.get("ry", "0"))
        ry = n("ry", element.get("rx", "0"))
        if rx < 0 or ry < 0:
            raise ValueError("Rounded rectangle radii cannot be negative.")
        rx, ry = min(rx, w / 2), min(ry, h / 2)
        if rx == 0 or ry == 0:
            return f"M{x} {y} h{w} v{h} h{-w} Z"
        return (
            f"M{x + rx} {y} H{x + w - rx} A{rx} {ry} 0 0 1 {x + w} {y + ry} "
            f"V{y + h - ry} A{rx} {ry} 0 0 1 {x + w - rx} {y + h} "
            f"H{x + rx} A{rx} {ry} 0 0 1 {x} {y + h - ry} "
            f"V{y + ry} A{rx} {ry} 0 0 1 {x + rx} {y} Z"
        )
    if tag in {"circle", "ellipse"}:
        x, y = n("cx"), n("cy")
        rx = n("r") if tag == "circle" else n("rx")
        ry = n("r") if tag == "circle" else n("ry")
        if rx < 0 or ry < 0:
            raise ValueError("SVG radii cannot be negative.")
        if rx == 0 or ry == 0:
            return ""
        return f"M{x - rx} {y} A{rx} {ry} 0 1 0 {x + rx} {y} A{rx} {ry} 0 1 0 {x - rx} {y} Z"
    raise ValueError(f"Unsupported SVG element <{tag}>. Convert it to paths in Corel first.")


def parse_subpaths(data, segment_limit=20_000):
    if not data.strip():
        return []
    if re.sub(rf"[MmZzLlHhVvCcSsQqTtAa]|{NUMBER}|[\s,]", "", data):
        raise ValueError("Invalid SVG path data.")
    if data.lstrip()[0] not in "Mm":
        raise ValueError("SVG path must begin with a move command.")
    if len(NUM_RE.findall(data)) > segment_limit * 8:
        raise ValueError("SVG path exceeds the coordinate complexity limit.")
    chunks = re.split(r"(?=[Mm])", data)
    current = 0j
    result = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        try:
            path = parse_path(chunk, current_pos=current)
        except (ValueError, IndexError, AssertionError, ZeroDivisionError) as exc:
            raise ValueError("Malformed SVG path; repair it in the source editor.") from exc
        if len(path) > segment_limit:
            raise ValueError(f"SVG path exceeds {segment_limit:,} segments.")
        if path:
            current = path[-1].end
            result.append(Subpath(tuple(path), bool(re.search(r"[Zz]", chunk))))
        if len(result) > 256:
            raise ValueError(
                "One compound path may contain at most 256 contours; split large text groups."
            )
    return result


def import_svg(text: str) -> Artwork:
    if not isinstance(text, str) or len(text.encode("utf-8")) > 10_000_000:
        raise ValueError("SVG exceeds the 10 MB import limit.")
    try:
        root = SafeET.fromstring(text)
    except Exception as exc:
        raise ValueError("Invalid or unsafe SVG XML (DTD/entities are unsupported).") from exc
    if root.tag not in {"svg", f"{{{SVG_NS}}}svg"}:
        raise ValueError("The file must contain an SVG root element.")
    if len(list(root.iter())) > 20_000:
        raise ValueError("SVG exceeds the 20,000 element limit.")
    stack = [(root, 0)]
    while stack:
        element, depth = stack.pop()
        if element.tag.split("}")[-1] == "script" or any(
            key.split("}")[-1].lower().startswith("on") for key in element.attrib
        ):
            raise ValueError("Active/scripted SVG content is unsupported, including definitions.")
        if depth > 64:
            raise ValueError("SVG group nesting exceeds 64 levels.")
        stack.extend((child, depth + 1) for child in element)
    warnings = []
    if "width" not in root.attrib or "height" not in root.attrib:
        raise ValueError("SVG needs explicit width and height. Export at physical size from Corel.")
    width, height = length(root.get("width"), True), length(root.get("height"), True)
    positive(width, "SVG width")
    positive(height, "SVG height")
    if not any(unit in root.get("width", "") for unit in ["mm", "cm", "in", "pt", "pc"]):
        warnings.append("Unitless/px SVG dimensions interpreted at 96 dpi. Verify physical size.")
    viewport = Affine(a=25.4 / 96, d=25.4 / 96)
    if "viewBox" in root.attrib:
        viewbox = numbers(root.get("viewBox"))
        if len(viewbox) != 4 or viewbox[2] <= 0 or viewbox[3] <= 0:
            raise ValueError("SVG viewBox must have a positive width and height.")
        x, y, w, h = viewbox
        sx, sy = width / w, height / h
        aspect = root.get("preserveAspectRatio", "xMidYMid meet").strip().split()
        dx = dy = 0
        if aspect != ["none"]:
            if aspect[-1] == "slice":
                raise ValueError("SVG viewport clipping (slice) is unsupported; expand/flatten it.")
            if (
                len(aspect) > 2
                or aspect[0]
                not in {f"x{a}Y{b}" for a in ["Min", "Mid", "Max"] for b in ["Min", "Mid", "Max"]}
                or (len(aspect) == 2 and aspect[1] != "meet")
            ):
                raise ValueError("Unsupported preserveAspectRatio.")
            sx = sy = min(sx, sy)
            dx = (width - w * sx) * {"Min": 0, "Mid": 0.5, "Max": 1}[aspect[0][1:4]]
            dy = (height - h * sy) * {"Min": 0, "Mid": 0.5, "Max": 1}[aspect[0][5:8]]
        viewport = Affine(a=sx, d=sy, e=dx - x * sx, f=dy - y * sy)
    shapes = []
    unsupported_attrs = {
        "clip-path",
        "mask",
        "filter",
        "vector-effect",
        "marker-start",
        "marker-mid",
        "marker-end",
        "stroke-dasharray",
        "stroke-dashoffset",
        "href",
        "class",
        "paint-order",
        "mix-blend-mode",
        "isolation",
        "transform-origin",
        "transform-box",
        "stroke-alignment",
    }

    def visit(element, transform, inherited, is_root=False):
        tag = element.tag.split("}")[-1]
        if tag in {"metadata", "title", "desc", "namedview"}:
            return
        if element.tag.startswith("{") and not element.tag.startswith("{" + SVG_NS + "}"):
            raise ValueError("Unsupported non-SVG rendering namespace.")
        # Definitions are allowed only as unused containers: references are rejected below.
        if tag == "defs":
            return
        for key, value in element.attrib.items():
            local = key.split("}")[-1]
            if local in unsupported_attrs and value.strip() not in {"none", ""}:
                raise ValueError(f"Unsupported SVG {local}; expand it to plain paths in Corel.")
            if local.lower().startswith("on"):
                raise ValueError("Active/scripted SVG content is unsupported.")
        style = style_for(element, inherited)
        if style["display"] == "none":
            return
        transform = transform @ parse_transform(element.get("transform", ""))
        if tag in {"g", "svg"}:
            if tag == "svg" and not is_root:
                raise ValueError("Nested SVG viewports are unsupported.")
            if float(style["opacity"]) != 1:
                raise ValueError("Group opacity requires compositing; flatten it before import.")
            for child in element:
                visit(child, transform, style)
            return
        if list(element):
            raise ValueError("Animated or nested SVG shape content is unsupported.")
        if style["visibility"] == "hidden":
            return
        data = primitive_path(tag, element)
        subpaths = parse_subpaths(data)
        if subpaths and (style["fill"] != "none" or style["stroke"] != "none"):
            shapes.append(
                Shape(tuple(subpaths), transform, MappingProxyType(style), element.get("id", tag))
            )

    visit(root, viewport, DEFAULT_STYLE, True)
    if not shapes:
        raise ValueError("SVG contains no supported visible vector artwork.")
    if sum(len(sub.segments) for shape in shapes for sub in shape.subpaths) > 20_000:
        raise ValueError("SVG exceeds 20,000 source segments.")
    return Artwork(width, height, tuple(shapes), text, tuple(warnings))
