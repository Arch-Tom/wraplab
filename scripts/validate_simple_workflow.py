"""Native source-only QA and exact engine comparison; never packages an executable."""

import argparse
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path, package=False):
    spec = importlib.util.spec_from_file_location(
        name, path, submodule_search_locations=[str(path.parent)] if package else None
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(output, reference_source, scale_factor=1.0):
    launcher = load_module("source_launcher", ROOT / "scripts/run_source.py")
    launcher.configure()
    if not 1 <= scale_factor <= 2:
        raise ValueError("QA display scale must be between 1 and 2")
    if scale_factor != 1:
        # QA-only process setting after isolation; no launcher or Windows policy change.
        os.environ["QT_SCALE_FACTOR"] = str(scale_factor)
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication

    from wraplab.persistence import load_project, save_project
    from wraplab.ui.app import MainWindow, STYLE

    load_module("wraplab_baseline", reference_source / "src/wraplab/__init__.py", True)
    baseline_domain = importlib.import_module("wraplab_baseline.domain")
    baseline_svg = importlib.import_module("wraplab_baseline.svg")
    output.mkdir(parents=True, exist_ok=False)
    app = QApplication.instance() or QApplication([])
    assert app.platformName() == "windows", "Native Windows QA requires the windows Qt plugin"
    app.setStyleSheet(STYLE)
    window = MainWindow(output / "user-data")
    window.show()

    def settle():
        deadline = time.monotonic() + 60
        while window._busy or window._timer.isActive():
            if time.monotonic() > deadline:
                raise RuntimeError("Source preview timed out")
            app.processEvents()
            time.sleep(0.01)
        for _ in range(4):
            app.processEvents()

    def screenshot(name, width=1370, height=900):
        window.resize(width, height)
        app.processEvents()
        settle()
        window.fit_views()
        app.processEvents()
        assert window.grab().save(str(output / (name + ".png")))
        button = window.export_button
        from PySide6.QtCore import QPoint
        bounds = button.rect().translated(button.mapTo(window, QPoint(0, 0)))
        assert window.rect().contains(bounds), "Primary export is clipped"
        assert window.development.transform().m11() == window.development.transform().m22()

    records = []
    try:
        settle()
        screenshot("empty")
        screenshot("empty-compact", 1050, 700)
        screenshot("empty-minimum", 980, 650)
        window.object_fields["diameter"].setValue(70)
        window.object_fields["height"].setValue(120)
        window.import_file(ROOT / "tests/fixtures/lettering.svg")
        # Historical engine comparisons use the historical page framing contract.
        window.artwork_frame.setCurrentIndex(window.artwork_frame.findData('page'))
        window.placement_fields["width"].setValue(40)
        window.center_artwork()
        settle()
        screenshot("cylinder")
        screenshot("cylinder-compact", 1050, 700)
        for name, mode, workflow in [
            ("cylinder", 0, 0), ("taper-front", 1, 0), ("taper-wrap", 1, 1), ("curved", 2, 0),
        ]:
            window.mode.setCurrentIndex(mode)
            window.workflow.setCurrentIndex(workflow)
            if mode == 1:
                window.object_fields["top_diameter"].setValue(65)
                window.object_fields["bottom_diameter"].setValue(90)
                window.object_fields["height"].setValue(100)
            if mode:
                window.import_file(ROOT / "tests/fixtures/lettering.svg")
                window.placement_fields["width"].setValue(25 if mode == 2 else 35)
            window.center_artwork()
            settle()
            assert window.export_button.isEnabled()
            assert window.development.renderer.isValid()
            if mode == 2:
                assert "Experimental" in window.badge.text()
            legacy_data = window.project.to_dict()
            legacy_data.pop('artwork_frame')
            legacy_data['schema_version'] = 1
            baseline = baseline_domain.Project.from_dict(legacy_data)
            artwork = baseline_svg.import_svg(window.project.source_svg)
            for export_mode in ["artwork", "guides", "template", "original"]:
                target = output / f"{name}-{export_mode}.svg"
                result, text = window.export_to(target, export_mode)
                previous = (baseline_svg.convert(artwork, baseline, original=export_mode == "original")
                            if export_mode != "template" else None)
                expected = baseline_svg.export_svg(previous, baseline, export_mode, window.project.source_name)
                svg = ET.fromstring(text)
                old_svg = ET.fromstring(expected)
                assert svg.attrib == old_svg.attrib, f"Baseline dimensions changed: {name}/{export_mode}"
                assert [p.attrib for p in svg.findall('.//{*}path')] == [
                    p.attrib for p in old_svg.findall('.//{*}path')
                ], f"Baseline vectors changed: {name}/{export_mode}"
                assert json.loads(svg.find('{*}metadata').text)['page_origin_mm'] == json.loads(
                    old_svg.find('{*}metadata').text)['page_origin_mm']
                assert svg.get("width").endswith("mm") and not svg.findall(".//{*}image")
                records.append({"scenario": name, "mode": export_mode,
                                "baseline_vectors_identical": True,
                                "baseline_metadata_changed": text != expected, "width": svg.get("width"),
                                "height": svg.get("height"), "nodes": result.node_count if result else None})
            path = output / f"{name}.wraplab"
            save_project(path, window.project)
            window.load_file(path)
            assert window.project.to_dict() == load_project(path).to_dict()
            window.preset_name.setText(name)
            window.save_preset()
            assert window.presets.objects()[name].mode == window.project.object.mode
            if mode:
                screenshot(name)
        window.object_fields["diameter"].setValue(0)
        window.mode.setCurrentIndex(0)
        settle()
        assert not window.export_button.isEnabled()
        screenshot("invalid-measurement")
        report = {
            "status": "passed", "python": sys.version.split()[0], "qt": qVersion(),
            "requested_qa_scale_factor": scale_factor, "device_pixel_ratio": app.primaryScreen().devicePixelRatio(),
            "qt_platform": app.platformName(), "packaged": False,
            "scenario_count": 4, "export_comparisons": records,
            "project_reload_and_presets": "passed", "empty_and_compact_layout": "passed",
            "invalid_measurement_blocks_export": True, "long_paths_tested": False,
            "physical_material_tested": False, "coreldraw_tested": False,
        }
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "export_comparisons"}, indent=2))
    finally:
        window.dirty = False
        window.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-source", type=Path, required=True)
    parser.add_argument("--scale-factor", type=float, default=1.0)
    args = parser.parse_args()
    run(args.output.resolve(), args.reference_source.resolve(), args.scale_factor)
