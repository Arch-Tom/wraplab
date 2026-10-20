"""One workspace; all compensation/export decisions live in non-UI modules."""

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from PySide6.QtCore import (
    QObject,
    QRect,
    QRunnable,
    QStandardPaths,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QTableWidgetItem,
)

from .. import __version__
from ..domain import ObjectSpec, Project
from ..geometry.units import Unit
from ..persistence import PresetStore, load_project, save_project
from ..svg import convert, export_svg, import_svg
from ..svg.exporter import ideal_front_svg, write_export
from .workspace import MeasurementSpinBox, build_workspace

MODES = [
    ("Cylinder — Exact", "cylinder"),
    ("Straight Taper — Exact", "frustum"),
    ("Measured Profile — Best-Fit / Experimental", "measured"),
]
STYLE = """
QMainWindow { background: #f3f6f8; }
QWidget { font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 13px; color: #203544; }
QToolBar { background: #192f40; padding: 9px; border: 0; spacing: 10px; }
QToolBar QLabel { color: white; font-size: 19px; font-weight: 600; padding-right: 16px; }
QToolBar QToolButton { color: #e3edf3; padding: 7px 9px; border-radius: 4px; }
QToolBar QToolButton:hover { background: #2f4c60; }
QToolBar QToolButton:disabled { color: #8295a0; }
QToolButton#Disclosure { color: #315367; padding: 5px 0; font-weight: 600; border: 0; }
QToolButton#Disclosure:disabled { color: #86969f; }
QLabel#Help { color: #526775; font-size: 12px; }
QLabel#Section { font-size: 14px; }
QLabel#WorkspaceTitle { font-size: 16px; font-weight: 600; }
QLabel#PreviewTitle { font-size: 15px; font-weight: 600; }
QFrame#PreviewPanel { background: white; border: 1px solid #dbe4e9; border-radius: 6px; }
QFrame#ExportFooter { background: white; border-top: 1px solid #dbe4e9; }
QLabel#GuideWarning { color: #916125; }
QPushButton#Import { background: #e0f3eb; border: 1px solid #bcded1; color: #13775b; font-weight: 600; }
QFrame#Panel { background: white; border-right: 1px solid #dbe4e9; }
QLabel#Section { font-weight: 600; color: #527083; padding-top: 12px; }
QLabel#Badge { background: #e0f3eb; color: #13775b; padding: 7px; border-radius: 4px; font-weight: 600; }
QLabel#Experimental { background: #fff1d7; color: #916125; padding: 7px; border-radius: 4px; font-weight: 600; }
QLabel#Notice { padding: 8px; background: #e8eff3; color: #425f70; border-radius: 4px; }
QLabel#Error { padding: 8px; background: #fff0e9; color: #9e4325; border-radius: 4px; }
QPushButton { padding: 7px 10px; background: #edf3f6; border: 1px solid #d7e2e8; border-radius: 4px; }
QPushButton:hover { background: #dfeaf0; }
QPushButton#Primary { background: #128467; color: white; border: 0; font-weight: 600; padding: 10px; }
QPushButton#Primary:disabled { background: #a1b8b0; }
QLineEdit, QDoubleSpinBox, QComboBox { padding: 5px; border: 1px solid #cddae1; border-radius: 3px; background: white; }
QTableWidget { border: 1px solid #dbe4e9; background: white; gridline-color: #e5ecf0; }
QHeaderView::section { background: #edf3f6; border: 0; padding: 6px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 10px 16px; background: #e7eef2; }
QTabBar::tab:selected { background: white; color: #128467; }
QStatusBar { background: white; border-top: 1px solid #dbe4e9; }
"""


class NoticeLabel(QLabel):
    """Reserve enough height for warnings when async text or available width changes."""

    def setText(self, text):
        super().setText(text)
        self._fit_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()

    def _fit_height(self):
        rect = QRect(0, 0, max(160, self.width() - 24), 10000)
        height = (
            self.fontMetrics().boundingRect(rect, Qt.TextFlag.TextWordWrap, self.text()).height()
        )
        self.setMinimumHeight(height + 24)


class JobSignals(QObject):
    finished = Signal(int, object, object)


class PreviewJob(QRunnable):
    def __init__(self, generation, artwork, project, export_mode="artwork"):
        super().__init__()
        self.generation, self.artwork, self.project = generation, artwork, project
        self.export_mode = export_mode
        self.signals = JobSignals()

    def run(self):
        try:
            if self.artwork:
                result = convert(self.artwork, self.project, preview=True)
                text = export_svg(result, self.project, "guides", self.project.source_name)
                original = convert(self.artwork, self.project, preview=True, original=True)
                original_text = export_svg(
                    original, self.project, "original", self.project.source_name
                )
                if self.export_mode == "original":
                    text = original_text
                elif self.export_mode == "template":
                    text = export_svg(None, self.project, "template")
                front = (
                    ideal_front_svg(self.artwork, self.project)
                    if self.project.physical_model == "front-view-vinyl"
                    else None
                )
                payload = (result, text, original_text, front)
            else:
                text = (None if self.project.object.mode == "measured" and self.export_mode != "template"
                        else export_svg(None, self.project, "template"))
                payload = (None, text, None, None)
            self.signals.finished.emit(self.generation, payload, None)
        except Exception as exc:
            self.signals.finished.emit(self.generation, None, str(exc))


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path | None = None):
        super().__init__()
        self.setWindowTitle(f"WrapLab {__version__} · Simple workflow")
        self.resize(1370, 900)
        self.setMinimumSize(980, 650)
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.resize(min(1370, max(980, available.width() - 40)),
                        min(900, max(650, available.height() - 70)))
        self.setAcceptDrops(True)
        self.project = Project()
        self.artwork = None
        self.source_path = None
        self.project_path = None
        self.dirty = False
        self.data_dir = data_dir or Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        )
        self.presets = PresetStore(self.data_dir / "objects.json")
        self._loading = True  # widget construction must never mutate the domain defaults
        self._invalid_cells = set()
        self._generation = 0
        self._busy = False
        self._job = None
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._start_preview)
        self._build()
        self._load_controls()
        self._load_presets()
        self.refresh()

    @property
    def unit(self):
        return Unit(self.project.units)

    def _build(self):
        build_workspace(self, NoticeLabel)

    def _spin(self, name, callback, unit=True):
        spin = MeasurementSpinBox()
        spin.setObjectName(name)
        spin.setDecimals(4)
        spin.setRange(0.0001, 1_000_000)
        spin.setSingleStep(1)
        spin.setKeyboardTracking(False)
        spin.setMinimumWidth(105)
        spin.setMaximumWidth(155)
        spin.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        if unit:
            spin.setSuffix(" mm")
        spin.valueChanged.connect(callback)
        return spin

    def new_job(self):
        try:
            self._autosave()
        except (ValueError, OSError) as exc:
            self.error("The current job could not be preserved. Save it before starting another. " + str(exc))
            return
        self.project = Project()
        self.artwork = self.source_path = self.project_path = None
        self._invalid_cells.clear()
        self.dirty = False
        self.source_label.setText("Choose your object, enter its measurements, then import an SVG.")
        self._load_controls()
        self.refresh()

    def resume_job(self):
        try:
            self.load_file(self.data_dir / "Last-session.wraplab")
        except (ValueError, OSError) as exc:
            self.error("The last job could not be opened. Choose Open project to recover another copy. " + str(exc))

    def _sync_presentation(self):
        imported = bool(self.artwork)
        editable_support = imported or self.export_mode.currentData() == "template"
        front = self.project.physical_model == "front-view-vinyl"
        for spin in self.placement_fields.values():
            spin.setEnabled(editable_support)
        for control in [self.aspect, self.center_button]:
            control.setEnabled(editable_support)
        self.reset_button.setEnabled(imported)
        self.original_section.toggle.setEnabled(imported)
        self.position_section.toggle.setEnabled(editable_support)
        self.advanced.toggle.setText("Advanced · " + self.workflow.currentText())
        self.object_preview_stack.setCurrentIndex(0 if imported and front else 1)
        self.front_caption.setText(
            "Front-view target · upright object · 2D preview"
            if imported and front else "Object profile (schematic) · TOP is height 0"
        )
        selected_export = self.export_mode.currentData()
        self.flat_title.setText("Uncompensated Comparison" if selected_export == "original" else
                                "Full Surface Template" if selected_export == "template" else "Flat Cutting Pattern")
        self.flat_caption.setText({
            "artwork": "Compensated artwork · reference lines are not exported",
            "guides": "Artwork and guides · guide paths may cut",
            "original": "Uncompensated comparison · no curvature correction",
            "template": "Full surface template · guide paths may cut",
        }[selected_export] if imported or selected_export == "template" else
            "Reference area · import artwork to see the cutting pattern")
        self.workflow_help.setText(
            "Match the design you want to see from the front. Width is the visible artwork width."
            if front else "Wrap around the surface. Width and horizontal position are surface distances."
        )
        self.horizontal_label.setText("Horizontal offset" if front else "Distance from seam")
        self.placement_fields["x"].setToolTip(
            "Offset from the front center; zero is centered." if front else
            "Surface distance from the left seam at mid-height; Center places artwork within the wrap."
        )
        self.next_step.setText(
            "Position → Compare previews → Export" if imported else "Measure your object → Import SVG"
        )
        mode = self.export_mode.currentData()
        self.export_warning.setVisible(mode in {"guides", "template"})
        self.export_button.setText({
            "artwork": "Export Compensated SVG…", "guides": "Export SVG with Guides…",
            "template": "Export Surface Template…", "original": "Export Uncompensated SVG…",
        }[mode])
        self.actions["Export SVG"].setEnabled(self.export_button.isEnabled())
        self.actions["Resume last job"].setEnabled((self.data_dir / "Last-session.wraplab").is_file())
        self.export_summary.setText("SVG in millimeters · artwork only" if imported and mode == "artwork"
                                    else "Import artwork to begin." if not imported and mode != "template"
                                    else "SVG in millimeters · " + self.export_mode.currentText())
        for spin in self.object_fields.values():
            spin.setStyleSheet("border:1px solid #bc5940;" if spin.value() <= 0 else "")

    def _load_controls(self):
        self._loading = True
        self.mode.setCurrentIndex([value for _, value in MODES].index(self.project.object.mode))
        self.workflow.setCurrentIndex(0 if self.project.physical_model == "front-view-vinyl" else 1)
        self.units.setCurrentIndex(0 if self.project.units == "mm" else 1)
        for key, spin in self.object_fields.items():
            spin.setSuffix(" " + self.project.units)
            spin.setValue(self.unit.from_mm(getattr(self.project.object, key)))
        for key, spin in self.placement_fields.items():
            spin.setSuffix(" " + self.project.units)
            spin.setValue(self.unit.from_mm(getattr(self.project.placement, key)))
        self.aspect.setChecked(self.project.placement.lock_aspect)
        self.coverage.setValue(self.project.wrap_degrees)
        self.rotation.setValue(self.project.rotation_degrees)
        self.tolerance.setValue(self.project.export_tolerance_mm)
        self.preset_name.setText(self.project.object.name)
        self.notes.setText(self.project.object.notes)
        self.uncertainty.setSuffix(" " + self.project.units)
        self.uncertainty.setValue(
            self.unit.from_mm(self.project.object.measurement_uncertainty or 0)
        )
        self.measurement_type.setCurrentIndex(
            0 if self.project.object.measurement_type == "diameter" else 1
        )
        self._fill_table()
        self._loading = False
        self._show_mode()

    def _fill_table(self):
        if self._invalid_cells:
            return
        blocked = self.table.blockSignals(True)
        self.table.setHorizontalHeaderLabels(
            [
                "Height (" + self.project.units + ")",
                ("Diameter" if self.project.object.measurement_type == "diameter" else "Circumf.")
                + " ("
                + self.project.units
                + ")",
            ]
        )
        self.table.setRowCount(len(self.project.object.points))
        for row, point in enumerate(self.project.object.points):
            for column, value in enumerate(point):
                self.table.setItem(row, column, QTableWidgetItem(f"{self.unit.from_mm(value):.4f}"))
        self.table.blockSignals(blocked)

    def _show_mode(self):
        mode = self.project.object.mode
        for key, spin in self.object_fields.items():
            visible = (
                (key == "diameter" and mode == "cylinder")
                or (key in {"top_diameter", "bottom_diameter"} and mode == "frustum")
                or (key == "height" and mode != "measured")
            )
            spin.setVisible(visible)
            self.object_rows[key].setVisible(visible)
        self.measurement_panel.setVisible(mode == "measured")
        self.badge.setText("Best-Fit / Experimental" if mode == "measured" else
                           "Exact for a cylinder" if mode == "cylinder" else "Exact for a straight taper")
        self.measurement_help.setText({
            "cylinder": "Measure diameter across the object and height straight down from its top.",
            "frustum": "Measure the top and bottom diameters, then the straight vertical height between them.",
            "measured": "Measure stations down from TOP. Curved surfaces may need stretch or cuts; test material first.",
        }[mode])
        self.badge.setObjectName("Experimental" if mode == "measured" else "Badge")
        self.badge.setStyleSheet(
            "background:#fff1d7;color:#916125;"
            if mode == "measured"
            else "background:#e0f3eb;color:#13775b;"
        )
        if mode == "measured":
            self.badge.setToolTip(
                "A curved rotational surface generally cannot be flattened without distortion. This template is experimental."
            )
        self._sync_presentation()

    def _changed(self):
        if self._loading:
            return
        self.dirty = True
        self.refresh()

    def mode_changed(self, index):
        if self._loading:
            return
        self.project.object.mode = self.mode.itemData(index)
        self._show_mode()
        self._changed()

    def workflow_changed(self, index):
        if not self._loading:
            self.project.physical_model = self.workflow.itemData(index)
            self.project.center_artwork()
            self._load_controls()
            self._changed()
            self.statusBar().showMessage(
                "Artwork size kept; placement centered for " + self.workflow.currentText().lower()
                + ". Horizontal placement now uses "
                + ("front-center offset." if index == 0 else "surface distance from the seam.")
            )

    def units_changed(self, index):
        if self._loading:
            return
        if self._invalid_cells:
            self._loading = True
            self.units.setCurrentIndex(0 if self.project.units == "mm" else 1)
            self._loading = False
            self.error("Correct the highlighted measurement before changing units.")
            return
        self.project.units = self.units.itemData(index)
        self._load_controls()  # display only; never reread rounded fields into model
        self._changed()

    def object_changed(self, key, value):
        if not self._loading:
            setattr(self.project.object, key, self.unit.to_mm(value))
            self._changed()

    def placement_changed(self, key, value):
        if self._loading:
            return
        placement = self.project.placement
        value = self.unit.to_mm(value)
        if placement.lock_aspect and key in {"width", "height"}:
            other = "height" if key == "width" else "width"
            setattr(placement, other, getattr(placement, other) * value / getattr(placement, key))
        setattr(placement, key, value)
        self._load_controls()
        self._changed()

    def aspect_changed(self, value):
        if not self._loading:
            self.project.placement.lock_aspect = value
            self._changed()

    def coverage_changed(self, value):
        if not self._loading:
            self.project.wrap_degrees = value
            self._changed()

    def rotation_changed(self, value):
        if not self._loading:
            self.project.rotation_degrees = value
            self._changed()

    def tolerance_changed(self, value):
        if not self._loading:
            self.project.export_tolerance_mm = value
            self._changed()

    def point_changed(self, row, column):
        if self._loading:
            return
        try:
            value = self.unit.to_mm(self.table.item(row, column).text())
            pair = list(self.project.object.points[row])
            pair[column] = value
            self.project.object.points[row] = tuple(pair)
            self._invalid_cells.discard((row, column))
            self.table.item(row, column).setBackground(Qt.GlobalColor.white)
            self._changed()
        except ValueError as exc:
            self._invalid_cells.add((row, column))
            from PySide6.QtGui import QColor

            self.table.item(row, column).setBackground(QColor("#ffe3d3"))
            self._timer.stop()
            self._generation += 1
            self.error(str(exc))

    def add_point(self):
        if self._invalid_cells:
            self.error("Correct the highlighted measurement first.")
            return
        if len(self.project.object.points) >= 30:
            self.error("The profile supports up to 30 measurements.")
            return
        points = self.project.object.points
        points.append(
            (points[-1][0] + self.unit.to_mm(0.25 if self.unit == Unit.INCH else 5), points[-1][1])
        )
        self._fill_table()
        self.table.selectRow(len(points) - 1)
        self._changed()

    def remove_point(self):
        if self._invalid_cells:
            self.error("Correct the highlighted measurement first.")
            return
        row = self.table.currentRow()
        if len(self.project.object.points) <= 3:
            self.error("Keep at least three measured points.")
        elif row >= 0:
            del self.project.object.points[row]
            self._fill_table()
            self._changed()

    def sort_points(self):
        if self._invalid_cells:
            self.error("Correct the highlighted measurement first.")
            return
        self.project.object.points.sort(key=lambda point: point[0])
        self._fill_table()
        self._changed()

    def center_artwork(self):
        try:
            self.project.center_artwork()
            self._load_controls()
            self._changed()
        except ValueError as exc:
            self.error(str(exc))

    def reset_artwork(self):
        if self.artwork:
            self.project.placement.width = self.artwork.width_mm
            self.project.placement.height = self.artwork.height_mm
            self.center_artwork()

    def name_changed(self):
        if not self._loading and self.preset_name.text().strip():
            self.project.object.name = self.preset_name.text().strip()
            self._changed()

    def measurement_type_changed(self, index):
        if self._loading:
            return
        if self._invalid_cells:
            self._loading = True
            self.measurement_type.setCurrentIndex(
                0 if self.project.object.measurement_type == "diameter" else 1
            )
            self._loading = False
            self.error("Correct the highlighted measurement first.")
            return
        import math

        new = self.measurement_type.itemData(index)
        factor = math.pi if new == "circumference" else 1 / math.pi
        self.project.object.points = [
            (z, value * factor) for z, value in self.project.object.points
        ]
        if self.project.object.measurement_uncertainty:
            self.project.object.measurement_uncertainty *= factor
        self.project.object.measurement_type = new
        self._load_controls()
        self._changed()

    def notes_changed(self):
        if not self._loading:
            self.project.object.notes = self.notes.text()
            self._changed()

    def uncertainty_changed(self, value):
        if not self._loading:
            self.project.object.measurement_uncertainty = self.unit.to_mm(value) if value else None
            self._changed()

    def import_file(self, path):
        self._assert_inputs()
        path = Path(path)
        if path.stat().st_size > 10_000_000:
            raise ValueError("SVG exceeds the 10 MB import limit.")
        artwork = import_svg(path.read_text(encoding="utf-8-sig"))
        surface = self.project.validate(False)
        available = self.project.wrap_width()
        if self.project.physical_model == "front-view-vinyl":
            zs = [surface.height * (i / 100) for i in range(100)] + [surface.height]
            radii = [surface.radius(z) for z in zs]
            import math

            limit = min(
                self.project.front_margin,
                math.sin(min(math.pi / 2, math.radians(self.project.wrap_degrees) / 2)),
            )
            available = 2 * min(radii) * limit
        scale = min(
            1, 0.85 * available / artwork.width_mm, 0.85 * surface.height / artwork.height_mm
        )
        self.project.source_svg = artwork.source
        self.project.source_name = path.name
        self.artwork = artwork
        self.source_path = path.resolve()
        self.project.placement.width = artwork.width_mm * scale
        self.project.placement.height = artwork.height_mm * scale
        self.project.center_artwork()
        self._load_controls()
        self.source_label.setText(
            f"{path.name}\nOriginal page: {self.unit.from_mm(artwork.width_mm):.3f} × {self.unit.from_mm(artwork.height_mm):.3f} {self.project.units}"
            + ("\nSized to fit the object; adjust below." if scale < 1 else "")
        )
        self._changed()

    def choose_svg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import vector artwork", "", "SVG files (*.svg)"
        )
        if path:
            try:
                self.import_file(path)
            except (ValueError, OSError, UnicodeError) as exc:
                self.error(str(exc))

    def load_file(self, path):
        project = load_project(Path(path))
        artwork = import_svg(project.source_svg) if project.source_svg else None
        self._autosave()
        self.project, self.artwork = project, artwork
        self._invalid_cells.clear()
        self.project_path, self.source_path = Path(path), None
        self.dirty = False
        self._load_controls()
        self.source_label.setText(
            project.source_name or "Drop a path-based SVG here, or use Import SVG."
        )
        self.refresh()

    def choose_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open project", str(self.data_dir), "WrapLab projects (*.wraplab)"
        )
        if path:
            try:
                self.load_file(path)
            except (ValueError, OSError) as exc:
                self.error(str(exc))

    def choose_save_project(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save project",
            str(self.project_path or self.data_dir / "Untitled.wraplab"),
            "WrapLab projects (*.wraplab)",
        )
        if path:
            try:
                self._assert_inputs()
                path = Path(path)
                if path.suffix.lower() != ".wraplab":
                    path = path.with_suffix(".wraplab")
                save_project(path, self.project)
                self.project_path = path
                self.dirty = False
                self.statusBar().showMessage("Project saved with embedded source artwork.")
            except (ValueError, OSError) as exc:
                self.error(str(exc))

    def _load_presets(self):
        self.preset_combo.clear()
        self.preset_combo.addItem("Choose a saved object…", None)
        try:
            for name, obj in self.presets.objects().items():
                self.preset_combo.addItem(name, obj)
        except (ValueError, OSError) as exc:
            self.error(str(exc))

    def save_preset(self):
        try:
            self._assert_inputs()
            name = self.preset_name.text().strip()
            self.presets.save(name, self.project.object)
            self.project.object.name = name
            self._load_presets()
            self.statusBar().showMessage("Object geometry saved locally; artwork is excluded.")
        except (ValueError, OSError) as exc:
            self.error(str(exc))

    def select_preset(self, index):
        obj = self.preset_combo.itemData(index)
        if obj:
            self._invalid_cells.clear()
            self.project.object = ObjectSpec(**asdict(obj))
            self._load_controls()
            self._changed()

    def refresh(self, *_):
        if self._loading:
            return
        self._generation += 1
        self.export_button.setEnabled(False)
        self._sync_presentation()
        self._set_preview_active(False)
        try:
            self._assert_inputs()
            surface = self.project.validate(False)
            points = surface.points if self.project.object.mode == "measured" else []
            self.profile_view.set_surface(
                surface, points, self.project.placement, bool(self.artwork)
            )
            length = self.unit.from_mm(surface.distance(surface.height))
            self.surface_summary.setText(
                f"Surface height: {length:.3f} {self.project.units}\nWrap width at mid-height: {self.unit.from_mm(self.project.wrap_width()):.3f} {self.project.units}"
            )
            if self.artwork:
                self.project.validate()
            self.notice.setObjectName("Notice")
            self.notice.setStyleSheet("background:#e8eff3;color:#425f70;padding:8px;")
            self.notice.setText(
                "Calculating preview…"
                if self.artwork
                else "Enter your object's measurements, then import an SVG. Convert live text to curves first."
            )
            self.result_label.setText(
                "Preview pending"
                if self.artwork
                else "Reference surface template · No artwork imported"
            )
            self._timer.start(180)
        except (ValueError, TypeError) as exc:
            self._timer.stop()
            self.error(str(exc))

    def _start_preview(self):
        if self._busy:
            return
        self._busy = True
        self._job = PreviewJob(self._generation, self.artwork, deepcopy(self.project), self.export_mode.currentData())
        self._job.signals.finished.connect(self._preview_done)
        self._pool.start(self._job)

    def _preview_done(self, generation, payload, error):
        self._busy = False
        self._job = None
        if generation != self._generation:
            # A timer may have expired while the old job ran. Queue only the latest valid state.
            try:
                self._assert_inputs()
                self.project.validate(bool(self.artwork))
                self._timer.start(1)
            except ValueError:
                pass
            return
        if error:
            self.error(error)
            return
        result, text, original_text, front_text = payload
        try:
            if text is None:
                self.development.set_message("Import SVG to define the curved artwork region.")
            else:
                self.development.set_svg(text)
            if original_text:
                self.original.set_svg(original_text)
            if front_text:
                self.front_view.set_svg(front_text)
            self.export_button.setEnabled(
                (bool(self.artwork) or self.export_mode.currentData() == "template") and text is not None
            )
            self._set_preview_active(True)
            self._sync_presentation()
            warnings = result.warnings if result else self.project.profile_warnings()
            if self.export_mode.currentData() in {"guides", "template"}:
                warnings = [
                    *warnings,
                    "Guide paths may cut. Remove the Guides group before production cutting.",
                ]
            assumption = (
                "Compare the front-view target with the flat pattern. Test actual vinyl before production."
                if self.project.physical_model == "front-view-vinyl"
                else "Surface-wrap artwork: dimensions follow the surface. The object profile is a schematic."
            )
            self.notice.setText(
                assumption
                + (
                    "\n" + "\n".join(warnings)
                    if warnings
                    else ""
                )
            )
            self.result_label.setText(
                f"Preview: {result.node_count:,} nodes · 0.08 mm tolerance · Wheel to zoom, drag to pan"
                if result
                else "Import SVG to define the curved artwork region." if text is None
                else "Reference template · Import SVG to add artwork"
            )
        except ValueError as exc:
            self.error(str(exc))

    def _set_preview_active(self, active):
        for view in [self.front_view, self.development, self.original, self.profile_view]:
            view.setEnabled(active)
            for item in view.scene().items():
                item.setOpacity(1 if active else 0.25)

    def error(self, message):
        self.notice.setText(message)
        self.notice.setObjectName("Error")
        self.notice.setStyleSheet("background:#fff0e9;color:#9e4325;padding:8px;")
        self.export_button.setEnabled(False)
        self.actions["Export SVG"].setEnabled(False)
        self.export_summary.setText("Export paused. Correct the message above to continue.")
        self._set_preview_active(False)
        self.flat_caption.setText("Previous preview · export paused until input is valid")
        self.statusBar().showMessage(message)

    def export_to(self, path, mode=None):
        self._assert_inputs()
        mode = mode or self.export_mode.currentData()
        path = Path(path)
        if path.name.casefold() == self.project.source_name.casefold():
            raise ValueError("Choose a new filename to protect the imported source SVG.")
        result = (
            convert(self.artwork, self.project, original=mode == "original")
            if mode != "template"
            else None
        )
        text = export_svg(result, self.project, mode, self.project.source_name)
        write_export(path, text, self.source_path)
        return result, text

    def _assert_inputs(self):
        if self.project.object.mode == "measured" and self._invalid_cells:
            raise ValueError("Correct the highlighted profile measurement before continuing.")

    def choose_export(self):
        if not self.export_button.isEnabled():
            return
        stem = Path(self.project.source_name).stem if self.project.source_name else "surface"
        suffix = {
            "artwork": "compensated",
            "guides": "compensated-guides",
            "template": "template",
            "original": "uncompensated",
        }[self.export_mode.currentData()]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export cutting pattern SVG", f"{stem}-{suffix}.svg", "SVG files (*.svg)"
        )
        if path:
            try:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                path = Path(path)
                if path.suffix.lower() != ".svg":
                    path = path.with_suffix(".svg")
                result, text = self.export_to(path)
                svg = ET.fromstring(text)
                dimensions = f"{float(svg.get('width')[:-2]):.3f} × {float(svg.get('height')[:-2]):.3f} mm"
                self.export_summary.setText(f"Saved {dimensions}\n{path.name}")
                self.export_summary.setToolTip(str(path.resolve()))
                self.statusBar().showMessage(
                    f"Saved {path.resolve()} · {dimensions}"
                    + (f" · {result.node_count:,} production nodes" if result else "")
                    + " · CorelDRAW verification pending"
                )
            except (ValueError, OSError) as exc:
                self.error(str(exc))
            finally:
                QApplication.restoreOverrideCursor()

    def fit_views(self):
        for view in [self.front_view, self.development, self.original, self.profile_view]:
            view.fit()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1:
            path = event.mimeData().urls()[0].toLocalFile()
            if Path(path).suffix.lower() == ".svg":
                event.acceptProposedAction()

    def dropEvent(self, event):
        try:
            self.import_file(event.mimeData().urls()[0].toLocalFile())
            event.acceptProposedAction()
        except (ValueError, OSError) as exc:
            self.error(str(exc))

    def _autosave(self):
        if self.dirty:
            save_project(self.data_dir / "Last-session.wraplab", self.project)

    def closeEvent(self, event):
        try:
            self._autosave()
        except (ValueError, OSError) as exc:
            self.error("Session could not be saved: " + str(exc))
            choice = QMessageBox.warning(
                self,
                "Session could not be saved",
                "The recovery file could not be written. Save the project somewhere else, "
                "discard unsaved changes, or cancel closing.\n\n" + str(exc),
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Save:
                self.choose_save_project()
            elif choice == QMessageBox.StandardButton.Discard:
                self.dirty = False
            if self.dirty:
                event.ignore()
                return
        self._timer.stop()
        self._pool.waitForDone()
        event.accept()


def launch(argv=None):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setOrganizationName("WrapLab")
    app.setApplicationName("WrapLab")
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    icon = resource_root / ("wraplab.ico" if getattr(sys, "frozen", False) else "packaging/windows/wraplab.ico")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    window = MainWindow()
    if argv:
        try:
            window.load_file(argv[0]) if argv[0].lower().endswith(
                ".wraplab"
            ) else window.import_file(argv[0])
        except (OSError, ValueError) as exc:
            window.error(str(exc))
    window.show()
    return app.exec()
