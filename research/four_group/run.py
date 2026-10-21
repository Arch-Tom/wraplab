"""python -m research.four_group.run --config PRIVATE.json --output NEW_DIRECTORY"""

import argparse
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np

from .artifacts import bind_manifest, build
from .core import BASELINE, groups, load_input, raw_source_audit, source_samples, target_points
from .independent import Fit, Profile
from .numerics import evaluate
from .presentation import figures
from .printable import printables
from .report import documents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="New private directory; refuses overwrite"
    )
    args = parser.parse_args()
    started = time.monotonic()
    subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE, "HEAD"], check=True)
    subprocess.run(
        [
            "git",
            "diff",
            "--exit-code",
            BASELINE,
            "--",
            "src",
            "tests",
            "scripts",
            "pyproject.toml",
            "requirements.lock",
        ],
        check=True,
    )
    config, source, art = load_input(args.config)
    selected = groups(art, config["groups"])
    args.output.mkdir(parents=True, exist_ok=False)
    source_audit = raw_source_audit(source, art)
    (args.output / "source-audit.json").write_text(json.dumps(source_audit, indent=2) + "\n")
    fingerprint = hashlib.sha256(
        "".join(
            p.name + hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        ).encode()
    ).hexdigest()
    rows, baseline, project, locals_ = evaluate(config, art, selected)
    assert rows[0]["complete_layout_valid"]
    (args.output / "numerical-scenarios.json").write_text(json.dumps(rows, indent=2) + "\n")
    independent = []
    for name, p in [("A", project), *locals_.items()]:
        group = art if name == "A" else selected[name]
        frame = p.source_frame(group)
        raw = source_samples(group, 5)
        raw = raw[:: max(1, len(raw) // 128)]
        desired = target_points(raw, art.visible_frame, project)
        ref = baseline[name]["fit"]
        mapped = ref.mapping(desired)
        mapper = p.mapper(frame.width, frame.height)
        production = np.array(
            [
                [q.real, q.imag]
                for q in (mapper(complex(x - frame.left, y - frame.top)) for x, y in raw)
            ]
        )
        difference = float(np.max(np.linalg.norm(mapped - production, axis=1)))
        assert difference < 1e-8
        tight = Fit(
            Profile(p.object.surface().points),
            rows[0]["fits"][name]["support_front_xz_mm"],
            order=96,
        )
        convergence = float(np.max(np.linalg.norm(mapped - tight.mapping(desired), axis=1)))
        assert convergence < 1e-8
        independent.append(
            {
                "fit": name,
                "sample_count": len(raw),
                "independent_vs_production_flat_max_mm": difference,
                "64_vs_96_gauss_order_flat_max_mm": convergence,
                "shared_assumptions": "same nominal measurements, PCHIP convention, support and conformal objective; separate interpolation/quadrature/fitter/map",
            }
        )
    (args.output / "independent-reference-checks.json").write_text(
        json.dumps(independent, indent=2) + "\n"
    )
    artifacts = build(args.output, config, art, selected, project, locals_, rows[0], baseline)
    figures(args.output, config, art, selected, project, locals_, rows, baseline)
    with (args.output / "sensitivity.csv").open("w", newline="") as handle:
        fields = [
            "scenario",
            "category",
            "complete_layout_valid",
            "fit",
            "valid",
            "extension_percent",
            "compression_percent",
            "sampled_width_mm",
            "sampled_height_mm",
            "aligned_change_mm",
            "C_to_AB_abs_strain_ratio",
            "rejection",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for name, data in row["fits"].items():
                writer.writerow(
                    {
                        "scenario": row["scenario"]["id"],
                        "category": row["scenario"]["category"],
                        "complete_layout_valid": row["complete_layout_valid"],
                        "fit": name,
                        "valid": data["valid"],
                        "extension_percent": 100 * data["strain"]["extension"]
                        if data["valid"]
                        else "",
                        "compression_percent": 100 * data["strain"]["compression"]
                        if data["valid"]
                        else "",
                        "sampled_width_mm": data["sampled_flat_width_height_mm"][0]
                        if data["valid"]
                        else "",
                        "sampled_height_mm": data["sampled_flat_width_height_mm"][1]
                        if data["valid"]
                        else "",
                        "aligned_change_mm": data.get("change_from_nominal", {}).get(
                            "sampled_max_difference_mm", ""
                        ),
                        "C_to_AB_abs_strain_ratio": data.get("C_to_AB_max_abs_strain_ratio", ""),
                        "rejection": data.get("rejection", ""),
                    }
                )
    summary = {
        "status": "passed",
        "baseline_commit": BASELINE,
        "research_code_fingerprint": fingerprint,
        "research_git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "dependency_versions": {
            name: version(name)
            for name in [
                "numpy",
                "scipy",
                "shapely",
                "svgpathtools",
                "matplotlib",
                "PySide6-Essentials",
                "defusedxml",
                "svgwrite",
            ]
        },
        "calculation_settings": {
            "algorithm": "pchip-conformal-support-fit-v1",
            "production_density_quad": {
                "epsabs": 1e-12,
                "epsrel": 1e-10,
                "near_reference_epsabs": 1e-14,
            },
            "production_objective_quad": {"scaled_epsabs_factor": 1e-11, "epsrel": 1e-10},
            "independent_legendre_orders": [64, 96],
            "source_contour_comparison_samples_per_segment": 9,
            "inverse_reference_samples_per_segment": 129,
            "visible_edge_ratio": 0.95,
            "wrap_degrees": project.wrap_degrees,
            "rotation_degrees": project.rotation_degrees,
            "export_tolerance_mm": project.export_tolerance_mm,
        },
        "input_status": config["input_status"],
        "source_frame_mm": vars(art.visible_frame),
        "source_audit": source_audit,
        "global_target_placement_mm": vars(project.placement),
        "scenarios": len(rows),
        "complete_valid_scenarios": sum(r["complete_layout_valid"] for r in rows),
        "rejected_scenarios": [r["scenario"]["id"] for r in rows if not r["complete_layout_valid"]],
        "nominal_strain_and_fit": rows[0]["fits"],
        "independent_verification": independent,
        "vector_and_registration": artifacts,
        "elapsed_seconds": time.monotonic() - started,
        "physical_tests": "not performed",
        "actual_saved_project": "not available; reconstructed nominal trial",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    documents(args.output, config, summary, rows)
    printables(args.output)
    bind_manifest(args.output, config, source, fingerprint)
    print(
        json.dumps(
            {
                "status": "passed",
                "scenarios": len(rows),
                "complete_valid_scenarios": summary["complete_valid_scenarios"],
                "seconds": summary["elapsed_seconds"],
                "output": str(args.output),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
