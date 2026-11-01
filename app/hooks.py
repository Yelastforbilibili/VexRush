"""全局低级输入钩子（键盘 + 鼠标），不依赖 pynput。

单文件打包后 pynput 的钩子线程在某些环境下静默失效：线程起来、``running`` 仍是真，
但回调一次都不来。这里自己用 ctypes 装 ``WH_KEYBOARD_LL`` / ``WH_MOUSE_LL``，
把安装结果、错误码和存活状态都写进日志，装不上也能立刻看到。

钩子回调跑在独立线程的消息循环里，只做「改状态 + 发 Qt 信号」，不碰界面。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
from typing import Callable

from . import debug, winapi

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_QUIT = 0x0012

USER32 = ctypes.WinDLL("user32", use_last_error=True)
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)

WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
LRESULT = ctypes.c_ssize_t

USER32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
USER32.SetWindowsHookExW.restype = ctypes.c_void_p
USER32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
USER32.UnhookWindowsHookEx.restype = ctypes.c_bool
# 第 4 个参数是 64 位 lParam：不声明 argtypes 会被按 32 位截断而抛 OverflowError，
# 回调抛异常时 ctypes 返回非零值，等于把这条输入从系统链上吞掉。
USER32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, WPARAM, LPARAM]
USER32.CallNextHookEx.restype = LRESULT
USER32.GetMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG), ctypes.c_void_p,
                               ctypes.c_uint, ctypes.c_uint]
USER32.GetMessageW.restype = ctypes.c_int
USER32.PostThreadMessageW.argtypes = [ctypes.c_uint, ctypes.c_uint, WPARAM, LPARAM]
KERNEL32.GetCurrentThreadId.restype = ctypes.c_uint


class _KbdLlHookStruct(ctypes.Structure):
    _fields_ = [("vkCode", ctypes.wintypes.DWORD),
                ("scanCode", ctypes.wintypes.DWORD),
                ("flags", ctypes.wintypes.DWORD),
                ("time", ctypes.wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


_HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)

_MOUSE_NAMES = {
    WM_LBUTTONDOWN: ("m:left", True),
    WM_LBUTTONUP: ("m:left", False),
    WM_RBUTTONDOWN: ("m:right", True),
    WM_RBUTTONUP: ("m:right", False),
    WM_MBUTTONDOWN: ("m:middle", True),
    WM_MBUTTONUP: ("m:middle", False),
}


class LowLevelHooks(threading.Thread):
    """一个线程同时装键盘与鼠标钩子，用消息循环保持钩子有效。"""

    def __init__(self, on_key: Callable[[str, bool], None],
                 on_mouse: Callable[[str, bool], None]) -> None:
        super().__init__(name="vexrush-hooks", daemon=True)
        self._on_key = on_key
        self._on_mouse = on_mouse
        self._thread_id = 0
        self._keyboard_hook = None
        self._mouse_hook = None
        self._ready = threading.Event()
        self._alive = False
        self.installed = False
        self.count = 0
        self.last_error = 0
        self._key_proc = _HOOKPROC(self._keyboard_callback)
        self._mouse_proc = _HOOKPROC(self._mouse_callback)

    # -- 生命周期 --------------------------------------------------
    def run(self) -> None:
        self._thread_id = KERNEL32.GetCurrentThreadId()
        try:
            # 低级钩子的回调在装钩子的进程内执行，hMod 传 0 即可；
            # 传 exe 的模块句柄在部分打包方式下会装不上。
            self._keyboard_hook = USER32.SetWindowsHookExW(WH_KEYBOARD_LL, self._key_proc, None, 0)
            key_error = ctypes.get_last_error()
            self._mouse_hook = USER32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, None, 0)
            mouse_error = ctypes.get_last_error()
            self.installed = bool(self._keyboard_hook) and bool(self._mouse_hook)
            self._alive = self.installed
            self.last_error = key_error or mouse_error
            debug.log("hook", "install keyboard=%s (%s) mouse=%s (%s)"
                      % (bool(self._keyboard_hook), key_error,
                         bool(self._mouse_hook), mouse_error))
        except Exception as exc:                        # pragma: no cover - 依赖系统环境
            self.installed = False
            self._alive = False
            debug.log("hook", "install failed: %r" % (exc,))
        finally:
            self._ready.set()
        if not self.installed:
            return
        message = ctypes.wintypes.MSG()
        while USER32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            USER32.TranslateMessage(ctypes.byref(message))
            USER32.DispatchMessageW(ctypes.byref(message))
        self._alive = False
        self._unhook()
        debug.log("hook", "loop finished after %d events" % self.count)

    def wait_ready(self, timeout: float = 2.0) -> bool:
        self._ready.wait(timeout)
        return self.installed

    def alive(self) -> bool:
        return bool(self._alive and self.is_alive())

    def events(self) -> int:
        return int(self.count)

    def stop(self) -> None:
        self._alive = False
        if self._thread_id:
            try:
                USER32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass

    def _unhook(self) -> None:
        for hook in (self._keyboard_hook, self._mouse_hook):
            if hook:
                try:
                    USER32.UnhookWindowsHookEx(hook)
                except Exception:
                    pass
        self._keyboard_hook = None
        self._mouse_hook = None

    def _call_next(self, hook, code: int, wparam: int, lparam: int) -> int:
        try:
            return int(USER32.CallNextHookEx(hook, code, wparam, lparam))
        except Exception:
            return 0            # 放行：任何异常都不能把输入吞掉

    # -- 回调 ------------------------------------------------------
    def _keyboard_callback(self, code: int, wparam: int, lparam: int) -> int:
        if code == 0:
            try:
                info = ctypes.cast(lparam, ctypes.POINTER(_KbdLlHookStruct)).contents
                up = wparam in (WM_KEYUP, WM_SYSKEYUP)
                if up or wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    name = winapi.vk_name(int(info.vkCode))
                    if name:
                        self.count += 1
                        self._on_key(name, not up)
            except Exception as exc:                    # pragma: no cover
                debug.log("hook", "keyboard callback error: %r" % (exc,))
        return self._call_next(self._keyboard_hook, code, wparam, lparam)

    def _mouse_callback(self, code: int, wparam: int, lparam: int) -> int:
        if code == 0:
            try:
                mapped = _MOUSE_NAMES.get(int(wparam))
                if mapped:
                    self.count += 1
                    self._on_mouse(mapped[0], mapped[1])
            except Exception as exc:                    # pragma: no cover
                debug.log("hook", "mouse callback error: %r" % (exc,))
        return self._call_next(self._mouse_hook, code, wparam, lparam)
