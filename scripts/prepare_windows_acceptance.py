"""Checksummed source/specimen handoff; never claims to build a Windows executable."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def files(root):
    return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob("*"))
            if p.is_file() and p != root / "SHA256SUMS.txt"}


def write_checksums(root):
    (root / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p)}  {name}\n" for name, p in files(root).items()), encoding="utf-8"
    )


def verify(root):
    expected = {}
    for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        checksum, name = line.split("  ", 1)
        if name in expected:
            raise ValueError(f"Duplicate checksum entry: {name}")
        expected[name] = checksum
    actual = files(root)
    if set(expected) != set(actual):
        raise ValueError("Checksum inventory differs from handoff contents")
    for name, path in actual.items():
        if digest(path) != expected[name]:
            raise ValueError(f"Checksum mismatch: {name}")
    return len(actual)


def prepare(output):
    if git("status", "--porcelain"):
        raise ValueError("Commit or preserve outstanding changes before preparing a source handoff")
    if output.exists():
        raise ValueError("Choose a new output directory; existing handoffs are preserved")
    sha = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    if not branch:
        raise ValueError("Prepare the source bundle from a named integration branch")
    epoch = int(git("show", "-s", "--format=%ct", "HEAD"))
    output.mkdir(parents=True)
    kit = output / "WrapLab-Windows-Acceptance"
    kit.mkdir()
    bundle = kit / "Source.bundle"
    subprocess.run(["git", "bundle", "create", str(bundle), branch], cwd=ROOT, check=True)
    subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)
    from wraplab.acceptance import build

    specimens = build(kit / "Corel-Acceptance")
    for source, name in [
        ("docs/windows-acceptance-pilot.md", "README.md"),
        ("docs/bell-measurement.md", "Bell-measurement.md"),
        ("docs/integration-status.md", "Integration-status.md"),
    ]:
        shutil.copyfile(ROOT / source, kit / name)
    metadata = {
        "kind": "source-and-svg-acceptance-handoff", "version": 1,
        "source_commit": sha, "source_tree": git("rev-parse", "HEAD^{tree}"),
        "source_branch": branch, "source_epoch": epoch, "generator_python": sys.version,
        "generator_dependencies": {n: importlib.metadata.version(n) for n in
                                   ["numpy", "scipy", "shapely", "PySide6-Essentials"]},
        "native_windows_executable_included": False,
        "windows_build_python": "3.12.10", "pyinstaller": "6.12.0", "hooks": "2025.2",
        "build": "Windows x64 / stock onedir / windowed / no UPX / asInvoker",
        "specimens": len(specimens),
        "windows_current_commit_verified": False, "standard_user_verified": False,
        "sentinelone_verified": False, "coreldraw_2019_verified": False,
        "physical_material_verified": False,
        "missing_workflow_commit": "0004bae1c669e792bad7ee07da76e6c071bf2216",
    }
    (kit / "Handoff-manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    write_checksums(kit)
    verify(kit)
    archive = output / f"WrapLab-Windows-Acceptance-{sha[:12]}.zip"
    timestamp = datetime.fromtimestamp(epoch, timezone.utc).timetuple()[:6]
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        for path in sorted(kit.rglob("*")):
            if path.is_file():
                entry = zipfile.ZipInfo(path.relative_to(output).as_posix(), timestamp)
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                stream.writestr(entry, path.read_bytes())
    (output / "SHA256SUMS.txt").write_text(f"{digest(archive)}  {archive.name}\n")
    print(json.dumps({"archive": str(archive), "sha256": digest(archive), **metadata}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/windows-acceptance")
    parser.add_argument("--verify", type=Path, help="Verify an extracted handoff's entire inventory")
    args = parser.parse_args()
    if args.verify:
        print(f"Verified {verify(args.verify)} handoff files")
    else:
        prepare(args.output_root.resolve())
