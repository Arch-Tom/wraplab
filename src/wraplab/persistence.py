"""Atomic local-only storage; object presets never contain artwork."""

import json
import os
from pathlib import Path
import secrets

from .domain import ObjectSpec, Project

MAX_PROJECT_BYTES = 12_000_000


def atomic_write(path: Path, text: str):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Windows os.access can report writable despite an ACL denial. tempfile.mkstemp
    # then retries PermissionError thousands of times. Retry name collisions only;
    # permission and storage errors must return promptly without touching the target.
    for _ in range(16):
        temporary = path.parent / (".wraplab-" + secrets.token_hex(16))
        try:
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
            )
        except FileExistsError:
            continue
        break
    else:
        raise FileExistsError("Could not create a unique temporary save file")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_project(path: Path, project: Project):
    project.validate(False)
    atomic_write(path, json.dumps(project.to_dict(), ensure_ascii=False, indent=2, allow_nan=False))


def load_project(path: Path):
    if Path(path).stat().st_size > MAX_PROJECT_BYTES:
        raise ValueError("Project exceeds the 12 MB limit.")
    try:
        return Project.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("Invalid project JSON.") from exc


class PresetStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def objects(self):
        if not self.path.exists():
            return {}
        if self.path.stat().st_size > 500_000:
            raise ValueError("Preset file is too large.")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1:
                raise ValueError("Unsupported preset version.")
            objects = {name: ObjectSpec(**item) for name, item in data["objects"].items()}
            for obj in objects.values():
                obj.surface()
            return objects
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            raise ValueError("Malformed preset file; existing data was preserved.") from exc

    def save(self, name: str, spec: ObjectSpec):
        from dataclasses import asdict

        name = name.strip()
        if not name or len(name) > 100:
            raise ValueError("Use a preset name of 1–100 characters.")
        spec.surface()
        objects = self.objects()
        objects[name] = ObjectSpec(**{**asdict(spec), "name": name})
        atomic_write(
            self.path,
            json.dumps(
                {
                    "schema_version": 1,
                    "units": "mm",
                    "objects": {k: asdict(v) for k, v in sorted(objects.items())},
                },
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            ),
        )
