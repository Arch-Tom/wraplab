"""Corrupt or incomplete handoffs must not pass checksum verification."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_windows_acceptance import verify, write_checksums


def test_handoff_rejects_corrupted_specimen(tmp_path):
    specimen = tmp_path / "specimen.svg"
    specimen.write_text("approved geometry")
    write_checksums(tmp_path)
    assert verify(tmp_path) == 1
    specimen.write_text("changed geometry")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        verify(tmp_path)


def test_handoff_rejects_incomplete_inventory(tmp_path):
    (tmp_path / "Source.bundle").write_bytes(b"source")
    write_checksums(tmp_path)
    (tmp_path / "unlisted.svg").write_bytes(b"<svg/>")
    with pytest.raises(ValueError, match="inventory differs"):
        verify(tmp_path)
