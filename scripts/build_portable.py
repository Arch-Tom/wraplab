"""Native-platform PyInstaller build + actual binary smoke test; Windows builds need Windows."""

import argparse
import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from make_acceptance_pack import build as acceptance_pack

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-smoke", action="store_true", help="Build only; no validation claim")
    args = parser.parse_args()
    artifacts = ROOT / "artifacts"
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
    acceptance_pack(portable / "Corel-Acceptance")
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
        "Build-validation/report.json records the actual native build test platform; a Linux "
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
    if not args.skip_smoke:
        binary = portable / ("WrapLab.exe" if sys.platform == "win32" else "WrapLab")
        environment = dict(os.environ)
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        environment.setdefault("XDG_CACHE_HOME", str(artifacts / "cache"))
        subprocess.run(
            [str(binary), "--self-test", str(artifacts / "packaged-self-test")],
            env=environment,
            cwd=ROOT,
            check=True,
            timeout=180,
        )
        shutil.copytree(
            artifacts / "packaged-self-test", portable / "Build-validation", dirs_exist_ok=True
        )
    name = f"WrapLab-0.1.0-{platform.system()}-{platform.machine()}-portable"
    shutil.make_archive(
        str(artifacts / name), "zip", root_dir=portable.parent, base_dir=portable.name
    )
    print("Portable artifact:", artifacts / (name + ".zip"))


if __name__ == "__main__":
    main()
