# WrapLab 0.1

Offline desktop preparation of vector artwork for axisymmetric objects and cut-vinyl patterns.
Python 3.12 + PySide6. No accounts, APIs, machine control, fonts, raster tracing, or telemetry.

**Default: Front-view vinyl.** Desired straight-on artwork maps onto the surface, then into a
flat cutting pattern. This assumes an upright object and a distant horizontal orthographic view.
Use **Surface wrap / template** only when artwork width describes arc distance around the object.

**Cylinder / Straight Taper: exact surface development.**
**Measured Profile: Best-Fit / Experimental.** Curved bells require strain or cuts; an ideal front
preview does not predict actual vinyl behavior. The bell measurements shipped with the app are
illustrative and must be replaced with real measurements.

## Run from source

Windows x64 (Python 3.12.10 installed), directly from source:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -I -c "import sys; assert sys.version_info[:3] == (3, 12, 10), sys.version"
.\.venv\Scripts\python.exe -I -m pip install --require-hashes --only-binary=:all: -r requirements-windows-runtime.lock
.\.venv\Scripts\python.exe scripts/patch_build_dependencies.py
.\.venv\Scripts\python.exe -I -m pip check
.\.venv\Scripts\pythonw.exe -I scripts/run_source.py
```

Use a fresh `.venv`; preserve an existing environment before replacing it. These commands
install the verified Windows runtime wheels and pip, without PyInstaller or development tools.
The source launcher isolates Python imports, DLL search PATH and Qt plugins to the checkout's
environment and the installed Python/Windows directories. It writes errors to
`artifacts/source-run/gui.log`. See [Windows source setup and validation](docs/windows-source.md).

**Windows executable packaging and distribution are paused while the Norton detection remains
unresolved.** Use Python source; the prior executable has not been restored or approved.

Linux/macOS:

```sh
bash scripts/setup.sh
.venv/bin/python -m wraplab
```

Dependencies need network access **during installation only**. App operation is local/offline.
Use the existing checkout; cloud tasks are already isolated and do not need a worktree.

## Shop workflow

1. Prepare the SVG in CorelDRAW 2019. Convert text to curves, expand unsupported effects, and
   export with explicit physical dimensions. Keep intentional margins when you need page framing.
2. Choose **Cylinder**, **Tapered object**, or **Custom curved object**, and mm/in display units.
3. Enter measurements **down from a labelled top**. A taper needs top diameter, bottom diameter
   and straight vertical height. For custom curved objects: enter 3–30 height/diameter or height/circumference
   pairs, check the profile, and save the geometry as **Bell — Current Project**.
4. Import/drop SVG. Choose **Visible artwork** (new-job default when bounds are available) or
   **Original SVG page** under **Size and position by**. Page framing includes blank margins.
   Set the selected frame's front-view target width/height, horizontal center offset, and top
   height. Import conservatively fits that frame to the object; inspect these dimensions.
   Existing projects retain original-page framing and saved placement.
5. Compare **On the Object** and **Flat Cutting Pattern** side by side. **Position artwork**
   exposes accurate horizontal and top-referenced placement; Center artwork sets both automatically.
   Interactive 3D shows the actual SVG on the measured object: drag orbits, right-drag pans,
   and wheel zooms. Front/side/rear/seam cameras and the retained 2D preview are available.
   Original artwork is below the previews. Neither display establishes physical approval.
6. Inspect measured-profile warnings and stretch/compression estimates. Test paper/vinyl first.
7. Use **Export Compensated SVG** for artwork-only output. **Export options** holds guides,
   full templates and uncompensated comparison; guide paths may cut. **Advanced** holds the
   alternative Surface-wrap interpretation, coverage, rotation and production tolerance.
8. Open in CorelDRAW at 100% size. Verify against [the acceptance checklist](docs/corel-acceptance.md).

Source SVG files remain untouched. Projects embed the original SVG; object presets contain geometry
only. Presets and last-session recovery live in the OS application-data directory, not the repository.
Use Open Project to recover `Last-session.wraplab`. Exported SVGs need no running WrapLab process.
Production output is in explicit **mm** even when the interface displays inches.

New job preserves a modified job in the existing recovery file; Resume last job reopens it.
Common shortcuts: Ctrl+O import, Ctrl+Shift+O open project, Ctrl+S save, Ctrl+E export, Ctrl+N new.
See [the simple-workflow guide and validation](docs/simple-workflow.md).
See [interactive 3D, three-mask planning and separate experimental output](docs/3d-mask-planning.md).

## Validate / build

Development tests use the complete pinned `requirements.lock`; this is separate from the
runtime-only Windows setup above. Windows packaging is paused; retained build commands describe
the packaging infrastructure and are not approval to create or distribute another executable.

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python scripts/make_acceptance_pack.py
.venv/bin/python scripts/build_portable.py
```

On Windows use `.\.venv\Scripts\python.exe` instead. Build on the **target operating system**.
The native build script creates a portable folder/ZIP and runs its actual executable through a
Qt + import + preview + 12-export + project/preset self-test. Windows CI performs the same steps.
No Windows executable is claimed until this build runs on Windows.

Headless conversion (same pipeline):

```sh
.venv/bin/python -m wraplab convert tests/fixtures/lettering.svg output-compensated.svg \
  --mode frustum --top 65 --bottom 90 --height 100 --width 40
```

`--project saved.wraplab` reuses geometry/placement. `--workflow surface-template` selects arc-width
placement. New CLI conversions default to visible-artwork framing; `--frame page` includes source
page margins. Saved projects retain their frame unless `--frame` explicitly overrides it.
`--export guides|template|original` selects an alternative output.

Target frame size describes the intended on-object design (or page). The flat cutting dimensions
are shown separately and may differ after compensation; output is not resized back to the target.
Version-1 projects open with unchanged page-based geometry. Saving writes explicit version-2
framing; keep originals if an older WrapLab installation must still open them.

## Evidence and boundaries

- [Geometry and physical model](docs/geometry.md)
- [SVG subset, tolerance, and topology policy](docs/svg-pipeline.md)
- [Mote research decisions](docs/research-decisions.md)
- [Bell measurement and dry-run procedure](docs/bell-measurement.md)
- [Packaging and evidence](docs/packaging.md)
- [Windows release and operator instructions](docs/windows-release.md)
- [Current integration status](docs/integration-status.md)
- [Supervised Windows/Corel/material acceptance handoff](docs/windows-acceptance-pilot.md)
- [Fresh source restoration](docs/restoration.md)
- [Validation record](docs/validation.md)
- [Correctness/framing changes and compatibility validation](docs/correctness-framing-validation.md)

CorelDRAW 2019 and actual Windows shop behavior require manual validation. Physical application
is unverified. Curved profiles use a continuous conformal fit over the support region with separate
required extension/compression diagnostics; this is experimental and is not a material simulation. SVG output uses adaptive polylines rather than refitted Béziers, with node counts
and geometric checks; dense sources or very tight tolerances may need source simplification.
