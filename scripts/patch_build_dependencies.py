"""Documented Windows build patch: avoid an unused test-helper WMI architecture probe.

No numerical routines, native libraries, platform answers or runtime API functions are
modified. This changes how one NumPy test-support constant detects WebAssembly.
"""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

ORIGINAL = 'IS_WASM = platform.machine() in ["wasm32", "wasm64"]'
REPLACEMENT = 'IS_WASM = sys.platform in ("emscripten", "wasi")  # WrapLab build: no OS/CPU probe for WebAssembly detection.'
REVIEWED_ORIGINAL_SHA256 = "52b5a931fb20403e782b8eae8f4d1d015c753db97c2450abd3fc9bee6d6e6644"


def apply_patch():
    if sys.platform != "win32":
        return None
    distribution = importlib.metadata.distribution("numpy")
    if distribution.version != "2.2.6":
        raise ValueError("Review the documented NumPy test-helper patch before changing NumPy versions")
    path = Path(distribution.locate_file("numpy/testing/_private/utils.py"))
    content = path.read_bytes().decode("utf-8")
    if content.count(ORIGINAL) == 1 and REPLACEMENT not in content:
        original = content
        patched = content.replace(ORIGINAL, REPLACEMENT)
        if hashlib.sha256(original.encode("utf-8")).hexdigest() != REVIEWED_ORIGINAL_SHA256:
            raise ValueError("NumPy test helper does not match the independently reviewed source hash")
        path.write_bytes(patched.encode("utf-8"))
        # Discard only this build environment's stale test-helper bytecode cache.
        for cache in (path.parent / "__pycache__").glob("utils.*.pyc"):
            cache.unlink()
    elif content.count(REPLACEMENT) == 1 and ORIGINAL not in content:
        patched = content
        original = content.replace(REPLACEMENT, ORIGINAL)
        if hashlib.sha256(original.encode("utf-8")).hexdigest() != REVIEWED_ORIGINAL_SHA256:
            raise ValueError("Patched NumPy test helper contains unreviewed changes")
    else:
        raise ValueError("NumPy test-helper source differs from the reviewed one-line patch")
    record = {
        "id": "numpy-2.2.6-windows-testing-platform-1", "package": "numpy", "version": "2.2.6",
        "file": "numpy/testing/_private/utils.py", "original_line": ORIGINAL, "replacement_line": REPLACEMENT,
        "original_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "patched_sha256": hashlib.sha256(patched.encode("utf-8")).hexdigest(),
        "reason": "Avoid local WMI OS/CPU queries and their possible shell fallback during scientific-library import; WebAssembly is identified by sys.platform",
        "numerical_code_changed": False, "native_binaries_changed": False,
        "runtime_monkeypatch": False,
    }
    target = Path(__file__).resolve().parents[1] / "artifacts/dependency-patch.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


if __name__ == "__main__":
    print(json.dumps(apply_patch(), indent=2))
