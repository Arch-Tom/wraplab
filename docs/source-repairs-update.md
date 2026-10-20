# Updating the source repairs safely

The `fix/import-profile-preview` branch contains the Simple workflow baseline
`f3104d315749af95860132d5850e561b4c40b1c1` plus two source repairs:

- The reviewed importer/contour repair: bounded internal class CSS, rendering hints,
  inherited `currentColor`, malformed-style runtime limits, and ULP-scale closure
  handling. Its original four-file patch SHA256 is
  `027722b41e1ab98572cd49d4831f6fe20007274467a43590175dd544e4a07045`.
- A profile-preview sampling correction. For an 8.5-inch profile, multiplying a
  millimetre height by the final sample index before dividing could place the last
  point one floating-point ULP beyond the measured height. The profile outline,
  highlighted region, front-view silhouette and import-size samples now retain their
  exact endpoints. Genuine out-of-range
  measurements and artwork remain rejected; the geometry guard is unchanged.

Regression fixtures are synthetic. Customer artwork, object presets, recovery files,
local environments and private validation output are excluded from the branch.
Windows executable packaging remains paused. Use source only.

## Home installation

The existing Simple source launcher continues to use its own isolated Python runtime.
An already-open process keeps its imported modules. Save the current project before
closing it, then reopen the same Simple shortcut to load the updated source. Do not
discard an unsaved project to restart. Artwork dimensions and measured geometry are
not changed by this update.

## Work computer, when available

Do not update an offline or unattended work computer remotely. When it is available:

1. Save the open project. Preserve the existing source directory, including all
   untracked files and local changes, and separately back up WrapLab application data
   (object presets and `Last-session.wraplab`). Keep the existing runtime intact.
2. Record the old checkout's `git status --short --branch`, revision and remotes.
   Review its complete local diff and untracked files. A clean status does not prove
   that ignored customer assets or runtime files have been backed up.
3. Clone the repair branch into a **new, unoccupied directory**, leaving the old
   `Simple` installation untouched:

   ```powershell
   git clone --branch fix/import-profile-preview --single-branch https://github.com/Arch-Tom/wraplab.git WrapLab-source-repairs
   git -C WrapLab-source-repairs log -2 --oneline
   git -C WrapLab-source-repairs status --short --branch
   ```

4. Compare work-only source modifications with this branch before transplanting them.
   The four-file importer repair above is already included; do not apply it twice.
   Preserve any additional differences for review instead of overwriting, resetting,
   stashing blindly or pulling over them. Never copy customer files into a commit.
5. Follow [the Windows source setup](windows-source.md) for the new checkout's fresh
   isolated Python 3.12.10 environment. Do not reuse or overwrite the old `.venv`.
   Run the test suite and a synthetic import/export check, then test a copy of the
   saved project. Point a new source shortcut to the verified checkout only afterward.

The branch does not update `main`, releases, security settings or packaged executables.
Existing GitHub packaging workflows run on main/PR/tag or explicit diagnostic triggers,
not a push to this repair branch. Local test results do not establish physical bell or
vinyl fit; measured curved profiles remain Best-Fit / Experimental.
