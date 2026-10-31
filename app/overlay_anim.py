"""悬浮显示的显隐动画与缓动曲线（与绘制、菜单无关）。"""
from __future__ import annotations

import math
import time
from typing import Tuple

from PyQt5.QtCore import QTimer


class OverlayAnimMixin:
    """入场/出场：淡入、缩放、滑入、弹簧、柔焦。"""

    @staticmethod
    def _ease_out_cubic(p: float) -> float:
        return 1.0 - (1.0 - p) ** 3

    @staticmethod
    @staticmethod
    def _ease_out_back(p: float, overshoot: float = 1.34) -> float:
        q = p - 1.0
        return 1.0 + (overshoot + 1.0) * q ** 3 + overshoot * q ** 2

    @staticmethod
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
