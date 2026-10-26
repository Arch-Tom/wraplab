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
from ..preview.settings import options as preview_options

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
                dimensions = (None if self.export_mode == 'template' else
                              original if self.export_mode == 'original' else result)
                payload = (result, text, original_text, front, dimensions)
            else:
                text = (None if self.project.object.mode == "measured" and self.export_mode != "template"
                        else export_svg(None, self.project, "template"))
                payload = (None, text, None, None, None)
            # Renderer/planner failures must not turn a valid ordinary SVG job into
            # an export failure. Geometry stays on the existing worker/generation guard.
            extra = {"scene": None, "plan": None, "scene_error": None, "plan_error": None}
            try:
                from ..preview.scene import build_scene
                from ..masks.model import assignment_from_dict
                from ..masks.planner import plan_masks
                settings = preview_options(self.project.preview_options)
                if self.artwork and settings["assignment"]:
                    try:
                        extra["plan"] = plan_masks(self.artwork, self.project,
                            assignment_from_dict(settings["assignment"]), settings["method"],
                            settings["margins_mm"], preview=True)
                    except (ValueError, ArithmeticError) as exc:
                        extra["plan_error"] = str(exc)
                extra["scene"] = build_scene(self.project, self.artwork,
                    original=original if self.artwork else None, plan=extra["plan"])
            except Exception as exc:
                extra["scene_error"] = str(exc)
            self.signals.finished.emit(self.generation, (*payload, extra), None)
        except Exception as exc:
            self.signals.finished.emit(self.generation, None, str(exc))


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path | None = None):
        super().__init__()
        self.setWindowTitle(f"WrapLab {__version__} · 3D preview & mask planning")
        self.resize(1370, 900)
        self.setMinimumSize(980, 650)
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.resize(min(1370, max(980, available.width() - 40)),
                        min(900, max(650, available.height() - 70)))
        self.setAcceptDrops(True)
        self.project = Project(artwork_frame='visible')
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
        self._plan = self._scene = None
        self._renderer_error = None
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
        self.project = Project(artwork_frame='visible')
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
        self.artwork_frame.setEnabled(imported)
        frame_name = 'Visible' if self.project.artwork_frame == 'visible' else 'Page'
        for key in ('width', 'height'):
            label = f'{frame_name} target {key}'
            self.placement_labels[key].setText(label)
            self.placement_fields[key].setAccessibleName(label)
        self.frame_help.setText(
            ('On-object front-view target' if front else 'Surface-distance target')
            + (' · visible design only.' if self.project.artwork_frame == 'visible'
               else ' · includes blank SVG page margins.')
            + ' Flat cutting dimensions may differ. Position anchors refer to this frame.'
        )
        if self.artwork:
            art = self.artwork
            bounds = art.bounds_result
            def size(width, height):
                return (f'{self.unit.from_mm(width):.3f} × '
                        f'{self.unit.from_mm(height):.3f} {self.project.units}')
            self.source_label.setText(
                self.project.source_name + '\nSource page: ' + size(art.width_mm, art.height_mm)
                + ('\nVisible artwork: ' + size(bounds.frame.width, bounds.frame.height)
                   + (' (numerical stroke envelope)' if bounds.frame.accuracy_mm else '')
                   if bounds.frame else '\nVisible bounds unavailable: ' + bounds.error)
            )
        self.original_section.toggle.setEnabled(imported)
        self.position_section.toggle.setEnabled(editable_support)
        self.advanced.toggle.setText("Advanced · " + self.workflow.currentText())
        settings = preview_options(self.project.preview_options)
        use_3d = settings["view"] == "3d" and self.scene_view is not None and not self._renderer_error
        self.object_preview_stack.setCurrentIndex(2 if use_3d else 0 if imported and front else 1)
        self.preview_mode.blockSignals(True)
        self.preview_mode.setCurrentIndex(0 if use_3d else 1)
        self.preview_mode.blockSignals(False)
        self.camera_views.setEnabled(use_3d)
        self.planner.restore(self.project.preview_options, self.artwork)
        self.front_caption.setText(
            "Orbit: drag · Pan: right-drag / Shift-drag · Zoom: wheel · Preview only"
            if use_3d else "Front-view target · upright object · 2D preview"
            if imported and front else "Object profile (schematic) · TOP is height 0"
        )
        if self._renderer_error and settings["view"]=="3d":
            self.front_caption.setText("3D unavailable · existing 2D view retained")
            self.front_caption.setToolTip(self._renderer_error)
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
            "Match the selected frame you want to see from the front. Target size differs from flat cutting size."
            if front else "Wrap around the surface. Width and horizontal position are surface distances."
        )
        self.horizontal_label.setText("Horizontal offset" if front else "Distance from seam")
        self.placement_fields["x"].setToolTip(
            "Selected frame's center offset from the object front center; zero is centered." if front else
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
        if imported and settings["assignment"] is not None:
            if mode=="artwork":
                self.export_button.setText("Export Whole Compensated SVG…")
            self.export_summary.setText("Whole layout · separate mask SVGs use Mask planning.")
        for spin in self.object_fields.values():
            spin.setStyleSheet("border:1px solid #bc5940;" if spin.value() <= 0 else "")

    def _load_controls(self):
        self._loading = True
        self.mode.setCurrentIndex([value for _, value in MODES].index(self.project.object.mode))
        self.workflow.setCurrentIndex(0 if self.project.physical_model == "front-view-vinyl" else 1)
        self.units.setCurrentIndex(0 if self.project.units == "mm" else 1)
        self.artwork_frame.setCurrentIndex(self.artwork_frame.findData(self.project.artwork_frame))
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

    def frame_changed(self, index):
        if self._loading or not self.artwork:
            return
        previous = self.project.artwork_frame
        selected = self.artwork_frame.itemData(index)
        try:
            frame = (self.artwork.visible_frame if selected == 'visible'
                     else self.artwork.page_frame)
        except ValueError as exc:
            self._loading = True
            self.artwork_frame.setCurrentIndex(self.artwork_frame.findData(previous))
            self._loading = False
            self.error(str(exc))
            return
        self.project.artwork_frame = selected
        if self.project.placement.lock_aspect:
            self.project.placement.width = self.project.placement.height * frame.width / frame.height
        self._load_controls()
        self._changed()
        self.statusBar().showMessage('Sizing frame changed; target height and top/horizontal anchors kept. '
                                     'Check the preview before export.')

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
            try:
                frame = self.project.source_frame(self.artwork)
                self.project.placement.width = frame.width
                self.project.placement.height = frame.height
                self.center_artwork()
            except ValueError as exc:
                self.error(str(exc))

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
        # Only a trustworthy supported bound can select visible-artwork sizing.
        if self.project.artwork_frame == 'visible' and artwork.bounds_result.frame is None:
            self.project.artwork_frame = 'page'
        frame = self.project.source_frame(artwork)
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
            1, 0.85 * available / frame.width, 0.85 * surface.height / frame.height
        )
        self.project.source_svg = artwork.source
        self.project.source_name = path.name
        self.artwork = artwork
        # Source-bound membership never transfers to a different imported document.
        settings = preview_options(self.project.preview_options)
        from ..masks.model import cantor_assignment
        try:
            settings["assignment"] = cantor_assignment(artwork).to_dict()
        except ValueError:
            settings["assignment"] = None
        settings.update(selected_mask="all", method="global-split", mask_layout=False)
        self.project.preview_options = settings
        self.source_path = path.resolve()
        self.project.placement.width = frame.width * scale
        self.project.placement.height = frame.height * scale
        self.project.center_artwork()
        self._load_controls()
        self._changed()
        if scale < 1:
            self.statusBar().showMessage('Selected frame sized to fit the object; inspect target dimensions.')

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
        self.flat_dimensions.setText('Flat artwork dimensions pending' if self.artwork else '')
        self.warning_details.setText("Preview details pending.")
        self.export_button.setEnabled(False)
        self.planner.export_button.setEnabled(False)
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
        result, text, original_text, front_text, dimensions, extra = payload
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
            self._plan, self._scene = extra["plan"], extra["scene"]
            self.planner.set_plan(self._plan, extra["plan_error"])
            if extra["scene_error"]:
                self.renderer_failed(extra["scene_error"])
            elif self._scene is not None and self.scene_view is not None:
                if not self.scene_view.failure:
                    self._renderer_error=None
                self.scene_view.set_scene(self._scene, self.project.preview_options)
            self.update_mask_views()
            if dimensions:
                points = [p for path in dimensions.paths for c in path.contours for p in c.points]
                width = max(p.real for p in points) - min(p.real for p in points)
                height = max(p.imag for p in points) - min(p.imag for p in points)
                label = ('Uncompensated artwork' if self.export_mode.currentData() == 'original'
                         else 'Flat artwork')
                self.flat_dimensions.setText(
                    f'{label} (preview): {self.unit.from_mm(width):.3f} × '
                    f'{self.unit.from_mm(height):.3f} {self.project.units}'
                )
            else:
                self.flat_dimensions.setText('')
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
            self.warning_details.setText("Full preview warnings\n"+"\n".join(warnings)
                                         if warnings else "No additional preview warnings.")
            if self.project.object.mode=="measured" and self.artwork:
                low,high=self.project.development().strain_extrema()
                summary=(f"EXPERIMENTAL measured band · modeled support extension {max(0,high):.2%}, "
                         f"compression {max(0,-low):.2%}. Carrier/adhesion unmodeled; no material limit approved. "
                         "Full warnings in Advanced.")
                if self.export_mode.currentData() in {"guides","template"}:
                    summary+=" Guide paths may cut."
                self.notice.setText(summary)
            else:
                self.notice.setText(assumption+("\n"+"\n".join(warnings) if warnings else ""))
            self.result_label.setText(
                f"Preview: {result.node_count:,} nodes · 0.08 mm tolerance · Wheel to zoom, drag to pan"
                if result
                else "Import SVG to define the curved artwork region." if text is None
                else "Reference template · Import SVG to add artwork"
            )
        except ValueError as exc:
            self.error(str(exc))

    def _set_preview_active(self, active):
        if self.scene_view is not None:
            self.scene_view.setEnabled(active)
        for view in [self.front_view, self.development, self.original, self.profile_view]:
            view.setEnabled(active)
            for item in view.scene().items():
                item.setOpacity(1 if active else 0.25)

    def error(self, message):
        self.flat_dimensions.setText('Flat dimensions unavailable · export paused')
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
                self.export_summary.setText(f"Saved flat pattern: {dimensions}\n{path.name}")
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
        self.mask_canvas.fit()
        if self.scene_view is not None:
            self.scene_view.set_camera_view("Reset")

    def preview_mode_changed(self, *_):
        settings = preview_options(self.project.preview_options)
        settings["view"] = self.preview_mode.currentData()
        self.preview_settings_changed(settings)

    def preview_settings_changed(self, settings):
        previous = preview_options(self.project.preview_options)
        self.project.preview_options = preview_options(settings)
        self.dirty = True
        if any(previous[key] != settings[key] for key in ("method", "margins_mm", "assignment", "physical_top_datum_mm")):
            self._changed()
        else:
            self._sync_presentation()
            if self.scene_view is not None:
                self.scene_view.set_options(settings)
            self.update_mask_views()

    def camera_changed(self, camera):
        settings = preview_options(self.project.preview_options)
        settings["camera"] = camera
        self.project.preview_options = settings
        self.dirty = True

    def camera_view_changed(self, index):
        if self.scene_view is not None:
            self.scene_view.set_camera_view(self.camera_views.itemText(index) if index >= 0 else "Reset")

    def renderer_failed(self, message):
        self._renderer_error = message
        self._sync_presentation()
        self.front_caption.setText("3D unavailable · existing 2D view retained")
        self.front_caption.setToolTip(message)
        self.statusBar().showMessage(message)

    def select_mask(self, mask_id):
        settings = preview_options(self.project.preview_options)
        settings["selected_mask"] = mask_id
        self.preview_settings_changed(settings)

    def update_mask_views(self):
        from .planning import highlight_global, apply_visibility
        settings = preview_options(self.project.preview_options)
        separate = bool(self._plan and (settings["mask_layout"] or self._plan.method=="independent"
                                       or settings["isolate"] and settings["selected_mask"]!="all"))
        self.flat_preview_stack.setCurrentIndex(1 if separate else 0)
        apply_visibility(self.development,settings)
        if not self._plan:
            return
        self.planner.set_plan(self._plan)
        if separate:
            self.mask_canvas.set_plan(self._plan, self.project, settings["selected_mask"], settings["isolate"],settings)
            self.flat_title.setText("Experimental Mask Patterns" if self._plan.method == "independent" else "Separate Mask Patterns")
            self.flat_caption.setText("Display gaps are not installation spacing · ordinary Export SVG remains unchanged")
        elif self._plan.method == "global-split" and self.export_mode.currentData() != "template":
            highlight_global(self.development, self._plan, self.project, settings,
                             original=self.export_mode.currentData() == "original")

    def apply_verified_grouping(self):
        if not self.artwork:
            return
        from ..masks.model import cantor_assignment
        try:
            settings=preview_options(self.project.preview_options)
            settings.update(assignment=cantor_assignment(self.artwork).to_dict(),
                            selected_mask="all",method="global-split",mask_layout=False)
            self.preview_settings_changed(settings)
        except ValueError as exc:
            self.planner.status.setText(str(exc))

    def apply_historical_trial(self):
        if not self.artwork:
            return
        from ..masks.model import cantor_trial
        try:
            self._autosave()  # Preserve the current project before this explicit replacement.
            trial = cantor_trial(self.artwork)
            trial.source_name = self.project.source_name
            self.project = trial
            self.project_path = None
            self._invalid_cells.clear()
            self._load_controls()
            self._changed()
            self.statusBar().showMessage("Historical nominal bell trial loaded. Measurements and production fit are NOT approved.")
        except (ValueError, OSError) as exc:
            self.planner.status.setText("Historical trial not applied: " + str(exc))

    def choose_mask_export(self):
        if self._busy or self._timer.isActive() or self._plan is None:
            return
        settings = preview_options(self.project.preview_options)
        if settings["method"] == "independent" and not self.planner.ack.isChecked():
            self.planner.status.setText("Acknowledge the experimental fit before exporting candidate masks.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Name a NEW mask-package folder",
                                             "WrapLab-masks-"+settings["method"], "New package folder (*)")
        if not path:
            return
        try:
            from ..masks.model import assignment_from_dict
            from ..masks.exporter import export_masks
            self._assert_inputs()
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            _,manifest = export_masks(Path(path), self.artwork, self.project,
                assignment_from_dict(settings["assignment"]), settings["method"], settings["margins_mm"],
                acknowledge_experimental=self.planner.ack.isChecked())
            self.planner.status.setText(f"Saved {manifest['mask_count']} vector masks to {Path(path).resolve()}. "
                "Reference SVG is DO NOT CUT. Corel/cutter/material verification remains pending.")
        except (ValueError, OSError) as exc:
            self.planner.status.setText("Mask export paused: "+str(exc))
        finally:
            QApplication.restoreOverrideCursor()

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
