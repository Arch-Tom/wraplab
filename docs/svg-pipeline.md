# Deterministic SVG pipeline

## Accepted subset

Explicit root width/height in mm, cm, in, pt, pc, px (unitless/px means 96 dpi and raises a note).
Positive viewBox, meet alignment or `preserveAspectRatio="none"`. Source page defines the imported
physical placement frame, including any blank margins. Artwork outside the page is rejected rather
than silently clipping. SVG limit: 10 MB, 20,000 elements/source segments.

Paths (M/L/H/V/C/S/Q/T/A/Z), lines, polylines, polygons, rectangles including rounded corners,
circles, ellipses, compound paths, groups, inherited solid fills/strokes, inline basic styles,
fill rules, shape opacity, caps/joins/miter limit. Matrix/translate/scale/rotate/skew transforms
compose in SVG order and normalize before placement. Reflecting/nonuniform affine transforms are
supported. Curves retain their analytical form until adaptive sampling.

Convert live text to curves. Reject raster images, fonts/text, use/references, scripts/events,
CSS classes/style sheets, gradients/pattern paints, external resources, clipping/masks/filters,
markers, dashes, non-scaling strokes, nested viewports, slice clipping and group opacity.
Unused defs and editor metadata can be ignored because all rendering references are rejected.
XML parsing disables DTD/entity expansion. Solid supported CSS colors are hex, basic named colors,
and comma-separated rgb; fancy CSS color/paint syntax is rejected. Safe strictness takes precedence
over pretending to import every Corel SVG variant.

## Nonlinear transformation and quality

Artwork -> canonical page mm -> physical placement -> optional front-view inverse projection ->
exact development / experimental conformal map -> flat-sheet rotation -> canonical export.

Adaptive subdivision evaluates the whole curve F(p(t)), including explicit and implicit closing
edges. It uses derivative-control hulls for Béziers, ellipse derivative bounds, and whole-support
Jacobian/Hessian bounds. For each C2 leaf, chord error is bounded by (H*V²+J*A)/8; acceptance uses
half the requested tolerance. Seven interior samples and backtracking checks are additional guards.
Source coordinate extrema and all measured-knot crossings are isolated analytically, including
multiple crossings/tangencies. Source and stroke curves use affine derivative bounds too.

Production default is 0.01 mm (stricter than Packet C's suggested 0.02 mm); user range 0.001–0.25 mm.
Preview uses 0.08 mm and is never reused for export. Six-decimal-mm serialization contributes
less than 0.000001 mm of coordinate rounding. Stroke pre-normalization has a separate smaller
budget based on affine/placement/map amplification. Exact-surface derivative bounds are analytical;
measured-profile bounds depend on numerical quadrature, not rigorous interval enclosure. Polygon
validation is not a proof of arbitrary continuous topology. These levels are reported honestly.

Limits: XML 10 MB/20,000 elements, group depth 64, 20,000 source segments, 256 contours per compound
path, recursion depth 20, 200,000 output nodes, 30 seconds per curve and two minutes per conversion.
Failure stops export with a diagnostic; it never silently increases tolerance or exports partial art.

Strokes become filled outlines **before** nonlinear compensation. Local curve/buffer approximation
gets a tighter budget based on affine, placement and conservative mapping amplification. Round caps
and joins use error-based buffer segmentation. This preserves physical stroke width on the mapped
source surface rather than emitting a misleading constant SVG stroke width after warping.
Flattening uses polylines; no Bézier refitting/simplification is implemented yet.

Closed paths export with Z, compound subpaths stay within a common path, and fill-rule is preserved.
Check every filled ring before/after for simplicity and positive area; reject touching/intersecting
compound contours, inverted winding or changed nesting. Open fill contours close implicitly per SVG;
open strokes retain caps during outlining. Overlaps between distinct painted shapes are permitted.
Self-intersecting source fills and touching compound counters are a deliberately unsupported subset.
Shared endpoints are evaluated deterministically; filled/stroked outline geometry is finite.

## Export

UTF-8 SVG 1.1, explicit mm width/height and matching deterministic viewBox. Minimal M/L/Z paths,
simple Artwork/Guides groups, basic inline presentation attributes, preserved opacity/fill rules.
No fonts, raster, resources, transforms or required application state. Six decimal places in mm;
metadata includes algorithm/version, object name, physical model, top direction, viewing assumption,
placement, tolerance and unverified Corel status. No timestamps/random IDs, so repeated exports hash
identically. Artwork-only page trims to actual vector bounds; page-origin metadata records translation
and artwork placement. The serialized output is reparsed and its rounded contours revalidated;
collapsed counters/changed nesting fail. Artwork Only physically excludes guides. Artwork + Guides
and Guides Only share the same page/origin. Guides may cut and are not inherently nonprinting.

Sources are never automatically overwritten. The desktop rejects the original source filename;
CLI checks resolved paths. Exports write atomically. All required work is local and deterministic.
SVG/Qt success does not establish CorelDRAW 2019 interoperability or actual material acceptance.
