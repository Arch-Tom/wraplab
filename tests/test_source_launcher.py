"""Reject foreign Python environments and inherited Qt/DLL search paths."""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "run_source", Path(__file__).resolve().parents[1] / "scripts/run_source.py"
)
run_source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_source)


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    environment = {
        "PATH": "unrelated-dll-directory", "QT_PLUGIN_PATH": "foreign-qt",
        "QT_QPA_PLATFORM": "offscreen", "QML_IMPORT_PATH": "foreign-qml",
        "SystemRoot": str(tmp_path / "Windows"), "KEEP_ME": "unchanged",
    }
    python = SimpleNamespace(
        platform="win32", version_info=(3, 12, 10), flags=SimpleNamespace(isolated=1),
        prefix=str(tmp_path / ".venv"), base_prefix=str(tmp_path / "Python312"), path=[],
    )
    monkeypatch.setattr(run_source, "ROOT", tmp_path)
    monkeypatch.setattr(run_source, "sys", python)
    monkeypatch.setattr(run_source, "os", SimpleNamespace(environ=environment, pathsep=os.pathsep))
    return python, environment, tmp_path


def test_source_launcher_excludes_foreign_dll_and_qt_paths(runtime):
    python, environment, root = runtime
    run_source.configure()
    assert environment["PATH"].split(os.pathsep) == [
        str(root / ".venv/Scripts"), str(root / "Python312"), str(root / "Python312/DLLs"),
        str(root / "Windows/System32"), str(root / "Windows"),
    ]
    assert environment["QT_PLUGIN_PATH"] == str(root / ".venv/Lib/site-packages/PySide6/plugins")
    assert environment["QT_QPA_PLATFORM_PLUGIN_PATH"] == str(
        root / ".venv/Lib/site-packages/PySide6/plugins/platforms"
    )
    assert environment["QT_QPA_PLATFORM"] == "windows"
    assert "QML_IMPORT_PATH" not in environment
    assert environment["KEEP_ME"] == "unchanged"
    assert python.path == [str(root / "src")]


@pytest.mark.parametrize("field,value", [
    ("platform", "linux"), ("version_info", (3, 12, 9)),
    ("flags", SimpleNamespace(isolated=0)), ("prefix", "foreign-environment"),
])
def test_source_launcher_rejects_unisolated_or_foreign_runtime(runtime, field, value):
    python, environment, _ = runtime
    original = environment.copy()
    setattr(python, field, value)
    with pytest.raises(RuntimeError):
        run_source.configure()
    assert environment == original
