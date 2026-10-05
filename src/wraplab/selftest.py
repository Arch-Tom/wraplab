"""Functional acceptance of the actual running binary, including Qt and production export."""

import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import xml.etree.ElementTree as ET


def run(directory):
    from PySide6.QtWidgets import QApplication

    from .persistence import PresetStore, save_project
    from .ui.app import MainWindow, STYLE

    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("WrapLab")
    app.setStyleSheet(STYLE)
    window = MainWindow(destination / "local-data")
    window.show()
    source = destination / "self-test-source.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="30mm" height="12mm" viewBox="0 0 30 12"><path fill-rule="evenodd" d="M0 0H30V12H0Z M8 4H22V8H8Z"/></svg>',
        encoding="utf-8",
    )
    records = []
    try:
        window.import_file(source)
        for mode in ["cylinder", "frustum", "measured"]:
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
            if not window.export_button.isEnabled() or not window.front_view.renderer.isValid():
                raise RuntimeError("Desktop preview failed: " + window.notice.text())
            for export_mode in ["artwork", "guides", "original", "template"]:
                target = destination / f"{mode}-{export_mode}.svg"
                result, text = window.export_to(target, export_mode)
                root = ET.fromstring(text)
                if not root.get("width").endswith("mm") or not root.findall(".//{*}path"):
                    raise RuntimeError("Invalid physical vector SVG output")
                if result and len(result.paths[0].contours) != 2:
                    raise RuntimeError("Counter lost in packaged conversion")
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
            PresetStore(destination / "self-test-presets.json").save(
                "Object " + mode, window.project.object
            )
        deadline = time.monotonic() + 60
        while window._busy or window._timer.isActive():
            if time.monotonic() > deadline:
                raise RuntimeError("Final saved-project preview timed out")
            app.processEvents()
            time.sleep(0.01)
        # Async completion schedules layout changes; let the final diagnostics settle before capture.
        for _ in range(3):
            app.processEvents()
        window.grab().save(str(destination / "workspace.png"))
        report = {
            "status": "passed",
            "platform": platform.system(),
            "python": platform.python_version(),
            "packaged": bool(getattr(sys, "frozen", False)),
            "physical_model": "front-view-vinyl",
            "windows_packaged_verified": sys.platform == "win32"
            and bool(getattr(sys, "frozen", False)),
            "coreldraw_2019_verified": False,
            "physical_vinyl_verified": False,
            "exports": records,
        }
        (destination / "report.json").write_text(
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
