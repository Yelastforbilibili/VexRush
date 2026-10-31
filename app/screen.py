"""屏幕相关的小工具：取可用区域、把窗口框在屏幕里。

单独拎出来是因为悬浮窗、主窗口、动画遮罩都要用，放在一起免得互相抄。
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QPoint, QRect


def screen_of(widget) -> Optional[QRect]:
    """控件所在的屏幕可用区域（去掉任务栏）；拿不到就返回 None。"""
    try:
        screen = widget.screen()
    except (RuntimeError, AttributeError):
        screen = None
    if screen is None:
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
    if screen is None:
        return None
    return screen.availableGeometry()


def clamp_point(pos: QPoint, size, area: Optional[QRect]) -> QPoint:
    """把「窗口左上角」夹进可用区域；窗口比屏幕大时贴左上。"""
    if area is None:
        return pos
    max_x = max(area.left(), area.right() - size[0] + 1)
    max_y = max(area.top(), area.bottom() - size[1] + 1)
    return QPoint(min(max(pos.x(), area.left()), max_x),
                  min(max(pos.y(), area.top()), max_y))


def clamp_widget(widget) -> bool:
    """把控件夹回屏幕，返回是否挪过。"""
    area = screen_of(widget)
    if area is None:
        return False
    current = widget.pos()
    fixed = clamp_point(current, (widget.width(), widget.height()), area)
    if fixed == current:
        return False
    widget.move(fixed)
    return True
