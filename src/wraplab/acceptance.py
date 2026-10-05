"""Deterministic specimens; none of these example profiles are actual bell measurements."""

import csv
import hashlib
import json
from pathlib import Path
import shutil
import platform
import sys
import xml.etree.ElementTree as ET

from .domain import ObjectSpec, Project
from .persistence import save_project
from .svg import convert, export_svg, import_svg

ROOT = Path(__file__).resolve().parents[2]
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
FIXTURES = (
    RESOURCE_ROOT / "acceptance-fixtures"
    if getattr(sys, "frozen", False)
    else ROOT / "tests" / "fixtures"
)
CHECKLIST = (
    RESOURCE_ROOT / "corel-acceptance.md"
    if getattr(sys, "frozen", False)
    else ROOT / "docs" / "corel-acceptance.md"
)


def build(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    examples = [
        ("01-cylinder-front", "calibration.svg", "cylinder", "artwork", 50),
        ("02-frustum-front", "calibration.svg", "frustum", "artwork", 40),
        ("03-bell-front-experimental", "lettering.svg", "measured", "artwork", 30),
        ("04-compound-lettering", "lettering.svg", "cylinder", "artwork", 60),
        ("05-bell-guides-experimental", "lettering.svg", "measured", "guides", 30),
        ("06-bell-uncompensated", "lettering.svg", "measured", "original", 30),
        ("07-reverse-frustum-front", "calibration.svg", "frustum", "artwork", 40),
        ("08-cylinder-full-template", "calibration.svg", "cylinder", "template", 40),
        ("09-frustum-full-template", "calibration.svg", "frustum", "template", 40),
        ("10-reference-100mm", "reference-100mm.svg", "cylinder", "artwork", 100),
        ("11-reference-25mm", "reference-25mm.svg", "cylinder", "artwork", 25.4),
        ("12-reference-inch", "reference-inch.svg", "cylinder", "artwork", 25.4),
        ("13-hebrew-path-geometry", "hebrew-paths.svg", "cylinder", "artwork", 40),
        ("14-eight-counters", "eight.svg", "frustum", "artwork", 20),
    ]
    manifest = []
    for name, fixture, mode, export, width in examples:
        source = (FIXTURES / fixture).read_text(encoding="utf-8")
        art = import_svg(source)
        project = Project(
            object=ObjectSpec(mode=mode, name="Illustrative " + mode + " — NOT real measurements"),
            source_svg=source,
            source_name=fixture,
        )
        project.placement.width = width
        project.placement.height = width * art.height_mm / art.width_mm
        if name.startswith("07"):
            project.object.top_diameter, project.object.bottom_diameter = 90, 65
        if "reference" in name:
            project.physical_model = "surface-template"
            project.object.height, project.object.diameter = 200, 200
        if export == "template":
            project.physical_model = "surface-template"
            project.wrap_degrees = 360
        project.center_artwork()
        result = (
            convert(art, project, original=export == "original") if export != "template" else None
        )
        text = export_svg(result, project, export, fixture)
        (destination / f"{name}.svg").write_bytes(text.encode("utf-8"))
        save_project(destination / f"{name}.wraplab", project)
        root = ET.fromstring(text)
        manifest.append(
            {
                "file": name + ".svg",
                "width": root.get("width"),
                "height": root.get("height"),
                "mode": mode,
                "status": project.object.surface().status,
                "physical_model": project.physical_model,
                "nodes": result.node_count if result else None,
                "contours_per_path": [len(p.contours) for p in result.paths] if result else [],
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "warnings": result.warnings if result else [],
            }
        )
    shutil.copyfile(CHECKLIST, destination / "READ-ME-Corel-acceptance.md")
    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "generator_platform": platform.system(),
                "generator_packaged": bool(getattr(sys, "frozen", False)),
                "corel_verified": False,
                "physical_vinyl_verified": False,
                "illustrative_geometry_only": True,
                "specimens": manifest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with (destination / "Operator-results.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "Specimen",
                "Expected width mm",
                "Expected height mm",
                "Status",
                "Import PASS/FAIL",
                "Size PASS/FAIL",
                "Geometry PASS/FAIL",
                "Editable PASS/FAIL",
                "Practical PASS/FAIL",
                "Measured width",
                "Measured height",
                "Notes",
            ]
        )
        for row in manifest:
            writer.writerow([row["file"], row["width"], row["height"], row["status"], *([""] * 8)])
    print(f"Created {len(manifest)} SVG specimens in {destination}")
    return manifest
