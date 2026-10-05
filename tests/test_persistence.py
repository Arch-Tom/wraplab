import json
import math

import pytest

from wraplab.domain import Project
from wraplab.persistence import PresetStore, load_project, save_project


def test_denied_atomic_save_fails_promptly_and_preserves_existing_file(tmp_path, monkeypatch):
    from wraplab import persistence

    target = tmp_path / "existing.svg"
    target.write_bytes(b"original")
    attempts = []

    def denied_open(*args):
        attempts.append(args)
        raise PermissionError("ACL denies file creation")

    monkeypatch.setattr(persistence.os, "open", denied_open)
    with pytest.raises(PermissionError, match="ACL denies"):
        persistence.atomic_write(target, "replacement")
    assert len(attempts) == 1
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_save_retries_collision_without_modifying_other_file(tmp_path, monkeypatch):
    from wraplab import persistence

    occupied = tmp_path / ".wraplab-occupied"
    occupied.write_bytes(b"another save")
    names = iter(["occupied", "available"])
    monkeypatch.setattr(persistence.secrets, "token_hex", lambda _: next(names))
    target = tmp_path / "project.json"
    persistence.atomic_write(target, "new data\n")
    assert target.read_bytes() == b"new data\n"
    assert occupied.read_bytes() == b"another save"
    assert not (tmp_path / ".wraplab-available").exists()


def test_project_and_geometry_only_preset_roundtrip(tmp_path):
    project = Project(source_svg="<svg/>", source_name="customer.svg")
    project.object.mode = "measured"
    project.units = "in"
    path = tmp_path / "bell.wraplab"
    save_project(path, project)
    assert load_project(path).to_dict() == json.loads(json.dumps(project.to_dict()))
    store = PresetStore(tmp_path / "presets.json")
    store.save("Bell — Current Project", project.object)
    text = store.path.read_text()
    assert "customer" not in text and "<svg" not in text
    loaded = store.objects()["Bell — Current Project"]
    assert loaded.mode == "measured"
    assert loaded.surface().radius(0) == project.object.surface().radius(0)
    store.save("Bell — Current Project", loaded)
    assert store.path.read_text() == text


def test_unknown_versions_and_corrupt_presets_preserve_file(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text('{"schema_version":99,"objects":{}}')
    before = path.read_text()
    with pytest.raises(ValueError):
        PresetStore(path).save("x", Project().object)
    assert path.read_text() == before
    data = Project().to_dict()
    data["physical_model"] = "unknown"
    with pytest.raises(ValueError):
        Project.from_dict(data)


def test_raw_circumference_notes_and_uncertainty_preserved_without_artwork(tmp_path):
    project = Project(source_svg="customer geometry", source_name="customer.svg")
    project.object.mode = "measured"
    expected = project.object.surface()
    project.object.points = [(z, d * math.pi) for z, d in project.object.points]
    project.object.measurement_type = "circumference"
    project.object.measurement_uncertainty = 0.2
    project.object.notes = "Raw circumference, measured down from artwork-band top"
    store = PresetStore(tmp_path / "presets.json")
    store.save("Bell", project.object)
    loaded = store.objects()["Bell"]
    assert loaded.points == [list(p) for p in project.object.points]
    assert loaded.measurement_type == "circumference" and loaded.measurement_uncertainty == 0.2
    assert loaded.notes == project.object.notes
    for z, _ in loaded.points:
        assert loaded.surface().radius(z) == pytest.approx(expected.radius(z), abs=1e-12)
    assert "customer" not in store.path.read_text()
