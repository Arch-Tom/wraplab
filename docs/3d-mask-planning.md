# Interactive 3D preview and mask planning

This is a source-only addition to the existing Windows workflow. The isolated
Python 3.12.10 / Qt 6.8.3 launcher and runtime dependency lock are unchanged.
No executable packaging, new dependency, web frontend, CDN or network service is used.
The unresolved Norton standalone-executable verdict is not cleared by this work.

## Ordinary workflow

Measure the object, import the actual SVG, choose its page/visible sizing frame,
enter the target dimensions and position, inspect the object and flat pattern,
then use the existing Export Compensated SVG button. That button retains its
existing vector pipeline, production tolerance, units, modes and overwrite protections.
Camera and mask settings never silently change ordinary compensation/export.

The On the Object pane now offers Interactive 3D and the retained Original 2D
preview. Drag to orbit, right-drag or Shift-drag to pan, and wheel to zoom. Front,
Left, Right, Rear, Seam and Reset view are available. All views are orthographic;
Front preserves the intended distant, upright viewing convention. These controls
move the camera, never the artwork. Continue to use numeric placement for physical changes.

Neutral shading and actual normalized SVG artwork are displayed on the cylinder,
straight taper or measured surface. The cut output remains vector geometry;
only the display texture is rasterized. Compound paths, counters, source colors,
supported transforms and element paint opacity are retained in that texture.
No fonts or replacement artwork are generated.

Measured objects display only their measured band. Open ends are limits of known
measurements, not a reconstructed crown, neck or lower bell skirt. Circumference
stations use the existing diameter conversion and PCHIP interpolation. No profile
extrapolation or invented surface is introduced.

If the native OpenGL renderer is unavailable, shader initialization fails, or
scene creation fails, the existing 2D preview remains available. A valid ordinary
export is not blocked by a renderer or mask-planning failure. Native graphics
availability must still be checked on the work computer.

## Exactly three CantorLand masks

Open Mask planning (experimental) below Advanced. The verified corrected
CantorLand source has three shapes, 44 closed contours and 12 openings. Its
source-bound recipe selects:

- STAR: the complete eight-contour star, preserving its asymmetric placement.
- HEBREW: all 22 contours from both Hebrew rows, on one physical carrier.
- CANTORLAND: all 14 contours of the English wordmark.

This recipe is used only for the authenticated source identity and verified
topology. Indices are not treated as a universal grouping algorithm. Unknown SVGs
continue to work in 3D and ordinary export; their mask planner requires an explicit
source-bound component assignment. It rejects duplicate/missing contours, a different
source, and any assignment separating an opening from its containing geometry.
For a saved CantorLand project without assignments, Use verified 3-mask grouping
retains all current object measurements and placement. The separate historical-trial
button explicitly replaces them; do not use it instead of newer measurements.
The first planner supports closed opaque fills; resolve live strokes, open paths
and translucency in the source editor before assigning masks. This restriction
does not narrow the existing importer or ordinary export.

Selecting a mask highlights its artwork in both views. Click artwork in the 3D
or flat pane, or use Inspect mask. Isolate selected mask hides the other artwork
and displays that mask's flat pattern. Show separate flat masks presents pieces
at true relative scale with labels and dimensions. Display gaps between these
pieces are for inspection only and are never installation spacing or automatic nesting.

Visibility controls separately cover artwork, cut-contour overlays, carrier edges,
registration, coverage seams and measured limits. Preview lines do not become
cutter commands merely because they are visible.
Carrier/reference overlays appear in the linked flat view as well as on the object.
The manifest retains their flat coordinates separately from cutter contours.
The measured-band warning stays concise so previews remain usable on small windows;
Advanced retains the complete original warning text and support assumptions.

## Two different compensation methods

Split existing compensation is the conservative default. It selects the exact
contour objects from one existing global conversion. It does not refit, recenter,
resample, resize or improve the existing strain field. Per-mask strain ranges
report that same field over the relevant support height, rather than implying
that handling separation itself changed the mathematics.

Independent fit is explicitly experimental. It uses the same existing conformal
support fitter on each group's combined front-plane support rectangle. Both
Hebrew rows use ONE fit, including the region between them. They are not two
separately transformed rows presented as one supposedly undistorted carrier.
The intended object-space locations and shared registration remain fixed.
The ordinary Export SVG button still exports the ordinary whole-layout result;
independent masks use the separate Export separate mask SVGs action.

The historical four-station/four-inch CantorLand trial is available through the
explicit Apply historical CantorLand bell trial button. It preserves recovery
before replacing measurements and placement. It is not applied silently on import.
The trial uses a visible-artwork target, not the original 13 x 11 inch page.
Its star center is approximately +2.195790901 mm from the front meridian.
Neither current measurements nor production settings are claimed approved.

For that historical trial, zero-margin fits give modeled maximum extension of
approximately 4.929% for the whole layout, 0.914% for an independent star,
0.356% for ONE combined Hebrew fit, and 0.0669% for the independent English wordmark.
The old four-group Hebrew figures do not transfer to the combined carrier.
These are software support-fit estimates, not permissible installed strain,
adhesion predictions or ORACAL/transfer-tape qualification.

## Carriers, margins and registration

Handling margins are explicitly L/R/TOP/BOTTOM in millimeters in the front
reference plane. Default zero margins add no handling allowance. Carrier regions
are separate reference geometry around natural components, not arbitrary vertical
slices. A margin outside the measured height or visible region is rejected.
Carrier overlap with another mask's artwork is reported and must be corrected
deliberately. No automatic trim or relief cuts through letters, openings or the star
are invented. Free-form carrier editing, nesting and physical carrier mechanics are
not implemented by this initial planner.

The lowest historical station is also the artwork's lower boundary. A positive
bottom allowance therefore needs additional real measurements or a deliberate
placement/margin change; it cannot be satisfied by extrapolation.

All masks use the same FRONT meridian and measured TOP. Three noncollinear
references, L/R/TOP, carry straight vertical distance down from that TOP and
signed circumferential tape arc at the corresponding height. Projected x is
NOT tape arc. A physical TOP height above a common operator datum may also be
recorded. Without it, heights above an actual physical base are not inferred.
Height above the measured band's bottom is named separately from physical datum height.

For the historical trial, TOP is 9.75 inches above the historical common datum,
and z-down = 9.75 inches minus physical height. This is historical input, not a
new physical verification. Independent fits must be installed from these object
references, never by copying gaps from the old global flat pattern.

## Separate mask export

Choose Export separate mask SVGs and name a NEW package folder. Existing folders
are never replaced. Independent output requires the explicit experimental
acknowledgment checkbox. The package contains:

- STAR.svg, HEBREW.svg and CANTORLAND.svg: artwork cut contours only.
- REFERENCE_ONLY_DO_NOT_CUT.svg: a separate front registration/reference sheet.
- REGISTRATION_REFERENCE_ONLY_DO_NOT_CUT.txt: operator coordinates and instructions.
- manifest.json: source/profile identity, method, assignment, support, dimensions,
  flat-coordinate origins, strain estimates, warnings and unverified acceptance state.

Mask SVGs have explicit millimeter sizes and matching viewBox values, tight bounds,
unchanged compound topology and vector contours. They contain no added carrier trim
cuts, registration cuts, labels, raster images or normal Guides group. Do not resize
their flat bounds back to the requested four-inch frontal height.

Generation/serialization validation completes before any output package is exposed.
Files are written into a unique sibling staging directory and committed together
with a non-overwriting directory rename on Windows. Failed writes clean only that
verified staging directory and preserve existing files. Names and contents are
deterministic for identical inputs. Reference-only filenames do not automatically
make lines noncutting in downstream software: never send the reference files to a cutter.

## Project compatibility and implementation boundaries

Existing version 1/2 projects continue to load. Schema 2 gains optional,
versioned `preview_options` with conservative defaults: camera, selected view/mask,
visibility, explicit source assignment, method, margins and optional physical datum.
No old project automatically becomes a segmented export. New projects containing
these optional fields may need this application version to reopen; retain originals
when switching between older application branches.

The pure Python version-1 scene contract uses canonical millimeters, X right,
Y up about the measured-band midpoint and Z toward the front viewer. The existing
Project mapper's source-to-surface step is shared as `surface_mapper`; development
and rendering consume the same location calculation. Meshes approximate display
surfaces; double-precision vector production calculations remain authoritative.
The scene records its small radial decal display offset to avoid depth fighting;
reference coordinates and all vector exports use the original unshifted surface.

The native viewer consumes only generated triangles, normalized SVG textures and
role-tagged overlays. It exposes no filesystem, JavaScript or network bridge.
The existing SVG security/unsupported-feature contract is unchanged. Qt OpenGL,
OpenGLWidgets and Svg are already included in the pinned Essentials wheel.

Use `scripts/protect_preview_exports.py` for the 72 synthetic production hashes,
`scripts/validate_simple_workflow.py` for the existing native four-scenario workflow,
and `scripts/validate_preview.py` for native renderer/mask/project acceptance. The
latter's optional `--private-svg` input and ALL customer-derived artifacts must remain
outside version control. See the separate validation record for actual results.

CorelDRAW 2019, printer/cutter scale, physical measurements, actual transfer carrier,
ORACAL 951 application and adhesion remain separate acceptance steps. A paper fit,
rendered preview or low numerical strain cannot approve the physical job.
