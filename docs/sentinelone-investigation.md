# WrapLab Windows compatibility investigation

## Scope and preserved baseline

This pass examines executable transparency, not endpoint bypass. SentinelOne is not
installed in our Linux workspace or GitHub Windows runner. Until the managed-PC event
and blocked-file SHA-256 are obtained, **E — cause unresolved** is the supported result.
The previously distributed RC4 may not be the binary blocked on the workstation.

Before edits: clean `release/windows-rc4`, HEAD
`9a214b50cdf6d9d27cf8a3cf92bd92bb420181ec`. Source Git bundle, state, lockfile/build
hashes and original package are retained locally under `artifacts/edr-forensics/baseline`.
The dedicated branch is `security/sentinelone-diagnostic`; no main merge, new tag,
public release, production deployment or endpoint configuration change is part of this pass.

RC4 ZIP: `WrapLab-0.1.0-Windows-x64-portable.zip`, 86,183,973 bytes,
SHA-256 `5d68abbc7fd8d62ef4c9c45927476c9df47e48af0bfc292ee212cacaa83d7e5b`.
RC4 EXE: SHA-256 `f113f8b9c7f95c0281886bd1306e99cbcd4a9b01317e4acb8c51d78105e7a754`.

## Architecture and launch-to-shutdown behavior

Python 3.12, PySide6-Essentials/Qt 6.8.3, NumPy 2.2.6, SciPy 1.15.3,
Shapely 2.0.7, svgpathtools 1.7.1, defusedxml 0.7.1. Native RC4 used
Python 3.12.10 and PyInstaller 6.12.0/hooks 2025.2 on Windows x64.
The local comparison workspace is Linux/Python 3.12.14, not a Windows emulator.

`scripts/build_portable.py` generates an ignored `.spec`, invokes standard PyInstaller
`--onedir --windowed`, ZIPs the folder and tests that exact extracted archive.
There is no installer, onefile release, custom bootloader, splash, shell launcher or updater.
`.github/workflows/build.yml` builds/tests native Windows and Linux, compares SVGs and
publishes only authorized release tags; `publish_release.py` and `write_evidence.py`
are build infrastructure. `setup.sh` and `setup-windows.ps1` install development tools.
No batch/PowerShell file is executed by or bundled as an application launcher.
The new build-only diagnostic workflow creates an authenticated Actions artifact, not a release.

Normal Windows launch: stock onedir bootloader establishes process-local `_internal`
DLL search paths, loads Python/bytecode and calls `wraplab.__main__.main` in the same
process. PySide loads Qt and native platform plugins. `ui.app.launch` creates QApplication,
the main window and event loop. The normal app has no child executable calls.
A 180 ms Qt timer debounces preview; a QThreadPool of at most one geometry task handles
preview in-process (native libraries can have additional computational threads).
Import reads SVG or JSON project data; defusedxml rejects entities and the SVG normalizer
rejects active content. Only regenerated normalized SVG reaches Qt rendering.
Placement is separate from original geometry. Production export recomputes validated
contours in-process; it never delegates to Inkscape, Python, cmd or a vector utility.
Atomic writes use short-lived sibling `.wraplab-*` **data files**, fsync and replace.
Shutdown stops preview, waits for its worker, saves recovery data and exits normally.

Normal data: Qt AppLocalDataLocation, ordinarily
`%LOCALAPPDATA%\WrapLab\WrapLab\objects.json` and `Last-session.wraplab`, plus
operator-chosen `.wraplab` project and SVG export paths. No install/system writes,
startup registration or scheduled tasks. The `WRAPLAB_QA_LOG` opt-in environment variable
writes a diagnostic text log only when an external tester supplies it.

## Meaningful security-sensitive findings

| Finding | Classification and purpose | EDR relevance / disposition |
|---|---|---|
| Standard CPython/PyInstaller bytecode archives, native DLL/PYD loading | Required; local interpreted app | Packed/interpreted new binaries can affect heuristics/reputation; ordinary onedir layout, no runtime executable generation |
| `_internal` DLL search, shiboken DLL directory and Qt plugin paths | Required, process-local dependency resolution | Loads outside System32 are conventional for portable apps; no system environment/security changes |
| QThreadPool and native math threads | Required responsiveness/geometry | Threads, not helper processes or injection; retained |
| Atomic preset/recovery/export data writes | Required durability | Temporary data creation is legitimate; no executable/script content; retained |
| Qt file dialogs/drag/drop and system integration | Required GUI | Windows OLE/shell/registry reads may occur inside Qt; not COM-port/machine control |
| Unused Qt TUIO plugin and its QtNetwork/TLS dependencies | Unnecessary bundle content | TUIO source can bind UDP 3333 when activated; mere presence is not activation or a proven trigger. Omitted via narrow build hook/module exclusion |
| NumPy `_multiarray_tests` native extension | Unnecessary test helper | Never used by WrapLab; excluded, other numerical modules retained |
| `platform.platform/system/machine` in Windows QA reports | Optional QA; WMI OS/CPU queries and possible shell fallback | Changed to `sys.getwindowsversion/sysconfig`, without altering geometry. No normal GUI use before change |
| CPython socket/ssl/ctypes/WMI/multiprocessing components and crypto DLLs | Suspicious-looking but legitimate library dependencies | Presence is not application use. Retained to avoid fragile trimming or provoking platform shell fallback |
| Missing PE version identity/default icon | Accidental packaging omission | Makes provenance less clear; added honest WrapLab identity and project icon |
| Unsigned primary executable | Legitimate internal distribution | Reputation/policy plausible; no evidence to rank it above an actual detection rule. Not signed in this pass |
| Build/QA subprocesses, Git/PowerShell/ACL tests | Required external tooling, never app runtime | Classified separately. Read-only install ACL is applied/restored only to disposable QA extraction; no endpoint/security changes |

Entire application and build tree searched for subprocess/shell, eval/exec, plugins,
registry/persistence, privilege, process control, hardware/COM/serial, sockets/servers,
network/update/telemetry, hooks/watchers, embedded executables and temporary scripts.
No application call sites implement those behaviors. `app.exec()` is a Qt event loop,
not Python `exec`; regex `compile` is not code execution. QA arguments select compiled-in
in-process tests, not arbitrary scripts. No production geometry rewrite was made.

## Actual baseline bundle and PE inspection

Static inventory of RC4: one EXE plus 224 DLL/PYD files, 213,508,880 native bytes;
no identical binary duplicates, UPX section markers or extra helper executable.
Main EXE: AMD64/GUI subsystem, no certificate table, no VERSIONINFO, default icon.
Existing default manifest already requests **asInvoker**, UI access false and long paths.
Old generated specs permit UPX (`upx=True` default) but inspected binaries show no UPX;
new builds explicitly use `--noupx`. Do not claim removal of observed UPX compression.

Provenance includes pinned CPython/MSVC, Qt/PySide/shiboken, NumPy BLAS, SciPy and
Shapely GEOS. SciPy's broad dependency graph and software OpenGL/image/platform plugins
are retained for reliability. Qt's `libssl-3-x64`/`libcrypto-3-x64` and CPython's
`libssl-3`/`libcrypto-3` were not identical duplicates. Full native rows record filenames,
SHA-256, PE imports, version/manifest/signature-table information and package provenance.
Read-only `Get-AuthenticodeSignature` is run externally on Windows for every native file.

References independently inspected: [PyInstaller 6.12 bootloader](https://github.com/pyinstaller/pyinstaller/blob/v6.12.0/bootloader/src/pyi_main.c)
and [Qt 6.8.3 TUIO handler](https://github.com/qt/qtbase/blob/v6.8.3/src/plugins/generic/tuiotouch/qtuiohandler.cpp).
Windows onedir uses one process; onefile uses extraction/parent-child characteristics.
A onefile comparison is not needed to explain this already-onedir release and would
introduce an unnecessary second architecture. No onefile candidate is shipped here.

## Changes and reproducibility

Diagnostic: Windows x64, stock PyInstaller 6.12.0, onedir/windowed/no UPX/no strip/no splash,
no elevation. Explicit version resource (0.1.0 / file 0.1.0.0), application icon, asInvoker
manifest; company left empty rather than inventing a publisher. Narrow unused-plugin/test
exclusions; acceptance data reduced to the seven SVG fixtures actually used. Source-date
PE timestamp set to commit epoch. Original artwork/geometry/export code unchanged.
Full bundle bit reproducibility is not claimed: native wheels, generated archive timestamps
and paths can differ. Manifest records source/tools/settings, EXE and final ZIP hashes.
No certificate purchased/fabricated, security exclusions, disguises, network settings,
machine privileges, telemetry or auto-updater introduced.

## Native runtime method and its limits

`forensic_windows.py` is an **external**, unbundled observer. It compares source
`pythonw -m wraplab`, hash-pinned RC4 and exact extracted diagnostic ZIP on a native
Windows runner: ordinary visible GUI launch/WM_CLOSE, in-process SVG import/manipulation/
three object types/12 exports/error paths, reopen/restart and 14 acceptance specimens.
Toolhelp module/process snapshots, token inspection and IPv4/IPv6 TCP/UDP owner tables
are polled at 20 ms (modules/windows at 200 ms). Before/after data/installation/TEMP
hashes identify lasting writes; kernel ETW additionally records process/thread/image,
file, registry/network and WMI events where runner permissions permit.

Polling alone cannot exclude very short processes/connections/deleted temporary files;
ETW availability, decoded counts and limitations are recorded honestly. Full ETL/XML is
retained briefly as a diagnostic artifact; small summary/inventory reports are preserved
on `release-evidence`. No debugger injection, input hooks, WMI observer, process concealment
or endpoint modification. A CI job can run with an inherited high-integrity token:
asInvoker prevents an elevation request but is not proof of a standard-user run.
SentinelOne, CorelDRAW 2019 and physical vinyl acceptance remain separate/unverified.

The complete suite must pass, then baseline/source/diagnostic SVG dimensions, contours,
holes/winding, nodes and hashes are compared. Any unexpected geometry change fails;
minor generator metadata differences are recorded, never silently treated as artwork changes.

## Managed workstation protocol

1. Download the authenticated Actions artifact while signed into GitHub. Extract the inner
   `WrapLab-0.1.0-Windows-x64-onedir-diagnostic.zip` normally, preserving `_internal`.
   Verify ZIP and `WrapLab.exe` SHA-256 against the supplied manifest; do not run as admin.
2. Record whether blocked on download/copy, extraction/file creation, first launch, GUI,
   import, processing, export, child start or shutdown. Keep the original blocked sample
   and event intact; do not disable protection, request exclusions or retry disguised names.
3. If allowed, import a known local SVG, change dimensions/placement, export into a writable
   user folder, reopen and close. Compare expected specimens and preserve any failing output.
4. Capture SentinelOne event/export: timestamp + timezone, hostname/agent version and policy,
   threat/detection name, engine/rule, static/reputation versus behavioral verdict, action
   (quarantine/block/kill), SHA-256 and full file path, command line, initiating user/token,
   parent and descendant process tree with hashes, module/file/registry/network behaviors,
   first triggering event and any security-console story/timeline/correlation ID.
   Also record download origin, Mark-of-the-Web/SmartScreen message if present (do not remove
   it as a workaround), and whether the event fingerprint matches RC4 or this candidate.

A: packaging would need demonstrated runtime differences tied to detection; current
onefile explanation unsupported. B: needs a concrete app behavior/event. C: needs a module
or dependency identified by event evidence. D: unsigned/reputation policy plausible but
unproven. **E remains the decision until managed-endpoint evidence distinguishes these.**
Proper organization-approved Authenticode signing is worthwhile for later production
provenance/reputation; it is not an endpoint bypass or a guarantee and should follow event
review, not substitute for it. No proprietary files were sent to public malware sandboxes.
