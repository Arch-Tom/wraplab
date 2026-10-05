"""Native-platform PyInstaller build + actual binary smoke test; Windows builds need Windows."""

import argparse
import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import json
import zipfile

from wraplab.acceptance import build as acceptance_pack
from release_checks import digest, execute, validate_extracted

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        help="New release directory; existing completed releases are preserved",
    )
    args = parser.parse_args()
    artifacts = (args.output_root or ROOT / "artifacts" / "releases" / platform.system()).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    if (artifacts / "SHA256SUMS.txt").exists():
        raise ValueError(
            "This release directory is complete. Choose a new --output-root to preserve it."
        )
    os.environ.setdefault("PYINSTALLER_CONFIG_DIR", str(artifacts / "pyinstaller-cache"))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--windowed",
            "--name",
            "WrapLab",
            "--exclude-module",
            "pytest",
            "--add-data",
            str(ROOT / "tests" / "fixtures") + os.pathsep + "acceptance-fixtures",
            "--add-data",
            str(ROOT / "docs" / "corel-acceptance.md") + os.pathsep + ".",
            "--paths",
            str(ROOT / "src"),
            "--specpath",
            str(artifacts / "packaging"),
            "--workpath",
            str(artifacts / "build"),
            "--distpath",
            str(artifacts / "dist"),
            str(ROOT / "scripts" / "entrypoint.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    portable = artifacts / "dist" / "WrapLab"
    source_pack = artifacts / "source-acceptance"
    acceptance_pack(source_pack)
    binary = portable / ("WrapLab.exe" if sys.platform == "win32" else "WrapLab")
    execute(
        binary,
        ["--acceptance-pack", portable / "Corel-Acceptance"],
        artifacts,
        dict(os.environ),
        artifacts / "bundled-corel.log",
    )
    shutil.copyfile(ROOT / "README.md", portable / "Source-README.md")
    shutil.copytree(ROOT / "docs", portable / "docs", dirs_exist_ok=True)
    (portable / "README.md").write_text(
        "# WrapLab portable 0.1\n\n"
        "Unzip the entire folder. Launch WrapLab.exe on Windows or WrapLab on Linux. "
        "Keep the _internal folder alongside the executable. Runtime operation is local/offline.\n\n"
        "Import a path-converted SVG, choose Front-view vinyl, enter dimensions down from the "
        "labelled top, place artwork and export Compensated Artwork Only. "
        "Measured profiles are experimental; examples are not your bell measurements.\n\n"
        "Corel-Acceptance contains 14 true-size review specimens and a checklist. "
        "Guides may cut. CorelDRAW 2019 and physical application remain unverified until tested. "
        "The separately supplied validation JSON records the actual native build test platform; a Linux "
        "pass does not establish Windows behavior.\n\n"
        "See docs/geometry.md, docs/bell-measurement.md and docs/validation.md.\n",
        encoding="utf-8",
    )
    shutil.copyfile(ROOT / "docs" / "bell-measurement.md", portable / "Bell-measurement.md")
    notices = portable / "Third-party-notices"
    for name in [
        "PySide6-Essentials",
        "shiboken6",
        "numpy",
        "scipy",
        "shapely",
        "svgpathtools",
        "defusedxml",
        "svgwrite",
        "pyinstaller",
    ]:
        dist = importlib.metadata.distribution(name)
        for file in dist.files or []:
            if "license" in str(file).lower() or Path(file).name.lower() in {
                "copying",
                "notice",
                "copyright",
            }:
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = (
                        notices
                        / name
                        / "__".join(part for part in Path(file).parts if part not in {"..", "."})
                    )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    system = platform.system()
    architecture = (
        "x64" if platform.machine().lower() in {"amd64", "x86_64"} else platform.machine()
    )
    name = f"WrapLab-0.1.0-{system}-{architecture}-portable"
    archive = Path(
        shutil.make_archive(
            str(artifacts / name), "zip", root_dir=portable.parent, base_dir=portable.name
        )
    )
    extraction = artifacts / "Extracted shop install שלום"
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        bundle.extractall(extraction)
        if os.name != "nt":
            for entry in bundle.infolist():
                path = extraction / entry.filename
                mode = entry.external_attr >> 16
                if mode:
                    path.chmod(mode & 0o777)
    report, pack = validate_extracted(extraction / "WrapLab", artifacts / "validation", source_pack)
    corel_archive = Path(
        shutil.make_archive(
            str(artifacts / f"WrapLab-0.1.0-{system}-Corel-Acceptance"),
            "zip",
            root_dir=pack.parent,
            base_dir=pack.name,
        )
    )
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    report["source_commit"] = source_sha
    report["source_dirty"] = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    )
    report["source_tree"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    report["workflow_run_id"] = os.environ.get("GITHUB_RUN_ID")
    report["unsigned"] = True
    report_file = artifacts / f"WrapLab-0.1.0-{system}-validation.json"
    report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # Hash the exact archive that was extracted and tested; never repack after validation.
    outputs = [archive, corel_archive, report_file]
    hashes = [{"file": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in outputs]
    (artifacts / "SHA256SUMS.txt").write_text(
        "".join(row["sha256"] + "  " + row["file"] + "\n" for row in hashes), encoding="utf-8"
    )
    (artifacts / "release-files.json").write_text(
        json.dumps(hashes, indent=2) + "\n", encoding="utf-8"
    )
    print("Portable artifact:", archive)


if __name__ == "__main__":
    main()
