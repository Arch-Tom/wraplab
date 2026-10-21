"""Render separate reference sheets at their SVG millimeter size, never cut files."""

import json
import re
import xml.etree.ElementTree as ET

from PySide6.QtCore import QMarginsF, QRectF, QSizeF
from PySide6.QtGui import (
    QGuiApplication,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QTextDocument,
)
from PySide6.QtSvg import QSvgRenderer


def printables(output):
    application = QGuiApplication.instance() or QGuiApplication([])
    audit = []
    for path in sorted((output / "REFERENCE_ONLY_DO_NOT_CUT").glob("*.svg")):
        root = ET.parse(path).getroot()
        width, height = [float(root.get(k)[:-2]) for k in ["width", "height"]]
        writer = QPdfWriter(str(path.with_suffix(".pdf")))
        writer.setTitle("REFERENCE ONLY — DO NOT CUT / print at actual size")
        writer.setResolution(144)
        writer.setPageSize(QPageSize(QSizeF(width, height), QPageSize.Unit.Millimeter))
        writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            raise ValueError("Invalid reference SVG")
        painter = QPainter(writer)
        if not painter.isActive():
            raise ValueError("Unable to create reference PDF")
        # Render content at exact physical size despite Qt's rounded media box.
        renderer.render(painter, QRectF(0, 0, width * 144 / 25.4, height * 144 / 25.4))
        painter.end()
        # The PDF media box must preserve size; raster/printer checks remain downstream.
        assert abs(writer.pageLayout().fullRect(QPageLayout.Unit.Millimeter).width() - width) < 0.01
        assert (
            abs(writer.pageLayout().fullRect(QPageLayout.Unit.Millimeter).height() - height) < 0.01
        )
        del writer
        media = re.search(rb"/MediaBox\s*\[([^]]+)\]", path.with_suffix(".pdf").read_bytes())
        assert media
        box = [float(n) for n in media[1].split()]
        page_mm = [(box[2] - box[0]) * 25.4 / 72, (box[3] - box[1]) * 25.4 / 72]
        assert max(abs(a - b) for a, b in zip(page_mm, [width, height], strict=True)) < 0.18
        audit.append(
            {
                "reference": path.name,
                "svg_mm": [width, height],
                "pdf_media_mm": page_mm,
                "rendering": "Exact SVG physical content dimensions; Qt media box rounds to nearest point; blank margins absorb rounding",
                "operator_X_Y_calibration": "PENDING",
            }
        )
    writer = QPdfWriter(str(output / "SHOP-TEST-GUIDE.pdf"))
    writer.setTitle("EXPERIMENTAL — NOT PRODUCTION APPROVED — shop test guide")
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(12, 12, 12, 12))
    document = QTextDocument()
    document.setMarkdown((output / "SHOP-TEST-GUIDE.md").read_text())
    document.print_(writer)
    (output / "printable-reference-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    # Keep the application alive until all Qt paint devices are finalized.
    assert application is not None
