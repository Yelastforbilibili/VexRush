# -*- coding: utf-8 -*-
"""外观切换的「幕布」。

主题重建本身要 90~140ms（重建样式表 + 重新 polish 所有控件），这段时间界面必然
卡一下，靠修代码消不掉。这里的做法是障眼法：真正重建的那一瞬间用一层「模糊的
旧画面 + 颜色渐变」整个盖住，重建完再把幕布淡出，露出已经换好的新配色。

配合 `overlay.play_out()/play_in()` 用同一套柔焦动画，观感上就是「旧界面淡出 →
颜色渐变 → 新界面淡入」。
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import (QEasingCurve, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt,
                          QTimer, QVariantAnimation)
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QWidget

from . import i18n
from .i18n import tr

FADE_IN_MS = 110          # 幕布盖上来
HOLD_MS = 70              # 盖好之后再动手，保证第一帧不抖
FADE_OUT_MS = 230         # 幕布淡出
TINT_TRAVEL_MS = 190      # 颜色从旧配色走到新配色


def _blurred_snapshot(area: QRect, downsample: int = 8) -> Optional[QPixmap]:
    """抓一块屏幕再缩下去放大，得到一个够用的模糊底图。"""
    screen = QApplication.primaryScreen()
    if screen is None or area.width() <= 0 or area.height() <= 0:
        return None
    try:
        raw = screen.grabWindow(0, area.x(), area.y(), area.width(), area.height())
    except Exception:
        return None
    if raw.isNull():
        return None
    small = raw.scaled(
        max(1, raw.width() // downsample),
        max(1, raw.height() // downsample),
        Qt.IgnoreAspectRatio,
        Qt.SmoothTransformation,
    )
    return small.scaled(raw.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


class _Curtain(QWidget):
    """全屏盖住的一层：模糊底图 + 纯色蒙版（蒙版颜色会从旧配色渐变到新配色）。"""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self._backdrop: Optional[QPixmap] = None
        self._tint = QColor(0, 0, 0)
        self._contrast = QColor(20, 20, 20)
        self._fade = 0.0
        self._label = tr("applying_appearance")

    # ---------------------------------------------------------------- 外部接口
    def prepare(self, area: QRect, tint: QColor, contrast: Optional[QColor] = None) -> None:
        self._backdrop = _blurred_snapshot(area)
        self._tint = QColor(tint)
        if contrast is not None:
            self._contrast = QColor(contrast)
        self.setGeometry(area)

    def set_tint(self, color: QColor) -> None:
        self._tint = QColor(color)
        self.update()

    def tint(self) -> QColor:
        return QColor(self._tint)

    def set_fade(self, value: float) -> None:
        self._fade = max(0.0, min(1.0, float(value)))
        self.update()

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:
        if self._fade <= 0.002:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = QRectF(self.rect())
        painter.setOpacity(self._fade)
        if self._backdrop is not None and not self._backdrop.isNull():
            painter.drawPixmap(self.rect(), self._backdrop)
        # 蒙版：中心稍微淡一点，边缘重一点，盖住细节又不至于像黑板
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base = QColor(self._tint)
        base.setAlphaF(0.80)
        edge = QColor(self._tint)
        edge.setAlphaF(0.92)
        gradient.setColorAt(0.0, base)
        gradient.setColorAt(1.0, edge)
        painter.fillRect(rect, gradient)
        # 居中的「转圈 + 文字」小药丸，配色跟界面文字反着来，深浅主题都看得见
        painter.setOpacity(self._fade)
        center = rect.center()
        font = QFont(self.font())
        font.setPointSizeF(9.5)
        painter.setFont(font)
        text = self._label
        metrics = painter.fontMetrics()
        text_width = min(int(metrics.width(text)) + 4, 260)
        pill_width = text_width + 62
        pill_height = 46
        pill = QRectF(center.x() - pill_width / 2.0, center.y() - pill_height / 2.0,
                      pill_width, pill_height)
        pill_color = QColor(self._contrast)
        pill_color.setAlphaF(0.13)
        painter.setPen(Qt.NoPen)
        painter.setBrush(pill_color)
        painter.drawRoundedRect(pill, pill_height / 2.0, pill_height / 2.0)

        radius = 9.0
        ring_center = QPointF(pill.left() + 26.0, pill.center().y())
        ring_rect = QRectF(ring_center.x() - radius, ring_center.y() - radius, radius * 2, radius * 2)
        track = QColor(self._contrast)
        track.setAlphaF(0.20)
        pen = painter.pen()
        pen.setColor(track)
        pen.setWidthF(2.4)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(ring_rect)
        arc = QColor(self._contrast)
        arc.setAlphaF(0.92)
        pen.setColor(arc)
        painter.setPen(pen)
        painter.drawArc(ring_rect, int(-self._spin * 16), 110 * 16)

        label_color = QColor(self._contrast)
        label_color.setAlphaF(0.94)
        painter.setPen(label_color)
        painter.drawText(QRectF(ring_center.x() + radius + 10.0, pill.top(),
                                pill.right() - (ring_center.x() + radius + 10.0) - 14.0, pill_height),
                         Qt.AlignVCenter | Qt.AlignLeft, text)

    _spin = 0.0

    def advance(self, degrees: float) -> None:
        self._spin = (self._spin + degrees) % 360.0
        self.update()


class ThemeSwitcher(QObject):
    """把「抓图 → 盖幕布 → 重建 → 淡出」这条链路串起来。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._curtain: Optional[_Curtain] = None
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(16)
        self._spin_timer.timeout.connect(self._advance_spin)
        self._busy = False

    def busy(self) -> bool:
        return self._busy

    # ------------------------------------------------------------------ 内部
    def _advance_spin(self) -> None:
        if self._curtain is not None:
            self._curtain.advance(9.0)

    def _curtain_for(self, area: QRect, tint: QColor, contrast: Optional[QColor] = None) -> _Curtain:
        curtain = _Curtain()
        curtain.prepare(area, tint, contrast)
        curtain.show()
        curtain.set_fade(0.0)
        return curtain

    @staticmethod
    def _animate(widget: _Curtain, start: float, end: float, duration: int,
                 curve: QEasingCurve.Type, on_done: Optional[Callable[[], None]] = None) -> QVariantAnimation:
        anim = QVariantAnimation(widget)
        anim.setStartValue(float(start))
        anim.setEndValue(float(end))
        anim.setDuration(max(1, int(duration)))
        anim.setEasingCurve(curve)
        anim.valueChanged.connect(lambda value: widget.set_fade(float(value)))
        if on_done is not None:
            anim.finished.connect(on_done)
        anim.start()
        return anim

    # ------------------------------------------------------------------ 主流程
    def run(self,
            area: QRect,
            old_color: QColor,
            new_color: QColor,
            apply: Callable[[], None],
            before: Optional[Callable[[], None]] = None,
            after: Optional[Callable[[], None]] = None,
            label: str = "",
            contrast: Optional[QColor] = None) -> None:
        """盖幕布 → 调 apply()（卡在这一帧里）→ 换色 → 淡出。"""
        if self._busy:
            # 已经在切换中：直接应用，别叠幕布
            apply()
            if after is not None:
                after()
            return
        self._busy = True
        if before is not None:
            before()
        curtain = self._curtain_for(area, old_color, contrast)
        if label:
            curtain._label = label
        self._curtain = curtain
        self._spin_timer.start()

        def when_covered() -> None:
            QTimer.singleShot(HOLD_MS, apply_now)

        def apply_now() -> None:
            try:
                apply()
            finally:
                travel()

        def travel() -> None:
            anim = QVariantAnimation(curtain)
            anim.setStartValue(QColor(old_color))
            anim.setEndValue(QColor(new_color))
            anim.setDuration(TINT_TRAVEL_MS)
            anim.setEasingCurve(QEasingCurve.InOutCubic)

            def on_color(value) -> None:
                curtain.set_tint(value)

            anim.valueChanged.connect(on_color)
            anim.start()
            self._travel = anim
            QTimer.singleShot(120, reveal)

        def reveal() -> None:
            if after is not None:
                after()
            self._animate(curtain, curtain._fade, 0.0, FADE_OUT_MS, QEasingCurve.OutCubic, finish)

        def finish() -> None:
            self._spin_timer.stop()
            curtain.close()
            curtain.deleteLater()
            self._curtain = None
            self._busy = False

        self._animate(curtain, 0.0, 1.0, FADE_IN_MS, QEasingCurve.OutCubic, when_covered)


def screen_area_for(widget: Optional[QWidget]) -> QRect:
    """优先盖住触发这次切换的那个窗口所在屏幕。"""
    screen = None
    if widget is not None:
        try:
            screen = widget.screen()
        except Exception:
            screen = None
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return QRect(0, 0, 1280, 720)
    return screen.geometry()
