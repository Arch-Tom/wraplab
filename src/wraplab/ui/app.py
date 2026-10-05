"""One workspace; all compensation/export decisions live in non-UI modules."""

from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import sys

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
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..domain import ObjectSpec, Project
from ..geometry.units import Unit
from ..persistence import PresetStore, load_project, save_project
from ..svg import convert, export_svg, import_svg
from ..svg.exporter import ideal_front_svg, write_export
from .views import Canvas, ProfileCanvas

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
QToolButton { color: #e3edf3; padding: 7px 9px; border-radius: 4px; }
QToolButton:hover { background: #2f4c60; }
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
    def __init__(self, generation, artwork, project):
        super().__init__()
        self.generation, self.artwork, self.project = generation, artwork, project
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
                front = (
                    ideal_front_svg(self.artwork, self.project)
                    if self.project.physical_model == "front-view-vinyl"
                    else None
                )
                payload = (result, text, original_text, front)
            else:
                payload = (None, export_svg(None, self.project, "template"), None, None)
            self.signals.finished.emit(self.generation, payload, None)
        except Exception as exc:
            self.signals.finished.emit(self.generation, None, str(exc))


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path | None = None):
        super().__init__()
        self.setWindowTitle(f"WrapLab {__version__} · Surface templates")
        self.resize(1370, 900)
        self.setMinimumSize(1050, 700)
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
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.addWidget(QLabel("WrapLab"))
        for title, callback in [
            ("Import SVG", self.choose_svg),
            ("Open Project", self.choose_project),
            ("Save Project", self.choose_save_project),
        ]:
            action = QAction(title, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)
        self.addToolBar(toolbar)

        panel = QFrame()
        panel.setObjectName("Panel")
        side = QVBoxLayout(panel)
        side.setContentsMargins(18, 6, 18, 18)
        side.setSpacing(9)
        self._section(side, "01  OBJECT & MEASUREMENTS")
        self.workflow = QComboBox()
        self.workflow.addItem("Front-view vinyl (level lettering)", "front-view-vinyl")
        self.workflow.addItem("Surface wrap / template", "surface-template")
        self.workflow.setToolTip(
            "Front-view vinyl assumes an upright object viewed horizontally from far away. Surface wrap uses arc-width placement."
        )
        self.workflow.currentIndexChanged.connect(self.workflow_changed)
        side.addWidget(self.workflow)
        self.mode = QComboBox()
        for label, value in MODES:
            self.mode.addItem(label, value)
        self.mode.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.mode.setMinimumContentsLength(16)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        side.addWidget(self.mode)
        self.badge = QLabel("Exact")
        self.badge.setObjectName("Badge")
        self.badge.setToolTip(
            "Exact refers to surface development for templates, not laser compensation."
        )
        side.addWidget(self.badge)
        self.units = QComboBox()
        self.units.addItem("Millimeters (mm)", "mm")
        self.units.addItem("Inches (in)", "in")
        self.units.currentIndexChanged.connect(self.units_changed)
        form = QFormLayout()
        form.addRow("Display units", self.units)
        self.object_fields = {}
        self.object_rows = {}
        for key, label in [
            ("diameter", "Diameter"),
            ("bottom_diameter", "Bottom diameter"),
            ("top_diameter", "Top diameter"),
            ("height", "Axial height"),
        ]:
            spin = self._spin(key, lambda value, k=key: self.object_changed(k, value))
            field_label = QLabel(label)
            form.addRow(field_label, spin)
            self.object_fields[key] = spin
            self.object_rows[key] = field_label
        side.addLayout(form)

        self.measurement_panel = QWidget()
        measured = QVBoxLayout(self.measurement_panel)
        measured.setContentsMargins(0, 0, 0, 0)
        self.measurement_type = QComboBox()
        self.measurement_type.addItem("Measure diameters", "diameter")
        self.measurement_type.addItem("Measure circumferences", "circumference")
        self.measurement_type.currentIndexChanged.connect(self.measurement_type_changed)
        measured.addWidget(self.measurement_type)
        self.table = QTableWidget(0, 2)
        self.table.setMinimumHeight(195)
        self.table.setMaximumHeight(245)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellChanged.connect(self.point_changed)
        measured.addWidget(self.table)
        row = QHBoxLayout()
        for title, callback in [
            ("+ Point", self.add_point),
            ("Remove", self.remove_point),
            ("Sort", self.sort_points),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        measured.addLayout(row)
        example = QLabel("Initial points are an example, not measurements of your bell.")
        example.setWordWrap(True)
        measured.addWidget(example)
        side.addWidget(self.measurement_panel)
        self.surface_summary = QLabel()
        self.surface_summary.setWordWrap(True)
        side.addWidget(self.surface_summary)

        self._section(side, "02  ARTWORK & PLACEMENT")
        self.source_label = QLabel("Drop a path-based SVG here, or use Import SVG.")
        self.source_label.setWordWrap(True)
        self.source_label.setObjectName("Notice")
        side.addWidget(self.source_label)
        form = QFormLayout()
        self.placement_fields = {}
        for key, label in [
            ("width", "Width"),
            ("height", "Axial art height"),
            ("x", "Horizontal position"),
            ("z", "Artwork top from TOP"),
        ]:
            spin = self._spin(key, lambda value, k=key: self.placement_changed(k, value))
            if key in {"x", "z"}:
                spin.setRange(-1_000_000, 1_000_000)
            self.placement_fields[key] = spin
            form.addRow(label, spin)
        self.aspect = QCheckBox("Lock aspect ratio")
        self.aspect.toggled.connect(self.aspect_changed)
        form.addRow(self.aspect)
        side.addLayout(form)
        row = QHBoxLayout()
        for label, callback in [
            ("Center", self.center_artwork),
            ("Reset size", self.reset_artwork),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        side.addLayout(row)

        self._section(side, "03  WRAP & EXPORT")
        form = QFormLayout()
        self.coverage = self._spin("coverage", self.coverage_changed, unit=False)
        self.coverage.setRange(0.1, 360)
        self.coverage.setSuffix(" °")
        form.addRow("Wrap coverage", self.coverage)
        self.rotation = self._spin("rotation", self.rotation_changed, unit=False)
        self.rotation.setRange(-360, 360)
        self.rotation.setSuffix(" °")
        form.addRow("Template rotation", self.rotation)
        self.tolerance = self._spin("tolerance", self.tolerance_changed, unit=False)
        self.tolerance.setDecimals(3)
        self.tolerance.setRange(0.001, 0.25)
        self.tolerance.setSingleStep(0.005)
        self.tolerance.setSuffix(" mm")
        self.tolerance.setToolTip(
            "Maximum target curve deviation for production export; preview uses 0.08 mm."
        )
        form.addRow("Curve tolerance", self.tolerance)
        side.addLayout(form)
        self.export_mode = QComboBox()
        for title, mode in [
            ("Compensated Artwork Only", "artwork"),
            ("Artwork + Guides", "guides"),
            ("Reference Surface Template", "template"),
            ("Uncompensated Comparison", "original"),
        ]:
            self.export_mode.addItem(title, mode)
        self.export_mode.currentIndexChanged.connect(self.refresh)
        side.addWidget(self.export_mode)
        self.export_button = QPushButton("Export SVG for Corel")
        self.export_button.setObjectName("Primary")
        self.export_button.clicked.connect(self.choose_export)
        side.addWidget(self.export_button)

        self._section(side, "SAVED OBJECTS")
        self.preset_combo = QComboBox()
        self.preset_combo.activated.connect(self.select_preset)
        side.addWidget(self.preset_combo)
        row = QHBoxLayout()
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("Object preset name")
        self.preset_name.editingFinished.connect(self.name_changed)
        row.addWidget(self.preset_name)
        button = QPushButton("Save")
        button.clicked.connect(self.save_preset)
        row.addWidget(button)
        side.addLayout(row)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Measurement notes (optional)")
        self.notes.editingFinished.connect(self.notes_changed)
        side.addWidget(self.notes)
        self.uncertainty = self._spin("uncertainty", self.uncertainty_changed)
        self.uncertainty.setRange(0, 1_000_000)
        self.uncertainty.setSpecialValueText("Not recorded")
        self.uncertainty.setToolTip(
            "Uncertainty of entered diameters/circumferences; recorded only, not included in material strain estimates."
        )
        form = QFormLayout()
        form.addRow("Measurement ±", self.uncertainty)
        side.addLayout(form)
        side.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(panel)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(330)
        scroll.setMaximumWidth(390)

        work = QWidget()
        layout = QVBoxLayout(work)
        layout.setContentsMargins(18, 16, 18, 14)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("<b>SURFACE WORKSPACE</b>"))
        title_row.addStretch()
        fit = QPushButton("Fit views")
        fit.clicked.connect(self.fit_views)
        title_row.addWidget(fit)
        layout.addLayout(title_row)
        self.notice = NoticeLabel("Surface-template development · Offline · No machine control")
        self.notice.setWordWrap(True)
        self.notice.setObjectName("Notice")
        layout.addWidget(self.notice)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.tabs = QTabWidget()
        self.front_view = Canvas()
        self.development = Canvas()
        self.original = Canvas()
        self.tabs.addTab(self.front_view, "Ideal front view")
        self.tabs.addTab(self.development, "Flat vinyl pattern")
        self.tabs.addTab(self.original, "Original artwork")
        split.addWidget(self.tabs)
        profile_panel = QWidget()
        profile_layout = QVBoxLayout(profile_panel)
        profile_layout.setContentsMargins(12, 0, 0, 0)
        profile_layout.addWidget(QLabel("<b>OBJECT PROFILE</b>"))
        self.profile_view = ProfileCanvas()
        profile_layout.addWidget(self.profile_view)
        self.profile_label = QLabel(
            "TOP = height 0\nAxial height ↓ from top\nGreen band = artwork region"
        )
        self.profile_label.setWordWrap(True)
        profile_layout.addWidget(self.profile_label)
        profile_panel.setMinimumWidth(170)
        split.addWidget(profile_panel)
        split.setSizes([640, 220])
        layout.addWidget(split, 1)
        self.result_label = QLabel("Import artwork to generate a compensated preview.")
        layout.addWidget(self.result_label)
        outer = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(scroll)
        outer.addWidget(work)
        outer.setSizes([360, 1010])
        self.setCentralWidget(outer)
        self.statusBar().showMessage(
            "Ready · Wheel to zoom, drag to pan · Exported SVG works independently of WrapLab"
        )

    def _section(self, layout, title):
        label = QLabel(title)
        label.setObjectName("Section")
        layout.addWidget(label)

    def _spin(self, name, callback, unit=True):
        spin = QDoubleSpinBox()
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
        self.badge.setText(
            "Best-Fit / Experimental" if mode == "measured" else "Exact surface development"
        )
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
            radii = [surface.radius(surface.height * i / 100) for i in range(101)]
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
                else "Import a path-based SVG. Text must be converted to curves."
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
        self._job = PreviewJob(self._generation, self.artwork, deepcopy(self.project))
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
            self.development.set_svg(text)
            if original_text:
                self.original.set_svg(original_text)
            self.tabs.setTabEnabled(0, self.project.physical_model == "front-view-vinyl")
            if front_text:
                self.front_view.set_svg(front_text)
            self.export_button.setEnabled(
                bool(self.artwork) or self.export_mode.currentData() == "template"
            )
            warnings = result.warnings if result else self.project.profile_warnings()
            if self.export_mode.currentData() in {"guides", "template"}:
                warnings = [
                    *warnings,
                    "Guide paths may cut. Remove the Guides group before production cutting.",
                ]
            assumption = (
                "Ideal front view: upright object, distant horizontal view. Test actual vinyl before production."
                if self.project.physical_model == "front-view-vinyl"
                else "Surface wrap: horizontal placement is arc distance at mid-height."
            )
            self.notice.setText(
                assumption
                + (
                    "\n" + "\n".join(warnings)
                    if warnings
                    else "\nExact surface development · Production uses finer tolerance than preview."
                )
            )
            self.result_label.setText(
                f"Preview: {result.node_count:,} nodes · 0.08 mm tolerance · Wheel to zoom, drag to pan"
                if result
                else "Reference template · Import SVG to add artwork"
            )
        except ValueError as exc:
            self.error(str(exc))

    def error(self, message):
        self.notice.setText(message)
        self.notice.setObjectName("Error")
        self.notice.setStyleSheet("background:#fff0e9;color:#9e4325;padding:8px;")
        self.export_button.setEnabled(False)
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
        stem = Path(self.project.source_name).stem if self.project.source_name else "surface"
        suffix = {
            "artwork": "compensated",
            "guides": "compensated-guides",
            "template": "template",
            "original": "uncompensated",
        }[self.export_mode.currentData()]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export SVG for Corel", f"{stem}-{suffix}.svg", "SVG files (*.svg)"
        )
        if path:
            try:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                path = Path(path)
                if path.suffix.lower() != ".svg":
                    path = path.with_suffix(".svg")
                result, _ = self.export_to(path)
                self.statusBar().showMessage(
                    f"Exported {path.name}"
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
            event.ignore()
            return
        self._timer.stop()
        self._pool.waitForDone()
        event.accept()


def launch(argv=None):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setOrganizationName("WrapLab")
    app.setApplicationName("WrapLab")
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
