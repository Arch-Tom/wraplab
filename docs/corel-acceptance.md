# CorelDRAW 2019 acceptance — NOT YET VERIFIED

Generate `artifacts/corel-acceptance` with `python scripts/make_acceptance_pack.py`.
Portable builds include `Corel-Acceptance`. All specimens use illustrative geometry, not the real bell.

Open/import each specimen at **100%**, with document units mm. Compare page/artwork physical
dimensions against `manifest.json`. Artwork-only exports trim the page to the actual compensated
vector bounds; blank source-page margins do not become production geometry. Guide exports retain
object-relative placement. Inch display never changes the mm output scale.

| Specimen | Main checks |
| --- | --- |
| 01 Cylinder front | Outlined thin strokes, circles, calibration geometry; true dimensions |
| 02 Frustum front | Level-front target mapped to curved vinyl pattern; narrow top |
| 03 Bell experimental | Curved profile; inspect distortion warnings, not physical approval |
| 04 Compound lettering | O/A/B/R holes/counters remain open; evenodd fills |
| 05 Bell guides | Artwork and Guides groups separable; alignment references visible |
| 06 Uncompensated bell | Control sample for an actual material/viewing comparison |
| 07 Reverse frustum | Wider top than bottom; correct orientation |
| 08–09 Full templates | Seam edges, top/bottom distinction, explicit physical sizes |
| 10–12 Size references | 100 mm square and identical 25.4 mm / one-inch squares |
| 13 Hebrew-like paths | Existing right-to-left geometry stays in source order; not a reference font |
| 14 Eight | Two counters survive curves and taper compensation |

For every file record:

- Opens without warning or unexplained scaling/clipping.
- Width/height and a ruler reference agree with the manifest in millimeters.
- Curves look smooth at shop magnification; inspect node count and practical editability.
- Counters stay open; winding/fill behavior matches the original; no tiny loops or inverted contours.
- Filled stroke outlines preserve intended thin lines; there are no live fonts or raster dependencies.
- Guide group is distinguishable/removable. Artwork-only output has no guides.
- Guide paths may cut; group names do not make paths nonprinting/noncutting.
- Artwork orientation, labelled top, and placement match the project.

Record Windows version, Corel build, import options, measured dimensions, node counts, and any
screen evidence in a shop acceptance report. Browser/Qt rendering is **not** Corel acceptance.
Keep Corel status unverified until a person completes these checks on CorelDRAW 2019.
