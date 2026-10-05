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
from patch_build_dependencies import apply_patch

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_FIXTURES = [
    "calibration.svg", "lettering.svg", "reference-100mm.svg", "reference-25mm.svg",
    "reference-inch.svg", "hebrew-paths.svg", "eight.svg",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        help="New release directory; existing completed releases are preserved",
    )
    parser.add_argument("--diagnostic", action="store_true", help="Build a clearly labelled Windows compatibility candidate; never publishes it")
    args = parser.parse_args()
    dependency_patch = apply_patch()
    artifacts = (args.output_root or ROOT / "artifacts" / "releases" / platform.system()).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    if (artifacts / "SHA256SUMS.txt").exists():
        raise ValueError(
            "This release directory is complete. Choose a new --output-root to preserve it."
        )
    os.environ.setdefault("PYINSTALLER_CONFIG_DIR", str(artifacts / "pyinstaller-cache"))
    source_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source_epoch = subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=ROOT, text=True).strip()
    build_environment = dict(os.environ, SOURCE_DATE_EPOCH=source_epoch)
    resource_arguments = []
    for fixture in ACCEPTANCE_FIXTURES:
        resource_arguments += ["--add-data", str(ROOT / "tests/fixtures" / fixture) + os.pathsep + "acceptance-fixtures"]
    if os.name == "nt":
        resource_arguments += [
            "--version-file", str(ROOT / "packaging/windows/version-info.txt"),
            "--manifest", str(ROOT / "packaging/windows/wraplab.manifest"),
            "--icon", str(ROOT / "packaging/windows/wraplab.ico"),
        ]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--windowed",
            "--noupx",
            "--name",
            "WrapLab",
            "--exclude-module",
            "pytest",
            "--exclude-module", "PySide6.QtNetwork",
            "--exclude-module", "numpy._core._multiarray_tests",
            "--additional-hooks-dir", str(ROOT / "packaging/hooks"),
            *resource_arguments,
            "--add-data", str(ROOT / "packaging/windows/wraplab.ico") + os.pathsep + ".",
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
        env=build_environment,
        check=True,
    )
    portable = artifacts / "dist" / "WrapLab"
    source_pack = artifacts / "source-acceptance"
    acceptance_pack(source_pack)
    binary = portable / ("WrapLab.exe" if sys.platform == "win32" else "WrapLab")
    build_settings = {
        "version": "0.1.0", "source_commit": source_sha,
        "source_date_epoch": int(source_epoch), "python": platform.python_version(),
        "pyinstaller": importlib.metadata.version("PyInstaller"),
        "qt": importlib.metadata.version("PySide6-Essentials"),
        "hooks_contrib": importlib.metadata.version("pyinstaller-hooks-contrib"),
        "platform": platform.system(), "architecture": "x64" if platform.machine().lower() in {"amd64", "x86_64"} else platform.machine(),
        "build_type": "onedir", "gui_no_console": True, "upx": False,
        "strip": False, "custom_bootloader": False, "splash": False,
        "installer": None, "requested_execution_level": "asInvoker",
        "runtime_shell_launcher": False, "runtime_downloader": False,
        "excluded_modules": ["pytest", "PySide6.QtNetwork", "numpy._core._multiarray_tests"],
        "dependency_patches": [dependency_patch] if dependency_patch else [],
        "build_hook": "packaging/hooks/hook-PySide6.QtGui.py (omit unused TUIO network touch plugin)",
        "binary_collection": "Stock dependency analysis, with documented module/plugin exclusions",
        "expected_executable": binary.name,
        "primary_executable_sha256": digest(binary),
        "expected_app_child_processes": [], "expected_app_network_connections": [],
        "expected_startup_wmi_queries": [],
        "expected_writes": ["Qt AppLocalDataLocation/WrapLab/WrapLab: objects.json and Last-session.wraplab", "Operator-selected project/export directories: JSON/SVG and short-lived sibling .wraplab-* atomic-save files"],
        "temporary_native_extraction": False,
        "sentinelone_tested": False,
    }
    if os.name == "nt":
        import PyInstaller
        from bundle_inventory import pe_details, write_inventory

        inventory = write_inventory(portable, artifacts / "bundle-inventory.json")
        primary = next(r for r in inventory["native_files"] if r["path"] == "WrapLab.exe")
        assert primary["version"]["ProductName"] == "WrapLab"
        assert primary["version"]["FileVersion"] == "0.1.0.0"
        assert primary["subsystem"] == 2 and primary["machine"] == "0x8664"
        assert primary["icon_resource_present"]
        assert any('level="asInvoker"' in m for m in primary["manifest"])
        assert not inventory["upx_section_markers"]
        assert len([r for r in inventory["native_files"] if r["path"].endswith(".exe")]) == 1
        assert not any("qt6network" in r["path"].lower() or "tuiotouch" in r["path"].lower() or "_multiarray_tests" in r["path"] for r in inventory["native_files"])
        stock = Path(PyInstaller.__file__).parent / "bootloader/Windows-64bit-intel/runw.exe"
        stock_text = next(s["sha256"] for s in pe_details(stock.read_bytes())["sections"] if s["name"] == ".text")
        assert stock_text == next(s["sha256"] for s in primary["sections"] if s["name"] == ".text"), "Executable code differs from pinned stock GUI bootloader"
        build_settings["stock_bootloader_text_sha256"] = stock_text
        build_settings["unsigned"] = primary["certificate_table_bytes"] == 0
        build_settings["native_file_count"] = inventory["native_count"]
        build_settings["native_bytes"] = inventory["native_bytes"]
    (portable / "Build-manifest.json").write_text(json.dumps(build_settings, indent=2) + "\n", encoding="utf-8")
    (portable / "Diagnostic-manifest.txt").write_text(
        "WrapLab 0.1.0 — conventional Windows compatibility candidate\n"
        + f"Source commit: {source_sha}\nBuild: onedir, GUI, stock PyInstaller {build_settings['pyinstaller']}, no UPX, no splash\n"
        + f"Platform: {build_settings['platform']} {build_settings['architecture']}; Python {build_settings['python']}; Qt {build_settings['qt']}\n"
        + "Documented Windows dependency patch: NumPy testing helper detects WebAssembly using sys.platform; numerical code/native binaries unchanged.\n"
        + f"Executable: {binary.name}\nExecutable SHA-256: {digest(binary)}\n"
        + "Expected app child processes: none. Expected app network connections: none.\n"
        + "No elevation requested (asInvoker). No runtime launcher, updater, downloads or temporary DLL/EXE extraction.\n"
        + "Writes: local per-user WrapLab preset/recovery JSON; chosen project/SVG paths and short-lived sibling atomic-save data.\n"
        + "No SentinelOne test has been performed. This manifest identifies the candidate; it is not endpoint approval.\n",
        encoding="utf-8",
    )
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
    if args.diagnostic:
        name = f"WrapLab-0.1.0-{system}-{architecture}-onedir-diagnostic"
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
    report["source_commit"] = source_sha
    report["source_dirty"] = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    )
    report["source_tree"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    report["workflow_run_id"] = os.environ.get("GITHUB_RUN_ID")
    report["unsigned"] = build_settings.get("unsigned", True)
    report["build_settings"] = build_settings
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
