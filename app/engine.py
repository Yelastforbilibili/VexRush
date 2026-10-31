"""连点引擎：目标窗口注册、全局输入监听、双通道连点线程。"""
from __future__ import annotations

import threading
import time
from typing import Dict, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from . import winapi
from .config import ChannelConfig
from .i18n import tr

try:
    from pynput import keyboard as pynput_keyboard
    from pynput import mouse as pynput_mouse
except ImportError:  # pragma: no cover
    pynput_keyboard = pynput_mouse = None


# ---------------------------------------------------------------- 输入状态

class InputState:
    """记录哪些触发键正被按住（"m:left"、"k:f1"）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._down: Dict[str, bool] = {}

    def set(self, spec: str, down: bool) -> None:
        if not spec:
            return
        with self._lock:
            if down:
                self._down[spec] = True
            else:
                self._down.pop(spec, None)

    def is_down(self, spec: str) -> bool:
        with self._lock:
            return bool(self._down.get(spec))

    def clear(self) -> None:
        with self._lock:
            self._down.clear()


class InputHub(QObject):
    """用 pynput 监听全局鼠标/键盘，转成 InputState + 热键信号。"""

    stateChanged = pyqtSignal(str, bool)
    hotkeyPressed = pyqtSignal(str)
    failed = pyqtSignal(str)

    _MOUSE_MAP = {}
    if pynput_mouse is not None:
        _MOUSE_MAP = {
            pynput_mouse.Button.left: "m:left",
            pynput_mouse.Button.right: "m:right",
            pynput_mouse.Button.middle: "m:middle",
        }

    def __init__(self, state: InputState, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.ignore_ime = False
        self._mouse_listener = None
        self._key_listener = None
        self._started = False

    # -- 生命周期 --------------------------------------------------
    def start(self) -> bool:
        if self._started or pynput_mouse is None:
            return self._started
        try:
            self._mouse_listener = pynput_mouse.Listener(on_click=self._on_click)
            self._mouse_listener.daemon = True
            self._mouse_listener.start()
            self._key_listener = pynput_keyboard.Listener(on_press=self._on_press,
                                                          on_release=self._on_release)
            self._key_listener.daemon = True
            self._key_listener.start()
            self._started = True
        except Exception as exc:  # pragma: no cover - 依赖系统环境
            self.failed.emit(tr("failed_to_start_global_listener") % exc)
            self._started = False
        return self._started

    def stop(self) -> None:
        for listener in (self._mouse_listener, self._key_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
        self._mouse_listener = None
        self._key_listener = None
        self._started = False
        self.state.clear()

    # -- 回调 ------------------------------------------------------
    def _on_click(self, _x, _y, button, pressed) -> None:
        spec = self._MOUSE_MAP.get(button)
        if not spec:
            return
        if pressed and self.ignore_ime and winapi.text_input_active():
            # 正在打字（光标在输入框里 / 输入法拼字中）：这下的按下不算触发
            return
        self.state.set(spec, pressed)
        try:
            self.stateChanged.emit(spec, bool(pressed))
        except RuntimeError:  # 窗口已销毁
            pass

    def _on_press(self, key) -> None:
        name = winapi.canon_key(getattr(key, "name", None) or getattr(key, "char", "") or "")
        if not name:
            return
        if self.ignore_ime and winapi.text_input_active():
            # 正在打字：这一下按键交给前台程序，热键与键盘触发都不响应
            return
        spec = "k:" + name
        self.state.set(spec, True)
        try:
            self.stateChanged.emit(spec, True)
            self.hotkeyPressed.emit(name)
        except RuntimeError:
            pass

    def _on_release(self, key) -> None:
        name = winapi.canon_key(getattr(key, "name", None) or getattr(key, "char", "") or "")
        if not name:
            return
        spec = "k:" + name
        self.state.set(spec, False)
        try:
            self.stateChanged.emit(spec, False)
        except RuntimeError:
            pass


# ---------------------------------------------------------------- 目标窗口

class TargetRegistry(QObject):
    """后台线程解析“要连点的窗口”，供两个通道共享。"""

    changed = pyqtSignal(int, str, str)  # hwnd, 进程名, 标题

    SCAN_INTERVAL = 0.9

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._hwnd = 0
        self._proc = ""
        self._title = ""
        self._process_name = ""
        self._manual_hwnd = 0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._wake = threading.Event()

    # -- 对外 ------------------------------------------------------
    def hwnd(self) -> int:
        with self._lock:
            return self._hwnd if winapi.is_window(self._hwnd) else 0

    def process_name(self) -> str:
        with self._lock:
            return self._process_name

    def info(self) -> tuple:
        with self._lock:
            return (self._hwnd, self._proc, self._title)

    def set_process(self, name: str, manual_hwnd: int = 0) -> None:
        with self._lock:
            self._process_name = str(name or "").strip()
            self._manual_hwnd = int(manual_hwnd or 0)
        self.refresh_now()

    def set_manual_hwnd(self, hwnd: int) -> None:
        with self._lock:
            self._manual_hwnd = int(hwnd or 0)
        self.refresh_now()

    def refresh_now(self) -> None:
        self._wake.set()
        self._resolve()

    # -- 解析 ------------------------------------------------------
    def _resolve(self) -> None:
        with self._lock:
            manual = self._manual_hwnd
            name = self._process_name
        hwnd, proc, title = 0, "", ""
        if manual and winapi.is_window(manual):
            hwnd = manual
            proc = winapi.process_name(winapi.window_pid(manual))
            title = winapi.window_title(manual)
        elif name:
            hwnd = winapi.find_target_window(name)
            if hwnd:
                pid = winapi.window_pid(hwnd)
                proc = winapi.process_name(pid)
                title = winapi.window_title(hwnd)
        with self._lock:
            changed = (hwnd, proc, title) != (self._hwnd, self._proc, self._title)
            if changed:
                self._hwnd, self._proc, self._title = hwnd, proc, title
        if changed:
            try:
                self.changed.emit(hwnd, proc, title)
            except RuntimeError:
                pass

    # -- 线程 ------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="target-registry", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._resolve()
            except Exception:
                pass
            self._wake.wait(self.SCAN_INTERVAL)
            self._wake.clear()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)


# ---------------------------------------------------------------- 连点线程

class ClickWorker(threading.Thread):
    """按通道配置循环投递点击；间隔变化即时生效。

    时间基准必须是 time.perf_counter()（QPC，亚微秒精度）：
    Windows 上 time.perf_counter() 走 GetTickCount64，粒度约 15.6ms，
    用它排程会让所有间隔 ≤15ms 的设置全部塌缩成 ~16ms 一次。
    """

    MAX_CATCH_UP = 4      # 落后时一次最多补几次，避免瞬间洪水

    def __init__(self, channel: "Channel") -> None:
        super().__init__(name="clicker-%d" % channel.index, daemon=True)
        self.channel = channel
        self.clicks = 0
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        clock = self.channel.shared.precision
        engaged = False
        next_at = 0.0
        try:
            while not self._stop_event.is_set():
                interval = max(0.001, self.channel.cfg.interval_ms / 1000.0)
                if self.channel.is_clicking():
                    if not engaged:
                        engaged = True
                        clock.acquire()
                        next_at = time.perf_counter()
                    now = time.perf_counter()
                    if now >= next_at:
                        sent = 0
                        while now >= next_at and sent < self.MAX_CATCH_UP:
                            if self.channel.fire_click():
                                self.clicks += 1
                            sent += 1
                            next_at += interval
                            now = time.perf_counter()
                        if now >= next_at:          # 落后太多，重新对齐
                            next_at = now + interval
                        continue
                    remain = next_at - now
                    if remain > 0.0015:
                        self._stop_event.wait(remain - 0.0010)
                    else:
                        time.sleep(0)
                else:
                    if engaged:
                        engaged = False
                        clock.release()
                    self._stop_event.wait(0.005)
        finally:
            if engaged:
                clock.release()


# ---------------------------------------------------------------- 共享状态

class SharedState:
    def __init__(self) -> None:
        self.registry = TargetRegistry()
        self.input_state = InputState()
        self.precision = winapi.PrecisionClock(1)
        self.send_mode = "post"
        self.guard_self = True
        self.ime_guard = False

    def close(self) -> None:
        self.precision.close()
        self.registry.stop()


class Channel:
    """一路连点：配置 + 线程 + 统计。"""

    def __init__(self, index: int, shared: SharedState) -> None:
        self.index = index
        self.shared = shared
        self.cfg = ChannelConfig()
        self.worker = ClickWorker(self)
        self._cps = 0.0
        self._last_count = 0
        self._last_time = time.perf_counter()

    # -- 状态 ------------------------------------------------------
    @property
    def clicks(self) -> int:
        return self.worker.clicks

    def reset_counter(self) -> None:
        self.worker.clicks = 0
        self._last_count = 0
        self._cps = 0.0
        self._last_time = time.perf_counter()

    def is_clicking(self) -> bool:
        if not self.cfg.enabled:
            return False
        if self.shared.guard_self and winapi.foreground_is_self():
            return False
        if self.shared.ime_guard and winapi.text_input_active():
            # 打字期间即使已经在按住，也立刻停下来
            return False
        return self.shared.input_state.is_down(self.cfg.trigger_spec())

    def is_holding(self) -> bool:
        """触发键是否被按住（不受开关影响，用于界面显示）。"""
        return self.shared.input_state.is_down(self.cfg.trigger_spec())

    def fire_click(self) -> bool:
        hwnd = self.shared.registry.hwnd()
        if not hwnd:
            return False
        return winapi.send_mouse_click(hwnd, self.cfg.sim_mouse, self.shared.send_mode == "send")

    def sample_cps(self) -> float:
        now = time.perf_counter()
        delta = now - self._last_time
        if delta <= 0:
            return self._cps
        count = self.worker.clicks
        rate = max(0.0, (count - self._last_count) / delta)
        self._last_count = count
        self._last_time = now
        self._cps = rate if rate > self._cps else self._cps * 0.55 + rate * 0.45
        if self._cps < 0.4:
            self._cps = 0.0
        return self._cps

    @property
    def cps(self) -> float:
        return self._cps

    # -- 生命周期 --------------------------------------------------
    def start(self) -> None:
        if not self.worker.is_alive():
            self.worker = ClickWorker(self)
            self.worker.start()

    def stop(self) -> None:
        self.worker.stop()
        if self.worker.is_alive():
            self.worker.join(timeout=1.0)
