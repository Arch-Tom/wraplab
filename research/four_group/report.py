"""Build the private experiment report and operator worksheet from measured outputs."""

import json

from .core import BASELINE, WARNING


def table(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
        + ["| " + " | ".join(str(x) for x in row) + " |" for row in rows]
    )


def numbers(values, digits=6):
    return ", ".join(f"{x:.{digits}f}" for x in values)


def documents(output, config, summary, rows):
    nominal = rows[0]["fits"]
    vector = summary["vector_and_registration"]
    names = list(vector["groups"])
    valid = [r for r in rows if r["complete_layout_valid"]]
    fit_rows, geometry_rows, sensitivity_rows, registration_rows = [], [], [], []
    for name in ["A", *names]:
        f = nominal[name]
        fit_rows.append(
            [
                name,
                numbers(f["support_front_xz_mm"], 4),
                f"{f['k']:.12f}",
                f"{f['reference_z_mm']:.6f} / {f['reference_radius_mm']:.6f}",
                f"{100 * f['strain']['extension']:.9f}",
                f"{100 * f['strain']['compression']:.9f}",
                f"{f['strain']['max_z_mm']:.6f} / {f['strain']['min_z_mm']:.6f}",
            ]
        )
    for name, data in vector["groups"].items():
        diff = nominal[name]["difference_from_A"]
        geometry_rows.append(
            [
                name,
                f"{data['membership']['shape']} / {data['membership']['contours']}",
                f"{data['audit'][0]['contours']} / {data['audit'][0]['openings']}",
                numbers(data["C_flat_svg_mm"]),
                f"{diff['sampled_max_difference_mm']:.6f}",
                f"{diff['target_center_anchor_alignment_max_mm']:.6f}",
            ]
        )
        strongest = max(valid, key=lambda r: r["fits"][name]["C_to_AB_max_abs_strain_ratio"])
        changed = max(
            valid,
            key=lambda r: r["fits"][name]
            .get("change_from_nominal", {})
            .get("sampled_max_difference_mm", 0),
        )
        ext = [100 * r["fits"][name]["strain"]["extension"] for r in valid]
        sensitivity_rows.append(
            [
                name,
                f"{min(ext):.6f}–{max(ext):.6f}",
                f"{strongest['fits'][name]['C_to_AB_max_abs_strain_ratio']:.6f}",
                strongest["scenario"]["id"],
                f"{changed['fits'][name]['change_from_nominal']['sampled_max_difference_mm']:.6f}",
                changed["scenario"]["id"],
            ]
        )
        for condition in ["B", "C"]:
            for a in data[condition + "_registration"]:
                registration_rows.append(
                    [
                        condition,
                        a["id"],
                        f"{a['global_front_x_mm']:.6f}",
                        f"{a['physical_height_above_bottom_in']:.6f}",
                        f"{a['surface_arc_from_front_meridian_mm']:.6f}",
                        numbers(a["cut_page_xy_mm"]),
                    ]
                )
    inverse = [
        (condition, name, d[condition + "_inverse_audit"])
        for name, d in vector["groups"].items()
        for condition in ["B", "C"]
    ]
    band_table = table(
        [
            "Group band",
            "A and B extension %",
            "A and B compression %",
            "C extension %",
            "C compression %",
        ],
        [
            [
                n,
                f"{100 * nominal[n]['A_and_B_same_field_over_group_band']['extension']:.9f}",
                f"{100 * nominal[n]['A_and_B_same_field_over_group_band']['compression']:.9f}",
                f"{100 * nominal[n]['strain']['extension']:.9f}",
                f"{100 * nominal[n]['strain']['compression']:.9f}",
            ]
            for n in names
        ],
    )
    inverse_table = table(
        [
            "Condition",
            "Group",
            "Inverted vertices",
            "Sampled front Hausdorff mm",
            "Inverse flat residual mm",
        ],
        [
            [
                c,
                n,
                d["serialized_vertices_inverted"],
                f"{d['sampled_max_inverse_front_contour_hausdorff_mm']:.9f}",
                f"{d['inverse_forward_residual_mm']:.3g}",
            ]
            for c, n, d in inverse
        ],
    )
    independent = summary["independent_verification"]
    a_dimensions = vector["A"]["flat_svg_mm"]
    placements = table(
        ["Group", "Front center x mm", "App top z mm", "Support width × height mm"],
        [
            [
                n,
                f"{d['target_placement_mm']['x']:.9f}",
                f"{d['target_placement_mm']['z']:.9f}",
                numbers([d["target_placement_mm"]["width"], d["target_placement_mm"]["height"]]),
            ]
            for n, d in vector["groups"].items()
        ],
    )
    report = f"""# Four-group compensation research — controlled nominal reconstruction

**{WARNING}**

## Decision and evidence boundary

**CONTINUE to a controlled paper, carrier and vinyl comparison.** The numerical hypothesis is supported under the explicit nominal surface model and the valid hypothetical variations tested. Practical superiority is **unverified**. Condition B may provide the same shop benefit with less alignment effort; it must be tested alongside C before a feature decision. No customer-production approval or product implementation follows from this report.

This is an authenticated uploaded source SVG applied to a reconstructed nominal trial. The saved Windows bell project and historical compensated export were unavailable. Latest physical measurements, native Windows acceptance, CorelDRAW 2019, cutter scale, actual paper/vinyl installation and durability remain **pending**. Outputs are experimental candidates for comparison, not validated instructions for the customer bell.

## A. Source and prerequisites

- Started from clean `fix/correctness-framing` at `{BASELINE}`; isolated local branch `research/four-group-compensation` based exactly on it. No applicable AGENTS.md was found.
- Reviewed `docs/correctness-framing-validation.md`, source framing, import/export, measured surface and conformal solver. Previous private full-suite XML records 306 tests, zero failures/errors/skips on that revision; publication verification records the same SHA. No later application changes were present. The historical `14a15c5` implementation was not substituted.
- Source SHA-256: `{config["source_sha256"]}`. Original uploaded SVG and read-only QA copy retained, never rewritten. No saved-project access is claimed.
- Frame: **visible artwork**, not the 13 × 11 inch page. Source frame in mm: `{json.dumps(summary["source_frame_mm"], sort_keys=True)}`. Visible width ≈12 in and height ≈7.897 in. Three compound paths, 44 closed contours and 12 nonzero-fill openings. Raw source path bounds were independently compared with the import frame.
- Group identifiers are explicit, hash-bound source contour indices, verified by vertical bands and containment. They are not a general automatic grouping rule. Hebrew source shape 0 contains both rows. No counter is assigned to a different group from its parent; every source contour is assigned exactly once.
- Linux / Python {summary["runtime"]["python"]}; pinned production dependencies plus isolated research plotting tools. Native Windows and shop equipment were unavailable. The production source, tests, dependency manifests and normal workflow remain unchanged.

The manifest records canonical inputs, artifact hashes, source hash and code fingerprint `{summary["research_code_fingerprint"]}`. Numerical JSON retains full precision; tables here are rounded for reading. The final local Git state is recorded separately in `final-source-state.json` when the package is finalized.

## B. Nominal reconstruction and Condition A

Physical heights/circumferences in inches, respectively: `{config["stations_physical_height_and_circumference_in"]}`. Canonical app z is `25.4 × (9.75 − physical height)` mm, giving 0, 38.1, 87.63 and 151.13 mm. Circumferences are converted to radii using C/(2π). Interpolation is the unchanged monotone PCHIP model.

Desired visible height is 101.6 mm (4 in); width is {summary["global_target_placement_mm"]["width"]:.9f} mm. Visible top/bottom are 7.8 / 3.8 in above the common bottom datum. Common front x=0; app z increases down; rotation=0; upright distant horizontal orthographic front view. Export approximation tolerance is {config["production_tolerance_mm"]} mm. No geometry is extrapolated beyond the measured stations.

The mathematical support is a rectangle around the intended artwork, including blank spaces. It is not a declaration of the actual weeded vinyl or carrier shape. A uses the complete support; C uses four subgroup supports. The lower visible edge lies exactly at the last station: **zero lower measurement coverage margin**.

{table(["Fit", "Support [left, top, right, bottom] mm", "k", "z_ref / radius_ref mm", "Max extension %", "Max compression %", "Max / min strain app z mm"], fit_rows)}

For each fit, conformal coordinate u is the integral of sqrt(1+r′²)/r relative to z_ref. The fitted coefficient k minimizes the existing support-weighted log-radius objective. R=r_ref exp(k u), and modeled application strain is r/R−1. These values describe an idealized conformal surface calculation, not a vinyl constitutive model or allowable installed strain. Extrema locations are horizontal bands because this strain field depends on z. Top-center anchoring translations and the complete production fit metadata are retained in `numerical-scenarios.json`.

A serialized flat bounds are **{a_dimensions[0]} × {a_dimensions[1]}**, approximately {float(a_dimensions[0][:-2]) / 25.4:.6f} × {float(a_dimensions[1][:-2]) / 25.4:.6f} in. The reported 4.93% / 0.027% global values and ≈6.112 × 4.601 in flat bounds are reproduced to their stated precision, using the corrected implementation and actual visible frame. No input was tuned to force that match. This agreement does not authenticate the missing Windows project.

## C. Three controlled conditions

| Condition | Calculation and geometry | Carrier concept | Interpretation |
| --- | --- | --- | --- |
| A | Existing whole-layout fit | One coupled intact arrangement | Global mathematical baseline |
| B | Exactly A's serialized numeric contour tokens, including all counters | Four separately registered carrier sections | Same A deformation field; any benefit is physical handling |
| C | Existing solver refitted independently on four explicit supports | Four independent carriers with common object references | Reduced modeled deformation plus extra registration work |

A and B whole-file path attributes and page attributes match; metadata differs. B subgroup contours are copied directly from A, with no refit, normalization, translation, or numeric rounding. B subgroup files intentionally retain **A's entire page and coordinate origin**, so blank page space is expected. They must not be resized or treated as recentered patterns. No mathematical strain benefit is assigned to B.

For a direct numerical comparison over the same occupied group bands:

{band_table}

## D. Group calculations, identity and differences

{placements}

The star center is **+{vector["groups"]["star"]["target_placement_mm"]["x"]:.9f} mm** relative to the common front meridian, independently derived from the source frame. It is not recentered. All group target coordinates are the same affine source-to-global-front mapping used by A, down to explicitly preserved endpoints. Hebrew order, orientation, baselines, original scale and intergroup spacing are preserved in target coordinates.

{table(["Group", "Source shape / contour indices", "Contours / openings", "C serialized flat W,H mm", "Max difference: mean translation mm", "Max difference: target-center translation mm"], geometry_rows)}

Contour differences use corresponding original curve samples (9 per source segment). The primary mean-translation comparison removes only the sample-weighted mean translation, no rotation. The separate target-center comparison aligns the mapped **same intended group center**. For English it reproduces approximately **4.215 mm**; a different translation convention gives approximately **3.484 mm**. Thus the old 4.215 mm figure is alignment-dependent. It demonstrates a real shape difference between cutting candidates, not a displacement to apply on the bell or measured physical installation error. Sampled maxima are not certified continuous-curve bounds. A separate best rigid rotation diagnostic is recorded in JSON and is not used to hide the primary differences.

Cut-pattern pages are trimmed independently for C. Their page origins have no direct physical meaning. Use their own registration sheets and common front coordinates; do not reuse A's flat spacing to lay out C as an intact sheet. Weeded vinyl pieces, ideal mathematical supports, carrier rectangles, relief cuts and handling margins are distinct. Changing a carrier alone does not change the mathematical field; changing a declared fitting support requires recalculation.

## E. Independent verification

An independently implemented Hermite/PCHIP interpolator, fixed-order Gauss-Legendre integration, fit objective, conformal map and inverse were checked without calling production interpolation, quadrature, fitting or mapping internals. Shared assumptions remain: same measurements, PCHIP convention, support weighting, conformal objective, axisymmetric surface and viewing model. NumPy floating arithmetic is shared. The natural-cubic scenario uses SciPy explicitly as an interpolation sensitivity comparison.

Analytic fixtures cover constant radius, both linear taper directions and ±1e-8 mm near-cylinder taper. Their expected cylinder/frustum developments come from separate closed formulas. Production versus independent nominal sampled flat discrepancy is at most **{max(x["independent_vs_production_flat_max_mm"] for x in independent):.3g} mm**. Increasing independent Gauss order from 64 to 96 changes sampled output by at most **{max(x["64_vs_96_gauss_order_flat_max_mm"] for x in independent):.3g} mm**. Reference tests also reject next-float-outside-domain and visible-edge violations. These numerical checks do not weaken production guards.

Actual serialized cutting vertices were independently inverted into global front coordinates. Those front polylines were compared with a dense independent source sampling (129 parameter samples per original segment):

{inverse_table}

Direct corresponding source-point forward/inverse checks are also recorded. The inverse remains in-domain; a 3e-6 mm forward residual budget is used only to audit serialized decimal rounding, never to extend production geometry. The inverse results establish computational target consistency under the model, not physical film fit. Front contour distances are sampled polygon comparisons, not mathematically certified global bounds.

All candidate cutting paths are closed and maintain nonzero fill, winding signs, parent containment and counters. No missing, duplicated, accidentally joined or invalid contours were detected. Across the four groups there are 44 contours / 12 openings. B retains A's exact cutting geometry; C retains the same compound topology. Artwork-only files have no text, images or guide group. Registration geometry is exported only in the separate reference directory. SVG validity has been checked; CorelDRAW and cutter behavior remain untested.

## F. Measurement, placement and support sensitivity

There are {len(rows)} deterministic scenarios: {len(valid)} complete valid comparisons and {len(rows) - len(valid)} rejected comparisons. These are **hypothetical variations**, not observed errors, probability distributions or confidence intervals. Full per-fit extension, compression, sampled dimensions, shape changes and registration-center shifts, including partial results for rejected layouts, are in JSON/CSV.

- Lowest-station physical height: ±0.05 and ±0.125 in; 6.30 in station height: ±0.125 and ±0.25 in.
- Each circumference and all circumferences together: ±0.125 in.
- Extra station at physical 5.05 in: nominal interpolated circumference and ±0.25 in. None is a new measurement. Even the zero-offset case changes neighboring PCHIP slopes when the station is inserted.
- Research-only piecewise-linear and natural-cubic interpolation alternatives.
- Artwork bottom placement: ±0.05 and ±0.125 in.
- All-side fitting-support margins and side-only margins: 1, 3, 5 mm. Support insets 1 and 3 mm are deliberately rejected because they exclude artwork.

{table(["C group", "Extension range % in complete valid cases", "Worst C / A-or-B same-band absolute strain", "Worst ratio scenario", "Largest aligned change mm", "Largest change scenario"], sensitivity_rows)}

The C advantage remains substantial in every complete valid scenario tested. Ratios compare C against **the same A/B field within that group's vertical band**, rather than artificially comparing every row only with the global worst case. The 6.30 in station-height ±0.25 in variations move global extension from about 2.37% to 7.66%; physical height uncertainty matters far more than the numerical quadrature refinement. English geometry changes by roughly 1.82 mm under the tested linear interpolation alternative after mean translation removal. This is a consequential modeling/measurement uncertainty despite the retained C strain advantage.

The near-zero C strain under piecewise-linear interpolation occurs when a group fits within one straight-frustum segment. It does not show that the real bell has straight cone sections or that the material will install without strain. A smooth unknown true profile can differ from either interpolation. Obtain extra measurements around the lower flare, including near 5.05 in and below the visible artwork if a lower margin is required.

Moving the lowest station upward or moving the artwork downward makes A and English leave the measured domain. Adding 1–5 mm all-side support similarly fails below the current last station. A 5 mm side-only global support crosses the front visibility margin. Partial group calculations in these scenarios are not a valid complete-layout candidate. Rejected scenario IDs: {", ".join(summary["rejected_scenarios"])}. No export is generated for them. Additional sensitivity combinations or updated real measurements require a new candidate directory; this finite scenario set does not establish robustness to every possible input error.

## G. Experimental artifact package and registration

- `EXPERIMENTAL_ARTWORK_ONLY`: A whole-layout SVG, B identical whole-layout SVG plus four exact-coordinate subsets, and four independently fitted C SVGs. Every filename and metadata marks experimental status; no warning text is part of cutting geometry.
- `REFERENCE_ONLY_DO_NOT_CUT`: intended true-size **front projection**, A whole-layout reference and B/C per-group reference sheets. These contain marks and text and must never be sent to the cutter. Each has independent 100 mm X/Y calibration lines. PDFs render content at the SVG's exact physical size; Qt rounds the blank page media box to the nearest point (≤0.18 mm), without stretching content. `printable-reference-audit.json` records those page sizes. Actual printer X/Y scale remains pending.
- `ANALYSIS_NOT_FOR_CUTTING`: strain, sensitivity and sampled shape comparison figures (SVG/PDF).
- `nominal-vector-and-registration-audit.json`: all fit-to-page origins, expected dimensions, L/R/TOP references and inverse checks. `summary.json`, `numerical-scenarios.json`, `sensitivity.csv` and `independent-reference-checks.json`: numerical evidence. `manifest.json`: exact input/configuration/code identity and output hashes.
- `SHOP-TEST-GUIDE.md` / PDF: operator checklist and record form. Final validation logs and local source state are added when final checks finish. The reproducibility source snapshot is separate from customer artwork.

Three noncollinear references per group establish translation and orientation: L/R at ±0.35 group width around the original group center at midheight; TOP at that original center and top height. They are references on separate paper/carrier, not additional vinyl cuts. The common physical bottom datum and front meridian must be marked reproducibly by the operator using a safe method. Surface circumferential arc is r(z) asin(x/r(z)), signed from that meridian at the stated height; it is not the projected front x distance. Arc distance is at constant physical height, not distance vertically along the curved surface. The table and JSON provide both concepts explicitly.

{table(["Condition", "Reference", "Front x mm", "Physical height in", "Signed circumferential arc mm", "XY on cut page mm"], registration_rows)}

Reference-sheet metadata gives the translation between cut-page coordinates and reference-sheet coordinates. Identify the same features on the weeded group and paper reference before transferring carrier marks. For B keep the original A cut coordinates or record any cropping translation explicitly. For C use its own page reference. Do not apply independently fitted patterns on one rigid intact carrier. The true-size front diagram is for checking visual composition, not a flat wrap template.

## H. Physical and downstream acceptance — pending

See the shop guide. Before testing, the operator must record acceptable positional errors, baseline/shape criteria, wrinkles/lift limits and application time. No invented universal vinyl tolerance or post-hoc success threshold is supplied. Import each actual SVG in CorelDRAW 2019 at 100%; check physical units, X and Y dimensions independently, orientation/mirroring, 44 contours/12 openings in total, Hebrew/star counters, and absence of guide paths. Do not resize flat patterns to a four-inch height. A preview or valid SVG is not proof of Corel compatibility or device scale.

Begin with true-size paper and safe registration rehearsal; paper cannot prove adhesive or film behavior. Then, where authorized, compare A intact, B separated with identical A geometry, and C refitted, using verified actual ORACAL 951 variant, transfer tape, compatible representative finish and manufacturer application conditions. Establish handling order, photograph a consistent distant frontal view, record application time, positional residuals, manipulations, wrinkles, release, letter/counter shape and initial lifting. Do not cut against the finished bell or select unverified adhesives/removal methods. Retention and durability require later observations; elongation-at-break is not an installed-strain limit.

## I. Decision rules

**Verified numerical result:** C materially reduces this modeled deformation without changing the intended global composition, with exact B/A equivalence and passing vector/reference checks. **Modeling limitation:** an axisymmetric, orthographic conformal calculation does not model film, adhesive, carrier stiffness, buckling or installation sequence. **Measurement uncertainty:** sparse nominal station heights and unknown true interpolation materially affect geometry. **Downstream verification / physical observations:** none performed in this environment. **Unverified hypothesis:** C's smaller deformation improves installation enough to offset added registration work.

Proceed to controlled testing, with updated measurements and accepted scale checks before any bell trial. Choose B if it equals C's physical result with less effort. C is a practical success only if it meets the predeclared appearance, registration, time, release and retention criteria and improves on B enough to justify complexity. If C is hard to register, revise the placement/registration strategy even if its numerical strain is lower. If none succeeds, investigate better measurements, changed placement/visible size, further segmentation or another physical process. No outcome is predetermined by the numerical table.

## J. Smallest future feature — proposal only

If C wins the physical comparison, consider a manual experiment mode with explicit contour selections, preserved common target coordinates and independent supports. UX must show original composition and separate carrier assumptions; geometry must reuse the existing guarded solver and support diagnostics. Persistence needs source-hash-bound stable selections, frame identity, global placement and versioned local-fit settings without changing old projects. Exports need separate artwork-only files, page origins, reference sheets, dimensional checks and complete provenance. Validation must cover counters/compound paths, invalid source changes, strict domains, A/B equivalence, exact cylinder/frustum references, target preservation and downstream shop acceptance. Do not implement automatic grouping or a new solver as the first feature. Nothing in this research changes application behavior.

## K. Final source state and reproducibility

Only isolated research scripts, focused reference tests and research documentation are eligible for a local commit. Customer SVGs, projects, configs, derived artwork and QA outputs stay in ignored private artifact directories. The verified correctness branch and default main are unchanged; no research push or merge is authorized or performed. Final commit, changed paths, validation commands/results and working-tree state are captured in `final-source-state.json` and accompanying logs. Reproduce with the instructions in the source snapshot README, supplying the authenticated original source and private input JSON. Output directories refuse overwrite; earlier candidates are retained separately.
"""
    (output / "RESEARCH-REPORT.md").write_text(report)
    dimensions = [["A / B full page", *a_dimensions]] + [
        ["C " + n, f"{d['C_flat_svg_mm'][0]:.6f}mm", f"{d['C_flat_svg_mm'][1]:.6f}mm"]
        for n, d in vector["groups"].items()
    ]
    b_dimensions = table(
        ["B group", "Actual contour width mm", "Actual contour height mm"],
        [
            [n, *[f"{v:.6f}" for v in d["B_artwork_width_height_mm"]]]
            for n, d in vector["groups"].items()
        ],
    )
    guide = f"""# Experimental shop comparison — operator worksheet

**{WARNING}**

Status: reconstructed nominal 4-inch front-view trial using the authenticated SVG. Latest bell measurements, Windows, CorelDRAW, cutter and physical acceptance are PENDING. This worksheet grants no production approval.

## 1. Agree the pass criteria before testing

Operator/date: __________  Reviewer: __________  Test surface/finish: __________

Actual film variant/lot: __________  Transfer tape/lot: __________

Verified manufacturer instructions, application conditions and compatible removal method: __________

Latest measurement record and datum definition: __________

Maximum positional error per group: ____ mm. Baseline / letter-shape tolerance and viewing distance: __________

Maximum allowed wrinkles, lifting or local distortion: __________

Acceptable application time and additional C registration effort: __________

Initial and later inspection times / retention criteria: __________

Use criteria accepted by the operator for this experiment; do not choose thresholds after seeing which condition wins.

## 2. Verify inputs, scale and paths — all pending operator checks

1. Identify candidate by manifest/source/output hashes. Original artwork stays unchanged. Confirm actual physical top/bottom and all circumferences/vertical heights. Nominal artwork is top 7.8 in, bottom 3.8 in. The lowest station equals the artwork bottom: additional lower support needs new measurements or a revised placement and a new calculation.
2. Import artwork-only SVGs into CorelDRAW 2019 at **100%**, correct mm units. Check width and height independently against the table. Check reference-sheet 100 mm X **and** Y lines without sending those lines to the cutter. Print reference PDFs at actual size, never fit-to-page. If a printer tiles pages, verify alignment and scale after assembly.
3. Verify upright orientation and mirroring state, source reading order, baselines, star openings and Hebrew/English counters. Total source topology is 44 closed contours and 12 openings. Per-group expectations are in the research report/JSON. Check missing, duplicate, open or joined cuts. No guide, label, reference mark or warning text belongs in cutter paths.
4. B subsets retain the whole A page. They contain exact A coordinates. Keep those coordinates or document cropping translation; **do not rescale**. C pages are independently trimmed. Do not resize any compensated output back to 4 inches; four inches is the desired viewed height, not the flat height.
5. Perform approved independent device-scale checks on safe scrap, verify X/Y after output, and record actual measured dimensions. Preview is not device proof. Stop on any dimensional, orientation or topology mismatch.

{table(["Candidate", "Expected SVG page width", "Expected SVG page height"], dimensions)}

For B group files the page is the full A page; individual group contour extents remain those in A. Use the JSON and SVG page origin when comparing cropped views.

{b_dimensions}

## 3. Establish common physical registration

Mark a safe reproducible common front meridian and bottom datum. Heights are straight vertical heights above the datum, **not lengths along the curved surface**. At each reference height use the modeled signed circumferential arc from the front meridian, not projected x as a tape distance. Verify the physical reference method independently on paper first. The full coordinate table is in the report and audit JSON.

Use separate `REFERENCE_ONLY_DO_NOT_CUT` sheets to identify each group's L/R/TOP anchors. Match artwork and transfer those marks to paper/carrier safely. Three noncollinear marks establish orientation and position. For B use A-derived marks; for C use C's own marks, targeting the same physical coordinates. Preserve the star's +2.19579 mm front offset. Do not center each group independently or reuse A flat spacing for C. The front-layout diagram is a front projection and is not a wrap template.

Record reference-mark method, placement order, margins, relief cuts, any allowed carrier flexibility and registration residuals: __________

## 4. Paper rehearsal, then controlled material comparison

Use true-size paper first to check gross geometry and registration. Record failures before proceeding. Paper success establishes neither vinyl fit nor adhesive compatibility. Verify safe test surface, actual film/tape/finish and manufacturer's application/inspection guidance before any material trial. Prefer approved representative surfaces; protect the customer bell. Never cut directly against its finish.

Compare all three conditions using comparable materials, finish, operator, environment, placement and observations. Rotate the test order or use repeat/independent rehearsals where feasible to reduce learning effects; record order and repetitions rather than inventing statistical confidence.

- **A:** unchanged global compensation, one coupled carrier arrangement. Record alignment, handling, wrinkles and baseline appearance.
- **B:** exactly the same global compensated contours, four independent carriers. Record whether separation alone improves handling or appearance, with no claim of mathematical strain reduction.
- **C:** four independently refitted patterns. Use shared physical target references and separate carriers; do not bridge them with an intact full-layout carrier. Record each row/star alignment and extra registration effort.

Do not infer allowed installed strain from film elongation-at-break. Do not introduce an unverified heat, solvent, adhesive or removal process. Stop if the test risks damage or violates the verified material instructions.

## 5. Record outcomes separately from modeled strain

{table(["Observation", "A", "B", "C"], [[s, "____", "____", "____"] for s in ["Trial order / repeat", "X/Y device dimensions", "Star positional residual mm", "Upper Hebrew residual mm", "Lower Hebrew residual mm", "English residual mm", "Baseline / spacing / letter appearance", "Application time", "Alignment corrections / manipulation", "Carrier wrinkles / local stretching", "Counter and letter integrity", "Transfer release / adhesive behavior", "Initial lifting / retention", "Later inspection date / lifting", "Accepted against prior criteria?"]])}

Photograph from a consistent distant horizontal frontal view, with scale/reference and condition ID; add closeups of defects. Record lighting/view distance. Observations: __________

Choose B if it performs as well as C with less effort. Numerical advantage alone does not make C a practical success. If registration fails, revise it. If all fail, reconsider measurements, placement, artwork size, segmentation or process. Short-term retention does not establish long-term durability. Keep Windows/Corel/cutter/physical/durability checks marked pending until actual records exist.
"""
    (output / "SHOP-TEST-GUIDE.md").write_text(guide)
