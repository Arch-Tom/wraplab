"""Progressive mask planning controls and a separate, true-scale mask inspection view."""

import json
from pathlib import Path
import xml.etree.ElementTree as ET

from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtGui import QColor, QPainterPath, QPen, QTransform
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
                              QLabel, QPushButton, QVBoxLayout, QWidget)

from ..masks.model import assignment_from_dict, cantor_assignment
from ..masks.exporter import mask_svg
from ..preview.settings import options
from .views import Canvas


class PlanningPanel(QWidget):
    changed = Signal(dict)
    historicalRequested = Signal()
    groupingRequested = Signal()
    exportRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values=options()
        self.loading=False
        self.artwork=None
        layout=QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        self.mask=QComboBox()
        self.mask.setAccessibleName("Selected physical mask")
        self.method=QComboBox()
        self.method.addItem("Split existing compensation", "global-split")
        self.method.addItem("Independent fit — EXPERIMENTAL", "independent")
        self.method.setAccessibleName("Mask compensation method")
        form=QFormLayout()
        form.addRow("Inspect mask",self.mask)
        form.addRow("Method",self.method)
        layout.addLayout(form)
        self.mask.currentIndexChanged.connect(self._changed)
        self.method.currentIndexChanged.connect(self._changed)
        self.toggles={}
        for title,key in (("Isolate selected mask","isolate"),("Show separate flat masks","mask_layout"),
                          ("Artwork","artwork"),("Cut contour overlay (preview)","cut_paths"),
                          ("Carrier edges (reference only)","carriers"),("Registration references","registration"),
                          ("Coverage seams (3D)","seam"),("Measured object limits (3D)","bounds")):
            check=QCheckBox(title)
            self.toggles[key]=check
            check.toggled.connect(self._changed)
            layout.addWidget(check)
        self.margins=[]
        grid=QGridLayout()
        from .workspace import MeasurementSpinBox
        for i,name in enumerate(("Left","Right","Top","Bottom")):
            spin=MeasurementSpinBox()
            spin.setRange(0,50)
            spin.setDecimals(2)
            spin.setSuffix(" mm")
            spin.setAccessibleName(name+" handling margin")
            spin.valueChanged.connect(self._changed)
            self.margins.append(spin)
            grid.addWidget(QLabel(name),i//2,(i%2)*2)
            grid.addWidget(spin,i//2,(i%2)*2+1)
        layout.addWidget(QLabel("Handling margins · front reference plane"))
        layout.addLayout(grid)
        self.datum_enabled=QCheckBox("Record physical TOP height above a common datum")
        self.datum=MeasurementSpinBox()
        self.datum.setRange(-1_000_000,1_000_000)
        self.datum.setDecimals(3)
        self.datum.setSuffix(" mm")
        self.datum.setAccessibleName("Physical measured TOP height above operator datum")
        self.datum_enabled.toggled.connect(self._changed)
        self.datum.valueChanged.connect(self._changed)
        layout.addWidget(self.datum_enabled)
        layout.addWidget(self.datum)
        hint=QLabel("Zero margins add no handling allowance. Edges are references, never automatic trim cuts. Missing measurements are not extrapolated.")
        hint.setWordWrap(True)
        hint.setObjectName("Help")
        layout.addWidget(hint)
        self.status=QLabel("Import artwork to inspect masks. Unknown SVGs need an explicit component assignment.")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.grouping=QPushButton("Use verified 3-mask grouping · keep measurements")
        self.grouping.clicked.connect(self.groupingRequested)
        layout.addWidget(self.grouping)
        self.historical=QPushButton("Apply historical CantorLand bell trial")
        self.historical.setToolTip("Explicitly replace object/placement with the unapproved historical four-station, four-inch trial. Save current work first.")
        self.historical.clicked.connect(self.historicalRequested)
        layout.addWidget(self.historical)
        load=QPushButton("Load component assignment JSON…")
        load.clicked.connect(self.load_assignment)
        layout.addWidget(load)
        self.ack=QCheckBox("I understand independent output is experimental")
        layout.addWidget(self.ack)
        self.export_button=QPushButton("Export separate mask SVGs…")
        self.export_button.clicked.connect(self.exportRequested)
        self.export_button.setEnabled(False)
        layout.addWidget(self.export_button)

    def restore(self, values, artwork):
        self.loading=True
        previous=self.values
        self.values=options(values)
        if previous["assignment"]!=self.values["assignment"] or previous["method"]!=self.values["method"]:
            self.ack.setChecked(False)
        self.artwork=artwork
        assignment=self.values["assignment"]
        groups=assignment_from_dict(assignment).groups if assignment else ()
        expected=[("All masks","all")]+[(g.id,g.id) for g in groups]
        if [self.mask.itemData(i) for i in range(self.mask.count())] != [v for _,v in expected]:
            self.mask.clear()
            for title,value in expected:
                self.mask.addItem(title,value)
        self.mask.setCurrentIndex(max(0,self.mask.findData(self.values["selected_mask"])))
        self.method.setCurrentIndex(self.method.findData(self.values["method"]))
        for key,check in self.toggles.items():
            check.setChecked(self.values[key])
        self.toggles["mask_layout"].setEnabled(self.values["method"]!="independent")
        for spin,value in zip(self.margins,self.values["margins_mm"], strict=False):
            spin.setValue(value)
        self.datum_enabled.setChecked(self.values["physical_top_datum_mm"] is not None)
        self.datum.setValue(self.values["physical_top_datum_mm"] or 0)
        self.datum.setEnabled(self.datum_enabled.isChecked())
        recognized=False
        if artwork:
            try:
                cantor_assignment(artwork)
                recognized=True
            except ValueError:
                pass
        self.historical.setVisible(recognized)
        self.grouping.setVisible(recognized and not assignment)
        self.ack.setVisible(self.values["method"]=="independent")
        self.loading=False

    def _changed(self, *_):
        if self.loading:
            return
        previous=self.values["method"]
        self.values.update(selected_mask=self.mask.currentData() or "all",method=self.method.currentData(),
                           margins_mm=[spin.value() for spin in self.margins])
        self.values.update({key:check.isChecked() for key,check in self.toggles.items()})
        self.values["physical_top_datum_mm"]=self.datum.value() if self.datum_enabled.isChecked() else None
        if previous!=self.values["method"] and self.values["method"]=="independent":
            self.values["mask_layout"]=True
        self.changed.emit(options(self.values))

    def set_plan(self, plan, error=None):
        self.export_button.setEnabled(plan is not None)
        if error:
            self.status.setText("Mask planning paused: "+error+" Ordinary export is unchanged.")
        elif plan:
            rows=[f"{m.id}: extension {max(0,m.strain[1])*100:.3f}%, compression {max(0,-m.strain[0])*100:.3f}%"
                  for m in plan.masks]
            self.status.setText(("Global mapping retained; separation does not improve its strain.\n"
                                 if plan.method=="global-split" else
                                 "EXPERIMENTAL · one combined Hebrew support fit.\n")+
                                "\n".join(rows)+"\nModeled support only; film, transfer tape and adhesion are unvalidated.")
            selected=self.values["selected_mask"]
            mask=next((m for m in plan.masks if m.id==selected),None)
            if mask and self.values["registration"]:
                self.status.setText(self.status.text()+"\n"+"\n".join(
                    f"{r['label']}: down {r['z_down_mm']:.3f} mm; tape arc {r['signed_front_arc_mm']:+.3f} mm"
                    for r in mask.references))

    def load_assignment(self):
        filename,_=QFileDialog.getOpenFileName(self,"Open source-bound mask assignment","","JSON (*.json)")
        if not filename:
            return
        try:
            path=Path(filename)
            if path.stat().st_size>200_000:
                raise ValueError("Assignment exceeds 200 KB.")
            assignment=assignment_from_dict(json.loads(path.read_text(encoding="utf-8")))
            self.values["assignment"]=assignment.to_dict()
            self.values["selected_mask"]="all"
            self.changed.emit(options(self.values))
        except (ValueError,OSError) as exc:
            self.status.setText(str(exc))


class MaskCanvas(Canvas):
    """Visual separation only; item translations are never fed back to cutting coordinates."""

    def __init__(self):
        super().__init__()
        self.renderers=[]
        self.mask_items=[]

    def set_plan(self, plan, project, selected="all", isolate=False, settings=None):
        settings=options(settings)
        self.scene().clear()
        self.mask_items=[]
        for renderer in self.renderers:
            renderer.deleteLater()
        self.renderers=[]
        self.svg_text=None
        y=0
        for mask in plan.masks:
            if isolate and selected not in {"all",mask.id}:
                continue
            text,_=mask_svg(mask,plan,project)
            root=ET.fromstring(text)
            width,height=[float(root.get(k)[:-2]) for k in ("width","height")]
            # Preview units are canonical mm; QSvgRenderer otherwise reports px.
            root.set("width",str(width))
            root.set("height",str(height))
            if selected==mask.id:
                for node in root.findall(".//{*}path"):
                    node.set("fill","#d88823")
            renderer=QSvgRenderer(QByteArray(ET.tostring(root)),self)
            if not renderer.isValid():
                raise ValueError("Mask preview could not render its validated vector output.")
            item=QGraphicsSvgItem()
            item.setSharedRenderer(renderer)
            intrinsic=item.boundingRect()
            item.setTransform(QTransform.fromScale(width/intrinsic.width(),height/intrinsic.height()))
            item.setData(0,mask.id)
            label=self.scene().addText(f"{mask.id} · {width:.3f} × {height:.3f} mm")
            label.setScale(.3)
            label.setPos(0,y)
            y+=8
            item.setPos(0,y)
            item.setVisible(settings["artwork"])
            self.scene().addItem(item)
            self.mask_items.append(item)
            self.renderers.append(renderer)
            origin=complex(*json.loads(root.find("{*}metadata").text)["page_origin_mm"])
            offset=origin-complex(0,y)
            if settings["carriers"]:
                line=polyline(mask.carrier_flat,offset,closed=True)
                guide=self.scene().addPath(line,reference_pen("#218d79"))
                guide.setData(0,mask.id)
                guide.setData(1,"REFERENCE_ONLY_DO_NOT_CUT")
            if settings["registration"]:
                for reference in mask.references:
                    point=reference_flat(mask,reference,project)-offset
                    mark=self.scene().addPath(cross(point),reference_pen("#b56e25"))
                    mark.setData(0,mask.id)
                    mark.setData(1,"REFERENCE_ONLY_DO_NOT_CUT")
                    text=self.scene().addText(reference["label"])
                    text.setScale(.25)
                    text.setPos(point.real+1,point.imag-4)
            if settings["cut_paths"]:
                for vector in mask.conversion.paths:
                    line=QPainterPath()
                    for contour in vector.contours:
                        line.addPath(polyline(contour.points,offset,contour.closed))
                    self.scene().addPath(line,reference_pen("#c85c3f"))
            y+=height+14
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-5,-5,5,5))
        self.fit()


def reference_pen(color):
    pen=QPen(QColor(color),0)
    pen.setCosmetic(True)
    return pen


def polyline(points,offset=0j,closed=False):
    path=QPainterPath()
    for i,point in enumerate(points):
        point-=offset
        if i==0:
            path.moveTo(point.real,point.imag)
        else:
            path.lineTo(point.real,point.imag)
    if closed:
        path.closeSubpath()
    return path


def cross(point):
    path=QPainterPath()
    path.moveTo(point.real-1.2,point.imag)
    path.lineTo(point.real+1.2,point.imag)
    path.moveTo(point.real,point.imag-1.2)
    path.lineTo(point.real,point.imag+1.2)
    return path


def reference_flat(mask,reference,project,original=False):
    index=mask.references.index(reference)
    return (mask.original_reference_points if original else mask.flat_reference_points)[index]


def apply_visibility(canvas,settings):
    if not canvas.svg_text or canvas.renderer is None:
        return
    # Display copy only: the original normalized document remains the export reference.
    root=ET.fromstring(canvas.svg_text)
    art=root.find("{*}g[@id='Artwork']")
    if art is not None and not settings["artwork"]:
        art.set("display","none")
    canvas.renderer.load(QByteArray(ET.tostring(root)))


def highlight_global(canvas, plan, project, settings, original=False):
    for item in getattr(canvas,"_mask_items",[]):
        if item.scene():
            canvas.scene().removeItem(item)
    canvas._mask_items=[]
    if not canvas.svg_text or not plan:
        return
    root=ET.fromstring(canvas.svg_text)
    metadata=root.find("{*}metadata")
    if metadata is None:
        return
    offset=complex(*json.loads(metadata.text)["page_origin_mm"])
    # Export coordinates use mm/viewBox units; the SVG item's intrinsic bounds
    # use pixels, including Qt's intrinsic-size rounding. Children share the SVG
    # item's scene transform; this maps their actual viewBox into its local bounds.
    view_box=canvas.renderer.viewBoxF()
    bounds=canvas.item.boundingRect()
    scale_x=bounds.width()/view_box.width()
    scale_y=bounds.height()/view_box.height()
    transform=QTransform(scale_x,0,0,scale_y,
                         bounds.left()-view_box.left()*scale_x,
                         bounds.top()-view_box.top()*scale_y)

    def attach(item,mask,role,z):
        item.setParentItem(canvas.item)
        item.setTransform(transform)
        item.setZValue(z)
        item.setData(0,mask)
        item.setData(1,role)
        canvas._mask_items.append(item)
    selected=settings["selected_mask"]
    for mask in plan.masks:
        for vector in (mask.original.paths if original else mask.conversion.paths):
            path=QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill if vector.fill_rule=="evenodd" else Qt.FillRule.WindingFill)
            for contour in vector.contours:
                if not contour.points:
                    continue
                points=[q-offset for q in contour.points]
                path.moveTo(points[0].real,points[0].imag)
                for q in points[1:]:
                    path.lineTo(q.real,q.imag)
                path.closeSubpath()
            visible=settings["artwork"] and selected==mask.id
            pen=reference_pen("#c85c3f") if settings["cut_paths"] and selected in {"all",mask.id} else QPen(Qt.PenStyle.NoPen)
            item=canvas.scene().addPath(path,pen,
                 QColor(224,142,40,190) if visible else QColor(0,0,0,0))
            attach(item,mask.id,"ARTWORK_SELECTION_OVERLAY",10)
        if selected not in {"all",mask.id}:
            continue
        if settings["carriers"]:
            if original:
                left,top,right,bottom=mask.support
                shift=complex(project.placement.x-project.placement.width/2,project.placement.z)
                border=[complex(left,top)-shift,complex(right,top)-shift,
                        complex(right,bottom)-shift,complex(left,bottom)-shift]
            else:
                border=mask.carrier_flat
            item=canvas.scene().addPath(polyline(border,offset,True),reference_pen("#218d79"))
            attach(item,mask.id,"REFERENCE_ONLY_DO_NOT_CUT",11)
        if settings["registration"]:
            for reference in mask.references:
                point=reference_flat(mask,reference,project,original)-offset
                item=canvas.scene().addPath(cross(point),reference_pen("#b56e25"))
                attach(item,mask.id,"REFERENCE_ONLY_DO_NOT_CUT",12)
    canvas.scene().setSceneRect(canvas.scene().itemsBoundingRect().adjusted(-5,-5,5,5))
    if canvas.auto_fit:
        canvas.fit()
