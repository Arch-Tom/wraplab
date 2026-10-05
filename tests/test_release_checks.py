"""Release comparison must reject material changes, even when bounds match."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from release_checks import compare_directories


@pytest.mark.parametrize("change", ["winding", "units", "geometry"])
def test_cross_platform_comparison_rejects_material_change(tmp_path, change):
    reference = tmp_path / "reference"
    reference.mkdir()
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" viewBox="0 0 10 10"><path fill="#000000" d="M0 0 L10 0 L10 10 L0 10 Z"/></svg>'
    (reference / "fixture.svg").write_text(source)
    (candidate / "fixture.svg").write_text(source.replace(" L", "\nL"))
    assert compare_directories(reference, candidate)["status"] == "passed"
    changed = source
    if change == "winding":
        changed = source.replace("M0 0 L10 0 L10 10 L0 10 Z", "M0 0 L0 10 L10 10 L10 0 Z")
    elif change == "units":
        changed = source.replace("10mm", "10in")
    else:
        changed = source.replace("L10 10", "L9 10")
    (candidate / "fixture.svg").write_text(changed)
    with pytest.raises(AssertionError):
        compare_directories(reference, candidate)
