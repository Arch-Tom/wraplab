from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


class Canvas(QGraphicsView):
    maskSelected = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#f3f6f8"))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.renderer = None
        self.svg_text = None
        self.item = None
        self.auto_fit = True
        self._mask_items = []
        self._mask_press = None

    def set_svg(self, text):
        renderer = QSvgRenderer(QByteArray(text.encode("utf-8")), self)
        if not renderer.isValid():
            renderer.deleteLater()
            raise ValueError("Preview renderer could not read the generated SVG.")
        self.scene().clear()
        self._mask_items = []
        if self.renderer:
            self.renderer.deleteLater()
        self.renderer = renderer
        self.svg_text = text
        self.item = QGraphicsSvgItem()
        self.item.setSharedRenderer(renderer)
        self.scene().addItem(self.item)
        self.scene().setSceneRect(self.item.boundingRect().adjusted(-5, -5, 5, 5))
        if self.auto_fit:
            self.fit()

    def set_message(self, text):
        self.scene().clear()
        self._mask_items = []
        if self.renderer:
            self.renderer.deleteLater()
        self.renderer = self.item = self.svg_text = None
        self.scene().addText(text)
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-8, -8, 8, 8))
        self.fit()

    def fit(self):
        self.auto_fit = True
        if not self.scene().itemsBoundingRect().isEmpty():
            self.fitInView(
                self.scene().itemsBoundingRect().adjusted(-3, -3, 3, 3),
                Qt.AspectRatioMode.KeepAspectRatio,
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_fit:
            self.fit()

    def wheelEvent(self, event):
        scale = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        if 0.01 < self.transform().m11() * scale < 1000:
            self.auto_fit = False
            self.scale(scale, scale)
        event.accept()

    def mousePressEvent(self, event):
        self._mask_press = event.position()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mask_press is not None and (event.position()-self._mask_press).manhattanLength()<4:
            item=self.itemAt(event.position().toPoint())
            if item is not None and isinstance(item.data(0),str):
                self.maskSelected.emit(item.data(0))
        self._mask_press=None
        super().mouseReleaseEvent(event)


class ProfileCanvas(Canvas):
    def set_surface(self, surface, points, placement, show_artwork=True):
        self.scene().clear()
        path = QPainterPath()
        # Preserve the exact endpoint: height * steps / steps can exceed height by one ULP.
        zs = [surface.height * (i / 160) for i in range(160)] + [surface.height]
        path.moveTo(-surface.radius(0), 0)
        for z in zs:
            path.lineTo(-surface.radius(z), z)
        for z in reversed(zs):
            path.lineTo(surface.radius(z), z)
        path.closeSubpath()
        self.scene().addPath(path, QPen(QColor("#476173"), 0.4), QColor("#e4ecf0"))
        if show_artwork:
            bottom, top = placement.z, placement.z + placement.height
            if 0 <= bottom <= top <= surface.height:
                region = QPainterPath()
                region.moveTo(-surface.radius(bottom), bottom)
                region_zs = [bottom] + [
                    bottom + (top - bottom) * (i / 80) for i in range(1, 80)
                ] + [top]
                for z in region_zs:
                    region.lineTo(-surface.radius(z), z)
                for z in reversed(region_zs):
                    region.lineTo(surface.radius(z), z)
                region.closeSubpath()
                self.scene().addPath(region, QPen(QColor("#138b72"), 0.25), QColor("#91d3bd"))
        for z, d in points:
            for x in [-d / 2, d / 2]:
                self.scene().addEllipse(
                    x - 0.7, z - 0.7, 1.4, 1.4, QPen(QColor("#345d72"), 0.1), QColor("#345d72")
                )
        self.scene().setSceneRect(self.scene().itemsBoundingRect().adjusted(-5, -5, 5, 5))
        self.fit()
