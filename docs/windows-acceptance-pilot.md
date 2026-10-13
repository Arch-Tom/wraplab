# Supervised Windows acceptance handoff

This handoff contains a Git source bundle, fourteen unchanged true-size SVG specimens,
projects, expected dimensions/node counts, an operator results CSV and checksums.
**It contains no Windows executable or copied security-investigation evidence.**
The application at `7c21723` has passed a local native Windows Python source GUI test;
see [Windows source setup and validation](windows-source.md). Packaged executable validation
remains incomplete. Windows packaging and distribution are paused while the Norton detection
is unresolved; the packaged pilot instructions below are retained for a later approved stage.

Cylinder and straight-frustum compensation remain exact for those ideal measured shapes.
Measured bells remain **Best-Fit / Experimental**. Shipped measurements are illustrative;
preview and software tests cannot approve material stretch, adhesion or application.

## Prepare and verify the handoff

From a clean, committed existing checkout with the pinned dependencies installed:

```text
python scripts/prepare_windows_acceptance.py --output-root artifacts/windows-acceptance
python scripts/prepare_windows_acceptance.py --verify artifacts/windows-acceptance/WrapLab-Windows-Acceptance
```

Use a new output directory for another run. The generator refuses outstanding source
changes and preserves completed handoffs. It verifies the source bundle, records the
source SHA/tree/branch and dependency versions, sets ZIP entry timestamps to the commit
epoch, and hashes every handoff file. The outer SHA256SUMS.txt hashes the delivered ZIP;
the inner file inventories its extracted contents. Source/toolchain/settings/checksums
make the build auditable; whole Windows binary bit-reproducibility is not promised.

## Build on an approved native Windows development host

The application work-PC pilot needs only the extracted onedir package. Python, Git and
build tools are needed on the development host, not the managed operator workstation.
Use **Windows x64 / Python 3.12.10 / PyInstaller 6.12.0 / hooks 2025.2 / Qt 6.8.3**.

Clone the included bundle using the branch recorded in Handoff-manifest.json:

```text
git clone --branch <source_branch-from-Handoff-manifest.json> Source.bundle WrapLab-source
cd WrapLab-source
git rev-parse HEAD
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -c "import sys; assert sys.version_info[:3] == (3, 12, 10), sys.version"
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe scripts/patch_build_dependencies.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q --junitxml=artifacts/windows-tests.xml
.\.venv\Scripts\python.exe -m ruff check src tests scripts packaging
.\.venv\Scripts\python.exe scripts/build_portable.py --diagnostic --output-root artifacts/releases/Windows-pilot
```

Confirm HEAD equals the handoff SHA before testing. The dependency patch fails on an
unknown version/source; preserve any failure rather than relaxing the guard. The builder
uses the standard GUI bootloader, onedir/no UPX, truthful icon/version identity and an
asInvoker manifest. It excludes the reviewed unused networking/test binaries and records
their settings and the EXE hash in Build-manifest.json. No updater, helper launcher or
runtime-downloaded dependencies are involved. No security/PowerShell policy change is needed.

The builder tests the **exact extracted ZIP**, native Qt `windows` plugin, import/previews,
twelve exports, project/preset reload and restart, Unicode/long paths, denied-write
preservation, and fourteen source-versus-packaged SVG specimens. Its temporary read-only
ACL test applies only to a disposable QA extraction and restores it. Retain logs/failures,
validation JSON, native inventory and SHA256SUMS.txt. Never repack a tested archive to
replace it. Do not substitute Linux/offscreen results for this Windows build gate.

## Standard-user managed-PC smoke test

1. With the supervisor/IT-approved procedure, verify the inner app ZIP SHA-256 against
   SHA256SUMS.txt (for example, `Get-FileHash <zip> -Algorithm SHA256`), extract the entire
   folder into an approved user-writable location, and compare WrapLab.exe with the build
   manifest's hash. Keep `_internal`. Use the exact artifact name; do not rename it to avoid detection.
2. Launch normally as the logged-in **standard user**, without administrator elevation.
   Record Windows version, user/integrity, EXE hash, build/commit and visible GUI/no-console
   behavior. Record expected one app process, no app children or internet connections;
   ordinary Qt/math threads are not child processes.
3. Import a local path-converted SVG; exercise width, position and object dimensions.
   Test exact cylinder and both taper directions. Inspect original, ideal front and flat
   pattern. Confirm measured-profile previews remain explicitly experimental.
4. Export **Compensated Artwork Only** into a writable user folder. Preserve source bytes,
   save/reopen the project and exported SVG, and shut down normally. Check counters,
   orientation, top/bottom, output dimensions and absence of guides in artwork-only output.
5. Try an unsupported live-text SVG or invalid visible-edge placement. Confirm a useful
   error and that an existing destination/source is not overwritten. Presets/recovery
   belong in `%LOCALAPPDATA%\WrapLab\WrapLab`; exports/projects in chosen folders.
   No native executable/script extraction or install-directory writes are expected.
6. If blocked, stop and preserve the event/sample. Capture SentinelOne rule/engine/action,
   timestamp/timezone, agent/policy, exact hash/path/command line, initiating user,
   parent/child tree, storyline ID and first failing stage (copy/extract, launch, GUI,
   import, processing, export, shutdown). Include module/temp/network/WMI details if cited.
   Distinguish SmartScreen/MOTW from SentinelOne. Do not disable protections or add exclusions.

The previous Windows CI used an inherited high-integrity token; it is not a standard-user
workstation pass. The current candidate remains unsigned. Signing with an approved
organizational identity may help provenance later, but does not replace this test.

## CorelDRAW 2019 true-size gate

Use Corel-Acceptance/READ-ME-Corel-acceptance.md and Operator-results.csv. Record actual
Windows/Corel build, import settings, measured dimensions and screenshots/failing SVGs.
Import at **100%** with document units mm; compare each page/artwork width/height with
manifest.json, without scaling to fit. In particular:

* Verify the 100 mm square and geometrically identical 25.4 mm / one-inch squares.
* Confirm outlined lettering and O/A/B/R/8 counters, Hebrew path order, both tapers,
  closed edges, smooth curves, practical node counts, selection and editability.
* Verify full-wrap seam/top/bottom geometry; keep original intended orientation.
* Verify Artwork Only excludes guides. Guide groups are ordinary paths and **may cut**;
  separate/remove them from cutter selection unless deliberately part of the trial.

Choose and record dimensional/visual acceptance tolerances before evaluating the files.
Do not mark this gate passed from Qt/browser rendering or automated XML tests.

## Small physical-material pilot

After software/workstation/Corel gates, follow Bell-measurement.md. First record actual
stations/units/uncertainty, front meridian, labelled top and viewing distance/orientation;
identify film, transfer tape, connected mask versus separate letters, finish and support
region. Check out-of-roundness and withheld stations. No safe strain percentage is inferred.
Use approved finish-compatible material on a surrogate or approved inconspicuous test area;
removable does not establish finish safety. Compare compensated and uncompensated lettering
with baseline/circle/grid references from the same straight-on viewpoint, inspecting
distortion, wrinkles and lift. Record trial results before any full application. No heat,
stretch or irreversible engraving recipe is introduced here.
