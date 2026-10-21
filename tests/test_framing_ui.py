import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from PySide6.QtWidgets import QApplication
import pytest

from wraplab.ui.app import MainWindow


def settle(window):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if not window._busy and not window._timer.isActive():
            return
        time.sleep(0.01)
    pytest.fail("Framing UI preview did not complete")


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path / "data")
    yield window
    window.dirty = False
    window.close()
    app.processEvents()


def test_new_job_visible_sizing_switching_anchors_units_and_flat_dimensions(window, tmp_path):
    source = tmp_path / "margins.svg"
    source.write_text(
        '<svg width="100mm" height="80mm" viewBox="0 0 100 80">'
        '<rect x="20" y="10" width="60" height="40"/></svg>'
    )
    before = source.read_bytes()
    window.object_fields["diameter"].setValue(200)
    window.object_fields["height"].setValue(200)
    window.import_file(source)
    assert window.project.artwork_frame == "visible"
    assert "Source page: 100.000 × 80.000 mm" in window.source_label.text()
    assert "Visible artwork: 60.000 × 40.000 mm" in window.source_label.text()
    window.placement_fields["height"].setValue(20)
    assert window.project.placement.width == 30
    window.placement_fields["x"].setValue(3)
    window.placement_fields["z"].setValue(25)
    settle(window)
    assert window.export_button.isEnabled()
    assert "Flat artwork (preview):" in window.flat_dimensions.text()
    assert "Visible target height" == window.placement_labels["height"].text()
    saved = window.export_to(tmp_path / "visible.svg")[1]
    for index, width in [(1, 25), (0, 30)]:
        window.artwork_frame.setCurrentIndex(index)
        assert window.project.placement.width == width
        assert window.project.placement.height == 20
        assert (window.project.placement.x, window.project.placement.z) == (3, 25)
        settle(window)
        assert window.export_button.isEnabled()
    window.units.setCurrentIndex(1)
    settle(window)
    assert "Source page: 3.937 × 3.150 in" in window.source_label.text()
    window.units.setCurrentIndex(0)
    assert window.export_to(tmp_path / "units.svg")[1] == saved
    window.aspect.setChecked(False)
    window.placement_fields["width"].setValue(10)
    window.aspect.setChecked(True)
    assert window.project.placement.width == 10  # Keep the operator's edited ratio.
    window.artwork_frame.setCurrentIndex(1)
    window.artwork_frame.setCurrentIndex(0)
    assert window.project.placement.width == 30
    window.export_mode.setCurrentIndex(window.export_mode.findData("original"))
    settle(window)
    assert "Uncompensated artwork (preview): 30.000 × 20.000 mm" in window.flat_dimensions.text()
    assert source.read_bytes() == before


def test_legacy_ui_open_keeps_placement_frame_file_and_export_vectors(window, tmp_path):
    case = json.loads((Path(__file__).parent / "fixtures/legacy-page-projects.json").read_text())[
        "cases"
    ][2]
    path = tmp_path / "legacy.wraplab"
    path.write_text(json.dumps(case["project"]))
    before = path.read_bytes()
    window.load_file(path)
    settle(window)
    assert window.project.artwork_frame == "page"
    assert window.artwork_frame.currentData() == "page"
    assert vars(window.project.placement) == case["project"]["placement"]
    assert window.placement_labels["width"].text() == "Page target width"
    text = window.export_to(tmp_path / "legacy-export.svg")[1]
    assert [p.attrib for p in ET.fromstring(text).findall(".//{*}path")] == case["expected_paths"]
    assert path.read_bytes() == before


def test_unsupported_topology_is_reported_and_does_not_create_a_visible_frame(window, tmp_path):
    path = tmp_path / "crossing.svg"
    path.write_text(
        '<svg width="80mm" height="80mm" viewBox="0 0 80 80">'
        '<path d="M10 10L60 60L10 60L60 10Z"/></svg>'
    )
    window.import_file(path)
    assert window.project.artwork_frame == "page"
    assert "Visible bounds unavailable" in window.source_label.text()
    settle(window)
    assert not window.export_button.isEnabled()
    window.artwork_frame.setCurrentIndex(0)
    assert window.project.artwork_frame == "page"
    assert "Visible artwork bounds unavailable" in window.notice.text()
