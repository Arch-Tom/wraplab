# WrapLab 0.1.0 release candidate

Starting baseline: fa8750032109507e144537ed498df55faa9ae828, clean tree, 142 tests.
The baseline source bundle, dependency inventory and artifact hashes are preserved in
artifacts/preservation-fa87500. Existing acceptance ZIPs and Linux portable artifacts are unchanged.
The baseline was published to the authorized GitHub repository without rewriting history.

## Scope and changes

Geometry and SVG compensation algorithms are unchanged. Release changes bundle acceptance inputs,
run the packaged generator, validate the exact extracted archive, test actual Windows Qt, preserve
failure reports, compare Windows/Linux exports, and provide downloadable release evidence.
Two UI regression tests cover recovery-file write failures: closing now offers Save Elsewhere,
Discard or Cancel instead of trapping the application. Three release-comparison tests reject changed
winding, physical units and geometry. The expected suite is 147 tests, with no skipped tests and all
18 independent Packet A fixtures retained.

The test-only pytest pin is 9.0.3 (and its Pygments dependency 2.21.0), resolving the audit finding
PYSEC-2026-1845 / CVE-2025-71176 affecting pytest 8.3.5. Runtime geometry dependencies are unchanged.
pip check and an isolated pip-audit 2.10.1 scan run in both native jobs. Audit failures block release.

RC1 native evidence is preserved under source commit 3faf0a6 on release-evidence. Windows passed
147 tests and its dependency audit, but the QA installation ACL denied SYNCHRONIZE through generic
write permission, preventing executable launch. RC2 uses explicit write/delete rights while retaining
read/execute access. Ubuntu CI also installs Qt's libegl1 and libopengl0 runtime libraries before
testing. These are validation-environment corrections; application geometry is unchanged.

## Native release procedure

1. Install Python 3.12 and use scripts/setup-windows.ps1 (Windows) or scripts/setup.sh (Linux).
2. Run pytest and Ruff as documented in README.md. Do not remove or skip failing tests.
3. Run `python scripts/build_portable.py --output-root artifacts/releases/Windows` on Windows.
   Use a new output root for another completed build; existing release artifacts are preserved.
4. The script packages Qt, native geometry dependencies and specimen resources, extracts the exact
   ZIP under a path with spaces/Hebrew, and launches it from outside the repository.
5. Native Windows validation requires Qt platform `windows`. Linux uses offscreen. A Windows
   offscreen pass cannot set Windows packaged validation to true.
6. The extracted installation receives a real Windows deny-write ACL (POSIX modes on Linux).
   New writes and overwriting an existing output must fail without data loss. The package runs with
   writable Qt user-data/output/temp locations, tests paths longer than 280 characters, restarts,
   reloads projects and UI presets, checks all three previews, and creates twelve exports.
7. The packaged executable regenerates the same fourteen Corel cases. Byte hashes, dimensions,
   viewBox, contours, counters, winding/ownership and edge geometry are checked. Windows newline
   conversion cannot change SVG file hashes. Separate cross-platform comparison runs in CI.
8. A release-tag push matching v0.1.0-rc* runs native Windows and Linux checks. Only successful
   jobs plus cross-platform comparison allow a draft GitHub prerelease to be created. Uploaded
   assets are downloaded and SHA-256 checked before the draft is published. Tags/assets are not
   overwritten. An installer is deferred; the self-contained portable ZIP is the release target.

## Operator steps

1. Download the **Windows x64 portable ZIP**, its validation JSON and SHA256SUMS.txt from the release.
2. Verify the hash (`Get-FileHash <zip> -Algorithm SHA256`) and extract the entire ZIP.
3. Launch WrapLab.exe; keep its _internal folder beside it. No Python installation is required.
4. Choose the object mode, enter dimensions or load a preset, then import path-converted SVG artwork.
5. Set size and position. Inspect Original, Ideal Front View and Flat Vinyl Pattern.
6. Export Compensated Artwork Only, then open it in CorelDRAW 2019 and verify physical dimensions.
7. Use the separate Windows Corel Acceptance ZIP and fill in Operator-results.csv for every specimen.

The build is unsigned. Windows may display a SmartScreen warning; verify origin/checksum and follow
shop approval policy. Do not disable antivirus or Windows protections globally.

## Evidence and acceptance states

Each native validation JSON records source commit/tree/dirty status, OS, Python/Qt versions, native
Qt plugin, executable hash, permissions/path tests, launch/restart and source-versus-packaged results.
Release publication rejects a dirty source tree. No archive is repacked after it was tested.
The CI summary records actual test count, all 18 fixtures, lint, dependency check and security audit.

GitHub API access is blocked from this cloud machine. Authorized Git access works. The workflow
therefore also appends small reports to `release-evidence`, under
`evidence/<full source SHA>/<run id>-<attempt>/`. It records failures as well as successes, exact
source/run identities, returned GitHub release/asset URLs, and artifact checksums. This is ordinary
remote CI publication; no local Windows execution is inferred from Linux checks.

Retrieve without changing the current checkout:

```
git fetch origin release-evidence
git ls-tree -r --name-only origin/release-evidence
# git show origin/release-evidence:evidence/<sha>/<run>/summary.json
```

CorelDRAW 2019 acceptance remains **PENDING** until the shop operator records actual import,
physical size, geometry and editability. Measured Profile remains **Best-Fit / Experimental**.
Real bell dimensions, vinyl, tape, application method and intended view require the approved
physical trial in bell-measurement.md. Software/native packaging success does not approve material use.
