"""Operator presentation over the existing model and MainWindow callbacks."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QScrollArea, QSplitter,
    QStackedWidget, QTableWidget, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from .views import Canvas, ProfileCanvas
from .planning import MaskCanvas, PlanningPanel


class MeasurementSpinBox(QDoubleSpinBox):
    """Scrolling the panel must never change physical measurements accidentally."""

    def wheelEvent(self, event):
        event.ignore()

    def textFromValue(self, value):
        text = super().textFromValue(value)
        separator = self.locale().decimalPoint()
        return text.rstrip("0").rstrip(separator) if separator in text else text


class ChoiceBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class Disclosure(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setObjectName("Disclosure")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setAccessibleName(title)
        layout.addWidget(self.toggle)
        self.content = QWidget()
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(7)
        layout.addWidget(self.content)
        self.content.hide()
        self.toggle.toggled.connect(self._toggle)

    def _toggle(self, checked):
        self.content.setVisible(checked)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)


def note(text):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setObjectName("Help")
    return label


def section(layout, title):
    label = QLabel(title)
    label.setObjectName("Section")
    layout.addWidget(label)


def form():
    layout = QFormLayout()
    layout.setHorizontalSpacing(10)
    layout.setVerticalSpacing(6)
    layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return layout


def build_workspace(window, notice_type):
    w = window
    toolbar = QToolBar()
    toolbar.setMovable(False)
    toolbar.addWidget(QLabel("WrapLab"))
    w.actions = {}
    for title, shortcut, callback in [
        ("New job", "Ctrl+N", w.new_job),
        ("Open project", "Ctrl+Shift+O", w.choose_project),
        ("Save project", "Ctrl+S", w.choose_save_project),
        ("Resume last job", "", w.resume_job),
    ]:
        action = QAction(title, w)
        action.setShortcut(shortcut)
        action.triggered.connect(callback)
        toolbar.addAction(action)
        w.actions[title] = action
    w.addToolBar(toolbar)
    for title, shortcut, callback in [
        ("Import SVG", "Ctrl+O", w.choose_svg), ("Export SVG", "Ctrl+E", w.choose_export),
    ]:
        action = QAction(title, w)
        action.setShortcut(shortcut)
        action.triggered.connect(callback)
        w.addAction(action)
        w.actions[title] = action

    panel = QFrame()
    panel.setObjectName("Panel")
    side = QVBoxLayout(panel)
    side.setContentsMargins(18, 8, 18, 18)
    side.setSpacing(8)
    section(side, "1  Measure your object")
    w.mode = ChoiceBox()
    for label, value in [
        ("Cylinder", "cylinder"), ("Tapered object", "frustum"),
        ("Custom curved object", "measured"),
    ]:
        w.mode.addItem(label, value)
    w.mode.setAccessibleName("Object type")
    w.mode.currentIndexChanged.connect(w.mode_changed)
    side.addWidget(w.mode)
    w.badge = note("Exact for a straight-sided round object")
    w.badge.setObjectName("Badge")
    side.addWidget(w.badge)
    w.units = ChoiceBox()
    w.units.addItem("Millimeters (mm)", "mm")
    w.units.addItem("Inches (in)", "in")
    w.units.currentIndexChanged.connect(w.units_changed)
    measurements = form()
    measurements.addRow("Units", w.units)
    w.object_fields, w.object_rows = {}, {}
    for key, label in [
        ("diameter", "Diameter"), ("top_diameter", "Top diameter"),
        ("bottom_diameter", "Bottom diameter"), ("height", "Object height"),
    ]:
        spin = w._spin(key, lambda value, k=key: w.object_changed(k, value))
        spin.setMinimum(0)
        spin.setAccessibleName(label)
        spin.setToolTip("Measure across the object." if key != "height" else
                        "Straight vertical height between the measured top and bottom; not slant length.")
        field_label = QLabel(label)
        field_label.setBuddy(spin)
        measurements.addRow(field_label, spin)
        w.object_fields[key], w.object_rows[key] = spin, field_label
    side.addLayout(measurements)
    w.measurement_help = note("Measure diameter across the object and height straight down from its top.")
    side.addWidget(w.measurement_help)

    w.measurement_panel = QWidget()
    measured = QVBoxLayout(w.measurement_panel)
    measured.setContentsMargins(0, 0, 0, 0)
    w.measurement_type = ChoiceBox()
    w.measurement_type.addItem("Measure diameters", "diameter")
    w.measurement_type.addItem("Measure circumferences", "circumference")
    w.measurement_type.currentIndexChanged.connect(w.measurement_type_changed)
    measured.addWidget(w.measurement_type)
    w.table = QTableWidget(0, 2)
    w.table.setMinimumHeight(190)
    w.table.setMaximumHeight(245)
    w.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    w.table.cellChanged.connect(w.point_changed)
    measured.addWidget(w.table)
    row = QHBoxLayout()
    for title, callback in [("Add point", w.add_point), ("Remove", w.remove_point), ("Sort", w.sort_points)]:
        button = QPushButton(title)
        button.clicked.connect(callback)
        row.addWidget(button)
    measured.addLayout(row)
    measured.addWidget(note("Example points are not measurements of your object. Enter 3–30 real stations from TOP."))
    side.addWidget(w.measurement_panel)

    interpretation = form()
    w.workflow = ChoiceBox()
    w.workflow.addItem("Front-view artwork", "front-view-vinyl")
    w.workflow.addItem("Surface-wrap artwork", "surface-template")
    w.workflow.currentIndexChanged.connect(w.workflow_changed)
    interpretation.addRow("Artwork means", w.workflow)
    w.workflow_help = note("")

    section(side, "2  Import & position artwork")
    w.import_button = QPushButton("Import SVG…")
    w.import_button.setObjectName("Import")
    w.import_button.setToolTip("Import a vector SVG (Ctrl+O). Convert text to curves in your editor first.")
    w.import_button.clicked.connect(w.choose_svg)
    side.addWidget(w.import_button)
    w.source_label = note("Choose your object, enter its measurements, then import an SVG.")
    side.addWidget(w.source_label)
    w.artwork_frame = ChoiceBox()
    w.artwork_frame.addItem('Visible artwork', 'visible')
    w.artwork_frame.addItem('Original SVG page', 'page')
    w.artwork_frame.setAccessibleName('Size and position by')
    w.artwork_frame.setToolTip('Switching keeps target height and placement anchors. '
                               'With proportions locked, width follows the selected frame.')
    w.artwork_frame.currentIndexChanged.connect(w.frame_changed)
    frame_choice = form()
    frame_choice.addRow('Size and position by', w.artwork_frame)
    side.addLayout(frame_choice)
    w.frame_help = note('')
    side.addWidget(w.frame_help)
    artwork = form()
    position = form()
    w.placement_fields, w.placement_labels = {}, {}
    for key, label in [
        ("width", "Page target width"), ("height", "Page target height"),
        ("x", "Horizontal offset"), ("z", "Distance from top"),
    ]:
        spin = w._spin(key, lambda value, k=key: w.placement_changed(k, value))
        if key in {"x", "z"}:
            spin.setRange(-1_000_000, 1_000_000)
        spin.setAccessibleName(label)
        spin.setToolTip("Measured straight down from the labelled TOP to the selected sizing frame's top edge." if key == "z"
                        else "Changes physical placement; preview dragging only pans the view.")
        w.placement_fields[key] = spin
        field_label = QLabel(label)
        w.placement_labels[key] = field_label
        field_label.setBuddy(spin)
        (position if key in {"x", "z"} else artwork).addRow(field_label, spin)
        if key == "x":
            w.horizontal_label = field_label
    w.aspect = QCheckBox("Keep proportions")
    w.aspect.toggled.connect(w.aspect_changed)
    artwork.addRow(w.aspect)
    side.addLayout(artwork)
    row = QHBoxLayout()
    w.center_button = QPushButton("Center artwork")
    w.center_button.clicked.connect(w.center_artwork)
    w.reset_button = QPushButton("Original size")
    w.reset_button.clicked.connect(w.reset_artwork)
    row.addWidget(w.center_button)
    row.addWidget(w.reset_button)
    side.addLayout(row)

    w.position_section = Disclosure("Position artwork")
    w.position_section.body.addLayout(position)
    w.position_section.body.addWidget(note("Position runs down from TOP. Dragging in a preview pans the view."))
    side.addWidget(w.position_section)

    w.advanced = Disclosure("Advanced settings")
    options = w.advanced.body
    options.addLayout(interpretation)
    options.addWidget(w.workflow_help)
    technical = form()
    w.coverage = w._spin("coverage", w.coverage_changed, unit=False)
    w.coverage.setRange(0.1, 360)
    w.coverage.setSuffix(" °")
    w.coverage.setToolTip("Angular area available for artwork. The default is a half wrap (180°).")
    technical.addRow("Wrap coverage", w.coverage)
    w.rotation = w._spin("rotation", w.rotation_changed, unit=False)
    w.rotation.setRange(-360, 360)
    w.rotation.setSuffix(" °")
    technical.addRow("Pattern rotation", w.rotation)
    w.tolerance = w._spin("tolerance", w.tolerance_changed, unit=False)
    w.tolerance.setDecimals(3)
    w.tolerance.setRange(0.001, 0.25)
    w.tolerance.setSingleStep(0.005)
    w.tolerance.setSuffix(" mm")
    w.tolerance.setToolTip("Production curve deviation target. Export recomputes at this setting; preview uses 0.08 mm.")
    technical.addRow("Curve tolerance", w.tolerance)
    options.addLayout(technical)
    w.surface_summary = note("")
    options.addWidget(w.surface_summary)
    w.result_label = note("")
    options.addWidget(w.result_label)
    w.warning_details = note("")
    w.warning_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    options.addWidget(w.warning_details)
    side.addWidget(w.advanced)

    w.mask_section = Disclosure("Mask planning · experimental")
    w.planner = PlanningPanel()
    w.planner.changed.connect(w.preview_settings_changed)
    w.planner.historicalRequested.connect(w.apply_historical_trial)
    w.planner.groupingRequested.connect(w.apply_verified_grouping)
    w.planner.exportRequested.connect(w.choose_mask_export)
    w.mask_section.body.addWidget(w.planner)
    side.addWidget(w.mask_section)

    w.preset_section = Disclosure("Saved objects & measurement notes")
    saved = w.preset_section.body
    w.preset_combo = ChoiceBox()
    w.preset_combo.activated.connect(w.select_preset)
    saved.addWidget(w.preset_combo)
    row = QHBoxLayout()
    w.preset_name = QLineEdit()
    w.preset_name.setPlaceholderText("Object name")
    w.preset_name.setAccessibleName("Saved object name")
    w.preset_name.editingFinished.connect(w.name_changed)
    row.addWidget(w.preset_name)
    button = QPushButton("Save object")
    button.clicked.connect(w.save_preset)
    row.addWidget(button)
    saved.addLayout(row)
    w.notes = QLineEdit()
    w.notes.setPlaceholderText("Measurement notes (optional)")
    w.notes.editingFinished.connect(w.notes_changed)
    saved.addWidget(w.notes)
    w.uncertainty = w._spin("uncertainty", w.uncertainty_changed)
    w.uncertainty.setRange(0, 1_000_000)
    w.uncertainty.setSpecialValueText("Not recorded")
    w.uncertainty.setToolTip("Recorded measurement uncertainty; not included in material strain estimates.")
    uncertainty = form()
    uncertainty.addRow("Measurement ±", w.uncertainty)
    saved.addLayout(uncertainty)
    side.addWidget(w.preset_section)
    side.addStretch()

    w.control_scroll = QScrollArea()
    w.control_scroll.setWidgetResizable(True)
    w.control_scroll.setFrameShape(QFrame.Shape.NoFrame)
    w.control_scroll.setWidget(panel)
    w.control_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    controls = QWidget()
    controls.setMinimumWidth(350)
    controls.setMaximumWidth(405)
    controls_layout = QVBoxLayout(controls)
    controls_layout.setContentsMargins(0, 0, 0, 0)
    controls_layout.setSpacing(0)
    controls_layout.addWidget(w.control_scroll, 1)
    footer = QFrame()
    footer.setObjectName("ExportFooter")
    export = QVBoxLayout(footer)
    export.setContentsMargins(18, 10, 18, 12)
    section(export, "3  Export your cutting pattern")
    w.export_options = Disclosure("Export options")
    w.export_mode = ChoiceBox()
    for title, mode in [
        ("Artwork only (recommended)", "artwork"), ("Artwork + cutting guides", "guides"),
        ("Full surface template", "template"), ("Uncompensated comparison", "original"),
    ]:
        w.export_mode.addItem(title, mode)
    w.export_mode.currentIndexChanged.connect(w.refresh)
    w.export_options.body.addWidget(w.export_mode)
    export.addWidget(w.export_options)
    w.export_warning = note("Guide paths may cut. Check the guide selection in your cutting software.")
    w.export_warning.setObjectName("GuideWarning")
    export.addWidget(w.export_warning)
    w.export_button = QPushButton("Export Compensated SVG…")
    w.export_button.setObjectName("Primary")
    w.export_button.setToolTip("Export a new SVG at physical millimeter size (Ctrl+E).")
    w.export_button.clicked.connect(w.choose_export)
    export.addWidget(w.export_button)
    w.export_summary = note("Import artwork to begin.")
    w.export_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    export.addWidget(w.export_summary)
    controls_layout.addWidget(footer)

    work = QWidget()
    layout = QVBoxLayout(work)
    layout.setContentsMargins(16, 12, 16, 12)
    title_row = QHBoxLayout()
    w.next_step = QLabel("Measure → Import → Position → Preview → Export")
    w.next_step.setObjectName("WorkspaceTitle")
    title_row.addWidget(w.next_step)
    title_row.addStretch()
    fit = QPushButton("Fit views")
    fit.clicked.connect(w.fit_views)
    title_row.addWidget(fit)
    layout.addLayout(title_row)
    w.notice = notice_type("")
    w.notice.setWordWrap(True)
    w.notice.setTextFormat(Qt.TextFormat.PlainText)
    w.notice.setObjectName("Notice")
    layout.addWidget(w.notice)
    camera_row = QHBoxLayout()
    w.preview_mode = ChoiceBox()
    w.preview_mode.addItem("Interactive 3D", "3d")
    w.preview_mode.addItem("Original 2D preview", "2d")
    w.preview_mode.setAccessibleName("Object preview mode")
    w.preview_mode.currentIndexChanged.connect(w.preview_mode_changed)
    camera_row.addWidget(w.preview_mode)
    w.camera_views = ChoiceBox()
    for name in ("Front", "Left", "Right", "Rear", "Seam"):
        w.camera_views.addItem(name)
    w.camera_views.setAccessibleName("3D camera direction")
    w.camera_views.activated.connect(w.camera_view_changed)
    camera_row.addWidget(w.camera_views)
    reset = QPushButton("Reset view")
    reset.clicked.connect(lambda: w.camera_view_changed(-1))
    camera_row.addWidget(reset)
    camera_row.addStretch()
    layout.addLayout(camera_row)
    w.preview_splitter = QSplitter(Qt.Orientation.Horizontal)
    w.preview_splitter.setChildrenCollapsible(False)
    w.front_view, w.development, w.original = Canvas(), Canvas(), Canvas()
    w.profile_view = ProfileCanvas()
    w.object_preview_stack = QStackedWidget()
    w.object_preview_stack.addWidget(w.front_view)
    w.object_preview_stack.addWidget(w.profile_view)
    w.scene_view = None
    try:
        from .scene3d import SceneView
        w.scene_view = SceneView()
        w.scene_view.failed.connect(w.renderer_failed)
        w.scene_view.cameraChanged.connect(w.camera_changed)
        w.scene_view.maskSelected.connect(w.select_mask)
        w.object_preview_stack.addWidget(w.scene_view)
    except (ImportError, RuntimeError) as exc:
        w._renderer_error = str(exc)
    w.mask_canvas = MaskCanvas()
    w.flat_preview_stack = QStackedWidget()
    w.flat_preview_stack.addWidget(w.development)
    w.flat_preview_stack.addWidget(w.mask_canvas)
    w.mask_canvas.maskSelected.connect(w.select_mask)
    w.development.maskSelected.connect(w.select_mask)
    for title, view, caption_name, caption in [
        ("On the Object", w.object_preview_stack, "front_caption", "Front-view target · 2D preview"),
        ("Flat Cutting Pattern", w.flat_preview_stack, "flat_caption", "Compensated artwork · preview only"),
    ]:
        frame = QFrame()
        frame.setObjectName("PreviewPanel")
        column = QVBoxLayout(frame)
        column.setContentsMargins(10, 10, 10, 10)
        heading = QLabel(title)
        heading.setObjectName("PreviewTitle")
        if title == "Flat Cutting Pattern":
            w.flat_title = heading
        column.addWidget(heading)
        column.addWidget(view, 1)
        caption_label = note(caption)
        column.addWidget(caption_label)
        if title == 'Flat Cutting Pattern':
            w.flat_dimensions = note('')
            column.addWidget(w.flat_dimensions)
        setattr(w, caption_name, caption_label)
        w.preview_splitter.addWidget(frame)
    w.preview_splitter.setSizes([500, 500])
    layout.addWidget(w.preview_splitter, 1)
    w.original_section = Disclosure("Original artwork")
    w.original.setMinimumHeight(140)
    w.original.setMaximumHeight(210)
    w.original_section.body.addWidget(w.original)
    layout.addWidget(w.original_section)
    w.profile_label = note("TOP = height 0 · Measurements and artwork position run down from the top.")
    layout.addWidget(w.profile_label)
    outer = QSplitter(Qt.Orientation.Horizontal)
    outer.setChildrenCollapsible(False)
    outer.addWidget(controls)
    outer.addWidget(work)
    outer.setSizes([370, 1000])
    w.setCentralWidget(outer)
    w.statusBar().showMessage("Choose your object and enter its measurements. Ctrl+O imports artwork.")
