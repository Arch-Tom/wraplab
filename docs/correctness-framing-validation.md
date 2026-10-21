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

## Acceptance boundaries

No customer source/project was provided. Tests and generated exports are synthetic;
no customer production cutting file was generated or approved. Windows, CorelDRAW
2019, cutter acceptance, real bell measurements, and physical vinyl fit require
separate native/manual validation. Windows executable distribution remains paused
under the existing repository instructions. No solver/group compensation or material
model changes are part of this pass.
