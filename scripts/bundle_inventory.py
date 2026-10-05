"""Read PE/bundle contents without executing them. Build/forensic tooling, never app code."""

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def provenance(path):
    lower = path.lower()
    for marker, purpose in [
        ("/pyside6/", "PySide6-Essentials 6.8.3: Qt GUI/SVG/platform/image plugins"),
        ("/shiboken6/", "shiboken6 6.8.3: Python/Qt binding runtime"),
        ("/numpy.libs/", "numpy 2.2.6: its OpenBLAS numerical runtime"),
        ("/numpy/", "numpy 2.2.6: numerical arrays/extensions"),
        ("/scipy.libs/", "scipy 1.15.3: its distinct OpenBLAS ABI/runtime"),
        ("/scipy/", "scipy 1.15.3: interpolation/integration/numerical extensions"),
        ("/shapely.libs/", "shapely 2.0.7: GEOS geometry runtime"),
        ("/shapely/", "shapely 2.0.7: topology/geometry bindings"),
    ]:
        if marker in lower:
            return purpose
    if lower.endswith("/wraplab.exe"):
        return "WrapLab + stock PyInstaller 6.12.0 Windows GUI bootloader"
    if "libssl-3-x64" in lower or "libcrypto-3-x64" in lower:
        return "Qt networking OpenSSL dependency; no application networking feature"
    if Path(path).suffix.lower() == ".pyd" or "python" in lower:
        return "Pinned CPython runtime/standard-library native extension"
    if any(x in lower for x in ["api-ms-win-", "ucrtbase", "vcruntime", "msvcp"]):
        return "Microsoft Windows API-set / Visual C++ / universal C runtime dependency"
    if any(x in lower for x in ["libssl", "libcrypto", "libffi"]):
        return "CPython standard-library SSL/hash/ctypes dependency"
    return "Unclassified: review required"


def pe_details(data):
    import pefile

    pe = pefile.PE(data=data)
    versions, manifests = {}, []
    for group in getattr(pe, "FileInfo", []):
        for block in group:
            for table in getattr(block, "StringTable", []):
                versions.update(
                    {k.decode(errors="replace"): v.decode(errors="replace") for k, v in table.entries.items()}
                )
    for typ in getattr(getattr(pe, "DIRECTORY_ENTRY_RESOURCE", None), "entries", []):
        if typ.id == 24:
            for ident in typ.directory.entries:
                for lang in ident.directory.entries:
                    d = lang.data.struct
                    manifests.append(pe.get_data(d.OffsetToData, d.Size).decode("utf-8", errors="replace"))
    return {
        "machine": hex(pe.FILE_HEADER.Machine),
        "subsystem": pe.OPTIONAL_HEADER.Subsystem,
        "pe_timestamp": pe.FILE_HEADER.TimeDateStamp,
        "certificate_table_bytes": pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size,
        "version": versions,
        "manifest": manifests,
        "icon_resource_present": any(
            e.id == 14 for e in getattr(getattr(pe, "DIRECTORY_ENTRY_RESOURCE", None), "entries", [])
        ),
        "sections": [
            {"name": s.Name.rstrip(b"\0").decode(errors="replace"), "entropy": round(s.get_entropy(), 3)}
            for s in pe.sections
        ],
        "imports": [x.dll.decode(errors="replace") for x in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])],
    }


def inspect_bundle(bundle):
    bundle = Path(bundle)
    if bundle.is_dir():
        files = ((str(p.relative_to(bundle)).replace("\\", "/"), p.read_bytes()) for p in sorted(bundle.rglob("*")) if p.is_file())
        archive = None
    else:
        archive = zipfile.ZipFile(bundle)
        files = ((f.filename, archive.read(f)) for f in archive.infolist() if not f.is_dir())
    rows, other = [], []
    try:
        for name, data in files:
            if Path(name).suffix.lower() in {".exe", ".dll", ".pyd"}:
                rows.append({"path": name, "bytes": len(data), "sha256": sha(data), "provenance": provenance("/" + name), **pe_details(data)})
            elif Path(name).suffix.lower() in {".py", ".ps1", ".bat", ".cmd", ".zip"}:
                other.append({"path": name, "bytes": len(data), "sha256": sha(data)})
    finally:
        if archive:
            archive.close()
    by_hash = collections.defaultdict(list)
    for row in rows:
        by_hash[row["sha256"]].append(row["path"])
    return {
        "source": str(bundle),
        "archive_sha256": sha(bundle.read_bytes()) if bundle.is_file() else None,
        "native_count": len(rows),
        "native_bytes": sum(r["bytes"] for r in rows),
        "native_files": rows,
        "exact_binary_duplicates": [v for v in by_hash.values() if len(v) > 1],
        "other_scripts_or_archives": other,
        "upx_section_markers": [r["path"] for r in rows if any("UPX" in s["name"].upper() for s in r["sections"])],
    }


def write_inventory(bundle, destination):
    destination = Path(destination)
    report = inspect_bundle(bundle)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with destination.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["path", "bytes", "sha256", "provenance", "machine", "subsystem", "certificate_table_bytes"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["native_files"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    report = write_inventory(args.bundle, args.destination)
    print(json.dumps({"native_count": report["native_count"], "native_bytes": report["native_bytes"]}))
