"""Trusted tag-run publisher. Upload, download and verify before publishing a draft."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def gh(*args):
    return subprocess.check_output(["gh", *map(str, args)], text=True)


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    tag = os.environ["GITHUB_REF_NAME"]
    sha = os.environ["GITHUB_SHA"]
    repository = os.environ["GITHUB_REPOSITORY"]
    root = Path("release-downloads")
    outputs = []
    for listing in root.rglob("release-files.json"):
        for entry in json.loads(listing.read_text(encoding="utf-8")):
            path = listing.parent / entry["file"]
            assert path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"]
            outputs.append(path)
    assert len(outputs) == 6, "Both platforms must supply portable, Corel and validation artifacts"
    reports = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in outputs
        if p.name.endswith("validation.json")
    ]
    assert {r["platform"] for r in reports} == {"Linux", "Windows"}
    assert all(
        r["source_commit"] == sha and not r["source_dirty"] and r["status"] == "passed"
        for r in reports
    )
    assert (
        next(r for r in reports if r["platform"] == "Windows")["launch"]["qt_platform"] == "windows"
    )
    sums = Path("SHA256SUMS.txt")
    sums.write_text("".join(digest(p) + "  " + p.name + "\n" for p in outputs), encoding="utf-8")
    outputs.append(sums)
    comparison = Path("comparison-report.json")
    assert json.loads(comparison.read_text())["status"] == "passed"
    outputs.append(comparison)
    notes = Path("release-notes.md")
    notes.write_text(
        """Native Windows x64 portable release candidate for CorelDRAW 2019 acceptance testing.

Extract the entire portable ZIP and launch WrapLab.exe. Python is bundled. Keep _internal alongside the executable.
The application is unsigned; Windows may show a SmartScreen warning. Verify the checksum and origin and follow shop policy; do not disable Windows protections globally.

Native Windows tests, the Windows Qt platform, extracted read-only installation, Unicode/spaces/long paths, restart, twelve exports and fourteen packaged Corel specimens passed. See the validation JSON for exact OS/toolchain and evidence. The Linux/Windows semantic comparison passed.

CorelDRAW 2019 acceptance: PENDING. Measured Bell physical acceptance: PENDING.
Measured Profile remains Best-Fit / Experimental. Use real dimensions and an approved material trial before production.

Source commit: """
        + sha
        + "\n",
        encoding="utf-8",
    )
    # Do not overwrite an existing release or move a tag. gh exits on a conflicting release.
    gh(
        "release",
        "create",
        tag,
        "--repo",
        repository,
        "--verify-tag",
        "--draft",
        "--prerelease",
        "--title",
        "WrapLab 0.1.0 " + tag,
        "--notes-file",
        notes,
    )
    gh("release", "upload", tag, *outputs, "--repo", repository)
    with tempfile.TemporaryDirectory() as temp:
        gh("release", "download", tag, "--repo", repository, "--dir", temp)
        for path in outputs:
            assert digest(Path(temp) / path.name) == digest(path), path.name
    gh("release", "edit", tag, "--repo", repository, "--draft=false")
    data = json.loads(gh("api", f"repos/{repository}/releases/tags/{tag}"))
    report = {
        "status": "published",
        "source_commit": sha,
        "tag": tag,
        "release_url": data["html_url"],
        "assets": [
            {"name": a["name"], "bytes": a["size"], "url": a["browser_download_url"]}
            for a in data["assets"]
        ],
        "uploaded_assets_downloaded_and_hash_verified": True,
        "coreldraw_2019_verified": False,
        "physical_bell_verified": False,
    }
    Path("publication.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
