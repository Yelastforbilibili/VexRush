"""自绘控件集合（B 端风格：微边框、同心圆角、克制的动效）。"""
from __future__ import annotations

import math
import time
from collections import deque
from typing import Iterable, List, Optional, Tuple

from PyQt5.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF,
                          QSize, Qt, QTimer, QVariantAnimation, pyqtSignal)
from PyQt5.QtGui import (QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                        QPen,
                         QPainterPath, QPen, QPolygonF)
from PyQt5.QtWidgets import (QAbstractButton, QButtonGroup, QColorDialog, QComboBox, QFrame,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpinBox,
                             QVBoxLayout, QWidget)

from . import winapi
from .i18n import tr

COLLAPSE_MS = 210

# ---------------------------------------------------------------- 令牌

_TOKENS: dict = {}


def set_tokens(tokens: dict) -> None:
    global _TOKENS
    _TOKENS = dict(tokens or {})


def tk(key: str, fallback: str = "#000000") -> str:
    value = _TOKENS.get(key)
    return str(value) if value else fallback


def tki(key: str, fallback: int = 0) -> int:
    try:
        return int(_TOKENS.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def color(key: str, alpha: float = 1.0) -> QColor:
    result = QColor(tk(key))
    if alpha < 1.0:
        result.setAlphaF(max(0.0, min(1.0, alpha)))
    return result


# ---------------------------------------------------------------- 小工具

def label(text: str = "", kind: str = "", parent: QWidget = None) -> QLabel:
    widget = QLabel(text, parent)
    if kind:
        widget.setObjectName(kind)
    return widget


def hline(parent: QWidget = None) -> QFrame:
    line = QFrame(parent)
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    line.setFrameShape(QFrame.NoFrame)
    return line


def vline(parent: QWidget = None) -> QFrame:
    line = QFrame(parent)
    line.setObjectName("VDivider")
    line.setFixedWidth(1)
    line.setFrameShape(QFrame.NoFrame)
    return line


def polish(widget: QWidget) -> QWidget:
    """动态属性变更后重新套用样式表。"""
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()
    return widget


# ---------------------------------------------------------------- 开关

class Switch(QAbstractButton):
    """36x20 的拨动开关，改变即生效。"""

    def __init__(self, checked: bool = False, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(38, 22)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._on_toggled)

    def _on_anim(self, value) -> None:
        self._pos = float(value)
        self.update()

    def _on_toggled(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self) -> QSize:
        return QSize(38, 22)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(1.0, 2.5, 36.0, 17.0)
        radius = rect.height() / 2.0
        on = self.isChecked()
        enabled = self.isEnabled()

        if on:
            track = color("accent")
        else:
            track = color("sunken") if not tk_bool("dark") else color("border")
        if not enabled:
            track.setAlphaF(0.45)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(track))
        painter.drawRoundedRect(rect, radius, radius)

        if not on:
            painter.setPen(QPen(color("border_strong", 0.9), 1.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)

        knob_d = 15.0
        left = 1.0 + 1.5
        right = rect.right() - 1.5 - knob_d
        x = left + (right - left) * self._pos
        knob = QRectF(x, rect.center().y() - knob_d / 2.0, knob_d, knob_d)
        painter.setPen(QPen(QColor(15, 23, 42, 36), 1.0))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawEllipse(knob)
        painter.end()


def tk_bool(key: str, fallback: bool = False) -> bool:
    return bool(_TOKENS.get(key, fallback))


# ---------------------------------------------------------------- 数字输入

class _Spin(QSpinBox):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setButtonSymbols(QSpinBox.NoButtons)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setKeyboardTracking(False)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event) -> None:
        step = 10 if event.modifiers() & Qt.ShiftModifier else 1
        self.setValue(self.value() + (step if event.angleDelta().y() > 0 else -step))
        event.accept()

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        return QSize(metrics.width("0000") + 8, metrics.height() + 6)


class NumberField(QFrame):
    """  [- 15 +] ms  —— 带加减按钮的数字输入。"""

    valueChanged = pyqtSignal(int)

    def __init__(self, value: int = 15, minimum: int = 1, maximum: int = 2000,
                 step: int = 1, suffix: str = "ms", parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("NumberField")
        self._step = step
        self._suffix = suffix

        self.spin = _Spin(self)
        self.spin.setRange(minimum, maximum)
        self.spin.setValue(value)

        self.btn_minus = QPushButton("−", self)
        self.btn_plus = QPushButton("+", self)
        for button in (self.btn_minus, self.btn_plus):
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 6, 2)
        layout.setSpacing(1)
        layout.addWidget(self.btn_minus)
        layout.addWidget(self.spin, 1)
        if suffix:
            unit = QLabel(suffix, self)
            unit.setObjectName("Caption")
            layout.addWidget(unit)
        layout.addWidget(self.btn_plus)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedHeight(max(30, self.spin.sizeHint().height() + 6))

        self.btn_minus.clicked.connect(lambda: self._bump(-self._step))
        self.btn_plus.clicked.connect(lambda: self._bump(self._step))
        self.spin.valueChanged.connect(self.valueChanged.emit)

    def _bump(self, delta: int) -> None:
        self.spin.setValue(self.spin.value() + delta)

    def value(self) -> int:
        return self.spin.value()

    def setValue(self, value: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        self.spin.blockSignals(False)

    def setSuffix(self, text: str) -> None:
        self._suffix = text


# ---------------------------------------------------------------- 下拉框

class Combo(QComboBox):
    """自绘箭头的下拉框（隐藏系统箭头，避免系统主题干扰视觉）。"""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(30)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContentsOnFirstShow)
        self.setMinimumWidth(150)
        view = self.view()
        if view is not None:
            view.setCursor(Qt.PointingHandCursor)

    def add_items(self, items: Iterable[Tuple[str, str]], current: str = "") -> None:
        for key, text in items:
            self.addItem(text, key)
        if current:
            self.select_data(current)

    def select_data(self, key: str, emit: bool = False) -> bool:
        index = self.findData(key)
        if index < 0:
            return False
        if emit:
            self.setCurrentIndex(index)
        else:
            self.blockSignals(True)
            self.setCurrentIndex(index)
            self.blockSignals(False)
        return True

    def current_data(self) -> str:
        data = self.currentData()
        return data if data is not None else ""

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(color("text3"), 1.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        cx = self.width() - 14
        cy = self.height() / 2.0
        painter.drawLine(QPointF(cx - 3.5, cy - 1.6), QPointF(cx, cy + 1.9))
        painter.drawLine(QPointF(cx, cy + 1.9), QPointF(cx + 3.5, cy - 1.6))
        painter.end()


# ---------------------------------------------------------------- 分段控件

class Segmented(QWidget):
    """2~4 个互斥选项平铺（Radio 语义），选中项用 surface 高亮。"""

    changed = pyqtSignal(str)

    def __init__(self, options: List[Tuple[str, str]], current: str = "",
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._buttons: dict = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)
        for key, text in options:
            button = QPushButton(text, self)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)
            button.setProperty("segKey", key)
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[key] = button
            button.clicked.connect(lambda _=False, k=key: self._on_click(k))
        self.set_value(current or (options[0][0] if options else ""))

    def _on_click(self, key: str) -> None:
        self.changed.emit(key)

    def set_value(self, key: str, emit: bool = False) -> None:
        button = self._buttons.get(key)
        if button is None:
            return
        if button.isChecked() and not emit:
            return
        button.setChecked(True)
        if emit:
            self.changed.emit(key)

    def value(self) -> str:
        for key, button in self._buttons.items():
            if button.isChecked():
                return key
        return ""


# ---------------------------------------------------------------- 折叠区

class ToggleHeader(QAbstractButton):
    """「更多设置 ⌄」文字按钮，展开时箭头翻转。"""

    def __init__(self, title: str = tr("more_settings"), parent: QWidget = None) -> None:
        super().__init__(parent)
        self._title = title
        self._expanded = False
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedHeight(24)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        return QSize(metrics.width(self._title) + 30, 24)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        text = self._title
        pen_color = color("text") if self._hover else color("text3")
        painter.setPen(QPen(pen_color))
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() - 0.4)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        baseline = (self.height() + metrics.ascent() - metrics.descent()) / 2.0
        painter.drawText(QPointF(0, baseline), text)

        cx = metrics.width(text) + 11.0
        cy = self.height() / 2.0
        chevron = QPen(pen_color, 1.3)
        chevron.setCapStyle(Qt.RoundCap)
        chevron.setJoinStyle(Qt.RoundJoin)
        painter.setPen(chevron)
        dy = -1.4 if self._expanded else 1.4
        painter.drawLine(QPointF(cx - 3.2, cy - dy), QPointF(cx, cy + dy))
        painter.drawLine(QPointF(cx, cy + dy), QPointF(cx + 3.2, cy - dy))
        painter.end()


class Collapsible(QWidget):
    """「更多设置」折叠区：展开时高度从 0 平滑过渡。"""

    def __init__(self, body: QWidget, title: str = tr("more_settings"), parent: QWidget = None) -> None:
        super().__init__(parent)
        self._body = body
        self._expanded = False

        self.header = ToggleHeader(title, self)
        self.header.clicked.connect(self.toggle)
        self._title = title

        self._body.setMaximumHeight(0)
        self._body.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header, 0, Qt.AlignLeft)
        layout.addWidget(self._body)

        self._anim = QPropertyAnimation(self._body, b"maximumHeight", self)
        self._anim.setDuration(COLLAPSE_MS)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

    # -- 状态 ------------------------------------------------------
    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self.header.set_expanded(expanded)
        target = self._body.sizeHint().height() if expanded else 0
        self._anim.stop()
        try:
            self._anim.finished.disconnect()
        except TypeError:
            pass
        if expanded:
            self._body.setVisible(True)
        self._anim.setStartValue(self._body.maximumHeight())
        self._anim.setEndValue(target)
        if not animate:
            self._body.setMaximumHeight(target)
            self._body.setVisible(expanded)
            self._refresh_parent()
            return

        def _done() -> None:
            if not self._expanded:
                self._body.setVisible(False)
                self._body.setMaximumHeight(0)
            self._refresh_parent()

        self._anim.finished.connect(_done)
        self._anim.start()

    def body_height(self) -> int:
        """折叠区展开后内容本身的高度（与当前状态无关）。"""
        return int(self._body.sizeHint().height())

    def expanded_delta(self) -> int:
        """展开后比现在多占的高度（收起时用作窗口长高的动画量）。"""
        return self._body.sizeHint().height() if not self._expanded else 0

    def collapsed_delta(self) -> int:
        """收起后能省下的高度。"""
        return self._body.height() if self._expanded else 0

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def _refresh_parent(self) -> None:
        parent = self.parentWidget()
        while parent is not None:
            parent.updateGeometry()
            parent = parent.parentWidget()
        self.updateGeometry()


# ---------------------------------------------------------------- 迷你趋势图

class Sparkline(QWidget):
    """速率趋势：面积填充 + 折线，无坐标轴。"""

    def __init__(self, points: int = 56, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._values = deque([0.0] * points, maxlen=points)
        self._ceiling = 120.0
        self.setMinimumHeight(34)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(38)

    def push(self, value: float, ceiling: float = 0.0) -> None:
        self._values.append(float(value))
        if ceiling and ceiling > 0:
            self._ceiling = max(ceiling, 10.0)
        self.update()

    def reset(self) -> None:
        self._values = deque([0.0] * len(self._values), maxlen=len(self._values))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 1.0, -0.5, -1.0)
        accent = color("accent")

        # 基线
        pen = QPen(color("border", 0.7), 1.0)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(rect.left(), rect.bottom()), QPointF(rect.right(), rect.bottom()))

        values = list(self._values)
        if len(values) < 2:
            return
        peak = max(self._ceiling, max(values) * 1.15, 1.0)
        step = rect.width() / (len(values) - 1)
        points = []
        for index, value in enumerate(values):
            ratio = max(0.0, min(1.0, value / peak))
            points.append(QPointF(rect.left() + step * index,
                                  rect.bottom() - ratio * (rect.height() - 2.0)))

        polygon = QPolygonF([QPointF(rect.left(), rect.bottom())] + points +
                            [QPointF(rect.right(), rect.bottom())])
        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        top = QColor(accent)
        top.setAlphaF(0.20)
        bottom = QColor(accent)
        bottom.setAlphaF(0.015)
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPolygon(polygon)

        line = QPen(accent, 1.6)
        line.setJoinStyle(Qt.RoundJoin)
        line.setCapStyle(Qt.RoundCap)
        painter.setPen(line)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(QPolygonF(points))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(accent))
        painter.drawEllipse(points[-1], 2.0, 2.0)
        painter.end()


# ---------------------------------------------------------------- 按键捕获

class KeyButton(QPushButton):
    """点击进入捕获态，按任意键设置热键。"""

    keyChanged = pyqtSignal(str)

    def __init__(self, key_name: str = "", parent: QWidget = None) -> None:
        super().__init__(parent)
        self._key = winapi.canon_key(key_name)
        self._capturing = False
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(96)
        self.setFocusPolicy(Qt.StrongFocus)
        self._refresh_text()

    # -- 对外 ------------------------------------------------------
    def key(self) -> str:
        return self._key

    def set_key(self, name: str) -> None:
        self._key = winapi.canon_key(name)
        self._refresh_text()

    def _refresh_text(self) -> None:
        if self._capturing:
            self.setText(tr("press_any_key"))
        else:
            self.setText(winapi.key_display(self._key))
        self.setToolTip(tr("click_then_press_a_key_esc_cancels"))

    # -- 交互 ------------------------------------------------------
    def begin_capture(self) -> None:
        self._capturing = True
        self._refresh_text()
        self.setFocus(Qt.OtherFocusReason)

    def cancel_capture(self) -> None:
        if not self._capturing:
            return
        self._capturing = False
        self._refresh_text()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.begin_capture()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key_Escape,):
            self.cancel_capture()
            event.accept()
            return
        if event.key() in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta):
            event.accept()
            return
        name = winapi.qt_key_to_name(event.key())
        if not name:
            event.accept()
            return
        self._key = name
        self._capturing = False
        self._refresh_text()
        self.keyChanged.emit(name)
        event.accept()

    def focusOutEvent(self, event) -> None:
        self.cancel_capture()
        super().focusOutEvent(event)


# ---------------------------------------------------------------- 颜色按钮

class ColorButton(QPushButton):
    colorChanged = pyqtSignal(str)

    def __init__(self, value: str = "#3b82f6", parent: QWidget = None) -> None:
        super().__init__(parent)
        self._value = value
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(84)
        self.clicked.connect(self._pick)
        self._refresh()

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        self._value = value
        self._refresh()

    def _refresh(self) -> None:
        self.setText(self._value.upper())
        self.setStyleSheet(
            "QPushButton { background:%s; color:%s; border:1px solid rgba(0,0,0,0.18);"
            " border-radius:6px; padding:5px 10px; }" % (self._value, _contrast(self._value))
        )

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._value), self, tr("select_color"))
        if chosen.isValid():
            self._value = chosen.name()
            self._refresh()
            self.colorChanged.emit(self._value)


def _contrast(hex_color: str) -> str:
    col = QColor(hex_color)
    luma = (0.299 * col.red() + 0.587 * col.green() + 0.114 * col.blue()) / 255.0
    return "#ffffff" if luma < 0.62 else "#0b1220"


# ---------------------------------------------------------------- 状态点

class StatusDot(QWidget):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._color = QColor(tk("text3"))
        self.setFixedSize(8, 8)

    def set_color(self, value) -> None:
        self._color = QColor(value)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(QRectF(0.5, 0.5, 7.0, 7.0))
        painter.end()


# ---------------------------------------------------------------- 卡片

class Card(QFrame):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.NoFrame)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        polish(self)

# ---------------------------------------------------------------- 等待遮罩

class BusyOverlay(QWidget):
    """半透明遮罩 + 转圈：界面重建要几十毫秒时给一点反馈。

    自己按 ``winapi.frame_interval_ms()`` 出帧，透明度用指数逼近做淡入淡出，
    因此在高刷屏上也是顺的。默认不拦截鼠标，只在显示时接管。
    """

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._text = u""
        self._fade = 0.0
        self._target = 0.0
        self._spin = 0.0
        self._last = 0.0
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.NoFocus)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(winapi.frame_interval_ms())
        self._timer.timeout.connect(self._on_frame)

    # -- 对外 ------------------------------------------------------
    def show_busy(self, text: str = u"") -> None:
        self._text = text
        self._target = 1.0
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self._last = time.perf_counter()
        if not self._timer.isActive():
            self._timer.start()
        self.setCursor(Qt.BusyCursor)

    def hide_busy(self) -> None:
        self._target = 0.0
        self.unsetCursor()
        if not self._timer.isActive():
            self.hide()
            return
        self._last = time.perf_counter()

    def busy(self) -> bool:
        return self.isVisible() and (self._target > 0.0 or self._fade > 0.02)

    # -- 帧 --------------------------------------------------------
    def _on_frame(self) -> None:
        now = time.perf_counter()
        dt = min(0.05, max(0.0, now - self._last))
        self._last = now
        step = 1.0 - math.exp(-dt * 16.0)
        self._fade += (self._target - self._fade) * step
        self._spin = (self._spin + dt * 300.0) % 360.0
        if self._target == 0.0 and self._fade < 0.03:
            self._fade = 0.0
            self._timer.stop()
            self.hide()
            return
        self.update()

    def paintEvent(self, event) -> None:
        if self._fade <= 0.01:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        scrim = color("canvas", 0.86 * self._fade)
        painter.fillRect(self.rect(), scrim)

        cx = self.width() / 2.0
        cy = self.height() / 2.0 - 12.0
        radius = 13.0
        pen = QPen(color("accent", self._fade), 2.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        painter.drawArc(rect, int(-self._spin * 16), int(110 * 16))

        painter.setPen(QPen(color("text2", self._fade)))
        font = QFont(self.font())
        font.setPointSizeF(9.0)
        painter.setFont(font)
        painter.drawText(QRectF(0, cy + radius + 8, self.width(), 24),
                         Qt.AlignHCenter | Qt.AlignTop, self._text)
        painter.end()


class MiniSpinner(QWidget):
    """按钮旁边的小转圈：固定 14px，start()/stop() 控制，隐藏时不占帧。"""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._angle = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._on_tick)
        self.hide()

    def start(self) -> None:
        if not self._timer.isActive():
            self.show()
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def running(self) -> bool:
        return self._timer.isActive()

    def _on_tick(self) -> None:
        self._angle = (self._angle + 24.0) % 360.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        radius = 5.0
        rect = QRectF(2.0, 2.0, radius * 2, radius * 2)
        track = color("border_strong", 0.9)
        pen = QPen(track)
        pen.setWidthF(1.8)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)
        pen.setColor(color("accent", 1.0))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, int(-self._angle * 16), int(110 * 16))
        painter.end()
