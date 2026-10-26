"""Native, offline Qt OpenGL viewport. No filesystem, script, network or export API."""

from array import array
from functools import lru_cache
import math
import time

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QImage, QMatrix4x4, QPainter, QSurfaceFormat,
                          QVector3D, QVector4D, QOpenGLContext, QOffscreenSurface)
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram, QOpenGLTexture
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtSvg import QSvgRenderer

from ..preview.settings import options

VERTEX = """
#version 120
attribute vec3 position;
attribute vec3 normal;
attribute vec2 uv;
uniform mat4 mvp;
uniform mat4 rotation;
varying vec3 n;
varying vec2 texcoord;
void main() { gl_Position=mvp*vec4(position,1.0); n=(rotation*vec4(normal,0.0)).xyz; texcoord=uv; }
"""
FRAGMENT = """
#version 120
uniform sampler2D image;
uniform int mode;
uniform vec4 color;
uniform float fade;
varying vec3 n;
varying vec2 texcoord;
void main() {
    if(mode==1) { vec4 c=texture2D(image,texcoord); if(c.a<0.004) discard; gl_FragColor=c; }
    else if(mode==2) gl_FragColor=color;
    else { float l=0.48+0.52*max(0.0,dot(normalize(n),normalize(vec3(-0.4,0.65,1.0))));
           gl_FragColor=vec4(color.rgb*l,1.0); }
    gl_FragColor.rgb=mix(vec3(0.96,0.975,0.98),gl_FragColor.rgb,fade);
}
"""


def raster_texture(svg, max_pixels=1536):
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    if not renderer.isValid():
        raise ValueError("Generated artwork texture could not be rendered; use the 2D preview.")
    size = renderer.viewBoxF().size()
    scale = max_pixels / max(size.width(), size.height())
    image = QImage(max(1, round(size.width()*scale)), max(1, round(size.height()*scale)),
                   QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        renderer.render(painter, QRectF(0, 0, image.width(), image.height()))
    finally:
        painter.end()
    return image


@lru_cache(maxsize=1)
def renderer_available():
    """Probe without making the main window depend on an OpenGL backing store."""
    fmt=QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    fmt.setVersion(2,1)
    context=QOpenGLContext()
    context.setFormat(fmt)
    if (not context.create() or context.isOpenGLES()
            or (context.format().majorVersion(),context.format().minorVersion())<(2,1)):
        return False
    surface=QOffscreenSurface()
    surface.setFormat(context.format())
    surface.create()
    try:
        return surface.isValid() and context.makeCurrent(surface)
    finally:
        context.doneCurrent()
        surface.destroy()


class SceneView(QOpenGLWidget):
    failed = Signal(str)
    cameraChanged = Signal(list)
    maskSelected = Signal(str)

    def __init__(self, parent=None):
        if not renderer_available():
            raise RuntimeError("Desktop OpenGL 2.1 is unavailable; use the retained 2D preview.")
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setVersion(2, 1)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)
        self.setMinimumSize(160, 180)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Interactive 3D object and artwork preview")
        self.setToolTip("Drag to orbit · right-drag or Shift-drag to pan · wheel to zoom · click artwork to select a mask")
        self.scene_data = None
        self.settings = options()
        self.program = None
        self.buffers, self.textures, self.images = {}, {}, {}
        self.pending = False
        self.failure = None
        self.last_frame_ms = 0
        self._press = self._last = None
        self._dragged = False
        self._context_timer = QTimer(self)
        self._context_timer.setSingleShot(True)
        self._context_timer.setInterval(600)
        self._context_timer.timeout.connect(self._check_context)

    def showEvent(self, event):
        super().showEvent(event)
        self._context_timer.start()

    def _check_context(self):
        if self.isVisible() and not self.isValid() and not self.failure:
            self._fail("A usable OpenGL context could not be created.")

    def set_scene(self, scene, settings):
        if scene.version != 1:
            raise ValueError("Unsupported 3D scene version; use 2D.")
        self.scene_data, self.settings, self.pending = scene, options(settings), True
        self.update()

    def set_options(self, settings):
        self.settings = options(settings)
        self.update()

    def initializeGL(self):
        try:
            self.functions = self.context().functions()
            self.functions.initializeOpenGLFunctions()
            self.program = QOpenGLShaderProgram(self)
            for kind, code in ((QOpenGLShader.ShaderTypeBit.Vertex, VERTEX),
                               (QOpenGLShader.ShaderTypeBit.Fragment, FRAGMENT)):
                if not self.program.addShaderFromSourceCode(kind, code):
                    raise RuntimeError("3D shader initialization failed. " + self.program.log()[:400])
            for index, name in enumerate(("position", "normal", "uv")):
                self.program.bindAttributeLocation(name, index)
            if not self.program.link():
                raise RuntimeError("3D shader link failed. " + self.program.log()[:400])
            self.context().aboutToBeDestroyed.connect(self.release_resources)
            self.pending = True
        except Exception as exc:
            self._fail(str(exc))

    def _fail(self, message):
        self.failure = message
        QTimer.singleShot(0, lambda: self.failed.emit("3D unavailable: " + message + " Existing 2D previews and ordinary export remain available."))

    def release_resources(self):
        self.makeCurrent()
        for buffer, _ in self.buffers.values():
            buffer.destroy()
        for texture in self.textures.values():
            texture.destroy()
        self.buffers, self.textures = {}, {}
        self.doneCurrent()

    def matrices(self):
        camera = self.settings["camera"]
        yaw, pitch, zoom, pan_x, pan_y = camera
        extent = self.scene_data.extent_mm if self.scene_data else 100
        half_height = extent * .62 / zoom
        half_width = half_height * max(1, self.width()) / max(1, self.height())
        projection = QMatrix4x4()
        projection.ortho(-half_width-pan_x*extent, half_width-pan_x*extent,
                         -half_height+pan_y*extent, half_height+pan_y*extent,
                         -extent*5, extent*5)
        rotation = QMatrix4x4()
        rotation.rotate(pitch, 1, 0, 0)
        rotation.rotate(yaw, 0, 1, 0)
        return projection * rotation, rotation

    def _upload(self):
        scene = self.scene_data
        for buffer, _ in self.buffers.values():
            buffer.destroy()
        for texture in self.textures.values():
            texture.destroy()
        self.buffers, self.textures, self.images = {}, {}, {}

        def store(key, vertices):
            data = array("f", (value for vertex in vertices for value in vertex)).tobytes()
            buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            if not buffer.create() or not buffer.bind():
                raise RuntimeError("3D vertex buffer could not be created.")
            buffer.allocate(data, len(data))
            buffer.release()
            self.buffers[key] = buffer, len(vertices)

        store("body", scene.body)
        if scene.artwork_mesh:
            store("artwork", scene.artwork_mesh)
        lines = {}
        for role, mask, points in scene.lines:
            key = role + ":" + mask
            vertices = lines.setdefault(key, [])
            for a, b in zip(points, points[1:], strict=False):
                vertices.extend(((*a, 0, 0, 0, 0, 0), (*b, 0, 0, 0, 0, 0)))
        for reference in scene.references:
            x,y,z = reference["xyz_mm"]
            size = scene.extent_mm*.012
            key = "registration:"+reference["mask"]
            lines.setdefault(key, []).extend([
                (x-size,y,z+.05,0,0,0,0,0), (x+size,y,z+.05,0,0,0,0,0),
                (x,y-size,z+.05,0,0,0,0,0), (x,y+size,z+.05,0,0,0,0,0)])
        for key, vertices in lines.items():
            store(key, vertices)
        for key, svg in scene.textures.items():
            image = raster_texture(svg)
            texture = QOpenGLTexture(image)
            texture.setMinificationFilter(QOpenGLTexture.Filter.LinearMipMapLinear)
            texture.setMagnificationFilter(QOpenGLTexture.Filter.Linear)
            texture.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
            self.textures[key], self.images[key] = texture, image
        self.pending = False

    def _draw(self, key, primitive=4):
        if key not in self.buffers:
            return
        buffer, count = self.buffers[key]
        buffer.bind()
        for index, size, offset in ((0,3,0), (1,3,12), (2,2,24)):
            self.program.enableAttributeArray(index)
            self.program.setAttributeBuffer(index, 0x1406, offset, size, 32)
        self.functions.glDrawArrays(primitive, 0, count)
        for index in range(3):
            self.program.disableAttributeArray(index)
        buffer.release()

    def paintGL(self):
        start = time.perf_counter()
        if self.failure or not self.program:
            return
        try:
            gl = self.functions
            # QPainter/compositor state is not guaranteed to survive a frame.
            gl.glDepthMask(True)
            gl.glDepthFunc(0x0201)
            gl.glColorMask(True,True,True,True)
            gl.glDisable(0x0C11)
            gl.glDisable(0x0B44)
            gl.glClearColor(.96, .975, .98, 1)
            gl.glClear(0x4000 | 0x0100)
            if not self.scene_data:
                return
            if self.pending:
                self._upload()
            gl.glEnable(0x0B71)  # depth testing, including artwork on the rear side
            gl.glEnable(0x0BE2)
            gl.glBlendFunc(0x0302, 0x0303)
            mvp, rotation = self.matrices()
            self.program.bind()
            self.program.setUniformValue("mvp", mvp)
            self.program.setUniformValue("rotation", rotation)
            # Explicit integer GL setters avoid PySide's int/QColor/float overload
            # ambiguity (a valid shader must never silently display an empty decal).
            gl.glUniform1i(self.program.uniformLocation("image"), 0)
            gl.glUniform1i(self.program.uniformLocation("mode"), 0)
            gl.glUniform1f(self.program.uniformLocation("fade"),1.0 if self.isEnabled() else .25)
            self.program.setUniformValue("color", QVector4D(.79,.83,.85,1))
            self._draw("body")
            selected = self.settings["selected_mask"]
            if selected not in self.textures:
                selected="all"
            if self.settings["artwork"] and self.textures:
                key = selected if self.settings["isolate"] and selected != "all" else "all"
                if key in self.textures:
                    gl.glUniform1i(self.program.uniformLocation("mode"), 1)
                    self.textures[key].bind(0)
                    self._draw("artwork")
                    self.textures[key].release()
                if selected+":highlight" in self.textures:
                    gl.glDepthFunc(0x0203)  # allow an identical selected overlay
                    self.textures[selected+":highlight"].bind(0)
                    self._draw("artwork")
                    self.textures[selected+":highlight"].release()
                    gl.glDepthFunc(0x0201)
            gl.glUniform1i(self.program.uniformLocation("mode"), 2)
            colors = {"seam":(.45,.55,.64,1), "bounds":(.60,.68,.71,1),
                      "carriers":(.12,.57,.50,1), "registration":(.74,.35,.12,1),
                      "cut_paths":(.84,.30,.20,1)}
            for key in self.buffers:
                if ":" not in key:
                    continue
                role, mask = key.split(":",1)
                if not self.settings.get(role) or (mask != "all" and selected not in {"all",mask}):
                    continue
                if role == "cut_paths" and ((selected == "all" and mask != "all") or
                                           (selected != "all" and mask == "all")):
                    continue
                self.program.setUniformValue("color", QVector4D(*colors[role]))
                self._draw(key, 1)
            self.program.release()
            gl.glDisable(0x0B71)
            painter = QPainter(self)
            painter.setPen(QColor("#526775"))
            painter.drawText(12, 22, "ORTHOGRAPHIC · 3D TECHNICAL PREVIEW")
            if self.settings["registration"]:
                painter.setPen(QColor("#a45b23"))
                for reference in self.scene_data.references:
                    if selected not in {"all",reference["mask"]}:
                        continue
                    xyz=reference["xyz_mm"]
                    radial=rotation.mapVector(QVector3D(xyz[0],0,xyz[2]))
                    if radial.z()<=0:
                        continue
                    position=mvp.map(QVector3D(*xyz))
                    painter.drawText(QPointF((position.x()+1)*self.width()/2+5,
                                            (1-position.y())*self.height()/2-5),
                                     reference["mask"]+" "+reference["label"])
            if self.scene_data.warnings:
                painter.drawText(QRectF(12,self.height()-52,self.width()-24,44),
                                 Qt.TextFlag.TextWordWrap, self.scene_data.warnings[0])
            painter.end()
            self.last_frame_ms = (time.perf_counter()-start)*1000
        except Exception as exc:
            self._fail(str(exc))

    def set_camera_view(self, name):
        yaw = {"Front":0, "Rear":180, "Left":90, "Right":-90, "Seam":180}
        if name == "Seam" and self.scene_data:
            # The first declared boundary is the actual selected coverage seam.
            points = next(p for role,_,p in self.scene_data.lines if role == "seam")
            yaw[name] = -math.degrees(math.atan2(points[0][0],points[0][2]))
        self.settings["camera"] = [yaw.get(name,0), 0, 1, 0, 0]
        self.cameraChanged.emit(self.settings["camera"][:])
        self.update()

    def wheelEvent(self, event):
        camera = self.settings["camera"][:]
        camera[2] = min(8,max(.2,camera[2]*(1.12 if event.angleDelta().y()>0 else 1/1.12)))
        self.settings["camera"] = camera
        self.cameraChanged.emit(camera)
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        self._press = self._last = event.position()
        self._dragged = False
        event.accept()

    def mouseMoveEvent(self, event):
        if self._last is None:
            return
        delta = event.position()-self._last
        self._last = event.position()
        self._dragged |= (event.position()-self._press).manhattanLength()>4
        camera = self.settings["camera"][:]
        if event.buttons() & Qt.MouseButton.RightButton or event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            camera[3] = min(4,max(-4,camera[3]+delta.x()/max(1,self.width())/camera[2]))
            camera[4] = min(4,max(-4,camera[4]+delta.y()/max(1,self.height())/camera[2]))
        else:
            camera[0] = (camera[0]+delta.x()*.5+180)%360-180
            camera[1] = min(85,max(-85,camera[1]+delta.y()*.5))
        self.settings["camera"] = camera
        self.cameraChanged.emit(camera)
        self.update()

    def mouseReleaseEvent(self, event):
        if not self._dragged:
            mask = self.pick_mask(event.position())
            if mask:
                self.maskSelected.emit(mask)
        self._last = None

    def pick_mask(self, point):
        """Barycentric hit test of the displayed surface texture; holes stay unselectable."""
        if not self.scene_data or not self.images:
            return None
        matrix, rotation = self.matrices()
        best = None
        vertices = self.scene_data.artwork_mesh
        for i in range(0,len(vertices),3):
            tri = vertices[i:i+3]
            normal = rotation.mapVector(QVector3D(*tri[0][3:6]))
            if normal.z() <= 0:
                continue
            p = [matrix.map(QVector3D(*v[:3])) for v in tri]
            screen = [QPointF((v.x()+1)*self.width()/2,(1-v.y())*self.height()/2) for v in p]
            a,b,c = screen
            det = (b.y()-c.y())*(a.x()-c.x())+(c.x()-b.x())*(a.y()-c.y())
            if abs(det)<1e-10:
                continue
            u=((b.y()-c.y())*(point.x()-c.x())+(c.x()-b.x())*(point.y()-c.y()))/det
            v=((c.y()-a.y())*(point.x()-c.x())+(a.x()-c.x())*(point.y()-c.y()))/det
            w=1-u-v
            if min(u,v,w)<0:
                continue
            depth=sum(weight*vertex.z() for weight,vertex in zip((u,v,w),p, strict=False))
            if best is None or depth < best[0]:
                uv=[sum(weight*vertex[j] for weight,vertex in zip((u,v,w),tri, strict=False)) for j in (6,7)]
                best=(depth,uv)
        if best:
            for key,image in self.images.items():
                if key == "all" or ":" in key:
                    continue
                u,v=best[1]
                x,y=min(image.width()-1,max(0,int(u*image.width()))),min(image.height()-1,max(0,int(v*image.height())))
                if image.pixelColor(x,y).alpha()>20:
                    return key
        return None
