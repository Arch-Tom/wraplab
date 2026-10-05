"""Release-only native package checks; production geometry stays untouched."""

from contextlib import contextmanager
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import xml.etree.ElementTree as ET

from shapely.geometry import LineString, LinearRing, Polygon


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inventory(root):
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


def svg_paths(path):
    root = ET.parse(path).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.get("width").endswith("mm") and root.get("height").endswith("mm")
    assert [float(v) for v in root.get("viewBox").split()] == [
        0,
        0,
        float(root.get("width")[:-2]),
        float(root.get("height")[:-2]),
    ]
    assert not root.findall(".//{*}image") and not root.findall(".//{*}text")
    result = []
    for element in root.findall(".//{*}path"):
        contours = []
        for part in re.split(r"(?=M)", element.get("d")):
            if not part.strip():
                continue
            closed = part.rstrip().endswith("Z")
            numbers = [
                float(v) for v in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", part)
            ]
            points = list(zip(numbers[::2], numbers[1::2], strict=True))
            if closed:
                points.append(points[0])
            contours.append((closed, LineString(points)))
        result.append((dict(element.attrib), contours))
    return root, result


def compare_directories(reference, candidate, tolerance=0.000002):
    reference, candidate = Path(reference), Path(candidate)
    names = sorted(p.name for p in reference.glob("*.svg"))
    assert names and names == sorted(p.name for p in candidate.glob("*.svg"))
    rows = []
    for name in names:
        a, paths_a = svg_paths(reference / name)
        b, paths_b = svg_paths(candidate / name)
        for attr in ("width", "height"):
            assert abs(float(a.get(attr)[:-2]) - float(b.get(attr)[:-2])) <= tolerance, (name, attr)
        assert len(paths_a) == len(paths_b), name
        max_error = 0.0
        for (attrs_a, rings_a), (attrs_b, rings_b) in zip(paths_a, paths_b, strict=True):
            assert {k: v for k, v in attrs_a.items() if k != "d"} == {
                k: v for k, v in attrs_b.items() if k != "d"
            }, name
            assert len(rings_a) == len(rings_b), name
            for (closed_a, ring_a), (closed_b, ring_b) in zip(rings_a, rings_b, strict=True):
                assert closed_a == closed_b and ring_a.is_simple == ring_b.is_simple, name
                if closed_a and attrs_a.get("fill", "black") != "none":
                    assert LinearRing(ring_a.coords).is_ccw == LinearRing(ring_b.coords).is_ccw, (
                        name
                    )
                error = ring_a.hausdorff_distance(ring_b)
                assert error <= tolerance, (name, error)
                max_error = max(max_error, error)
            if attrs_a.get("fill", "black") != "none":
                polygons_a = [Polygon(r.coords) for closed, r in rings_a if closed]
                polygons_b = [Polygon(r.coords) for closed, r in rings_b if closed]
                assert [[a.contains(b) for b in polygons_a] for a in polygons_a] == [
                    [a.contains(b) for b in polygons_b] for a in polygons_b
                ], name
        rows.append(
            {
                "file": name,
                "identical_bytes": digest(reference / name) == digest(candidate / name),
                "max_edge_difference_mm": max_error,
                "reference_nodes": sum(
                    len(r.coords) - int(closed) for _, rings in paths_a for closed, r in rings
                ),
                "candidate_nodes": sum(
                    len(r.coords) - int(closed) for _, rings in paths_b for closed, r in rings
                ),
            }
        )
    return {"status": "passed", "tolerance_mm": tolerance, "specimens": rows}


@contextmanager
def read_only_install(root, log_dir):
    """Real Windows deny-write ACL or Linux mode test, isolated to the extracted QA copy."""
    paths = [root, *root.rglob("*")]
    modes = {p: p.stat().st_mode for p in paths}
    sid = None
    try:
        if os.name == "nt":
            row = next(
                csv.reader(
                    [
                        subprocess.check_output(
                            ["whoami", "/user", "/fo", "csv", "/nh"], text=True
                        ).strip()
                    ]
                )
            )
            sid = row[-1]
            result = subprocess.run(
                ["icacls", str(root), "/deny", f"*{sid}:(OI)(CI)(W,D,DC)"],
                capture_output=True,
                text=True,
                check=True,
            )
            (log_dir / "readonly-acl.log").write_text(result.stdout, encoding="utf-8")
        else:
            for path in paths:
                path.chmod(modes[path] & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        probe = root / "write-must-fail.txt"
        try:
            probe.write_text("unexpected", encoding="utf-8")
        except PermissionError:
            pass
        else:
            raise RuntimeError("Read-only install probe unexpectedly allowed a write")
        yield "Windows deny-write ACL" if os.name == "nt" else "POSIX read-only modes"
    finally:
        if sid:
            restored = subprocess.run(
                ["icacls", str(root), "/remove:d", "*" + sid, "/T", "/C"],
                capture_output=True,
                text=True,
                check=True,
            )
            (log_dir / "restored-acl.log").write_text(restored.stdout, encoding="utf-8")
        elif os.name != "nt":
            for path in paths:
                path.chmod(modes[path])
        probe = root / "write-after-cleanup.txt"
        probe.write_text("restored", encoding="utf-8")
        probe.unlink()


def execute(binary, arguments, cwd, environment, log, timeout=300):
    with Path(log).open("w", encoding="utf-8") as handle:
        subprocess.run(
            [str(binary), *map(str, arguments)],
            cwd=cwd,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=True,
        )


def validate_extracted(extracted, output, source_pack):
    output.mkdir(parents=True)
    binary = extracted / ("WrapLab.exe" if os.name == "nt" else "WrapLab")
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "windows" if os.name == "nt" else "offscreen"
    env["XDG_CACHE_HOME"] = str(output / "cache")
    if os.name != "nt":
        env["XDG_DATA_HOME"] = str(output / "user data")
    env["TEMP"] = str(output / "temporary files")
    env["TMP"] = env["TEMP"]
    Path(env["TEMP"]).mkdir()
    denied_target = extracted / "denied-existing.svg"
    denied_target.write_text("preserve existing file", encoding="utf-8")
    before = inventory(extracted)
    destination = output / "Shop test שלום"
    pack = output / "Corel-Acceptance"
    with read_only_install(extracted, output) as permission_test:
        denied = subprocess.run(
            [
                str(binary),
                "convert",
                str(extracted / "_internal" / "acceptance-fixtures" / "lettering.svg"),
                str(denied_target),
                "--width",
                "30",
            ],
            cwd=output,
            env=env,
            capture_output=True,
            timeout=60,
        )
        assert (
            denied.returncode == 2
            and denied_target.read_text(encoding="utf-8") == "preserve existing file"
        )
        execute(binary, ["--self-test", destination], output, env, output / "packaged-launch.log")
        execute(
            binary,
            ["--self-test", destination, "--resume"],
            output,
            env,
            output / "packaged-restart.log",
        )
        execute(binary, ["--acceptance-pack", pack], output, env, output / "packaged-corel.log")
        assert inventory(extracted) == before, "Application wrote into installation tree"
    launch = json.loads((destination / "report.json").read_text(encoding="utf-8"))
    restart = json.loads((destination / "restart-report.json").read_text(encoding="utf-8"))
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert launch["packaged"] and restart["restart_verified"] and manifest["generator_packaged"]
    assert len(launch["exports"]) == 12 and len(manifest["specimens"]) == 14
    assert all(digest(pack / row["file"]) == row["sha256"] for row in manifest["specimens"])
    if os.name == "nt":
        assert launch["windows_packaged_verified"] and launch["qt_platform"] == "windows"
    comparison = compare_directories(source_pack, pack)
    report = {
        "status": "passed",
        "platform": platform.system(),
        "read_only_install": permission_test,
        "denied_export_preserved_existing_file": True,
        "extracted_archive_tested": True,
        "executable_sha256": digest(binary),
        "launch": launch,
        "restart": restart,
        "source_vs_packaged": comparison,
        "coreldraw_2019_verified": False,
        "physical_bell_verified": False,
    }
    (output / "release-validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report, pack


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    args.report.write_text(
        json.dumps(compare_directories(args.reference, args.candidate), indent=2) + "\n",
        encoding="utf-8",
    )
