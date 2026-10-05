import os
from pathlib import Path
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/wraplab-test-cache")

from PySide6.QtWidgets import QApplication, QMessageBox
import pytest

from wraplab.persistence import save_project
from wraplab.svg import convert, export_svg
from wraplab.ui.app import MainWindow, STYLE


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    return app


def wait_for_preview(app, window):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        app.processEvents()
        if not window._busy and not window._timer.isActive():
            return
        time.sleep(0.01)
    pytest.fail("Desktop preview did not complete")


def test_full_desktop_workflow_profile_presets_projects_and_export(app, tmp_path):
    window = MainWindow(tmp_path / "data")
    window.show()
    wait_for_preview(app, window)
    assert window.development.renderer.isValid()
    window.import_file(Path(__file__).parent / "fixtures" / "lettering.svg")
    wait_for_preview(app, window)
    assert window.export_button.isEnabled()
    assert window.front_view.renderer.isValid()
    assert window.original.renderer.isValid()
    assert window.notice.height() >= window.notice.minimumHeight()
    before = window.project.to_dict()
    for _ in range(50):
        window.units.setCurrentIndex(1)
        window.units.setCurrentIndex(0)
    assert window.project.to_dict() == before
    window.mode.setCurrentIndex(2)
    window.placement_fields["width"].setValue(25)
    window.center_artwork()
    window.preset_name.setText("Bell — Current Project")
    window.save_preset()
    assert window.presets.objects()["Bell — Current Project"].mode == "measured"
    save_project(tmp_path / "bell.wraplab", window.project)
    window.load_file(tmp_path / "bell.wraplab")
    wait_for_preview(app, window)
    result, text = window.export_to(tmp_path / "bell-compensated.svg")
    assert result.node_count > 20
    assert "Best-Fit / Experimental" in text
    assert "front-view-vinyl" in text
    window.development.fit()
    image = window.grab().toImage()
    assert not image.isNull() and image.width() >= 1050
    image.save(str(tmp_path / "workspace.png"))
    window.close()


def test_invalid_measurement_cannot_export_or_get_silently_replaced(app, tmp_path):
    window = MainWindow(tmp_path / "data")
    window.mode.setCurrentIndex(2)
    window.import_file(Path(__file__).parent / "fixtures" / "lettering.svg")
    wait_for_preview(app, window)
    window.table.item(1, 1).setText("not a number")
    assert not window.export_button.isEnabled()
    window.placement_fields["width"].setValue(20)
    wait_for_preview(app, window)
    assert window.table.item(1, 1).text() == "not a number"
    assert not window.export_button.isEnabled()
    with pytest.raises(ValueError, match="highlighted"):
        window.export_to(tmp_path / "invalid.svg")
    window.table.item(1, 1).setText("50.8")
    window.center_artwork()
    wait_for_preview(app, window)
    assert window.export_button.isEnabled()
    window.close()


def test_rapid_changes_cannot_export_stale_preview(app, tmp_path):
    window = MainWindow(tmp_path / "data")
    window.import_file(Path(__file__).parent / "fixtures" / "lettering.svg")
    wait_for_preview(app, window)
    for width in [20, 55, 30]:
        window.placement_fields["width"].setValue(width)
        app.processEvents()
    assert not window.export_button.isEnabled()
    result, text = window.export_to(tmp_path / "latest.svg")
    expected = convert(window.artwork, window.project)
    assert result.node_count == expected.node_count
    assert text == export_svg(expected, window.project, "artwork", window.project.source_name)
    wait_for_preview(app, window)
    assert window.export_button.isEnabled()
    window.close()


@pytest.mark.parametrize(
    "choice", [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard]
)
def test_unwritable_recovery_does_not_trap_exit_or_discard_silently(
    app, tmp_path, monkeypatch, choice
):
    window = MainWindow(tmp_path / "data")
    window.show()
    wait_for_preview(app, window)
    window.dirty = True

    def denied():
        raise PermissionError("Read-only user-data folder")

    monkeypatch.setattr(window, "_autosave", denied)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: choice)
    closed = window.close()
    assert closed == (choice == QMessageBox.StandardButton.Discard)
    assert window.dirty == (choice == QMessageBox.StandardButton.Cancel)
    window.dirty = False
    monkeypatch.setattr(window, "_autosave", lambda: None)
    window.close()
