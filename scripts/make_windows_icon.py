"""Render the project's visible SVG identity into a conventional multi-size ICO."""

from pathlib import Path
import struct

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]


def main():
    renderer = QSvgRenderer(str(ROOT / "packaging/windows/wraplab.svg"))
    assert renderer.isValid()
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    for size in sizes:
        picture = QImage(size, size, QImage.Format.Format_ARGB32)
        picture.fill(0)
        painter = QPainter(picture)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert picture.save(buffer, "PNG")
        images.append(bytes(data))
    offset = 6 + 16 * len(images)
    headers = []
    for size, data in zip(sizes, images, strict=True):
        dimension = size if size < 256 else 0
        headers.append(struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    target = ROOT / "packaging/windows/wraplab.ico"
    target.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + b"".join(headers + images))
    print(target)


if __name__ == "__main__":
    main()
