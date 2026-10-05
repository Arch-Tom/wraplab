# WrapLab 0.1.0 RC4 acceptance handoff

Recommendation: **COREL ACCEPTANCE TESTING**. Software/native packaging acceptance passed;
CorelDRAW 2019 and physical bell/vinyl acceptance remain pending.

Baseline: `fa8750032109507e144537ed498df55faa9ae828` (142 tests).
Final source: `9a214b50cdf6d9d27cf8a3cf92bd92bb420181ec`, tag `v0.1.0-rc4`,
branch `release/windows-rc4`; remote `main` was fast-forwarded to this same commit.
The source working tree is clean. Earlier tags, failure evidence and baseline artifact hashes
remain preserved; no history was rewritten.

Release: https://github.com/Arch-Tom/wraplab/releases/tag/v0.1.0-rc4
Native run: https://github.com/Arch-Tom/wraplab/actions/runs/37263004103

## Verified

- Native Windows Server 2025, build 26100, AMD64; Python 3.12.10, Qt 6.8.3 with the
  native `windows` plugin, PyInstaller 6.12.0. Linux CI also passed.
- 149 tests on each OS, zero skips, all 18 independent Packet A fixtures; Ruff,
  dependency consistency and security audit passed. The seven additional tests cover
  recovery/close failures (2), release comparison rejection (3), and atomic-save failures (2).
- The actual extracted Windows archive launched, rendered its UI and three previews,
  exercised all object modes, saved/loaded presets and projects, exported 12 cases, and
  restarted in a separate process. Real read-only ACLs denied creation, overwrite and
  deletion; failed export preserved the existing file. Unicode/spaces and a 316-character
  path passed. Writable user-data and temporary locations were outside the install tree.
- The packaged Windows executable generated all 14 Corel specimens, with dimensions,
  manifest, operator checklist and PASS/FAIL CSV. The 12 GUI exports and 14 Corel specimens
  match Linux geometry, dimensions, fills, contours and hole ownership: maximum edge
  difference 0.0 mm. Some measured-profile hashes differ only in floating-point diagnostic
  metadata (approximately 1e-14); the SVG geometry is identical. Separate comparison JSONs
  preserve these findings. No material output difference was found.
- All published assets were downloaded and hash-checked by CI before publication.
  The Windows ZIP, Corel ZIP and validation JSON were independently downloaded from the
  public release and SHA-256 verified again in this cloud workspace.
- An exact RC4 remote clone, new virtual environment and documented setup passed 149 tests,
  lint, dependency checks, the source Qt workflow and a rebuilt/extracted Linux package.
  Evidence is on `release-evidence/restoration/9a214b50cdf6d9d27cf8a3cf92bd92bb420181ec`.
- Exact cylinder/frustum geometry and SVG compensation algorithms are unchanged. The
  Windows save fix avoids Python temporary-file retries on ACL denial while retaining
  exclusive creation, flush/fsync and atomic replacement.

## Operator use and remaining gates

Download and extract the complete Windows portable ZIP; launch `WrapLab.exe`, keeping
`_internal` beside it. No Python installation is required. The executable is unsigned;
verify its checksum/origin and follow shop policy for SmartScreen. No installer was produced.

Use the Windows Corel Acceptance ZIP and record actual import, dimensions, orientation,
counter/fill preservation and editability in CorelDRAW 2019. Guide paths may cut.

Measured Profile remains **Best-Fit / Experimental**. Obtain the actual bell measurements,
vinyl, tape/application method and intended viewing setup. A finish-compatible approved
material trial must compare compensated/uncompensated appearance and wrinkles/lift before
full application. The preview is an ideal geometric correspondence, not a film simulation.

The cloud setup/startup draft is saved at RC4 and its startup check passed. Activating that
snapshot requires saving/publishing through environment settings, which the user currently
cannot change. A new cloud task was not tested; the exact Git-based fresh restoration above
is verified independently.
