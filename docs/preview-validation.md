# Native 3D and three-mask validation record

## Source and preservation

Feature branch: `codex/interactive-3d-mask-planning`.
Verified baseline: `a0dc157c655edbf064024b7493e6a0625e446d97`.
This latest available SVG-corrected source includes the earlier framing fixes and
four-group research; the older `14a15c5` working checkout was preserved, not reset.
Main/RC4 and existing integration/research/release references are not changed.

The canonical source-to-surface step was extracted into `Project.surface_mapper`
without changing its arithmetic, so development and rendering share it. Optional
project presentation/planning state was added. Geometry fitters, SVG importer,
production converter/exporter, atomic persistence, original numerical fixtures,
runtime lock, isolated launcher, packaging and CI tooling remain unchanged.
Two old UI visibility assertions now check the active preview pane instead of
requiring a particular old 2D widget; numerical assertions were not weakened.

No dependency was added. The fresh runtime was installed offline using the existing
hash-required Windows wheel lock/cache and guarded NumPy helper patch. Python and
pythonw signatures are valid Python Software Foundation signatures. `pip check`
and Ruff pass. No PyInstaller command, standalone executable, release or security
setting change is part of this work.

## Environment and results

All following execution is local Windows x64, Python 3.12.10, Qt 6.8.3 and the native
Windows Qt platform. The renderer initialized a working desktop OpenGL context.
There is no substituted Linux/cloud acceptance.

| Check | Observed result |
| --- | --- |
| Fresh untouched application baseline, tests directory | 355 passed, 1 pre-existing failure, 8 optional Inkscape skips |
| Final complete application + recovered reference suite | 395 passed, 1 identical pre-existing failure, 8 optional Inkscape skips; 404 collected |
| Focused planner/mapping/serialization tests | 19 passed; includes independent numerical reference, source membership, containment, carrier/seam/domain conflicts, deterministic output and transactional failure |
| Post-alignment native renderer/UI tests | 10 passed; rendered colors/orientation/counter/opacity pixels, rear occlusion, startup/runtime graphics fallback, linked selection, true-scale mask display, project reload and export isolation |
| Original independent geometry corpus | All 18 fixtures pass |
| Protected synthetic production exports | All 72 SHA-256 values match the pre-edit native baseline |
| Existing native workflow validator | Four scenarios (cylinder, taper-front, taper-wrap, measured); all 16 export modes byte-identical to the preserved baseline; project/preset and invalid-input checks pass |
| Actual supplied CantorLand ordinary exports | All four ordinary modes byte-identical to the preserved baseline, at both native QA scales |
| Actual CantorLand masks | Exactly STAR / HEBREW / CANTORLAND; both Hebrew rows together; 44 contours / 12 openings retained |
| Actual independent three-group reference calculation | Maximum fit-slope difference 2.23e-16, flat-coordinate difference 5.69e-14 mm, inverse object-coordinate difference 1.72e-11 mm |
| Native scene/layout/project QA | 100% / 125% process-local scale; all camera directions, isolation, both mask methods, save/close/reopen, standard/compact/minimum layouts pass |
| Corrected actual flat-overlay alignment | All three rendered SVG elements agree with scene overlays within 1.17e-6 scene pixels at both scales |

The full suite's nonzero exit is NOT a new feature regression or an all-green run.
`test_legacy_export_geometry_matches_captured_prechange_output` already fails before
edits on this Windows environment: measured unrounded `page_origin_mm` differs by
approximately 2e-15 mm from the captured reference. Its serialized path attributes
and physical dimensions match. The exact fixture/assertion is retained unchanged;
neither metadata nor production exports were altered to hide the portability issue.
The eight skips require the optional Inkscape CLI, which is unavailable here.

## Actual CantorLand comparison

The most recent file supplied by the owner authenticates as the corrected
three-shape source. Its topology is checked before using the source-specific
assignment; no replacement lettering or synthetic customer logo is used as evidence.
Customer files, saved projects, screenshots, derived SVGs and raw evidence remain
local under ignored acceptance artifacts, outside the public source change.

The comparison uses the explicitly labeled historical nominal bell stations and
four-inch VISIBLE artwork trial, not unconfirmed newer measurements or page sizing.
The star's front offset is +2.195790901 mm and is not independently centered.
Both Hebrew rows are one 22-contour mask with one combined support fit.

| Group | Existing global field over group support | Independent group fit |
| --- | --- | --- |
| STAR | 4.929% maximum modeled extension | 0.914% |
| HEBREW, both rows together | 1.783% | 0.356% |
| CANTORLAND | 4.633% | 0.0669% |

Splitting the existing global conversion retains every contour and the SAME field;
it does not achieve the independent-fit column. The earlier four separately fitted
groups' Hebrew numbers do not apply to one combined carrier. All figures describe
the mathematical support model, not validated film/tape/adhesion behavior.

## Visual defect found and corrected during acceptance

An independent visual review caught displaced flat-view overlays. The SVG item's
intrinsic scene bounds were in pixels, while overlay paths were in millimeters.
Overlays now use the renderer's actual viewBox, the item's actual bounds and its
parent scene transform. Separate-mask items also compensate fractional intrinsic
size rounding so their scene dimensions equal the true vector dimensions.

The added regression samples actual rendered ink pixels before and after selecting
a mask, not merely item presence or brush color. Customer element/overlay bounding
comparisons and corrected screenshots at both scales independently confirm the fix.
Carrier/reference overlays are display-only and do not enter ordinary cutting files.

## Commands and local evidence

Development tests use the preserved verified developer interpreter; the runtime-only
`.venv` intentionally has no pytest, Ruff or packaging tools. From the checkout,
the completed full target was:

```powershell
python -I -m pytest -q tests research/four_group/test_reference.py -o 'pythonpath=src .' --junitxml=artifacts/preview-acceptance/reviewed-final-tests.xml
python -I -m ruff check src scripts tests research/four_group
```

Runtime/native validation uses the unchanged source isolation helper:

```powershell
.\.venv\Scripts\python.exe -I scripts/protect_preview_exports.py --compare artifacts/preview-acceptance/protected-baseline.json
.\.venv\Scripts\python.exe -I scripts/validate_simple_workflow.py --output artifacts/NEW-workflow-check --reference-source PRESERVED_BASELINE_CHECKOUT
.\.venv\Scripts\python.exe -I scripts/validate_preview.py --output artifacts/NEW-preview-check --reference-source PRESERVED_BASELINE_CHECKOUT
```

The preview validator additionally supports `--scale-factor 1.25` and an optional
`--private-svg` path for the authenticated customer source. Scale changes affect
only that QA process, not Windows or the production launcher. Always choose a new
output folder; validators preserve existing evidence. Customer-derived QA output
must not be committed or publicly distributed.

Retained local evidence includes baseline/final JUnit/logs, protected hashes,
native workflow reports, two-scale customer reports, independent reference results,
mask packages and corrected `aligned-100` / `aligned-125` screenshots. The actual
cutting export validations use production tolerance; previews use their existing
coarser display tolerance and do not rasterize cutter geometry.

## Acceptance limits

The desktop control helper exposed application accessibility but returned a black
capture and failed to activate the window after one recovery/rebinding attempt.
Mouse/keyboard automation was stopped. Live OS-level import/save dialogs and manual
orbit/pan interaction are therefore NOT claimed passed in this session. Native Qt
source startup, rendered-pixel checks, camera controls, source/project loading,
exports and close/reopen were exercised by the native application QA instead.

CorelDRAW 2019, work-computer deployment, printed/cutter scale, independently
reconfirmed bell measurements, actual ORACAL 951, transfer carrier and physical
application/adhesion remain unverified. Carrier edges are reference geometry;
automatic trim/relief cuts, general nesting and physical sheet simulation are not
implemented. Positive bottom handling allowance at the last measured station is
rejected rather than extrapolated.

The extended-path smoke/restart was not claimed passed; keep paths short. The older
non-terminating Qt/COM diagnostic has not been proven fixed. The Norton standalone
executable verdict remains unresolved. No quarantined executable was restored,
protection disabled, exclusion added, or executable package created/published.

For a safe work-computer trial, use [the separate-checkout and backup instructions](work-pc-preview-update.md).
