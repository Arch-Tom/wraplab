# Source integration status

This document records the preserved source-integration baseline at `30c539a`. The newer,
local-only `codex/wraplab-simple-workflow` implementation is described in
[the simple-workflow guide and validation](simple-workflow.md). Its geometry/persistence
engine remains unchanged; its operator UI and scoped SVG diagnostics have changed.

The dedicated branch is `codex/source-integration`, prepared for
`https://github.com/Arch-Tom/wraplab.git`. Main and existing releases are unchanged.
This branch carries source, tests and documentation; Windows executable packaging and
distribution remain paused while the Norton detection is unresolved.

## Preserved source history

| Reference | Integration decision |
| --- | --- |
| `9a214b50cdf6d9d27cf8a3cf92bd92bb420181ec` | Existing GitHub main / RC4; retained as an ancestor |
| `5772293ff7eccd665ecb345efce7b287cc9c4828` | Existing GitHub hardening tip; parent of this integration work |
| `7c21723ab3b2a46631ccc56ede711cde93cebc70` | Preserved unchanged in the original local acceptance checkout and bundle; its source/test/documentation changes are carried forward without the security-evidence JSON |
| `0004bae1c669e792bad7ee07da76e6c071bf2216` | Previously reported local UX branch remains unavailable in the supplied handoff; no changes inferred or reconstructed |

The integration retains every application source file from `7c21723`, including exact
cylinder/frustum compensation, experimental measured-profile mapping, units, compound
contours, placement/export contracts, atomic saves and Windows runtime identity.
Existing regression tests and packaging/diagnostic source tooling are retained. Existing
historical diagnostic documentation is already in the published hardening history; no new
security-investigation report or local evidence is included. The unpushed `7c21723` commit
itself is not an ancestor of the proposed GitHub branch, so its excluded JSON is not newly
introduced through Git history.

The source/specimen handoff generator and its corruption/inventory tests are retained;
the generator no longer copies the excluded historical security JSON. CI's Python pin
remains 3.12.10. The new hash-pinned Windows runtime dependency list and checkout-relative
source launcher make the successful local Python procedure reproducible without PyInstaller.

## Validation and remaining gates

The application at `7c21723` passed 152 native Windows regression tests (zero skips/failures)
and the local source GUI import/dimensions/preview/export workflow. See
[Windows source setup and validation](windows-source.md). This prepared integration then
passed **157 native Windows tests**, including the original 152 tests, five source-launcher
isolation checks and all 18 independent geometry fixtures. Ruff, dependency consistency,
and an offline hash-required installation of all nine runtime/installer wheels passed.
The new launcher loaded this checkout's source using Qt's native Windows plugin.

The additional source Qt self-test completed twelve exports, project save/reload and preset
checks, then stopped at its over-280-character path fixture. Windows `LongPathsEnabled`
was observed as zero and an absolute-path retry produced error 206 (filename too long).
The full extended smoke/restart is therefore not a pass. No Windows settings were changed;
use short checkout and export paths on this machine. The original interactive source GUI
workflow remains passed.

Managed workstation operation, CorelDRAW 2019 and physical material trials remain separate,
unverified gates. The source GUI result does not approve a packaged executable or resolve
the Norton detection. Original source, handoffs, regression logs and security evidence remain
preserved locally; none of the local environments, executable artifacts or investigation
evidence is copied into this branch.
