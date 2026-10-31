"""悬浮显示的右键菜单：自己画的圆角深色菜单（不用系统默认那层方块窗）。"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QMenu

from .i18n import tr


class OverlayMenu(QMenu):
    """悬浮窗右键菜单：无边框圆角、跟随悬浮窗配色。"""

    def __init__(self, cfg: OverlayConfig, accent: QColor, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet(self._qss(cfg, accent))

    @staticmethod
    def _qss(cfg: OverlayConfig, accent: QColor) -> str:
        bg = QColor(cfg.bg_color)
        fg = QColor(cfg.fg_color)
        radius = max(6, int(cfg.radius))
        hover = QColor(accent)
        return """
QMenu {
    background-color: rgba(%d, %d, %d, %d);
    border: 1px solid rgba(%d, %d, %d, 36);
    border-radius: %dpx;
    padding: 6px;
    color: rgba(%d, %d, %d, 235);
}
QMenu::item {
    padding: 6px 22px 6px 10px;
    border-radius: 6px;
    margin: 1px 2px;
    color: rgba(%d, %d, %d, 235);
}
QMenu::item:disabled {
    color: rgba(%d, %d, %d, 110);
}
QMenu::item:selected {
    background-color: rgba(%d, %d, %d, 56);
    color: rgba(%d, %d, %d, 255);
}
QMenu::separator {
    height: 1px;
    margin: 5px 10px;
    background-color: rgba(%d, %d, %d, 28);
}
""" % (bg.red(), bg.green(), bg.blue(), int(250 * cfg.opacity / 100.0),
       fg.red(), fg.green(), fg.blue(), radius,
       fg.red(), fg.green(), fg.blue(),
       fg.red(), fg.green(), fg.blue(),
       fg.red(), fg.green(), fg.blue(),
       hover.red(), hover.green(), hover.blue(),
       fg.red(), fg.green(), fg.blue(),
       fg.red(), fg.green(), fg.blue())
