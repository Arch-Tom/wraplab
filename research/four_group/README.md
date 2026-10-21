# Isolated four-group compensation experiment

This manually invoked research harness compares the unchanged whole-layout fit
(A), exactly the same contours on separate carriers (B), and four independently
fitted groups (C). It does not add application behavior, project semantics or a
new production solver. It is specific to the authenticated three-path / 44-contour
research source; the group identifiers are **not** an automatic grouping feature.

All generated materials are **EXPERIMENTAL — NOT PRODUCTION APPROVED**. Numerical
strain does not establish physical installation success. Customer source SVGs,
projects, private configs and derived patterns must remain outside version control
and normal production exports. `artifacts/` is ignored by this repository.

## Foundation and environment

Use the repaired baseline `23181d3672dc11abc548412eb4d8316cf9bae422`, or a
research-only descendant with identical `src`, `tests`, `scripts`, production
dependency lock and project manifest. The runner checks this requirement. Never
substitute the older investigation revision or relax measured-domain guards.

From the repository root, with the baseline's pinned Python environment installed:

```sh
.venv/bin/python -m pip install -r research/four_group/requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q research/four_group/test_reference.py
.venv/bin/python -m ruff check research/four_group
```

Qt is used only to produce printable reference PDFs. On a headless Linux host set
`QT_QPA_PLATFORM=offscreen`, and set `XDG_DATA_HOME`, `XDG_CACHE_HOME` and
`MPLCONFIGDIR` to writable task-specific directories. The full GUI test suite also
needs the baseline's documented 1600 × 1000 offscreen display configuration.

## Private input

Prepare an ignored JSON config containing:

```json
{
  "baseline_commit": "23181d3672dc11abc548412eb4d8316cf9bae422",
  "source_svg": "/absolute/private/path/to/original.svg",
  "source_sha256": "SHA256_OF_UNCHANGED_AUTHENTICATED_SOURCE",
  "input_status": "Identify authenticated source and reconstructed versus saved-project inputs",
  "physical_top_height_in": "9.75",
  "stations_physical_height_and_circumference_in": [
    ["9.75", "17.125"], ["8.25", "20.125"],
    ["6.30", "25.1875"], ["3.80", "36.125"]
  ],
  "visible_height_in": "4.0",
  "visible_bottom_physical_height_in": "3.80",
  "global_front_center_mm": 0,
  "frame": "visible",
  "production_tolerance_mm": 0.01,
  "groups": [
    {"id": "star", "shape": 1, "contours": [0,1,2,3,4,5,6,7]},
    {"id": "upper_hebrew", "shape": 0, "contours": [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]},
    {"id": "lower_hebrew", "shape": 0, "contours": [15,16,17,18,19,20,21]},
    {"id": "cantorland", "shape": 2, "contours": [0,1,2,3,4,5,6,7,8,9,10,11,12,13]}
  ]
}
```

The station values are nominal user research inputs, not physically reconfirmed
measurements. Group indices must be reverified against the actual hash-bound
source. The source audit deliberately rejects transforms or a non-mm/scaled page;
such input needs an explicit new reference audit, not silent normalization.
Never treat this config as an authenticated saved Windows project.

## Run and inspect

```sh
.venv/bin/python -m research.four_group.run \
  --config artifacts/private-experiment/inputs.json \
  --output artifacts/private-experiment/candidate-001
```

The runner refuses to overwrite an output directory. Use a new numbered directory
for any correction, measurement revision or scenario change. Do not run with
Python's assertion-disabling `-O` option: assertions are intentional research
acceptance gates.

The output contains:

- `RESEARCH-REPORT.md` and a printable `SHOP-TEST-GUIDE.md` / PDF.
- `EXPERIMENTAL_ARTWORK_ONLY`: A and B whole-layout files, four exact-coordinate
  B subsets and four independent C fits. B subsets retain A's page and origin.
- `REFERENCE_ONLY_DO_NOT_CUT`: separate SVG/PDF references with L/R/TOP anchors,
  common physical coordinates, a front-view diagram and 100 mm X/Y references.
  These files contain guides/text and must never be sent to the cutter.
- `ANALYSIS_NOT_FOR_CUTTING`: standalone analysis figures in SVG/PDF.
- `source-audit.json`, `numerical-scenarios.json`, `sensitivity.csv`,
  `independent-reference-checks.json`, `nominal-vector-and-registration-audit.json`,
  `summary.json` and `manifest.json`: full numerical provenance and output hashes.

The manifest can be rebound with `artifacts.bind_manifest` after adding final
validation logs, a source snapshot and a final source-state record. Its hashes
cover every file except the manifest itself. Preserve the original candidate if
revising cutting geometry; never overwrite customer originals.

## Independent checks and limits

`independent.py` separately implements PCHIP/Hermite interpolation, fixed-order
Gauss-Legendre integration, the same mathematical fitting objective, conformal
map and inverse. Analytic cylinder / increasing and decreasing frustum / near-
cylinder fixtures check it against separate formulas. The real-artwork run checks
it against production output and independently inverts serialized cutting
vertices. Shared mathematical assumptions and libraries are disclosed in the
report; successful inverse mapping is not a physical fit test.

The 36 deterministic scenarios vary station heights, circumference, a hypothetical
extra station, interpolation, placement and supports. Invalid complete layouts
are rejected, even if some individual groups remain calculable. Variations are
not measured distributions or confidence intervals. Samples and Hausdorff
comparisons are not certified continuous-curve error bounds. Harmless consecutive
audit points within 1e-10 mm are removed only from reference polylines to avoid
zero-length source-closure segments; source and cutting geometry remain intact.

For this experiment, numerical success permits further controlled comparison.
Windows/CorelDRAW 2019, cutter scale, actual film/tape/finish, registration,
appearance, release, retention and durability require operator evidence. B can
win if carrier separation gives the same physical result with less effort. Do not
publish research code or any customer-derived artifact without explicit approval.
