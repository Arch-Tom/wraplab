# Deterministic SVG pipeline

## Accepted subset

Explicit root width/height in mm, cm, in, pt, pc, px (unitless/px means 96 dpi and raises a note).
Positive viewBox, meet alignment or `preserveAspectRatio="none"`. Source page coordinates and
dimensions are retained. The explicitly selected source frame controls sizing/placement:
original page (including blank margins) or supported visible-artwork bounds. Artwork outside
the page is still rejected rather
than silently clipping. SVG limit: 10 MB, 20,000 elements/source segments.

Paths (M/L/H/V/C/S/Q/T/A/Z), lines, polylines, polygons, rectangles including rounded corners,
circles, ellipses, compound paths, groups, inherited solid fills/strokes, inline basic styles,
fill rules, shape opacity, caps/joins/miter limit. Matrix/translate/scale/rotate/skew transforms
compose in SVG order and normalize before placement. Reflecting/nonuniform affine transforms are
supported. Curves retain their analytical form until adaptive sampling.

Convert live text to curves. Reject raster images, fonts/text, use/references, scripts/events,
complex or external CSS, gradients/pattern paints, external resources, clipping/masks/filters,
markers, dashes, non-scaling strokes, nested viewports, slice clipping and group opacity.
Unused defs and editor metadata can be ignored because all rendering references are rejected.
XML parsing disables DTD/entity expansion. Solid supported CSS colors are hex, basic named colors,
and comma-separated rgb; fancy CSS color/paint syntax is rejected. Safe strictness takes precedence
over pretending to import every Corel SVG variant.

Conditional-processing attributes (`requiredExtensions`, `requiredFeatures`, `systemLanguage`)
are rejected throughout the document, including groups, hidden descendants and unused definitions.
Resolve the intended visible content in the source editor and export an unconditional plain SVG.
XML stylesheet processing instructions are detected by the safe parser before they are discarded
and rejected; ordinary comments, metadata text and unrelated processing instructions remain valid.
No stylesheet resource is loaded.

Element opacity is applied after its fill and outlined stroke have been painted. When conversion
emits both paints, export keeps their separate cutting contours and individual paint opacity in
one SVG group carrying the element opacity. Opaque and single-paint output retains its existing
representation. The ideal-front preview preserves this grouping as well. Arbitrary group opacity
on imported SVG remains unsupported; importing a newly exported semitransparent two-paint group
therefore still requires resolving it in the source editor. Its downstream CorelDRAW behavior is
unverified. This export correction does not change geometry or broaden the imported SVG subset.

The parser blocks XML entity declarations and external XML references. A bare SVG DOCTYPE
does not necessarily fail and is not fetched as a rendering resource. Malformed XML is reported
with parser-provided line/column; blocked declarations get separate operator guidance without
printing resource paths or entity values. A transparent root SVG `background-color` can be
ignored with an explicit note: it contributes no painted geometry. Opaque page backgrounds,
the same property on rendered elements and other unknown inline properties remain unsupported.
Internal CSS supports only simple single-class selectors (including comma-separated lists) and
the existing solid fill/stroke properties. Presentation attributes are overridden by matching
class rules in stylesheet order, then by inline declarations; explicit inherit uses the parent
computed style. Unresolved classes, conditional rules, complex selectors, important declarations,
resource paints and unsupported properties are rejected, including in unused rules.

Known shape/text/image rendering hint values are validated and ignored with a note: WrapLab's
own physical curve tolerance controls sampling. A valid clip-rule has no painted effect without
clipping; actual clip-path references remain unsupported. Fill-rule is retained and resolved
independently, including class rules overriding an inherited evenodd value with nonzero.
Corel compatibility regressions are synthetic; real job artwork is tested locally, not committed.

## Source framing

Visible bounds are cached on immutable Artwork. The existing solid-paint conversion
pipeline resolves supported inherited/class styles, fill rules, implicit fill closure,
compound paths and stroke outlines in canonical page mm. Transparent/hidden paint
and line-only fills contribute no bounds. Analytical curve extrema, including nested
affine transforms and ellipse extrema, are retained before sampling. Bounds come from
supported painted geometry, not control-point hulls or the SVG viewBox alone.

Straight stroke outlines use their actual caps/joins. Curved/round strokes use a
tighter numerical outline budget and an outward 0.00001 mm source envelope, with
miter amplification included in the local budget. This is a numerical envelope under
the existing outline approximation, not a browser-renderer or interval-arithmetic
proof. Visible-frame conversion uses the same or tighter source outline precision.
If the envelope scaled to the target exceeds one quarter of production tolerance,
conversion fails explicitly. The preview cannot bypass that production-accuracy gate.

Existing source-page, topology, node/time, paint and resource limits still apply. A
failed bounds calculation is reported and cannot select guessed visible bounds.
The GUI falls back visibly to original-page framing; this does not bypass a conversion
error for unsupported geometry. Masks, clipping, filters, dashes and other unsupported
appearance features remain rejected. Simplify the source or use original-page framing
where the existing converter can safely handle it.

Version 2 stores `artwork_frame` as `page` or `visible`. Version-1 files migrate only
in memory to `page`, preserving placement, source coordinates and object settings.
Opening does not write the source project. Explicit saves write version 2; older
WrapLab versions cannot read those files. Programmatic `Project()` retains page
semantics for existing callers; new GUI jobs and CLI conversions prefer visible.

The selected frame is translated to a local origin before scaling; derivative bounds
are unchanged by translation, while measured-knot source coordinates include the frame
offset. The same frame controls import fit, aspect lock/reset, placement, support-band
validation, original/front previews and production conversion. Switching frames keeps
target height and physical top/horizontal anchors; locked proportions update width.
Neither frame is a cutting sheet or transfer-tape model. The existing conformal solver
still fits one selected rectangular support region. No grouping is implemented.

Production SVG pages continue to trim to the exported vectors; metadata records the
translation, selected frame, intended frame size and calculated flat artwork size.
Selecting original-page framing preserves input page sizing semantics, including
margins; it does not change this existing output trimming rule.

## Nonlinear transformation and quality

Artwork -> canonical page mm -> selected frame origin/size -> physical placement -> optional front-view inverse projection ->
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
Topology checks ignore a terminal closure sample only when it differs from the first by at most
four coordinate floating-point ULPs, capped at 1e-10 mm. Interior vertices and source/export point
lists remain untouched. Genuine self-crossings, compound intersections/touches, negligible area,
winding inversion and counter changes still stop export. Valid SVG with intersecting compound
fills can therefore remain unsupported for cutting, even after successful style-aware import.

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
