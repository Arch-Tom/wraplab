# Correctness and framing validation

## Source and baseline

Started from a clean `work` branch at `9a214b50cdf6d9d27cf8a3cf92bd92bb420181ec`
(the older main implementation). Fetched and inspected the requested investigation
branch, then created local `fix/correctness-framing` at its exact tip,
`14a15c52890edf9bdd92f17b1d8ea88e0e88d505`. No later repairs existed on that branch.
No AGENTS.md files were found. Read README, source repair, SVG pipeline, geometry,
integration, persistence, and operator workflow documentation. Existing ignored
environments, artifacts, and operator data were preserved. Nothing was pushed or merged.

The baseline already includes bounded Corel class CSS, rendering hints, inherited
currentColor, ULP-scale terminal closure checks, and exact endpoints in profile/front
preview and import-fit sampling. Those repairs are retained.

## Stage A

Before editing application code, `tests/test_correctness.py` produced **11 failures
and 5 passes**. The reproductions confirmed:

* `M10 10 m5 5 h10 v10 h-10 z` starts at (5,5), rather than (15,15).
  Moveto-only chunks lost the current point. `parse_subpaths` now retains it, even
  when the parser returns no drawable segments.
* `M10 10H20V20H10Z L30 30` becomes a single closed stroke. Splitting after Z now
  preserves the closing current point and starts an independent open continuation.
  Each subpath gets its own caps/joins; overlapping painted stroke regions are
  combined before topology validation. An independent square-annulus plus
  butt-capped diagonal polygon establishes bounds (9,9) and the expected area.
  Disjoint stroke outlines retain their previous order and coordinates.
* At height `8.5 * 25.4`, mapping page y=20 reconstructs a value one ULP too large
  for cylinders, frustums, and measured profiles. The mapper now preserves the
  explicitly selected frame's top/bottom endpoints. Interior arithmetic and strict
  surface guards are unchanged; even the next float beyond a surface's height is
  still rejected by its radius function.
* First stations within the existing 1e-10 mm zero acceptance threshold were not
  canonical, leaving radius(0) undefined for positive values. Only the constructed
  surface now canonicalizes those accepted stations to zero. Raw ObjectSpec values
  remain intact; values beyond the existing threshold still fail.

Path-state expectations follow SVG 2 Paths, sections on moveto and closepath:
https://www.w3.org/TR/SVG2/paths.html#PathDataMovetoCommands and
https://www.w3.org/TR/SVG2/paths.html#PathDataClosePathCommand.
These are synthetic cases, not evidence of damage to CantorLand artwork.

Stage A labels say Page target width/height and explain blank margins; no framing
semantics changed. Saved output is labelled flat pattern. The conformal method,
PCHIP interpolation, fit objective, integration, exact surface formulas, topology
guards, atomic persistence, and source protection remain in place.

`tests/fixtures/legacy-page-projects.json` contains three synthetic version-1
projects captured from the investigated commit, with cylinder/frustum/measured
objects, page margins, transformed compound holes, a stroked shape, and rotations.
Captured SVG attributes, every exported path attribute, and untrimmed page origin
are compared directly. This verifies actual exported vectors, not just loading.

Validation uses Linux x86_64, Python 3.12.14, PySide6/Qt 6.8.3 and the pinned
requirements.lock. Initial baseline: **262 passed, 1 failed** in 194.72 seconds;
the failure is tests/test_ui.py's screenshot minimum width (980 vs 1050 pixels)
on Qt's default offscreen screen. No assertion was weakened. A Qt offscreen
configuration with a 1600x1000 screen resolves the display prerequisite:

```sh
python3 -c 'import json; json.dump({"screens":[{"width":1600,"height":1000,"logicalDpi":96}]},open("/tmp/wraplab-offscreen.json","w"))'
export QT_QPA_PLATFORM=offscreen:configfile=/tmp/wraplab-offscreen.json
export XDG_DATA_HOME=/workspace/.local/share/wraplab
export XDG_CACHE_HOME=/workspace/.cache/wraplab
```

Commands run from `/workspace/wraplab`:

```sh
.venv/bin/python -m pytest -q tests/test_correctness.py
.venv/bin/python -m pytest -q tests/test_correctness.py tests/test_geometry.py tests/test_front_view.py tests/test_svg.py tests/test_corel_compatibility.py tests/test_research.py
.venv/bin/python -m pytest -q --junitxml=artifacts/correctness/stage-a-tests.xml
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m wraplab --self-test artifacts/correctness/stage-a-smoke
```

Focused stage A: **210 passed** in 40.45 seconds. Lint passed. Qt self-test passed
12 exports, project/preset round trips, previews and source protection. Legacy
export vectors and origins were byte-for-byte unchanged in the captured cases.
Logs remain under ignored `artifacts/correctness/`.

Full Stage A checkpoint: **279 passed, zero failures/skips** in 181.16 seconds
with the configured offscreen display. All 18 independent research fixtures ran.
Stage B starts only after this checkpoint; no required Stage A checks remain blocked.

## Stage B: explicit source frames

`svg/model.py` represents a frame as canonical page-mm origin/extent, with numerical
accuracy/outline precision where needed. `svg/framing.py` calculates visible bounds
through the existing solid-paint converter. Filled-curve coordinate extrema survive
sampling, including affine/group transforms; compound holes, class/inherited styles,
transparent paint and stroke caps/joins follow the existing importer/outline rules.
Curved/round stroke bounds use a small outward numerical envelope, with miter budget
and the same or tighter source outline precision during actual conversion. An enlarged
target that would exceed the allowed bounds-accuracy budget fails explicitly.
This is the supported manufacturing subset, not general browser rendering. See
[the source-frame contract and precision limits](svg-pipeline.md#source-framing).

`Project.source_frame` selects the page or visible frame. `svg/exporter.convert`
translates page coordinates by that frame's origin, then applies placement scaling
and the existing projection/development. Measured-knot source coordinates include
the translation; derivative bounds do not change. Import fitting, Original size,
aspect/frame changes, support validation, front/original previews, CLI conversion and
production export all use this selection. Original vectors/source text are retained.

New GUI jobs and CLI conversions prefer visible bounds. Programmatic `Project()`
keeps page semantics for existing callers. `--frame page|visible` selects explicitly;
`--project` retains its persisted frame unless overridden. Invalid/unsupported bounds
cannot silently become guessed geometry. GUI fallback reports why page framing is
selected, and existing conversion errors remain blocking. The source-page overflow,
visible-edge, seam, measured-domain, topology, resource and complexity guards remain.

The UI adds one frame selector, source-page/visible readouts and a calculated flat
artwork readout. Target labels identify the selected frame. Switching frames retains
target height and physical placement anchors; with Keep proportions, width adopts
the selected frame's ratio. The existing ability to unlock/stretch and then lock the
operator's edited proportions is preserved. Units only affect display. The original
comparison readout uses uncompensated dimensions; compensated exports are never
resized back to target size. Export metadata distinguishes target frame dimensions
from flat artwork dimensions. Support assumptions are labelled separately from
unmodeled physical transfer tape/carriers. No grouping or new solver was introduced.

### Compatibility evidence

Schema 1 loads in memory as schema 2 with explicit `page` framing. Saved placement,
rotation, units, physical model, raw station data and source text retain their values.
Opening does not rewrite files. Explicit saves write schema 2 with a required frame;
keep old files if an older installation must read them. No user migration is required
to open legacy jobs in this version.

All three captured synthetic legacy projects produce the same SVG physical page
dimensions, every path attribute/serialized vertex (including rotated positions and
compound counters), topology and page-origin metadata as the investigated baseline.
UI opening/export and CLI `--project` also exercise actual saved version-1 fixtures.
Files are compared before/after opening, not merely deserialized. Added metadata and
support-warning wording are intentionally different; physical geometry is unchanged.
The Windows source-QA comparison script now explicitly chooses page framing for its
historical reference and compares vectors/origins separately from changed metadata.
That Windows-only runner was updated but not executed on this Linux host.

Synthetic bounds tests cover margins, nested mirrored/nonuniform transforms, class
fills, counters, interior cubic/ellipse extrema, expanded stroke caps/round joins,
unsupported appearance, page overflow, true crossings, frame/unit persistence and
full-height stroke placement. Analytical cylinder and both-direction/near-cylinder
frustum corner expectations are independent of Project.mapper. Existing measured
PCHIP/conformal research tests remain intact. The 13x11-inch synthetic reference has
304.7996x200.575 mm visible geometry: a 4-inch visible target is 6.0785163 inches wide;
page sizing instead makes the visible height approximately 2.87151 inches. This does
not independently verify CantorLand or its investigative 4.601-inch flat-height value.

### Validation commands and results

Use the same Linux display/XDG settings above. Additional commands executed:

```sh
.venv/bin/python -m pytest -q tests/test_framing.py tests/test_simple_workflow.py
.venv/bin/python -m pytest -q tests/test_framing_ui.py
.venv/bin/python -m pytest -q tests/test_framing.py
.venv/bin/python -m pytest -q --junitxml=artifacts/correctness/stage-b-tests.xml
.venv/bin/python -m pytest -q --junitxml=artifacts/correctness/final-tests.xml
.venv/bin/python -m pytest -q tests/test_framing_ui.py tests/test_simple_workflow.py::test_unlocked_size_and_relocked_current_proportions_are_preserved
.venv/bin/python -m pytest -q --junitxml=artifacts/correctness/final-verified-tests.xml
.venv/bin/python -m pip check
.venv/bin/python -m ruff check src tests scripts
git diff --check
.venv/bin/python -m wraplab --self-test artifacts/correctness/stage-b-smoke
.venv/bin/python -m wraplab --self-test artifacts/correctness/stage-b-smoke --resume
.venv/bin/python -m wraplab --self-test artifacts/correctness/final-smoke
.venv/bin/python -m wraplab --self-test artifacts/correctness/final-smoke --resume
.venv/bin/python -m pytest -q tests/test_correctness.py tests/test_geometry.py tests/test_front_view.py tests/test_svg.py tests/test_corel_compatibility.py tests/test_research.py
.venv/bin/python -m wraplab convert tests/fixtures/lettering.svg artifacts/correctness/cli-visible.svg --mode frustum --top 65 --bottom 90 --height 100 --width 40
.venv/bin/python -m wraplab convert tests/fixtures/lettering.svg artifacts/correctness/cli-page.svg --mode frustum --top 65 --bottom 90 --height 100 --width 40 --frame page
```

The first broad Stage B run passed **299 tests**, zero failures/skips, in 271.18 seconds.
Expanded framing checks passed **22 tests** in 25.05 seconds; dedicated UI checks
passed **3 tests**. Qt launch and restart self-tests each passed all 12 exports,
project/preset persistence, previews, Unicode paths and source-overwrite protection.
Screenshot inspection confirmed the existing workspace/footer remains accessible.
CLI page and visible conversions succeeded, with separately reported target/flat
dimensions. CLI legacy measured-project vectors match the captured baseline exactly.

During development, one synthetic square-cap reference omitted the group's x-scale;
its independent expectation was corrected. A tight round-stroke bounds calculation
hit the existing per-curve time limit during concurrent exploratory runs; isolated
and broad reruns passed without weakening that limit. A later combined run caught
an unintended change to the existing edited-proportion relock contract; that change
was reverted and its regression plus the three framing UI tests passed (4 total).
No assertion or production guard was disabled to resolve these results.

The intermediate combined run recorded **303 passed, 1 failed** (the relock regression
above); it is not counted as a clean pass. Final source launch/restart self-tests each
passed again. A final parser review also reproduced a new boundary case introduced
by splitting after Z: bare coordinates could be mistaken for an implicit line after
the wrapper injected its internal moveto. An explicit following command is now
required, matching SVG grammar and the underlying parser's previous rejection.
After this last guard, the full relevant SVG/geometry/independent-research selection
passed **212 tests** in 50.17 seconds, including both new malformed-input regressions.

The final combined run completed **304 passed, zero failures/errors/skips** in
272.47 seconds. It collected before the two final closepath grammar cases were
added; the subsequent 212-test SVG/geometry run covers those cases and the last
parser change. Together the full and focused runs cover all **306 distinct tests**
in the final checkout. All 18 independent Packet A research cases executed.
Ruff, dependency consistency and `git diff --check` passed. No required Linux
development checks remain unresolved. New native packaging, Windows source QA,
CorelDRAW and physical acceptance were not executed for these changes.

## Final implementation state

Local branch: `fix/correctness-framing`. Stage A is commit `2d854d9`; Stage B is the
subsequent commit named `Add explicit source frames while preserving legacy vectors`.
The final response records its identifier. Application changes are confined to SVG
state/outlines/framing, endpoint handling, versioned frame persistence, CLI selection
and the limited UI controls/readouts. Tests add synthetic legacy exports and focused
correctness/framing/UI regressions. README and geometry/SVG/operator documentation
describe the behavior. Windows source QA distinguishes vectors from metadata.
Dependencies and mathematical fitting algorithms were not replaced. No merge/push,
workstation changes, customer file edits, or release distribution was performed.

Suggested next task: native Windows **source** validation on copies of real saved
projects, followed by supervised CorelDRAW 2019 acceptance. Preserve originals before
explicitly saving version-2 files; choose Original SVG page to retain intentional
page margins. Do not change the currently installed shop runtime without validation.

## Acceptance boundaries

No customer source/project was provided. Tests and generated exports are synthetic;
no customer production cutting file was generated or approved. Windows, CorelDRAW
2019, cutter acceptance, real bell measurements, and physical vinyl fit require
separate native/manual validation. Windows executable distribution remains paused
under the existing repository instructions. No solver/group compensation or material
model changes are part of this pass.
