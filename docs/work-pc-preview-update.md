# Use the 3D/mask feature on a Windows work computer

Keep the existing WrapLab installation, local commits, `.venv`, projects, object presets
and recovery data. Use a separate short folder for this feature candidate. No reset,
clean, forced checkout, installer, executable bundle or security exception is needed.
Follow your employer's software policy; ask IT if Python, Git, PyPI access or native
graphics are restricted. This feature has not been accepted on your particular workstation.

Before the first launch, close WrapLab. Copy your named private `.wraplab` and SVG
files to a backup folder outside the repository. In File Explorer, open
`%LOCALAPPDATA%` and copy the existing `WrapLab` folder to that backup too; preserve
the original folder in place. This includes object presets and last-session recovery.
A separate source checkout still uses the normal application-data location, so a
trial session can replace last-session recovery. Open project copies and use Save As
for trial files. Do not overwrite the originals or delete an existing environment.

## Get the exact source branch

Repository: https://github.com/Arch-Tom/wraplab

Branch: `codex/interactive-3d-mask-planning`

If Git is available, open PowerShell and clone into a NEW folder:

```powershell
git clone --branch codex/interactive-3d-mask-planning --single-branch https://github.com/Arch-Tom/wraplab.git "$env:USERPROFILE\WrapLab-3D"
git -C "$env:USERPROFILE\WrapLab-3D" rev-parse HEAD
```

Compare the full SHA with the published handoff. Do not clone over an existing folder.
Without Git, open that branch in GitHub, choose Code > Download ZIP, extract it, and
move/rename the inner source folder to `%USERPROFILE%\WrapLab-3D`. `README.md`,
`requirements-windows-runtime.lock`, `scripts` and `src` must be directly inside it.
Keep input and output paths short too; extended-path compatibility is not established.

## Install the pinned runtime

Use Windows x64 with the approved Python 3.12.10 x64 installation and Python launcher.
Ask IT to supply that exact version if it is unavailable; this source launcher deliberately
checks the version. Installation needs PyPI access or an IT-supplied verified wheel cache.
Application operation afterward is offline. Qt 6.8.3 is installed by the lock file.

Run one command at a time, stopping on any error:

```powershell
Set-Location "$env:USERPROFILE\WrapLab-3D"
py -3.12 --version
```

Continue only if this reports Python 3.12.10. In this fresh folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -I -c "import sys; assert sys.version_info[:3] == (3, 12, 10), sys.version"
.\.venv\Scripts\python.exe -I -m pip install --require-hashes --only-binary=:all: -r requirements-windows-runtime.lock
.\.venv\Scripts\python.exe scripts/patch_build_dependencies.py
.\.venv\Scripts\python.exe -I -m pip check
.\.venv\Scripts\pythonw.exe -I .\scripts\run_source.py
```

These are the existing documented runtime commands. They install no PyInstaller,
WebEngine or additional graphics package. The source helper isolates imports, DLL search
paths and Qt plugins for this process. Do not change system-wide Python, Qt or antivirus
settings. If installation, a hash check or endpoint protection blocks a step, preserve
the error and contact IT rather than weakening a guard.

## First checks

1. Start with `tests\fixtures\lettering.svg`. Select Cylinder, diameter 70 mm,
   height 120 mm, page framing, width 40 mm with proportions locked, then Center artwork.
2. Confirm Interactive 3D, orbit/pan/zoom, Front/Left/Right/Rear/Seam and the 2D fallback.
   Compare the on-object target with the flat pattern. Use a new output filename.
3. Open a COPY of an existing project and verify its units, frame, measurements,
   placement and ordinary export before trying experimental masks. Existing page-framed
   projects retain page framing; they are not silently changed to visible-artwork framing.
4. Load the current private CantorLand source/project from your own approved storage.
   Artwork and projects are deliberately absent from GitHub. The authenticated source's
   three-mask recipe preserves both Hebrew rows together. For an older project, the
   grouping-only button preserves its measurements; the historical-trial button replaces
   them explicitly and is not approval of current bell dimensions.
5. Inspect mask/reference overlays and the separate mask export. Keep reference-only
   SVG/TXT files away from the cutter. Independent output is experimental; inspect
   CorelDRAW at 100%, verify scale/counters/orientation, and qualify the actual material
   and transfer carrier before any production use.

If graphics cannot initialize, the application should use its retained 2D preview.
The new 3D path still needs workstation acceptance; ordinary source operation is not
proof of the quarantined standalone executable's safety.

An optional desktop shortcut can target this folder's `.venv\Scripts\pythonw.exe`
with arguments `-I "FULL_PATH_TO_WrapLab-3D\scripts\run_source.py"` and Start in set
to the source folder. Use actual absolute paths from your machine. Local errors are
logged to ignored `artifacts\source-run\gui.log`; do not commit those logs or private jobs.

The unresolved Norton verdict, older Qt diagnostic, extended-path issue, actual Corel
interoperability and physical vinyl acceptance remain separate, unresolved matters.
