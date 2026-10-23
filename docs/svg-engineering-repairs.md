# October 2026 targeted SVG repairs

Research baseline: `aa4087a430423a0ac2b2762dd7b03babcb0712e5`, preserving the corrected
Phase 1 source. Dedicated repair branch: `fix/svg-rendering-contracts`. The authoritative
research branch is not changed. These repairs do not establish production approval.

## Conditional processing — P2

**Root cause.** The importer validated selected unsupported attributes only during rendering
traversal. SVG conditional-processing attributes were absent from those checks. Their conditions
were ignored, causing excluded shapes to participate in visible bounds and cutting output.

**Change.** The document-wide preflight rejects `requiredExtensions`, `requiredFeatures` and
`systemLanguage` before rendering traversal, including root/groups, hidden descendants, unused
definitions and empty attributes. The error identifies the attribute and tells the operator to
resolve conditional content in the source editor and export an unconditional plain SVG. No locale
or extension support is guessed. Referenced rendering content remains unsupported.

**Before/after.** The independent 10 mm square/conditional 50 mm rectangle fixture previously
produced 80 mm source bounds, a 1.25 mm intended square and unwanted cutting geometry at a 10 mm
target height. It now fails import explicitly. The equivalent unconditional square retains its
10 mm visible extent and requested 10 mm output height.

**Regression coverage.** All three attributes, nonempty/empty values, shape/group/root/hidden/defs
contexts; ordinary visible content and `display="none"` remain supported. This intentionally
narrows acceptance of previously misinterpreted conditional documents, including unused content.

## Element opacity — P2

**Root cause.** Conversion multiplied element opacity into both emitted fill and outlined-stroke
paths. Overlapping half-opacity paints then composited at 75% alpha rather than applying 50%
opacity once to the completed element.

**Change.** The internal vector-path record can associate consecutive paints with one source
element. When a nonopaque element actually emits both fill and stroke, their individual paint
opacities are kept separate and export places them in one group with the element opacity. Cut
path coordinates, ordering, winding, contours, page bounds and compensation are unchanged. The
ideal-front preview preserves that association. Opaque and single-paint output keep their
existing representation; neighboring source elements have distinct groups.

**Before/after.** Independent Inkscape rendering of the reported overlap changed from exported
RGBA `(85, 0, 0, 192)` to the correct `(0, 0, 0, 128)`, matching the source. Mixed fill/stroke paint
opacity is composited inside the element opacity rather than conflated with it.

**Regression coverage.** Overlap; individual paint opacity; separate neighboring elements; fill
only; stroke only; transparent stroke; opaque artwork; ideal-front preview; exact contour/path
and dimension equality for cylinder, frustum and measured compensation. Eight independent
Inkscape rendering combinations compare interior, overlap and stroke-only samples. Inkscape is
an optional test tool; those checks explicitly skip if it is unavailable. It was available for
this validation. No production dependency was added.

**Limitation.** Arbitrary imported group opacity remains outside the accepted input subset.
Newly exported semitransparent two-paint SVGs use standard group opacity and cannot be reimported
unchanged through that strict subset. Resolve the compositing in the source editor if reimport is
required. CorelDRAW 2019 interpretation of these newly grouped exports still needs downstream
verification. Existing opaque frozen customer files do not acquire these groups.

## Stylesheet processing instructions — P3

**Root cause.** The safe XML parser discarded processing instructions before the SVG checks,
so `xml-stylesheet` bypassed the promised external-stylesheet rejection.

**Change.** A tree-builder callback observes the actual XML instruction events before they are
discarded. Any `xml-stylesheet` instruction is rejected with self-contained/inline-style guidance.
The existing defused parser protections and malformed-XML diagnostics remain. No resource is
fetched, and text-pattern matching is not used to classify XML instructions.

**Before/after.** External CSS instructions previously imported with no warning; they now fail
explicitly. Ordinary XML declarations, unrelated instructions, comments, metadata and CDATA text
containing stylesheet-like strings remain valid.

**Regression coverage.** Relative and remote stylesheet references before/inside/after the root
and inside metadata, plus harmless lookalike text. Existing entity, external-resource, malformed
XML, Corel-style and source-framing regressions also remain in the full suite.

## Validation and protected inputs

New cases are in `tests/test_svg_rendering_contracts.py`; all fixtures are synthetic. Before the
repair, the original independent probe reproduced 12 passes and four failures. The new regression
file also failed against the baseline, including the opacity renderer comparisons.

The original independent probe's conditional-case text permits rejection, but the runner did not
catch that exception. The post-repair run therefore uses a separate copy with only an explicit
successful-rejection branch added. Original evidence is unchanged; rendering comparisons and
other expectations are unchanged. The adapter diff, before/after results and run logs are kept
in the private validation evidence, not mixed with customer packages.

The local validation directory is `/workspace/wraplab-svg-repair-20261023/`. Its
`VALIDATION-REPORT.md` records final counts, independent probes, output comparisons and protected
hashes. No protected artwork, candidate file, calibration vector, measurement record or archive
is modified or regenerated. No solver, geometry, persistence, Windows installation or packaging
code is changed. No artifact package is repacked.

Final validation: **375 tests passed, zero failures/skips** (317 existing plus 58 new cases).
The rejection-aware independent SVG probe passes **16/16**. All **72 synthetic safe SVG exports**
are byte-identical to the research baseline across three geometry modes, page/visible framing,
two scales and artwork/guide exports. Fresh independent geometry and registration probes pass.
All **2,155 private artifact files**, including the three frozen ZIPs, retain their hashes.
Ruff and dependency checks pass. Windows/CorelDRAW, physical printer/cutter scale, current bell
measurements, apparatus accuracy and material behavior remain unverified.

For the next experimental physical step, use [the bench checklist](bench-rehearsal-checklist.md)
with unchanged candidate-009 and the private revised guides. Software correctness cannot establish
the original datum, current bell geometry, apparatus accuracy, finish compatibility or material
acceptance.
