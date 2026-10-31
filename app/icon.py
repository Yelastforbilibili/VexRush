"""程序图标：不依赖外部图片文件，直接用 QPainter 画出来。"""
from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen,
                         QPixmap, QPolygonF)

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)

_ARROW = ((33.0, 15.0), (33.0, 76.0), (47.0, 62.0), (56.0, 84.0),
          (66.0, 79.0), (57.0, 58.0), (74.0, 58.0))


def icon_pixmap(size: int = 64) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    scale = size / 100.0
    painter.scale(scale, scale)

    # 底板
    body = QRectF(4.0, 4.0, 92.0, 92.0)
    radius = max(18.0, 92.0 * 0.24)
    gradient = QLinearGradient(0.0, 4.0, 0.0, 96.0)
    gradient.setColorAt(0.0, QColor("#3b82f6"))
    gradient.setColorAt(1.0, QColor("#1d4ed8"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(body, radius, radius)

    # 白色光标
    path = QPainterPath()
    first = _ARROW[0]
    path.moveTo(QPointF(*first))
    for point in _ARROW[1:]:
        path.lineTo(QPointF(*point))
    path.closeSubpath()

    shadow = QPainterPath(path)
    painter.save()
    painter.translate(0.0, 1.6)
    painter.setBrush(QBrush(QColor(0, 0, 0, 46)))
    painter.drawPath(shadow)
    painter.restore()

    painter.setBrush(QBrush(QColor("#ffffff")))
    painter.setPen(QPen(QColor(15, 23, 42, 40), 1.0))
    painter.drawPath(path)

    # 橙色小点
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#f59e0b")))
    painter.drawEllipse(QRectF(78.0, 78.0, 14.0, 14.0))
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(icon_pixmap(size))
    return icon
