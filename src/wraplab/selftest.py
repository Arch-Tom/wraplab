"""Functional acceptance of the actual running binary, including Qt and production export."""

import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import xml.etree.ElementTree as ET


def run(directory, resume=False):
    from PySide6.QtCore import QStandardPaths, qVersion
    from PySide6.QtWidgets import QApplication

    from .persistence import load_project, save_project
    from .ui.app import MainWindow, STYLE

    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setOrganizationName("WrapLab")
    app.setApplicationName("WrapLab")
    app.setStyleSheet(STYLE)
    standard_data = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    )
    # Probe the real Qt user-data location, isolating QA files from existing operator presets.
    data_dir = (
        standard_data
        / "Release-validation"
        / hashlib.sha256(str(destination.resolve()).encode()).hexdigest()[:12]
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    probe = data_dir / "write-probe.txt"
    probe.write_text("writable", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "writable"
    probe.unlink()
    if sys.platform == "win32" and app.platformName() != "windows":
        raise RuntimeError(
            "Windows release acceptance requires Qt's native windows platform plugin"
        )
    window = MainWindow(data_dir)
    window.show()
    source = destination / "self-test-source.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="30mm" height="12mm" viewBox="0 0 30 12"><path fill-rule="evenodd" d="M0 0H30V12H0Z M8 4H22V8H8Z"/></svg>',
        encoding="utf-8",
    )
    records = []
    try:
        if resume:
            prior = json.loads((destination / "report.json").read_text(encoding="utf-8"))
            assert prior["status"] == "passed"
            window.load_file(destination / "measured.wraplab")
            assert (
                window.project.to_dict() == load_project(destination / "measured.wraplab").to_dict()
            )
            stored = window.presets.objects()
            assert set(stored) == {"Object cylinder", "Object frustum", "Object measured"}
            assert stored["Object measured"].points == window.project.object.points
            preset_index = window.preset_combo.findText("Object measured")
            assert preset_index >= 0
            window.mode.setCurrentIndex(0)
            assert window.project.object.mode == "cylinder"
            window.preset_combo.setCurrentIndex(preset_index)
            window.preset_combo.activated.emit(preset_index)
            assert window.project.object.mode == "measured"
            assert window.project.object.name == "Object measured"
        window.import_file(source)
        for index, mode in enumerate(["cylinder", "frustum", "measured"]):
            window.mode.setCurrentIndex(index)
            window.project.object.mode = mode
            window.project.object.name = "Self-test " + mode + " (illustrative geometry)"
            window.project.placement.width, window.project.placement.height = 30, 12
            window.project.center_artwork()
            window._load_controls()
            window.refresh()
            deadline = time.monotonic() + 60
            while window._busy or window._timer.isActive():
                if time.monotonic() > deadline:
                    raise RuntimeError("Packaged preview timed out")
                app.processEvents()
                time.sleep(0.01)
            if not window.export_button.isEnabled() or not all(
                view.renderer.isValid()
                for view in [window.front_view, window.original, window.development]
            ):
                raise RuntimeError("Desktop preview failed: " + window.notice.text())
            for export_mode in ["artwork", "guides", "original", "template"]:
                target = destination / f"{mode}-{export_mode}.svg"
                result, text = window.export_to(target, export_mode)
                root = ET.fromstring(text)
                if not root.get("width").endswith("mm") or not root.findall(".//{*}path"):
                    raise RuntimeError("Invalid physical vector SVG output")
                if result and len(result.paths[0].contours) != 2:
                    raise RuntimeError("Counter lost in packaged conversion")
                viewbox = [float(v) for v in root.get("viewBox").split()]
                assert viewbox == [
                    0,
                    0,
                    float(root.get("width")[:-2]),
                    float(root.get("height")[:-2]),
                ]
                assert not root.findall(".//{*}image") and not root.findall(".//{*}text")
                assert result is None or result.node_count < 200_000
                if export_mode in {"artwork", "original"}:
                    assert all(p.get("d").endswith("Z") for p in root.findall(".//{*}path"))
                if mode == "cylinder" and export_mode == "artwork":
                    import math

                    expected = 80 * math.asin(30 / 80)
                    if abs(float(root.get("width")[:-2]) - expected) > 1e-5:
                        raise RuntimeError("Packaged cylinder physical width is incorrect")
                records.append(
                    {
                        "mode": mode,
                        "export": export_mode,
                        "width": root.get("width"),
                        "height": root.get("height"),
                        "nodes": result.node_count if result else None,
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    }
                )
            path = destination / f"{mode}.wraplab"
            save_project(path, window.project)
            window.load_file(path)
            window.preset_name.setText("Object " + mode)
            window.save_preset()
            assert window.presets.objects()["Object " + mode].mode == mode
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        try:
            window.export_to(source)
        except ValueError:
            pass
        else:
            raise RuntimeError("Source overwrite protection failed")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        saved_width = window.project.placement.width
        window.project.placement.width = 1e6
        try:
            window.project.validate()
        except ValueError:
            pass
        else:
            raise RuntimeError("Visible-edge rejection failed")
        finally:
            window.project.placement.width = saved_width
        long_dir = destination / "Unicode shop path שלום"
        while len(str(long_dir.resolve())) < 280:
            long_dir /= "long path segment 0123456789"
        long_dir.mkdir(parents=True, exist_ok=True)
        unicode_source = long_dir / "שלום artwork.svg"
        unicode_source.write_bytes(source.read_bytes())
        window.import_file(unicode_source)
        window.export_to(long_dir / "שלום compensated.svg")
        assert unicode_source.read_bytes() == source.read_bytes()
        window.load_file(destination / "measured.wraplab")
        deadline = time.monotonic() + 60
        while window._busy or window._timer.isActive():
            if time.monotonic() > deadline:
                raise RuntimeError("Final saved-project preview timed out")
            app.processEvents()
            time.sleep(0.01)
        # Async completion schedules layout changes; let the final diagnostics settle before capture.
        for _ in range(3):
            app.processEvents()
        assert window.grab().save(str(destination / "workspace.png"))
        report = {
            "status": "passed",
            "platform": platform.system(),
            "python": platform.python_version(),
            "os_version": platform.platform(),
            "architecture": platform.machine(),
            "qt_version": qVersion(),
            "qt_platform": app.platformName(),
            "executable": sys.executable,
            "standard_user_data": str(standard_data),
            "isolated_user_data": str(data_dir),
            "temporary_directory": os.environ.get("TEMP") or os.environ.get("TMPDIR"),
            "restart_verified": resume,
            "unicode_and_spaces_verified": True,
            "long_path_characters": len(str(unicode_source.resolve())),
            "source_preserved": True,
            "visible_edge_rejected": True,
            "packaged": bool(getattr(sys, "frozen", False)),
            "physical_model": "front-view-vinyl",
            "windows_packaged_verified": sys.platform == "win32"
            and bool(getattr(sys, "frozen", False))
            and app.platformName() == "windows",
            "coreldraw_2019_verified": False,
            "physical_vinyl_verified": False,
            "exports": records,
        }
        if resume:
            assert [r["sha256"] for r in prior["exports"]] == [r["sha256"] for r in records]
        (destination / ("restart-report.json" if resume else "report.json")).write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {"status": "passed", "packaged": report["packaged"], "exports": len(records)}
            )
        )
        return 0
    finally:
        window.close()
