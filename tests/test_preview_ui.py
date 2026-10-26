"""Native Qt integration: real renderer pixels, fallback, synchronization and reload."""

import json
from pathlib import Path
import time
import math

import numpy as np

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QVector3D, QImage
from PySide6.QtWidgets import QApplication

from wraplab.domain import Project
from wraplab.masks.model import Assignment, MaskGroup, source_identity
from wraplab.persistence import save_project
from wraplab.preview.scene import build_scene
from wraplab.preview.settings import options
from wraplab.svg import import_svg
from wraplab.ui.app import MainWindow, STYLE
from wraplab.ui.scene3d import SceneView, raster_texture
from wraplab.svg import convert
from wraplab.preview.scene import texture_svg


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    return app


def settle(app,window):
    deadline=time.monotonic()+45
    while window._busy or window._timer.isActive():
        app.processEvents()
        time.sleep(.01)
        if time.monotonic()>deadline:
            pytest.fail("Native preview timed out")
    for _ in range(4):
        app.processEvents()


@pytest.fixture
def window(app,tmp_path):
    window=MainWindow(tmp_path/"data")
    window.show()
    settle(app,window)
    window.import_file(Path(__file__).parent/"fixtures/lettering.svg")
    settle(app,window)
    yield window
    window.dirty=False
    window.close()
    app.processEvents()


def assign_masks(window):
    art=window.artwork
    assignment=Assignment(source_identity(art),(
        MaskGroup("MASK_A",tuple((si,tuple(range(len(art.shapes[si].subpaths)))) for si in (0,1))),
        MaskGroup("MASK_B",((2,tuple(range(len(art.shapes[2].subpaths)))),)),
        MaskGroup("MASK_C",((3,tuple(range(len(art.shapes[3].subpaths)))),)),
    ))
    settings=options(window.project.preview_options)
    settings["assignment"]=assignment.to_dict()
    window.preview_settings_changed(settings)


def test_real_gpu_pixels_preserve_orientation_colors_and_compound_opening(app):
    if app.platformName() not in {"windows","xcb","wayland"}:
        pytest.skip("A native display/OpenGL context is required for renderer pixel acceptance.")
    art=import_svg('''<svg width="20mm" height="20mm" viewBox="0 0 20 20">
    <path fill="red" fill-rule="evenodd" d="M1 1H9V19H1Z M3 4H7V16H3Z"/>
    <path fill="blue" d="M11 10H19V19H11Z"/></svg>''')
    p=Project()
    p.placement.width=p.placement.height=40
    p.placement.z=30
    view=SceneView()
    view.resize(500,600)
    view.set_scene(build_scene(p,art),options())
    view.show()
    for _ in range(10):
        app.processEvents()
    try:
        assert view.isValid() and not view.failure
        image=view.grabFramebuffer()
        matrix,_=view.matrices()
        locate=p.surface_mapper(20,20)
        def pixel(x,y):
            theta,z=locate(complex(x,y))
            r=p.object.surface().radius(z)
            point=matrix.map(QVector3D(r*math.sin(theta),50-z,r*math.cos(theta)))
            return image.pixelColor(round((point.x()+1)*image.width()/2),round((1-point.y())*image.height()/2))
        red,blue,hole=pixel(2,2),pixel(15,15),pixel(5,10)
        assert red.red()>220 and red.green()<40 and red.blue()<40
        assert blue.blue()>220 and blue.red()<40
        assert hole.red()>80 and abs(hole.red()-hole.green())<40
        for name in ("Left","Right","Rear","Seam","Front"):
            view.set_camera_view(name)
            app.processEvents()
            frame=view.grabFramebuffer()
            assert not frame.isNull()
            if name=="Rear":
                rgba=frame.convertToFormat(QImage.Format.Format_RGBA8888)
                pixels=np.frombuffer(rgba.bits(),dtype=np.uint8).reshape(rgba.height(),rgba.width(),4)
                assert not np.any((pixels[:,:,0]>220)&(pixels[:,:,1]<40)&(pixels[:,:,2]<40))
                assert not np.any((pixels[:,:,2]>220)&(pixels[:,:,0]<40)&(pixels[:,:,1]<40))
    finally:
        view.close()
        app.processEvents()


def test_normalized_texture_preserves_element_opacity_compositing(app):
    art=import_svg('<svg width="100mm" height="100mm" viewBox="0 0 100 100">'
        '<path d="M20 20H80V80H20Z" fill="red" stroke="black" stroke-width="20" opacity=".5"/></svg>')
    p=Project()
    p.object.diameter=300
    p.object.height=200
    p.placement.width=p.placement.height=100
    original=convert(art,p,original=True)
    image=raster_texture(texture_svg(original,100,100),1000)
    for x,y in ((50,50),(22,50),(15,50)):
        assert image.pixelColor(x*10,y*10).alpha() in {127,128}


def test_linked_mask_selection_independent_preview_and_ordinary_export(window,app,tmp_path):
    before=window.export_to(tmp_path/"before.svg")[1]
    assign_masks(window)
    settle(app,window)
    assert len(window._plan.masks)==3
    window.scene_view.maskSelected.emit("MASK_B")
    assert window.planner.mask.currentData()=="MASK_B"
    assert window.scene_view.settings["selected_mask"]=="MASK_B"
    selected=[item for item in window.development._mask_items if item.data(0)=="MASK_B"]
    assert selected and all(item.brush().color().alpha()>0 for item in selected)
    settings=options(window.project.preview_options)
    settings.update(method="independent",mask_layout=True,isolate=True)
    window.preview_settings_changed(settings)
    settle(app,window)
    assert window.flat_preview_stack.currentWidget() is window.mask_canvas
    assert len(window.mask_canvas.mask_items)==1
    assert window.mask_canvas.mask_items[0].data(0)=="MASK_B"
    displayed=window.mask_canvas.mask_items[0].sceneBoundingRect()
    selected_mask=next(mask for mask in window._plan.masks if mask.id=="MASK_B")
    points=[point for path in selected_mask.conversion.paths for contour in path.contours for point in contour.points]
    assert displayed.width()==pytest.approx(max(p.real for p in points)-min(p.real for p in points),abs=1e-6)
    assert displayed.height()==pytest.approx(max(p.imag for p in points)-min(p.imag for p in points),abs=1e-6)
    assert "ordinary Export SVG remains unchanged" in window.flat_caption.text()
    assert "Whole" in window.export_button.text()
    assert window.export_to(tmp_path/"after.svg")[1]==before
    assert window.planner.export_button.isEnabled()


def test_saved_preferences_reopen_and_old_2d_view_remains_available(window,app,tmp_path):
    assign_masks(window)
    settle(app,window)
    settings=options(window.project.preview_options)
    settings.update(camera=[35,20,1.5,.1,-.1],selected_mask="MASK_C",registration=True)
    window.preview_settings_changed(settings)
    path=tmp_path/"saved.wraplab"
    save_project(path,window.project)
    second=MainWindow(tmp_path/"second-data")
    second.load_file(path)
    second.show()
    settle(app,second)
    try:
        assert second.project.preview_options==json.loads(json.dumps(settings))
        assert second.planner.mask.currentData()=="MASK_C"
        second.preview_mode.setCurrentIndex(second.preview_mode.findData("2d"))
        assert second.front_view.isVisible()
        assert second.front_view.renderer.isValid()
        assert second.export_button.isEnabled()
    finally:
        second.dirty=False
        second.close()
        app.processEvents()


def test_renderer_failure_retains_2d_and_valid_export(window,tmp_path):
    expected=window.export_to(tmp_path/"before.svg")[1]
    window.renderer_failed("Simulated unavailable graphics context")
    assert window.front_view.isVisible()
    assert "3D unavailable" in window.front_caption.text()
    assert window.export_button.isEnabled()
    assert window.export_to(tmp_path/"after.svg")[1]==expected


def test_planner_domain_error_does_not_block_ordinary_export(window,app,tmp_path):
    expected=window.export_to(tmp_path/"before.svg")[1]
    assign_masks(window)
    settle(app,window)
    settings=options(window.project.preview_options)
    settings["margins_mm"]=[0,0,50,0]
    window.preview_settings_changed(settings)
    settle(app,window)
    assert window._plan is None
    assert "Mask planning paused" in window.planner.status.text()
    assert not window.planner.export_button.isEnabled()
    assert window.export_button.isEnabled()
    assert window.export_to(tmp_path/"after.svg")[1]==expected


def test_explicit_verified_grouping_preserves_current_measurements_and_placement(window,app,monkeypatch):
    import wraplab.masks.model as model
    art=window.artwork
    assignment=Assignment(source_identity(art),tuple(
        MaskGroup("MASK_"+str(i),((i,tuple(range(len(s.subpaths)))),)) for i,s in enumerate(art.shapes)))
    monkeypatch.setattr(model,"cantor_assignment",lambda candidate:assignment)
    before_object=window.project.to_dict()["object"]
    before_placement=window.project.to_dict()["placement"]
    window.apply_verified_grouping()
    settle(app,window)
    assert window.project.to_dict()["object"]==before_object
    assert window.project.to_dict()["placement"]==before_placement
    assert window.project.preview_options["assignment"]==assignment.to_dict()


def test_flat_reference_roles_and_visibility_never_enter_ordinary_export(window,app,tmp_path):
    assign_masks(window)
    settle(app,window)
    expected=window.export_to(tmp_path/"before.svg")[1]
    settings=options(window.project.preview_options)
    settings.update(registration=True,carriers=True,cut_paths=True,artwork=False)
    window.preview_settings_changed(settings)
    roles=[item.data(1) for item in window.development._mask_items]
    assert "REFERENCE_ONLY_DO_NOT_CUT" in roles
    assert "ARTWORK_SELECTION_OVERLAY" in roles
    assert all(item.brush().color().alpha()==0 for item in window.development._mask_items
               if item.data(1)=="ARTWORK_SELECTION_OVERLAY")
    assert window.export_to(tmp_path/"after.svg")[1]==expected


def test_unavailable_graphics_starts_without_a_3d_widget(app,tmp_path,monkeypatch):
    import wraplab.ui.scene3d as renderer
    monkeypatch.setattr(renderer,"renderer_available",lambda:False)
    window=MainWindow(tmp_path/"no-graphics-data")
    window.show()
    window.import_file(Path(__file__).parent/"fixtures/lettering.svg")
    settle(app,window)
    try:
        assert window.scene_view is None
        assert window.front_view.isVisible()
        assert "3D unavailable" in window.front_caption.text()
        assert window.export_button.isEnabled()
        window.export_to(tmp_path/"normal.svg")
    finally:
        window.dirty=False
        window.close()
        app.processEvents()


def test_flat_selection_aligns_with_intrinsic_svg_scene_and_rendered_pixels(window,app):
    assign_masks(window)
    settle(app,window)
    canvas=window.development
    overlay=next(item for item in canvas._mask_items
                 if item.data(0)=="MASK_B" and item.data(1)=="ARTWORK_SELECTION_OVERLAY")
    path=overlay.path()
    region=path.boundingRect()
    inside=None
    for x in np.linspace(region.left()+.3,region.right()-.3,25):
        for y in np.linspace(region.top()+.3,region.bottom()-.3,25):
            if path.contains(QRectF(x-.2,y-.2,.4,.4)):
                inside=QPointF(x,y)
                break
        if inside is not None:
            break
    assert inside is not None
    # Independently use the renderer's actual SVG viewport and item's intrinsic
    # size, rather than assuming an mm/px ratio or reusing the overlay transform.
    viewport=canvas.renderer.viewBoxF()
    bounds=canvas.item.boundingRect()
    local=QPointF(bounds.left()+(inside.x()-viewport.left())*bounds.width()/viewport.width(),
                  bounds.top()+(inside.y()-viewport.top())*bounds.height()/viewport.height())
    scene_point=canvas.item.mapToScene(local)
    assert overlay.contains(overlay.mapFromScene(scene_point))
    pixel=canvas.mapFromScene(scene_point)
    def color():
        image=canvas.viewport().grab().toImage()
        ratio=image.width()/canvas.viewport().width()
        return image.pixelColor(round(pixel.x()*ratio),round(pixel.y()*ratio))
    before=color()
    assert before.red()<90 and before.green()<110  # actual unselected vector ink
    window.select_mask("MASK_B")
    app.processEvents()
    after=color()
    assert after.red()>140 and after.red()>after.green()+25  # highlight at the same ink pixel
