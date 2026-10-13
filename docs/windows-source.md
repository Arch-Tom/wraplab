# Run WrapLab from Python on Windows

Use Windows x64 and Python 3.12.10. Clone the dedicated integration branch from
`https://github.com/Arch-Tom/wraplab.git`, enter the checkout, and follow the Windows
commands in [README](../README.md#run-from-source). Installation requires access to PyPI;
operation after installation is offline.

`requirements-windows-runtime.lock` contains SHA-256 hashes for the exact Windows wheels
verified against official PyPI metadata and used in the successful local source environment:
defusedxml 0.7.1, NumPy 2.2.6, SciPy 1.15.3, PySide6-Essentials 6.8.3, shiboken6 6.8.3,
Shapely 2.0.7, svgpathtools 1.7.1 and svgwrite 1.4.3, plus installer pip 26.2.1.
`--require-hashes --only-binary=:all:` rejects other wheel contents and source distributions.
The complete development/build dependency set remains in `requirements.lock`.

The existing dependency patch script verifies the original NumPy Windows testing-helper
hash before applying its documented one-line platform-detection change. It does not modify
numerical code or native binaries. If the guard fails, preserve the error and inspect the
environment instead of weakening the check.

To reopen the application from the checkout:

```powershell
.\.venv\Scripts\pythonw.exe -I scripts/run_source.py
```

The real application entry point remains `wraplab.__main__.main`, which calls
`wraplab.ui.app.launch`. The source helper requires this checkout's `.venv` and isolated
Python 3.12.10, clears inherited Qt/QML settings, restricts process-local PATH and chooses
this environment's Windows Qt plugin. It changes no system environment settings. Runtime
failures are logged locally in ignored `artifacts/source-run/gui.log`.

## Completed local native source validation

The unchanged application source at `7c21723ab3b2a46631ccc56ede711cde93cebc70` ran on a local
Windows machine with an isolated Python 3.12.10 environment and Qt 6.8.3 Windows platform:

- Native regression suite: 152 passed, zero failures/skips, including 18 independent geometry
  fixtures. Ruff and dependency consistency checks passed.
- Imported the tracked outlined O/A/B/R lettering fixture with its 60 x 25 mm source page.
- Changed cylinder diameter to 70 mm and axial height to 120 mm; selected 180-degree coverage.
- Changed artwork width to 40 mm with aspect ratio locked; artwork height became 16.6667 mm.
  Centering placed the artwork top at 51.6667 mm and horizontal position at zero.
- Observed Ideal front view and Flat vinyl pattern previews with letter counters intact;
  the final preview reported 249 nodes at 0.08 mm preview tolerance.
- Exported Compensated Artwork Only at 0.01 mm production tolerance: 662 production nodes.
  XML verification found four paths, explicit millimeter dimensions and a matching viewBox,
  without text or image elements. Tight artwork bounds exclude the source page margins.
- The running process loaded Qt from the isolated environment; no Codex/libheif DLL paths
  were present. Antivirus protection remained enabled. No application correction was needed.

The reusable source helper in this branch adapts that tested procedure to any checkout path.
Local environments, exported specimens, desktop shortcuts, logs, process inventories and
security evidence are deliberately not part of the source branch.

The prepared integration passed 157 native Windows regression tests, including five new
launcher-isolation checks, and a fresh offline installation of the hash-pinned runtime.
Its launcher loaded this checkout's source with the Qt Windows plugin. An additional
source self-test completed twelve exports and project/preset checks, but its deliberately
long path fixture failed with Windows error 206 because this host's `LongPathsEnabled`
setting is zero. The full extended smoke/restart was not completed. Keep checkout, input
and export paths comfortably below Windows' traditional 260-character limit on such hosts;
no Windows setting was changed for this validation.

CorelDRAW 2019 import, the managed work computer and physical vinyl application remain
unverified. This source pass does not clear the unresolved Norton executable detection.
Do not restore the quarantined executable, disable protection, add exclusions or distribute
a Windows executable while that status remains unresolved.
