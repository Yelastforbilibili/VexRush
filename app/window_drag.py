"""主窗口的「跟手」那一层：窗口拖动、原生消息、高度/宽度自适应。

单独拎出来的原因：这些代码全是 Win32 消息与像素动画，和连点逻辑、界面布局没有关系，
混在主窗口里会让那个文件无限膨胀。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import math
import os
import time
from typing import Optional

import win32api
import win32gui

from PyQt5.QtCore import QAbstractNativeEventFilter, QEasingCurve, QRect, Qt, QTimer, QVariantAnimation
from PyQt5.QtWidgets import QApplication

from . import debug, winapi
from .i18n import tr

WM_ENTERSIZEMOVE = 0x0231
WM_EXITSIZEMOVE = 0x0232
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCLBUTTONDBLCLK = 0x00A3
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_CAPTURECHANGED = 0x0215
HTCAPTION = 2
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
DRAG_RATE = 20.0
USER32 = ctypes.WinDLL("user32", use_last_error=True)
WM_KEYDOWN = 0x0100


class _WindowDragFilter(QAbstractNativeEventFilter):
    """把应用级原生消息转给自己的主窗口（非客户区消息 Qt 不会转给 widget）。"""

    def __init__(self, window) -> None:
        super().__init__()
        self._window = window

    def nativeEventFilter(self, event_type, message):
        window = self._window
        if window is None:
            return False, 0
        try:
            result = window.filter_native(message)
        except Exception:
            result = None
        if result is None:
            return False, 0
        return True, result


class CaptionDragMixin:
    """拖动标题栏 / 缩放边框 / 高度自适应 的 Win32 侧实现。"""

    def _animate_height(self, target: int, duration: int = 210) -> None:
        """窗口高度平滑过渡（展开折叠区时和卡片动画同帧）。"""
        floor = max(self.minimumHeight(), self.minimumSizeHint().height())
        target = int(max(floor, min(target, self._max_height())))
        if target == self.height() or duration <= 0:
            return
        anim = getattr(self, "_height_anim", None)
        if anim is not None:
            anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(float(self.height()))
        anim.setEndValue(float(target))
        anim.setDuration(int(duration))
        anim.setEasingCurve(QEasingCurve.InOutCubic)
        anim.valueChanged.connect(lambda value: self.resize(self.width(), int(value)))
        anim.finished.connect(lambda: self.resize(self.width(), target))
        self._height_anim = anim
        anim.start()

    def _max_height(self) -> int:
        screen = QApplication.desktop().availableGeometry(self)
        return max(320, screen.height() - 80)

    def _animate_width(self, target: int, duration: int = 260) -> None:
        anim = getattr(self, "_width_anim", None)
        if anim is not None:
            anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(float(self.width()))
        anim.setEndValue(float(int(target)))
        anim.setDuration(int(duration))
        anim.setEasingCurve(QEasingCurve.OutBack)        # 回弹
        anim.valueChanged.connect(lambda value: self.resize(int(value), self.height()))
        anim.finished.connect(lambda: self.resize(int(target), self.height()))
        self._width_anim = anim
        anim.start()

    def _min_width_for_cards(self) -> int:
        """卡片并排时窗口不能再窄的宽度（再窄就会互相挤压）。"""
        host = self.cards_host.minimumSizeHint().width()
        margins = self.centralWidget().layout().contentsMargins()
        chrome = margins.left() + margins.right() + 4
        return int(max(self.minimumWidth(), host + chrome))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_busy_geometry()
        if (getattr(self, "_drag_active", False) or getattr(self, "_easing", False)
                or getattr(self, "_width_guard", False)):
            return
        # 用户手动改窗口大小后，若卡片被挤掉就重新贴合高度（#5）
        if getattr(self, "_fit_timer", None) is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._fit_height(allow_shrink=False, animate=True))
            self._fit_timer = timer
        self._fit_timer.start(240)
        need = self._min_width_for_cards()
        if self.width() < need and not self.isMaximized():
            guard = getattr(self, "_squeeze_timer", None)
            if guard is None:
                guard = QTimer(self)
                guard.setSingleShot(True)
                guard.timeout.connect(self._spring_back_width)
                self._squeeze_timer = guard
            guard.start(160)

    def _spring_back_width(self) -> None:
        if self.isMaximized() or self.isFullScreen():
            return
        if getattr(self, "_caption_drag", False) or getattr(self, "_drag_active", False):
            return
        need = self._min_width_for_cards()
        if self.width() < need:
            self._animate_width(need)

    # ------------------------------------------------- 窗口拖动缓动（自己接管标题栏）
    # 为什么要自己接管：Windows 的拖动是「模态移动循环」，它发来的 WM_MOVING
    # 里的矩形是相对**当前窗口位置**算出来的增量。在里面做插值只会让窗口
    # 以 k 倍速度爬行（实测 k≈0.34 时，光标走 240px 窗口只走 82px），
    # 表现就是「难拖动」。所以拖动这一路改成自己跑：按下标题栏时拿到鼠标
    # 抓取点，每帧按指数缓动把窗口位置往「光标 - 抓取点」逼近，跟悬浮窗
    # 那套插值完全一致。缩放（拖边框）交给系统原生，保持即时跟手。
    def _drag_log(self, text: str) -> None:
        path = os.environ.get("VEXRUSH_DRAG_LOG")
        if not path:
            return
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("%.3f %s\n" % (time.perf_counter(), text))
        except Exception:
            pass

    def _caption_start(self) -> bool:
        """标题栏按下：接管拖动。返回 True 表示已经处理，不再走系统默认。"""
        try:
            cursor = win32api.GetCursorPos()
        except Exception:
            return False
        # 双击标题栏要能最大化/还原：系统会在第一次按下后等第二次按下才算双击，
        # 但第一次按下已经被我们接管了，所以自己判断「短时间内几乎没动的第二次按下」。
        last = getattr(self, "_last_click", None)
        if last is not None:
            stamp, spot = last
            if (time.perf_counter() - stamp < 0.45
                    and abs(cursor[0] - spot[0]) <= 6 and abs(cursor[1] - spot[1]) <= 6):
                self._last_click = None
                if self.isMaximized():
                    self.showNormal()
                else:
                    self.showMaximized()
                return True
        if self.isMaximized() or self.isFullScreen():
            return False
        try:
            hwnd = int(self.winId())
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            return False
        for name in ("_fit_timer", "_squeeze_timer"):
            timer = getattr(self, name, None)
            if timer is not None:
                timer.stop()
        anim = getattr(self, "_width_anim", None)
        if anim is not None:
            anim.stop()
        self._drag_grab = (cursor[0] - rect[0], cursor[1] - rect[1])
        self._drag_origin = (rect[0], rect[1])
        self._last_click = None
        self._drag_pos = [float(rect[0]), float(rect[1])]
        self._drag_target = (float(rect[0]), float(rect[1]))
        self._drag_stamp = time.perf_counter()
        self._drag_active = True
        self._caption_drag = True
        try:
            USER32.SetCapture(hwnd)
        except Exception:
            pass
        if not self.isActiveWindow():
            try:
                winapi.bring_to_front(hwnd)
            except Exception:
                pass
        timer = getattr(self, "_drag_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setTimerType(Qt.PreciseTimer)
            timer.setInterval(winapi.frame_interval_ms())
            timer.timeout.connect(self._caption_step)
            self._drag_timer = timer
        timer.start()
        self._drag_log("start pos=%s grab=%s" % (self._drag_pos, self._drag_grab))
        return True

    def _caption_step(self) -> None:
        if not getattr(self, "_caption_drag", False):
            return
        try:
            hwnd = int(self.winId())
            cursor = win32api.GetCursorPos()
        except Exception:
            return
        grab = getattr(self, "_drag_grab", (0, 0))
        target = (float(cursor[0] - grab[0]), float(cursor[1] - grab[1]))
        pos = getattr(self, "_drag_pos", [target[0], target[1]])
        now = time.perf_counter()
        dt = min(0.05, max(0.002, now - getattr(self, "_drag_stamp", now)))
        self._drag_stamp = now
        dx, dy = target[0] - pos[0], target[1] - pos[1]
        if abs(dx) + abs(dy) > 2000.0:      # 光标瞬移（切显示器等）就直接对齐
            pos = [target[0], target[1]]
            dx = dy = 0.0
        else:
            k = min(0.55, 1.0 - math.exp(-dt * DRAG_RATE))
            pos = [pos[0] + dx * k, pos[1] + dy * k]
            if abs(target[0] - pos[0]) < 0.6:
                pos[0] = target[0]
            if abs(target[1] - pos[1]) < 0.6:
                pos[1] = target[1]
        self._drag_pos = pos
        self._drag_target = target
        self._drag_log("step target=%s pos=%s" % (target, (round(pos[0], 1), round(pos[1], 1))))
        try:
            win32gui.SetWindowPos(hwnd, 0, int(round(pos[0])), int(round(pos[1])), 0, 0,
                                  SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception:
            pass

    def _caption_end(self, snap: bool = True) -> None:
        if snap and getattr(self, "_caption_drag", False):
            try:
                hwnd = int(self.winId())
                target = getattr(self, "_drag_target", None)
                if target is not None:
                    win32gui.SetWindowPos(hwnd, 0, int(round(target[0])),
                                          int(round(target[1])), 0, 0,
                                          SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            except Exception:
                pass
        timer = getattr(self, "_drag_timer", None)
        if timer is not None:
            timer.stop()
        if getattr(self, "_caption_drag", False):
            try:
                if USER32.GetCapture() == int(self.winId()):
                    USER32.ReleaseCapture()
            except Exception:
                pass
        self._caption_drag = False
        self._drag_active = False
        try:
            cursor = win32api.GetCursorPos()
        except Exception:
            cursor = None
        origin = getattr(self, "_drag_origin", None)
        if snap and cursor is not None and origin is not None:
            if abs(cursor[0] - origin[0]) <= 4 and abs(cursor[1] - origin[1]) <= 4:
                self._last_click = (time.perf_counter(), cursor)
        else:
            self._last_click = None
        self._drag_log("end snap=%s target=%s" % (snap, getattr(self, "_drag_target", None)))
        self.mark_dirty()
        QTimer.singleShot(70, lambda: self._fit_height(allow_shrink=False, animate=True))

    def filter_native(self, message):
        """应用级过滤器调到这里；返回 None 表示不拦，返回数字表示吃掉并返回它。"""
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
        except Exception:
            return None
        handled = self._handle_native_msg(msg)
        if not handled:
            return None
        return handled[1]

    def nativeEvent(self, event_type, message):
        """兜底：万一某条消息走到了窗口过程，这里同样处理一遍。"""
        if event_type != b"windows_generic_MSG":
            return super().nativeEvent(event_type, message)
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
        except Exception:
            return super().nativeEvent(event_type, message)
        handled = self._handle_native_msg(msg)
        if handled:
            return True, handled[1]
        return super().nativeEvent(event_type, message)

    def _handle_native_msg(self, msg):
        """返回 (True, 返回值) 表示吃掉这条消息；返回 None 表示放行。"""
        own = getattr(self, "_hwnd", 0)
        if not own:
            return None
        command = msg.message
        smooth = bool(getattr(self.cfg, "smooth_window", False))
        same_window = (int(msg.hWnd) == own)
        if command == WM_NCLBUTTONDOWN and same_window:
            if smooth and msg.wParam == HTCAPTION and self._caption_start():
                return True, 1
            return None
        if command == WM_NCLBUTTONDBLCLK and same_window:
            if smooth and msg.wParam == HTCAPTION:
                if self.isMaximized():
                    self.showNormal()
                else:
                    self.showMaximized()
                return True, 1
            return None
        if getattr(self, "_caption_drag", False) and same_window:
            if command == WM_MOUSEMOVE:
                return True, 0
            if command == WM_LBUTTONDOWN:
                return True, 0
            if command in (WM_LBUTTONUP, WM_NCLBUTTONUP):
                self._drag_log("lbuttonup")
                self._caption_end(snap=True)
                return True, 0
            if command == WM_KEYDOWN and msg.wParam == 0x1B:      # Esc 取消这次拖动
                self._caption_end(snap=True)
                return True, 0
            if command == WM_CAPTURECHANGED:
                self._caption_end(snap=False)
                return None
        # 系统模态循环（拖边框缩放）：期间不能让自动贴合插一脚，否则会互相推
        if command == winapi.WM_HOTKEY:
            mapping = getattr(self, "_hotkey_map", None) or {}
            name = mapping.get(int(msg.wParam))
            if name:
                self._on_hotkey(name)
                return True, 0
            return None
        if command == WM_ENTERSIZEMOVE and same_window:
            self._drag_active = True
            for name in ("_fit_timer", "_squeeze_timer"):
                timer = getattr(self, name, None)
                if timer is not None:
                    timer.stop()
            return None
        if command == WM_EXITSIZEMOVE and same_window:
            self._drag_active = False
            QTimer.singleShot(80, lambda: self._fit_height(allow_shrink=False, animate=True))
            if self.width() < self._min_width_for_cards():
                QTimer.singleShot(140, self._spring_back_width)
            return None

    def _fit_height(self, allow_shrink: bool = False, animate: bool = True) -> None:
        """让窗口高度贴合卡片内容：挤到就长高，多出空白就收一点。"""
        if getattr(self, "_caption_drag", False) or getattr(self, "_drag_active", False):
            return
        viewport = self.cards_scroll.viewport().height()
        content = self.cards_host.sizeHint().height()
        if viewport <= 0 or content <= 0:
            return
        delta = content - viewport
        if abs(delta) <= 2:
            return
        if delta < 0 and not allow_shrink:
            return
        target = min(self.height() + delta, self._max_height())
        if target == self.height():
            return
        if abs(delta) <= 2:
            return
        if animate:
            self._animate_height(target, 150)
        else:
            self.resize(self.width(), int(target))

    # ------------------------------------------------------------- 心跳
