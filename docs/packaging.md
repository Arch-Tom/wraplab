# Native portable builds

Install pinned Python 3.12 requirements and run `python scripts/build_portable.py` on the target OS.
The script runs PyInstaller one-folder packaging, generates acceptance specimens, gathers available
dependency license notices, launches the **actual executable** through its desktop self-test, and
creates `artifacts/WrapLab-0.1.0-<OS>-<architecture>-portable.zip`.

The self-test instantiates the Qt workspace, imports a compound SVG, computes previews, exports
four modes for each of three objects, checks physical cylinder inverse-projection width and the
counter, saves/loads projects and presets, and captures the workspace. `Build-validation/report.json`
records platform, frozen/source status, dimensions, node counts and output hashes. Failure preserves
the process exit status and prevents a validated artifact claim. `--skip-smoke` explicitly omits this
evidence and should not be used for a release acceptance claim.

Windows executable/ZIP builds require **native Windows**. The Linux development host cannot produce
or exercise a Windows PyInstaller executable. `.github/workflows/build.yml` defines Python 3.12
Windows and Ubuntu builds, test runs and artifact uploads. It is configuration only until run.
No workflow was pushed/dispatched by the local implementation task.

Shop test: unzip the complete portable folder, launch `WrapLab.exe`, disconnect networking and
repeat import/placement/export. Do not move only the exe without its `_internal` dependencies.
Validate in CorelDRAW 2019 and on finish-compatible approved paper/vinyl on a surrogate or approved test area. No installer/signing is provided
yet; this milestone uses a portable app. See `docs/validation.md` for evidence actually obtained.

Dependencies include Qt/PySide licensing terms and scientific-library notices. The build copies
available distribution notices into `Third-party-notices`; retain these when redistributing.

The first frozen build failed because the original NumPy/SciPy versions and PyInstaller hook set
were incompatible (numpy._core._exceptions missing at startup). The tested set is NumPy 2.2.6,
SciPy 1.15.3, PyInstaller 6.12.0 and hooks-contrib 2025.2. A clean rebuild and actual frozen Qt
self-test succeeded after replacing those pins; no failed binary is the accepted artifact.
