from copy import deepcopy
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QFileDialog
import pytest
from svgpathtools import parse_path

from wraplab.domain import Project
from wraplab.persistence import load_project, save_project
from wraplab.svg import convert, export_svg
from wraplab.ui.app import MainWindow, STYLE

LETTERING = Path(__file__).parent / "fixtures/lettering.svg"


def canonical(project):
    # The established JSON format serializes point tuples as lists.
    return json.loads(json.dumps(project.to_dict()))


def settle(window):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if not window._busy and not window._timer.isActive():
            return
        time.sleep(0.01)
    pytest.fail("Source workflow preview timed out")


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    widget = MainWindow(tmp_path / "data")
    widget.show()
    settle(widget)
    yield widget
    widget.dirty = False
    widget.close()
    app.processEvents()


def test_empty_state_common_controls_and_export_remain_accessible(window):
    assert window.mode.itemText(0) == "Cylinder"
    assert window.mode.itemText(1) == "Tapered object"
    assert window.mode.itemText(2) == "Custom curved object"
    assert not window.advanced.toggle.isChecked()
    assert not window.export_options.toggle.isChecked()
    assert window.export_mode.currentData() == "artwork"
    assert window.import_button.isVisible()
    assert window.export_button.isVisible() and not window.export_button.isEnabled()
    assert not window.center_button.isEnabled()
    assert not window.placement_fields["width"].isEnabled()
    assert window.profile_view.isVisible() and window.development.isVisible()


def test_cylinder_job_preserves_reference_engine_output_units_and_counters(window, tmp_path):
    window.object_fields["diameter"].setValue(70)
    window.object_fields["height"].setValue(120)
    window.import_file(LETTERING)
    window.placement_fields["width"].setValue(40)
    window.center_artwork()
    settle(window)
    assert window.project.placement.height == pytest.approx(25 * 40 / 60)
    assert window.project.placement.x == 0
    assert window.project.placement.z == pytest.approx((120 - 25 * 40 / 60) / 2)
    assert window.front_view.isVisible() and window.development.isVisible()
    assert window.export_button.isEnabled()
    reference = Project()
    reference.object.diameter, reference.object.height = 70, 120
    reference.placement.width, reference.placement.height = 40, 25 * 40 / 60
    reference.center_artwork()
    result, text = window.export_to(tmp_path / "cut.svg")
    expected = convert(window.artwork, reference)
    assert result.node_count == expected.node_count
    expected_svg = ET.fromstring(export_svg(expected, reference, "artwork", LETTERING.name))
    svg = ET.fromstring(text)
    assert svg.attrib == expected_svg.attrib
    for actual_path, expected_path in zip(svg.findall(".//{*}path"), expected_svg.findall(".//{*}path"), strict=True):
        assert {k: v for k, v in actual_path.attrib.items() if k != "d"} == {
            k: v for k, v in expected_path.attrib.items() if k != "d"
        }
        assert actual_path.get("d").count("Z") == expected_path.get("d").count("Z")
        actual_segments, expected_segments = parse_path(actual_path.get("d")), parse_path(expected_path.get("d"))
        assert len(actual_segments) == len(expected_segments)
        # Import-fit arithmetic can move one six-decimal-mm serialization quantum (0.000001 mm).
        # Compare all serialized vertices; identical model inputs are tested byte-for-byte in native QA.
        assert max(abs(a.end - b.end) for a, b in zip(actual_segments, expected_segments, strict=True)) <= 1.5e-6
    assert svg.get("width").endswith("mm") and svg.get("height").endswith("mm")
    assert len(svg.findall(".//{*}path")) == 4
    assert not svg.findall(".//{*}g[@id='Guides']")
    before = window.project.to_dict()
    window.units.setCurrentIndex(1)
    assert window.object_fields["diameter"].value() == pytest.approx(70 / 25.4, abs=0.0001)
    window.units.setCurrentIndex(0)
    assert window.project.to_dict() == before
    assert window.export_to(tmp_path / "cut-mm.svg")[1] == text


@pytest.mark.parametrize("physical_model", ["front-view-vinyl", "surface-template"])
def test_taper_measurements_and_interpretation_preserve_engine_mapping(window, tmp_path, physical_model):
    window.mode.setCurrentIndex(1)
    window.object_fields["top_diameter"].setValue(65)
    window.object_fields["bottom_diameter"].setValue(90)
    window.object_fields["height"].setValue(100)
    window.import_file(LETTERING)
    window.placement_fields["width"].setValue(35)
    size = (window.project.placement.width, window.project.placement.height)
    window.workflow.setCurrentIndex(0 if physical_model == "front-view-vinyl" else 1)
    window.center_artwork()
    settle(window)
    assert (window.project.placement.width, window.project.placement.height) == size
    assert window.project.physical_model == physical_model
    reference = deepcopy(window.project)
    expected = convert(window.artwork, reference)
    assert window.export_to(tmp_path / "taper.svg")[1] == export_svg(expected, reference, "artwork", LETTERING.name)
    assert window.object_fields["top_diameter"].isVisible()
    assert window.object_fields["bottom_diameter"].isVisible()
    if physical_model == "surface-template":
        assert window.project.placement.x == pytest.approx((window.project.wrap_width() - size[0]) / 2)
        assert "centered" in window.statusBar().currentMessage()


def test_custom_object_keeps_experimental_warning_and_project_preset_round_trip(window, tmp_path):
    window.mode.setCurrentIndex(2)
    window.import_file(LETTERING)
    window.placement_fields["width"].setValue(25)
    window.center_artwork()
    settle(window)
    assert "Experimental" in window.badge.text()
    assert window.measurement_panel.isVisible()
    assert any("example points" in label.text().lower()
               for label in window.measurement_panel.findChildren(type(window.source_label)))
    window.preset_name.setText("Curved test object")
    window.save_preset()
    saved = tmp_path / "curved.wraplab"
    save_project(saved, window.project)
    previous = canonical(window.project)
    window.load_file(saved)
    assert canonical(window.project) == previous
    assert window.presets.objects()["Curved test object"].mode == "measured"
    assert "Best-Fit / Experimental" in window.export_to(tmp_path / "curved.svg")[1]


def test_invalid_measurement_and_source_overwrite_preserve_existing_destination(window, tmp_path):
    window.import_file(LETTERING)
    settle(window)
    target = tmp_path / "keep.svg"
    window.export_to(target)
    before = target.read_bytes()
    window.object_fields["diameter"].setValue(0)
    settle(window)
    assert not window.export_button.isEnabled()
    assert not window.development.isEnabled()
    assert "Previous preview" in window.flat_caption.text()
    assert "border" in window.object_fields["diameter"].styleSheet()
    with pytest.raises(ValueError):
        window.export_to(target)
    assert target.read_bytes() == before
    window.object_fields["diameter"].setValue(80)
    settle(window)
    with pytest.raises(ValueError, match="protect"):
        window.export_to(tmp_path / LETTERING.name)


def test_guide_options_are_explicit_and_success_reports_true_size(window, tmp_path, monkeypatch):
    window.import_file(LETTERING)
    settle(window)
    assert not window.export_warning.isVisible()
    window.export_mode.setCurrentIndex(1)
    settle(window)
    assert window.export_warning.isVisible()
    assert "Guides" in window.export_button.text()
    window.export_mode.setCurrentIndex(0)
    settle(window)
    target = tmp_path / "size-report.svg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    window.choose_export()
    svg = ET.fromstring(target.read_text())
    dimensions = f"{float(svg.get('width')[:-2]):.3f} × {float(svg.get('height')[:-2]):.3f} mm"
    assert dimensions in window.export_summary.text()
    assert str(target) in window.statusBar().currentMessage()


def test_new_job_preserves_recovery_and_resume_reopens_the_embedded_artwork(window):
    window.import_file(LETTERING)
    settle(window)
    prior = canonical(window.project)
    window.new_job()
    settle(window)
    assert window.artwork is None and not window.dirty
    assert canonical(load_project(window.data_dir / "Last-session.wraplab")) == prior
    assert window.actions["Resume last job"].isEnabled()
    window.resume_job()
    settle(window)
    assert canonical(window.project) == prior
    assert window.artwork is not None and window.export_button.isEnabled()


def test_wheel_scrolling_does_not_change_a_physical_measurement(window):
    spin = window.object_fields["diameter"]
    previous = spin.value()
    from PySide6.QtCore import QPoint
    event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(spin, event)
    assert spin.value() == previous


def test_secondary_export_choices_show_the_matching_preview(window, tmp_path):
    window.import_file(LETTERING)
    window.export_mode.setCurrentIndex(3)
    settle(window)
    assert window.flat_title.text() == "Uncompensated Comparison"
    preview = ET.fromstring(window.development.svg_text)
    exported = ET.fromstring(window.export_to(tmp_path / "uncompensated.svg")[1])
    assert preview.attrib == exported.attrib
    assert [p.get("fill-rule") for p in preview.findall(".//{*}path")] == [
        p.get("fill-rule") for p in exported.findall(".//{*}path")
    ]
    window.export_mode.setCurrentIndex(2)
    settle(window)
    assert window.flat_title.text() == "Full Surface Template"
    assert window.export_warning.isVisible()
    template = ET.fromstring(window.development.svg_text)
    assert not template.findall(".//{*}g[@id='Artwork']")


def test_unlocked_size_and_relocked_current_proportions_are_preserved(window):
    window.import_file(LETTERING)
    window.aspect.setChecked(False)
    window.placement_fields["height"].setValue(10)
    window.placement_fields["width"].setValue(30)
    assert window.project.placement.height == 10
    window.aspect.setChecked(True)
    window.placement_fields["width"].setValue(45)
    assert window.project.placement.height == 15
    settle(window)
    assert window.export_button.isEnabled()


def test_numeric_position_keeps_top_reference_through_unit_changes(window):
    window.import_file(LETTERING)
    window.placement_fields["width"].setValue(30)
    window.position_section.toggle.setChecked(True)
    window.placement_fields["x"].setValue(5)
    window.placement_fields["z"].setValue(10)
    assert window.project.placement.x == 5 and window.project.placement.z == 10
    before = canonical(window.project)
    window.units.setCurrentIndex(1)
    assert window.placement_fields["z"].value() == pytest.approx(10 / 25.4, abs=0.0001)
    window.units.setCurrentIndex(0)
    assert canonical(window.project) == before
    settle(window)
    assert window.export_button.isEnabled()


def test_new_job_does_not_discard_work_when_recovery_write_fails(window, monkeypatch):
    window.import_file(LETTERING)
    settle(window)
    previous = canonical(window.project)

    def denied():
        raise PermissionError("QA simulated recovery write denial")

    monkeypatch.setattr(window, "_autosave", denied)
    window.new_job()
    assert canonical(window.project) == previous
    assert window.artwork is not None and window.dirty
    assert "Save it before starting another" in window.notice.text()


def test_empty_curved_object_prompts_for_artwork_and_keeps_template_support_controls(window, tmp_path):
    window.mode.setCurrentIndex(2)
    settle(window)
    assert window.notice.objectName() != "Error"
    assert not window.export_button.isEnabled()
    assert "Import SVG" in window.result_label.text()
    window.export_mode.setCurrentIndex(2)
    window.placement_fields["width"].setValue(20)
    window.placement_fields["height"].setValue(10)
    window.center_artwork()
    settle(window)
    assert window.placement_fields["width"].isEnabled()
    assert not window.reset_button.isEnabled()
    assert window.export_button.isEnabled()
    assert window.export_to(tmp_path / "curved-template.svg")[0] is None
