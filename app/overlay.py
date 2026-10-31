"""「连点显示」悬浮窗：可全面配置、带过渡与彩虹特效，默认关闭。

相比上一版重做了三件事：
* 横向排布按「块」测量与绘制，不再用整行宽度，文字不会挤在一起；
* 动画改成 16ms 帧 + 指数缓动，背景缓存成位图，只有状态变化时才重绘；
* 右键菜单是无边框 + 半透明窗口 + 自绘圆角，用的是悬浮窗自己的深色配色。
"""
from __future__ import annotations

import math
import time
from typing import List, Optional

from PyQt5.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QAction, QMenu, QWidget

from . import winapi
from .config import OverlayConfig
from .widgets import set_tokens as _set_global_tokens
from .widgets import tk
from .i18n import tr

FRAME_MS = 16                 # 兜底帧长；实际用 winapi.frame_interval_ms()
BAR_W = 3.0
BAR_GAP = 7.0
META_GAP = 9.0
DIVIDER_GAP = 9.0

CHANNEL_LABELS = ("连点1", "连点2")


def _meta_sample(cfg: OverlayConfig) -> str:
    """用于测量「元信息」列宽的样板串，保证面板宽度不随数字跳动。"""
    parts = []
    if cfg.show_state:
        parts.append(tr("运行"))
    if cfg.show_cps:
        parts.append(tr("999.9 次/秒"))
    if cfg.show_count:
        parts.append(tr("9,999,999 次"))
    if cfg.show_interval:
        parts.append("2000 ms")
    return "  ".join(parts)


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


class OverlayWindow(QWidget):
    positionChanged = pyqtSignal(str)
    styleChanged = pyqtSignal()
    requestSettings = pyqtSignal()
    requestHide = pyqtSignal()

    def __init__(self, cfg: OverlayConfig, tokens: dict, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        _set_global_tokens(tokens or {})
        self._tokens = tokens or {}
        self._rows = [
            {"title": tr(CHANNEL_LABELS[0]), "enabled": False, "clicking": False},
            {"title": tr(CHANNEL_LABELS[1]), "enabled": False, "clicking": False},
        ]
        self._level = [0.0, 0.0]
        self._target_level = [0.0, 0.0]
        self._flash = [0.0, 0.0]
        self._hue = 0.0
        self._pulse = 0.0
        self._drag_offset: Optional[QPoint] = None
        self._drag_target: Optional[QPoint] = None
        self._drag_active = False
        self._vel = QPointF(0.0, 0.0)
        self._anim_t = 1.0
        self._anim_kind = "in"
        self._anim_start = 0.0
        self._anim_len = 0.0
        self._anim_active = False
        self._last_frame = 0.0
        self._bg_key = None
        self._bg_pixmap: Optional[QPixmap] = None
        self._size_cache: Optional[QSize] = None
        self._rebuild_fonts()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                            Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)

        self._frame_ms = winapi.frame_interval_ms()
        self._timer = QTimer(self)
        self._timer.setInterval(self._frame_ms)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._on_frame)

    # ------------------------------------------------------------ 配置
    def set_cfg(self, cfg: OverlayConfig) -> None:
        self.cfg = cfg
        self._rebuild_fonts()
        self._apply_window_style()
        self._relayout(force=True)

    def set_tokens(self, tokens: dict) -> None:
        self._tokens = tokens or {}
        _set_global_tokens(self._tokens)
        self._invalidate_background()
        self.update()

    def set_rows(self, rows: List[dict]) -> None:
        changed = False
        for index, row in enumerate(rows[:len(self._rows)]):
            current = self._rows[index]
            for key, value in row.items():
                if current.get(key) != value:
                    changed = True
                current[key] = value
            clicking = bool(current.get("clicking"))
            enabled = bool(current.get("enabled"))
            self._target_level[index] = 1.0 if clicking else (0.55 if enabled else 0.0)
        if changed:
            self._relayout()
        if self._needs_frames():
            self._start_frames()

    def flash(self, index: int) -> None:
        if 0 <= index < len(self._flash):
            self._flash[index] = 1.0
            self._start_frames()

    # ------------------------------------------------------------ 字体
    def _rebuild_fonts(self) -> None:
        base = 8.8 * (self.cfg.scale / 100.0)
        self._font_main = QFont(self.font())
        self._font_main.setPointSizeF(max(6.0, base))
        self._font_main.setWeight(QFont.DemiBold)
        self._font_meta = QFont(self.font())
        self._font_meta.setPointSizeF(max(5.8, base * 0.92))
        self._font_title = QFont(self.font())
        self._font_title.setPointSizeF(max(5.8, base * 0.82))
        self._metrics_main = QFontMetrics(self._font_main)
        self._metrics_meta = QFontMetrics(self._font_meta)
        self._metrics_title = QFontMetrics(self._font_title)
        self._meta_width = self._metrics_meta.width(_meta_sample(self.cfg)) if self._meta_col() else 0
        self._row_h = max(self._metrics_main.height(), self._metrics_meta.height()) + 7
        self._size_cache = None
        self._bg_key = None

    def _meta_col(self) -> bool:
        return bool(self.cfg.show_state or self.cfg.show_cps or self.cfg.show_count
                    or self.cfg.show_interval)

    def _has_title(self) -> bool:
        return bool(self.cfg.show_title and (self.cfg.title_text or "").strip())

    def _title_height(self) -> int:
        return self._metrics_title.height() + 2 if self._has_title() else 0

    # ------------------------------------------------------------ 度量
    def _meta_text(self, row: dict) -> str:
        parts = []
        if self.cfg.show_state:
            if row.get("clicking"):
                parts.append(tr("运行"))
            elif row.get("enabled"):
                parts.append(tr("就绪"))
            else:
                parts.append(tr("暂停"))
        if self.cfg.show_cps:
            parts.append(tr("%.1f 次/秒") % float(row.get("cps") or 0.0))
        if self.cfg.show_count:
            parts.append(tr("{:,} 次").format(int(row.get("count") or 0)))
        if self.cfg.show_interval:
            parts.append("%d ms" % int(row.get("interval") or 0))
        return "  ".join(parts)

    def _block_width(self, row: dict) -> float:
        width = BAR_W + BAR_GAP + self._metrics_main.width(str(row.get("title") or ""))
        if self._meta_width:
            width += META_GAP + self._meta_width
        return float(width)

    def _inner_width(self) -> float:
        if self.cfg.layout == "h":
            total = 0.0
            for index, row in enumerate(self._rows):
                if index:
                    total += DIVIDER_GAP * 2
                total += self._block_width(row)
            return total
        return max(self._block_width(row) for row in self._rows)

    def _relayout(self, force: bool = False) -> None:
        pad = int(self.cfg.padding)
        gap = int(self.cfg.gap)
        rows = len(self._rows)
        inner_w = self._inner_width()
        title_h = self._title_height()
        if self.cfg.layout == "h":
            width = pad * 2 + inner_w
            height = pad * 2 + title_h + self._row_h
        else:
            width = pad * 2 + inner_w
            height = pad * 2 + title_h + rows * self._row_h + gap * max(0, rows - 1)
        size = QSize(max(64, int(round(width)) + 2), max(26, int(round(height))))
        if force or size != self._size_cache:
            self._size_cache = size
            if self.size() != size:
                self.setFixedSize(size)
            self._invalidate_background()
            self.update()

    # ------------------------------------------------------------ 背景缓存
    def _invalidate_background(self) -> None:
        self._bg_key = None
        self._bg_pixmap = None

    def _background(self) -> Optional[QPixmap]:
        active = any(bool(row.get("clicking")) for row in self._rows)
        key = (self.width(), self.height(), self.cfg.radius, self.cfg.bg_color,
               self.cfg.bg_opacity, self.cfg.fg_color, active)
        if self._bg_key == key and self._bg_pixmap is not None:
            return self._bg_pixmap
        ratio = self.devicePixelRatioF() or 1.0
        pixmap = QPixmap(int(self.width() * ratio), int(self.height() * ratio))
        if pixmap.isNull():
            return None
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        radius = float(self.cfg.radius)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        bg = QColor(self.cfg.bg_color)
        alpha = self.cfg.bg_opacity / 100.0
        bg.setAlphaF(max(0.0, min(1.0, alpha)))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawPath(path)
        border = QColor(self.cfg.fg_color)
        border.setAlphaF(0.16 if active else 0.10)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(border, 1.0))
        painter.drawPath(path)
        painter.end()
        self._bg_key = key
        self._bg_pixmap = pixmap
        return pixmap

    # ------------------------------------------------------------ 动画
    def _needs_frames(self) -> bool:
        if self._anim_active:
            return True
        if self._drag_active and self._drag_target is not None and self.cfg.drag_smooth:
            return True
        if abs(self._vel.x()) > 8.0 or abs(self._vel.y()) > 8.0:
            return True
        for index in range(len(self._level)):
            if abs(self._target_level[index] - self._level[index]) > 0.002:
                return True
        if any(value > 0.01 for value in self._flash):
            return True
        clicking = any(bool(row.get("clicking")) for row in self._rows)
        if clicking and self.cfg.rainbow:
            return True
        if clicking and self.cfg.animation == "pulse":
            return True
        return False

    def _start_frames(self) -> None:
        if not self._timer.isActive():
            self._last_frame = time.perf_counter()
            self._timer.start()

    def _on_frame(self) -> None:
        now = time.perf_counter()
        dt = max(0.001, min(0.05, now - self._last_frame))
        self._last_frame = now

        settled = True
        for index in range(len(self._level)):
            level = self._level[index]
            target = self._target_level[index]
            diff = target - level
            if abs(diff) > 0.002:
                # 与帧率无关的指数逼近：约 150ms 收敛
                level += diff * (1.0 - math.exp(-dt * 20.0))
                self._level[index] = level
                settled = False
            elif level != target:
                self._level[index] = target
        for index in range(len(self._flash)):
            if self._flash[index] > 0:
                self._flash[index] = max(0.0, self._flash[index] - dt * 2.6)
                settled = False

        clicking = any(bool(row.get("clicking")) for row in self._rows)
        if clicking and self.cfg.rainbow:
            speed = max(16, int(self.cfg.rainbow_speed))
            self._hue = (self._hue + dt * (1000.0 / speed) * 0.016) % 1.0
            settled = False
        if clicking and self.cfg.animation == "pulse":
            self._pulse = (self._pulse + dt * 4.0) % (math.pi * 2.0)
            settled = False

        if self._anim_active:
            self._anim_progress(now)
            settled = False

        if self._drag_active and self._drag_target is not None and self.cfg.drag_smooth:
            current = self.pos()
            target = self._drag_target
            k = 1.0 - math.exp(-dt * max(6, int(self.cfg.drag_ease)))
            nx = current.x() + (target.x() - current.x()) * k
            ny = current.y() + (target.y() - current.y()) * k
            if abs(target.x() - nx) < 0.6:
                nx = target.x()
            if abs(target.y() - ny) < 0.6:
                ny = target.y()
            if nx != current.x() or ny != current.y():
                self.move(int(round(nx)), int(round(ny)))
            if nx != target.x() or ny != target.y():
                settled = False

        if not self._drag_active and (abs(self._vel.x()) > 1.0 or abs(self._vel.y()) > 1.0):
            current = self.pos()
            self.move(int(round(current.x() + self._vel.x() * dt)),
                      int(round(current.y() + self._vel.y() * dt)))
            decay = math.exp(-dt * 4.2)
            self._vel = QPointF(self._vel.x() * decay, self._vel.y() * decay)
            if abs(self._vel.x()) < 12.0 and abs(self._vel.y()) < 12.0:
                self._vel = QPointF(0.0, 0.0)
                self.positionChanged.emit(self.save_position())
            settled = False

        self.update()
        if settled and not self._needs_frames():
            self._timer.stop()

    # ------------------------------------------------------------ 缓动
    @staticmethod
    def _ease_out_cubic(p: float) -> float:
        return 1.0 - (1.0 - p) ** 3

    @staticmethod
    def _ease_out_back(p: float, overshoot: float = 1.34) -> float:
        q = p - 1.0
        return 1.0 + (overshoot + 1.0) * q ** 3 + overshoot * q ** 2

    @staticmethod
    def _ease_in_out_sine(p: float) -> float:
        return -(math.cos(math.pi * p) - 1.0) / 2.0

    def _anim_seconds(self, kind: str) -> float:
        return {"none": 0.0, "fade": 0.22, "slide": 0.26, "scale": 0.26,
                "spring": 0.34, "blur": 0.3}.get(kind, 0.22)

    def playing(self) -> bool:
        return self._anim_active

    def play_in(self) -> None:
        """入场：按 cfg.anim_in 选择动画。"""
        kind = self.cfg.anim_in or "fade"
        self._anim_kind = "in"
        self._anim_len = self._anim_seconds(kind)
        self._anim_t = 0.0 if self._anim_len > 0 else 1.0
        self._anim_active = self._anim_len > 0
        self._anim_start = time.perf_counter()
        if not self.isVisible():
            self.show()
        self._apply_window_style()
        if self._anim_active:
            self._start_frames()
        self.update()

    def play_out(self, hide_after: bool = True) -> None:
        """出场：放完再真正隐藏，避免硬切。"""
        kind = self.cfg.anim_out or "fade"
        self._anim_kind = "out"
        self._anim_len = self._anim_seconds(kind)
        self._hide_after = bool(hide_after)
        if self._anim_len <= 0 or not self.isVisible():
            self._anim_active = False
            self._anim_t = 1.0
            if hide_after:
                self.hide()
            return
        self._anim_t = 0.0
        self._anim_active = True
        self._anim_start = time.perf_counter()
        self._start_frames()
        self.update()

    def _anim_progress(self, now: float) -> None:
        if not self._anim_active:
            return
        if self._anim_len <= 0:
            self._anim_t = 1.0
            self._anim_active = False
            return
        raw = (now - self._anim_start) / self._anim_len
        self._anim_t = 1.0 if raw >= 1.0 else max(0.0, raw)
        if raw >= 1.0:
            self._anim_active = False
            if self._anim_kind == "out" and getattr(self, "_hide_after", True):
                self.hide()

    def _anim_curve(self) -> float:
        kind = self.cfg.anim_in if self._anim_kind == "in" else self.cfg.anim_out
        t = max(0.0, min(1.0, self._anim_t))
        if kind == "spring":
            return max(0.0, self._ease_out_back(t))
        if kind == "scale":
            return self._ease_out_cubic(t)
        if kind == "blur":
            return self._ease_in_out_sine(t)
        return self._ease_out_cubic(t)

    def _anim_paint_state(self):
        """返回 (额外透明度倍率, 缩放, 竖直位移)。"""
        kind = self.cfg.anim_in if self._anim_kind == "in" else self.cfg.anim_out
        if kind == "none" or (not self._anim_active and self._anim_t >= 1.0):
            return 1.0, 1.0, 0.0
        t = max(0.0, min(1.0, self._anim_t))
        if self._anim_kind == "out":
            t = 1.0 - t
        if kind == "spring":
            curve = self._ease_out_back(t) if self._anim_kind == "in" else self._ease_out_cubic(t)
        elif kind == "blur":
            curve = self._ease_in_out_sine(t)
        else:
            curve = self._ease_out_cubic(t)
        if kind == "spring":
            # 弹性：允许轻微过冲（回弹那一下），透明度仍夹在 0..1
            raw = max(0.0, curve)
            return min(1.0, raw), 0.80 + 0.20 * raw, 0.0
        curve = max(0.0, min(1.0, curve))
        if kind == "slide":
            return curve, 1.0, (1.0 - curve) * 18.0
        if kind == "scale":
            return curve, 0.90 + 0.10 * curve, 0.0
        if kind == "blur":
            return min(1.0, curve * 1.15), 1.04 - 0.04 * curve, 0.0
        return curve, 1.0, 0.0

    # ------------------------------------------------------------ 颜色
    def _accent_color(self, index: int, row: dict) -> QColor:
        mode = self.cfg.accent_mode
        if mode == "custom":
            base = QColor(self.cfg.custom_accent)
        elif mode == "channel":
            base = QColor(tk("accent")) if index == 0 else QColor(tk("warning", "#f59e0b"))
        else:
            base = QColor(tk("accent"))
        if self.cfg.rainbow and row.get("clicking"):
            base = QColor.fromHsv(int(self._hue * 359) % 360, 210, 255)
        return base

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        overall = max(0.1, min(1.0, self.cfg.opacity / 100.0))
        anim_alpha, anim_scale, anim_dy = self._anim_paint_state()
        overall *= anim_alpha
        if anim_scale != 1.0 or anim_dy:
            painter.save()
            center = QRectF(0, 0, self.width(), self.height()).center()
            painter.translate(center.x(), center.y() + anim_dy)
            painter.scale(anim_scale, anim_scale)
            painter.translate(-center.x(), -center.y())
        background = self._background()
        if background is not None:
            painter.setOpacity(overall)
            painter.drawPixmap(0, 0, background)
            painter.setOpacity(1.0)

        alpha = overall
        pad = float(self.cfg.padding)
        top = pad
        if self._has_title():
            title_color = QColor(self.cfg.fg_color)
            title_color.setAlphaF(0.62 * alpha)
            painter.setFont(self._font_title)
            painter.setPen(title_color)
            rect = QRectF(pad, top, self.width() - pad * 2, self._metrics_title.height() + 2)
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, self.cfg.title_text)
            top += self._title_height()

        if self.cfg.layout == "h":
            self._paint_horizontal(painter, pad, top, alpha)
        else:
            self._paint_vertical(painter, pad, top, alpha)
        if anim_scale != 1.0 or anim_dy:
            painter.restore()
        painter.end()

    def _paint_vertical(self, painter: QPainter, pad: float, top: float, alpha: float) -> None:
        width = self.width() - pad * 2
        cursor = top
        gap = float(self.cfg.gap)
        for index, row in enumerate(self._rows):
            self._paint_row(painter, index, row, pad, cursor, width, alpha, True)
            cursor += self._row_h + gap

    def _paint_horizontal(self, painter: QPainter, pad: float, top: float, alpha: float) -> None:
        cursor = pad
        for index, row in enumerate(self._rows):
            if index:
                cursor += DIVIDER_GAP
                divider = QColor(self.cfg.fg_color)
                divider.setAlphaF(0.16 * alpha)
                painter.setPen(QPen(divider, 1.0))
                painter.drawLine(QPointF(cursor, top + 2),
                                 QPointF(cursor, top + self._row_h - 2))
                cursor += DIVIDER_GAP
            block = self._block_width(row)
            self._paint_row(painter, index, row, cursor, top, block, alpha, False)
            cursor += block

    def _paint_row(self, painter: QPainter, index: int, row: dict, x: float, y: float,
                   width: float, alpha: float, meta_right: bool) -> None:
        level = max(0.0, min(1.0, self._level[index]))
        dim = self.cfg.off_opacity / 100.0
        strength = dim + (1.0 - dim) * level
        accent = self._accent_color(index, row)
        clicking = bool(row.get("clicking"))
        animation = self.cfg.animation

        if self._flash[index] > 0.01:
            flash = QColor(accent)
            flash.setAlphaF(0.14 * self._flash[index] * alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(flash))
            painter.drawRoundedRect(QRectF(x - 3, y - 1, width + 6, self._row_h), 5, 5)

        bar_color = QColor(accent)
        bar_alpha = 0.32 + 0.68 * level
        if animation == "pulse" and clicking:
            bar_alpha *= 0.72 + 0.28 * math.sin(self._pulse)
        bar_color.setAlphaF(max(0.0, min(1.0, bar_alpha * alpha)))
        bar_w = BAR_W
        if animation == "slide":
            bar_w = max(1.2, BAR_W * (0.35 + 0.65 * level))
        bar_h = self._row_h * (0.42 + 0.34 * level)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bar_color))
        painter.drawRoundedRect(QRectF(x, y + (self._row_h - bar_h) / 2.0, bar_w, bar_h),
                                bar_w / 2.0, bar_w / 2.0)

        title_color = QColor(accent) if (clicking and self.cfg.rainbow) else QColor(self.cfg.fg_color)
        title_color.setAlphaF(max(0.0, min(1.0, strength * alpha)))
        painter.setFont(self._font_main)
        painter.setPen(title_color)
        metrics = self._metrics_main
        baseline = y + (self._row_h + metrics.ascent() - metrics.descent()) / 2.0
        text_x = x + bar_w + BAR_GAP
        title = str(row.get("title") or "")
        painter.drawText(QPointF(text_x, baseline), title)

        meta = self._meta_text(row)
        if meta and self._meta_width:
            meta_color = QColor(self.cfg.fg_color)
            meta_color.setAlphaF(max(0.0, min(1.0, 0.62 * strength * alpha)))
            painter.setFont(self._font_meta)
            painter.setPen(meta_color)
            meta_metrics = self._metrics_meta
            meta_baseline = y + (self._row_h + meta_metrics.ascent() - meta_metrics.descent()) / 2.0
            meta_w = meta_metrics.width(meta)
            meta_x = (x + width - meta_w) if meta_right else (text_x + metrics.width(title) + META_GAP)
            painter.drawText(QPointF(meta_x, meta_baseline), meta)

    # ------------------------------------------------------------ 窗口行为
    def apply_display(self) -> None:
        self._apply_window_style()
        if self.cfg.enabled:
            self._rebuild_fonts()
            self._relayout(force=True)
            if not self.isVisible() or self._anim_kind == "out" and self._anim_active:
                self.restore_position()
                self.play_in()
            elif self._needs_frames():
                self._start_frames()
        else:
            if self.isVisible():
                self.play_out()
            else:
                self._timer.stop()

    def _apply_window_style(self) -> None:
        try:
            hwnd = int(self.winId())
        except (RuntimeError, TypeError):
            return
        if not hwnd:
            return
        winapi.set_tool_window(hwnd, True)
        winapi.set_click_through(hwnd, bool(self.cfg.click_through))
        self.setAttribute(Qt.WA_TransparentForMouseEvents, bool(self.cfg.click_through))

    def restore_position(self) -> None:
        self._rebuild_fonts()
        self._relayout(force=True)
        text = (self.cfg.pos or "").strip()
        if text:
            try:
                x_text, y_text = text.split(",")
                self.move(int(float(x_text)), int(float(y_text)))
                return
            except (ValueError, TypeError):
                pass
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            self.move(screen.right() - self.width() - 22, screen.top() + 22)

    def save_position(self) -> str:
        pos = "%d,%d" % (self.x(), self.y())
        self.cfg.pos = pos
        return pos

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_window_style()
        frame_ms = winapi.frame_interval_ms()
        if frame_ms != self._frame_ms:      # 换过显示器 / 改过刷新率
            self._frame_ms = frame_ms
            self._timer.setInterval(frame_ms)
        if self._needs_frames():
            self._start_frames()

    # ------------------------------------------------------------ 鼠标
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self.cfg.locked:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self._drag_target = self.pos()
            self._drag_active = True
            self._vel = QPointF(0.0, 0.0)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            target = event.globalPos() - self._drag_offset
            previous = self._drag_target or self.pos()
            now = time.perf_counter()
            dt = max(0.0, now - getattr(self, "_drag_stamp", now))
            if dt > 0.004:
                # 用最近一段位移估算松手时的惯性速度
                self._vel = QPointF((target.x() - previous.x()) / dt * 0.65,
                                    (target.y() - previous.y()) / dt * 0.65)
                self._drag_stamp = now
            self._drag_target = target
            if not self.cfg.drag_smooth:
                self.move(target)
            else:
                self._start_frames()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            self._drag_active = False
            if self.cfg.drag_smooth and self._drag_target is not None:
                self.move(self._drag_target)
            self._drag_target = None
            speed = math.hypot(self._vel.x(), self._vel.y())
            if not self.cfg.drag_inertia or speed < 60.0:
                self._vel = QPointF(0.0, 0.0)
                self.positionChanged.emit(self.save_position())
            else:
                # 惯性滑行，停稳后再保存位置
                limit = 2600.0
                if speed > limit:
                    self._vel = QPointF(self._vel.x() / speed * limit, self._vel.y() / speed * limit)
                self._start_frames()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------ 右键菜单
    def build_menu(self) -> OverlayMenu:
        accent = QColor(tk("accent")) if self.cfg.accent_mode != "custom" \
            else QColor(self.cfg.custom_accent)
        menu = OverlayMenu(self.cfg, accent, self)

        def add(text: str, checked: Optional[bool] = None, callback=None) -> None:
            label = text
            if checked is not None:
                label = ("✓  " if checked else "    ") + text
            action = QAction(label, menu)
            if callback is not None:
                action.triggered.connect(callback)
            menu.addAction(action)

        add(tr("锁定位置"), self.cfg.locked, self._toggle_locked)
        add(tr("点击穿透"), self.cfg.click_through, self._toggle_click_through)
        menu.addSeparator()
        add(tr("显示标题"), self.cfg.show_title, lambda: self._toggle_field("show_title", not self.cfg.show_title))
        add(tr("显示状态"), self.cfg.show_state, lambda: self._toggle_field("show_state", not self.cfg.show_state))
        add(tr("显示速率"), self.cfg.show_cps, lambda: self._toggle_field("show_cps", not self.cfg.show_cps))
        add(tr("显示次数"), self.cfg.show_count, lambda: self._toggle_field("show_count", not self.cfg.show_count))
        add(tr("显示间隔"), self.cfg.show_interval, lambda: self._toggle_field("show_interval", not self.cfg.show_interval))
        menu.addSeparator()
        add(tr("彩虹特效"), self.cfg.rainbow, lambda: self._toggle_field("rainbow", not self.cfg.rainbow))
        add(tr("横向排布"), self.cfg.layout == "h",
            lambda: self._set_value("layout", "v" if self.cfg.layout == "h" else "h"))
        menu.addSeparator()
        add(tr("悬浮显示设置…"), None, self.requestSettings.emit)
        add(tr("关闭悬浮显示"), None, self.requestHide.emit)
        return menu

    def contextMenuEvent(self, event) -> None:
        menu = self.build_menu()
        menu.exec_(event.globalPos())
        menu.deleteLater()

    def _toggle_locked(self) -> None:
        self.cfg.locked = not self.cfg.locked
        self.styleChanged.emit()

    def _toggle_click_through(self) -> None:
        self.cfg.click_through = not self.cfg.click_through
        self._apply_window_style()
        self.styleChanged.emit()

    def _set_value(self, name: str, value) -> None:
        setattr(self.cfg, name, value)
        self._rebuild_fonts()
        self._relayout(force=True)
        self.styleChanged.emit()

    def _toggle_field(self, name: str, checked: Optional[bool] = None) -> None:
        value = (not getattr(self.cfg, name)) if checked is None else bool(checked)
        setattr(self.cfg, name, value)
        self._rebuild_fonts()
        self._relayout(force=True)
        self.styleChanged.emit()
