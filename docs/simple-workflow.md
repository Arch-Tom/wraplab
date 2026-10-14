# WrapLab simple operator workflow

This implementation is on `codex/wraplab-simple-workflow`, based on verified source integration
`30c539a55410d7015df0360616f3fe8d3521266b`. Main/RC4 and the integration reference are unchanged.
The unavailable historical UX commit was not recovered or reconstructed.

## What changed

The existing engineering is presented through a small operator workspace: measure the object,
import an SVG, set size/position, compare two simultaneous previews, and export from a fixed
footer. The engine, physical model defaults, project format and original fixtures are retained.

- Cylinder asks for diameter and object height; Tapered object asks for top/bottom diameters
  and straight vertical height. Custom curved object retains station measurements, diameter/
  circumference entry, uncertainty/notes, presets and its Best-Fit / Experimental status.
  Its empty cutting view prompts for artwork instead of validating a nonexistent design.
  Advanced template-only export retains editable numeric support-area size/placement.
- Main artwork controls are width, height, Keep proportions and Center artwork. Position artwork
  exposes numeric offset/distance-from-seam and distance down from TOP. Dragging pans the preview
  and never approximately moves physical artwork. Scrolling over measurements cannot change them.
- On the Object and Flat Cutting Pattern are visible together with aspect-correct fit and wheel
  zoom. Front-view is an upright, distant-view 2D target. In Surface-wrap mode the left side is
  explicitly a schematic profile, not a simulated wrapped rendering. Original artwork is secondary.
- Advanced contains interpretation, coverage, pattern rotation and production tolerance. Switching
  interpretation preserves artwork size and explicitly reports recentering because horizontal
  offsets have different meanings. All calculations still use the existing canonical millimeters.
- Artwork-only export remains the default. Other export choices have matching right-side previews
  and clear guide/cutting warnings. Preview reference lines are not included in artwork-only export.
  Export recomputes at the existing production tolerance and reports the path and true tight bounds.
- Loading/invalid states disable export and fade prior previews. Zero measurements are visible
  invalid values, with highlighted fields, rather than silently being replaced by a tiny positive value.
- New job first preserves modified work through the established atomic recovery writer. Resume last
  job reopens that data. Existing saved projects and object presets remain compatible.

The restrained Qt design has readable physical measurements, consistent controls, a clear empty
state and progressive disclosure. The footer stays visible at compact sizes; the remaining controls
scroll. Initial sizing respects available screen space and display scaling. No new dependencies,
web frontend, separate beginner app, project schema or geometry model were introduced.

## Launch and one cylinder job

Follow README's Windows runtime setup with Python 3.12.10 x64 and the hash-pinned runtime lock.
The unchanged isolated launcher is:

```powershell
.\.venv\Scripts\pythonw.exe -I scripts/run_source.py
```

1. Select Cylinder, millimeters, diameter 70 mm and object height 120 mm.
2. Import `tests/fixtures/lettering.svg`, the outlined 60 x 25 mm O/A/B/R example.
3. Set artwork width to 40 mm, leave Keep proportions checked and press Center artwork.
   Height becomes approximately 16.6667 mm; top placement becomes approximately 51.6667 mm.
4. Compare the two previews. Use Position artwork for precise adjustments. Advanced keeps the
   default Front-view artwork, 180-degree coverage and 0.01 mm production tolerance.
5. Export Compensated SVG to a new filename. This example's tight cutting bounds are approximately
   40.316852 x 14 mm, after curvature compensation and removal of blank source-page margins.
   The saved file is a four-path SVG with counters intact and explicit millimeter dimensions.
6. Import at 100% in the cutting editor and verify actual dimensions and material behavior before production.

Ctrl+O imports, Ctrl+Shift+O opens a project, Ctrl+S saves, Ctrl+E exports and Ctrl+N starts a new job.
Local errors are logged by the source launcher in ignored `artifacts/source-run/gui.log`.

## SVG diagnostic and compatibility results

Malformed XML now reports the parser's line and column and an export/repair action. Entity
declarations and external XML constructs remain blocked, with separate explanations that do not
expose resource paths or entity contents. Live text, images, stylesheets and reused artwork receive
specific conversion guidance while remaining unsupported.

Only `background-color:transparent` on the root SVG is newly accepted, with a visible note. Its
synthetic Corel-like compound-path fixture establishes unchanged fill rules, counters, paths and
physical output. Nontransparent backgrounds, the property on painted shapes, unknown properties,
filters, clipping, dashes and other unsupported graphics remain rejected. Scripts/events, unsafe
references, topology, dimensions and unit validation retain their existing boundaries.

Neither missing original failing SVG has been tested or claimed repaired. Actual Corel exports
may still require narrow additional compatibility work backed by the real source files.

## Native Windows validation

Validation used local Windows, Python 3.12.10 x64 and Qt 6.8.3's Windows plugin; no Linux substitute.

| Check | Result |
| --- | --- |
| Fresh baseline at the verified integration | 157 passed, zero failures/skips |
| Complete implementation regression suite | 186 passed, zero failures/skips; all 18 independent geometry fixtures |
| Focused new coverage | 29 added cases: operator mapping, locked/unlocked sizing, numeric placement, recovery/export/preview modes, empty curved/template workflows and SVG diagnostics/style safety |
| Geometry/domain/persistence/adaptive/exporter and original fixtures | Unchanged from the verified source |
| Native source QA | Cylinder, taper-front, taper-wrap and experimental curved profile; project reload and object presets passed |
| Reference comparison | All 16 SVG exports byte-identical to the preserved engine for identical model inputs |
| Native layout/scaling QA | Empty, populated, invalid and compact states; 980 x 650 minimum, 1050 x 700 compact and standard size; 100% and 125% Qt process-local scaling |
| Actual desktop interaction | Import dialog, 70 x 120 mm measurements, 40 mm proportional artwork, Center, previews and native save dialog passed |
| Lint / dependency consistency | Ruff and pip check passed; no new dependencies |

Recorded regression targets were `python -m pytest -q tests` (JUnit report
`artifacts/simple-workflow/complete-final-tests.xml`) and `python -m ruff check src tests scripts packaging`.
These used the preserved, verified development Python; the new isolated runtime intentionally
contains no test or packaging tools. After the final Original size button enablement adjustment,
`tests/test_simple_workflow.py::test_empty_curved_object_prompts_for_artwork_and_keeps_template_support_controls`
was rechecked: 1 passed, zero failures/skips. The complete 186-test run preceded that adjustment.

The source-only QA command (using a separate preserved baseline checkout) is:

```powershell
.\.venv\Scripts\python.exe -I scripts/validate_simple_workflow.py --output artifacts/new-native-qa --reference-source <preserved-baseline-checkout>
```

`--scale-factor 1.25` changes only that QA process's Qt display scale after launcher isolation.
It does not modify the production launcher or Windows settings. Choose a new output directory;
the validator preserves existing reports and generates only local source/SVG/project/screenshot data.

## Limits and consequential follow-up

Native pytest emitted `Windows fatal exception: code 0x8001010d` during Qt event processing in
later runs, including a serial repeat and the complete 186-test run. Those processes continued
and returned success; the ordinary source GUI and native workflow QA did not terminate. Microsoft identifies
this code as a restriction on outgoing COM calls during synchronous input dispatch
([COM error reference](https://learn.microsoft.com/en-us/windows/win32/com/com-error-codes-3)).
The originating native component is not proven; this diagnostic has not been suppressed or
claimed fixed. The logs are preserved locally for follow-up on a clean work-computer run.

LongPathsEnabled was previously zero on this host. No operating-system setting was changed;
the over-280-character extended smoke/restart remains unverified. Use short paths.

Remaining work: obtain the real failing SVGs; validate the managed work computer, CorelDRAW 2019
imports and physical vinyl behavior; investigate the observed COM diagnostic if reproducible
outside this desktop test session. There was no independent first-time-operator usability study.
Measured profiles remain experimental and do not certify material strain, adhesion or suitability.

The Norton standalone verdict remains unresolved. No executable was built, packaged, signed,
restored, distributed or run; no protection or exclusion was changed. No push, merge, PR, tag,
release or packaging workflow was performed. Local implementation commits are for review only.
