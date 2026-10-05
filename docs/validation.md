# Milestone validation — 5 October 2026

## Software evidence

Host: Linux x86_64, Python 3.12.14, PySide6 Essentials 6.8.3. Existing checkout `/workspace/wraplab`.
Dependencies installed from the complete pinned requirements.lock. Repeated scripts/setup.sh
succeeded; pip check reports no broken requirements. Ruff passes. The final full suite passed **142 tests in 36.74 seconds** (see log for exact runtime).
Implementation commit: a2c7b96. The final full-suite record is
in artifacts/tests-final.log; additional gate checks are in artifacts/tests-final-additions.log.

Tests cover exact cylinder and both taper directions, near-cylinder stability, metrics/arc bounds,
front inverse projection and no clamping, all 18 independent research cases/76 sample points,
unit equivalence, measured cylinder/linear limits, analytic sphere/catenoid and withheld sampling,
SVG primitives/transforms/units/closing curves, counters/thin gaps/serialization, source order and
immutability, source rejection, raw measurement preservation, preset/project and Qt workflows.
Rapid setting changes are tested against freshly computed production output rather than previews.

The complete supplied research document was downloaded by exact owned ID and SHA-256 verified.
Packets 0 and A–F are incorporated; [decisions](research-decisions.md) record adaptations and limits.
Exact shapes use analytical contour derivative bounds. Measured profiles use analytical derivatives
with numerical quadrature: **not rigorous interval certification**. Shape topology is checked on
source/output approximations and rounded output, not proved for every arbitrary continuous path.
The geometric source domain is conservatively checked over the whole placement/support rectangle.

## Executed package and samples

The native Linux PyInstaller binary executed the Qt desktop self-test with three object modes,
three previews, 12 exports, counters, physical cylinder width, project/preset round trips and a
captured workspace. The frozen CLI also converted a lettering fixture from /tmp without the
source working directory. artifacts/packaged-self-test/report.json records packaged=true, platform=Linux,
status=passed, dimensions, nodes and SHA-256. Screenshot review identified clipped diagnostics;
the final warning label reserves enough height and the package was rebuilt after that fix.
The first failed frozen dependency build is documented in [packaging](packaging.md).

14 Corel specimens in artifacts/corel-acceptance include exact 100 mm and 25.4 mm/one-inch
references, forward/reverse taper, calibration strokes, O/A/B/R/8 counters, Hebrew-like path geometry,
experimental bell, guides/control samples and full templates. The Hebrew specimen is synthetic
geometry, **not font conversion fidelity evidence**. Manifest dimensions/hashes/node counts are
recorded. Production calibration examples use roughly 1,900–2,200 nodes; curved bell lettering
roughly 1,100. This is an export observation, not a claim about Corel import speed.

ART ONLY physically excludes guide paths. Guides + art and guide-only output preserve the same
origin/page. Guide paths may cut. Export metadata records units/origin/view/support/reference,
fit/strain, digital tolerance, certificate level and Corel status. No source file is overwritten.

## Acceptance states and next steps

| Gate | Status |
| --- | --- |
| Installed development workflow and local software tests | Verified on this Linux instance |
| Native Linux frozen executable/portable ZIP | Executed; desktop self-test passed |
| Native Windows executable/portable ZIP | **Not built or executed here**; native Windows runner required |
| CorelDRAW 2019 interoperability | **NEEDS REAL COREL2019 TEST**; 14 specimens/checklist prepared |
| Actual bell / vinyl / tape / viewing setup | **Unverified**; real measurements and approved application trial required |
| New-task cloud restoration | **Unverified**; local-only commits are not a remote restoration guarantee |

Windows/Ubuntu CI and native Windows setup/build scripts are provided, but no workflow was pushed
or dispatched. No Windows EXE, Corel pass, physical-production badge or approved material strain
is claimed. No heat/stretch recipe, engraving trial, machine control, automatic lettering redesign,
segmentation or general material simulation is included.

The measured-bell workflow is ready for real measurement entry and controlled experimental review.
It is not physically approved for full application. Run the native Windows build, then the Corel
checklist and finish-compatible approved trial in [bell measurement](bell-measurement.md).

Repository changes are local commits only. Generated builds, evidence logs, projects and downloaded
research are ignored under artifacts; portable and Corel ZIPs are available in the workspace.

Durable evidence: [frozen build](evidence/linux-frozen-report.json),
[Corel specimens](evidence/corel-specimens.json), [artifact sizes/checksums](evidence/artifacts.json).
A small Corel acceptance ZIP is separate from the native Linux portable ZIP. ZIP integrity passed.
