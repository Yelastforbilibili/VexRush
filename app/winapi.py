"""Win32 封装：找目标窗口、投递鼠标消息、键名映射、DPI/标题栏小工具。

只在 Windows 上运行。所有对外函数都做了健壮性保护，避免控件线程被异常打断。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import time
from typing import Dict, List, Optional, Tuple
from .i18n import tr

try:  # pragma: no cover - 非 Windows 环境仅用于静态检查
    import win32api
    import win32con
    import win32gui
    import win32process
except ImportError:  # pragma: no cover
    win32api = win32con = win32gui = win32process = None

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

try:
    from ctypes import wintypes
except ImportError:  # pragma: no cover
    wintypes = None

USER32 = ctypes.windll.user32 if os.name == "nt" else None
SHELL32 = ctypes.windll.shell32 if os.name == "nt" else None

# ---------------------------------------------------------------- 常量

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_APPWINDOW = 0x00040000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

DWMWA_USE_IMMERSIVE_DARK_MODE = 20

MOUSE_DOWN_UP = {
    "left": (0x0201, 0x0202, 0x0001),    # WM_LBUTTONDOWN / UP, MK_LBUTTON
    "right": (0x0204, 0x0205, 0x0002),   # WM_RBUTTONDOWN / UP, MK_RBUTTON
    "middle": (0x0207, 0x0208, 0x0010),  # WM_MBUTTONDOWN / UP, MK_MBUTTON
}

MOUSE_VK = {"left": 0x01, "right": 0x02, "middle": 0x04}

# ---------------------------------------------------------------- 键名

_VK_BY_NAME = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "shift": 0x10,
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "menu": 0x12, "pause": 0x13,
    "caps_lock": 0x14, "esc": 0x1B, "escape": 0x1B, "space": 0x20, "page_up": 0x21,
    "page_down": 0x22, "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26,
    "right": 0x27, "down": 0x28, "insert": 0x2D, "delete": 0x2E,
    "num_lock": 0x90, "scroll_lock": 0x91, "print_screen": 0x2C,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
for _i in range(1, 25):
    _VK_BY_NAME["f%d" % _i] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz":
    _VK_BY_NAME[_c] = ord(_c.upper())
for _d in "0123456789":
    _VK_BY_NAME[_d] = ord(_d)

_CANON_ALIASES = {
    "esc": "esc", "escape": "esc", "return": "enter", "control": "ctrl",
    "menu": "alt", "lshift": "shift", "rshift": "shift", "lctrl": "ctrl",
    "rctrl": "ctrl", "lalt": "alt", "ralt": "alt", "spacebar": "space",
    "prior": "page_up", "next": "page_down", "capital": "caps_lock",
}

_DISPLAY = {
    "esc": "Esc", "enter": "Enter", "tab": "Tab", "space": tr("space"), "backspace": tr("backspace"),
    "delete": "Delete", "insert": "Insert", "home": "Home", "end": "End",
    "page_up": "PgUp", "page_down": "PgDn", "up": "↑", "down": "↓", "left": "←",
    "right": "→", "shift": "Shift", "ctrl": "Ctrl", "alt": "Alt", "caps_lock": "Caps",
    "print_screen": "PrtSc", "num_lock": "NumLock", "scroll_lock": "ScrLock",
    "`": "`", ";": ";", "'": "'", ",": ",", ".": ".", "/": "/", "\\": "\\",
    "[": "[", "]": "]", "-": "-", "=": "=",
}


def canon_key(name: str) -> str:
    """把各种键名写法归一，例如 'Left Ctrl' / 'lctrl' → 'ctrl'。"""
    text = str(name or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not text:
        return ""
    if text.startswith("key."):
        text = text[4:]
    text = _CANON_ALIASES.get(text, text)
    if text.startswith("num_") and len(text) == 5:
        text = text[4:]
    return text


def key_display(name: str) -> str:
    canon = canon_key(name)
    if not canon:
        return tr("not_set")
    if canon in _DISPLAY:
        return _DISPLAY[canon]
    if len(canon) == 1:
        return canon.upper()
    return canon.upper()


def key_vk(name: str) -> int:
    return _VK_BY_NAME.get(canon_key(name), 0)


_QT_NAMES = {
    0x01000000: "esc", 0x01000001: "tab", 0x01000003: "backspace", 0x01000004: "enter",
    0x01000005: "enter", 0x01000007: "delete", 0x01000009: "print_screen",
    0x01000010: "home", 0x01000011: "end", 0x01000012: "left", 0x01000013: "up",
    0x01000014: "right", 0x01000015: "down", 0x01000016: "page_up", 0x01000017: "page_down",
    0x01000020: "shift", 0x01000021: "ctrl", 0x01000023: "alt", 0x01000024: "caps_lock",
    0x01000025: "num_lock", 0x01000026: "scroll_lock", 0x01000030: "f1", 0x01000031: "f2",
    0x01000032: "f3", 0x01000033: "f4", 0x01000034: "f5", 0x01000035: "f6", 0x01000036: "f7",
    0x01000037: "f8", 0x01000038: "f9", 0x01000039: "f10", 0x0100003A: "f11", 0x0100003B: "f12",
    0x20: "space",
}

# F13–F24：Qt 与 Win32 都有，但它们不在上面的常见键表里
for _fk in range(13, 25):
    _QT_NAMES[0x01000030 + _fk - 1] = "f%d" % _fk
del _fk


def qt_key_to_name(key: int) -> str:
    """Qt.Key → 统一的键名。"""
    if key in _QT_NAMES:
        return _QT_NAMES[key]
    if 0x41 <= key <= 0x5A:
        return chr(key).lower()
    if 0x30 <= key <= 0x39:
        return chr(key)
    char = chr(key) if 32 <= key < 128 else ""
    if char and char.lower() in _VK_BY_NAME:
        return char.lower()
    return ""


# ---------------------------------------------------------------- 窗口

def is_window(hwnd) -> bool:
    if not hwnd or win32gui is None:
        return False
    try:
        return bool(win32gui.IsWindow(hwnd))
    except Exception:
        return False


def window_pid(hwnd) -> int:
    if not hwnd or win32process is None:
        return 0
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return int(pid)
    except Exception:
        return 0


def process_name(pid: int) -> str:
    if not pid or psutil is None:
        return ""
    try:
        return psutil.Process(pid).name() or ""
    except Exception:
        return ""


def process_exe_path(pid: int) -> str:
    if not pid or psutil is None:
        return ""
    try:
        return psutil.Process(pid).exe() or ""
    except Exception:
        return ""


def _strip_exe(name: str) -> str:
    text = (name or "").strip().lower()
    return text[:-4] if text.endswith(".exe") else text


def _proc_matches(actual: str, wanted: str) -> bool:
    a, w = _strip_exe(actual), _strip_exe(wanted)
    return bool(a) and bool(w) and (a == w or a.startswith(w) or w.startswith(a))


def window_title(hwnd) -> str:
    try:
        return win32gui.GetWindowText(hwnd) or ""
    except Exception:
        return ""


def window_class(hwnd) -> str:
    try:
        return win32gui.GetClassName(hwnd) or ""
    except Exception:
        return ""


def client_area(hwnd) -> int:
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        return max(0, right - left) * max(0, bottom - top)
    except Exception:
        return 0


def window_rect(hwnd) -> Tuple[int, int, int, int]:
    try:
        return tuple(win32gui.GetWindowRect(hwnd))  # type: ignore[return-value]
    except Exception:
        return (0, 0, 0, 0)


def foreground_window() -> int:
    try:
        return int(win32gui.GetForegroundWindow() or 0)
    except Exception:
        return 0


def foreground_process_name() -> str:
    return process_name(window_pid(foreground_window()))


def is_admin() -> bool:
    """当前进程是否以管理员权限运行。"""
    try:
        return bool(SHELL32.IsUserAnAdmin())
    except Exception:
        return False


def foreground_is_self() -> bool:
    hwnd = foreground_window()
    if not hwnd:
        return False
    return window_pid(hwnd) == os.getpid()


# ---------------------------------------------------------------- 显示器

class _DevModeW(ctypes.Structure):
    _fields_ = [("dmDeviceName", ctypes.c_wchar * 32),
                ("dmSpecVersion", ctypes.c_ushort),
                ("dmDriverVersion", ctypes.c_ushort),
                ("dmSize", ctypes.c_ushort),
                ("dmDriverExtra", ctypes.c_ushort),
                ("dmFields", ctypes.c_uint),
                ("dmPositionX", ctypes.c_long),
                ("dmPositionY", ctypes.c_long),
                ("dmDisplayOrientation", ctypes.c_uint),
                ("dmDisplayFixedOutput", ctypes.c_uint),
                ("dmColor", ctypes.c_short),
                ("dmDuplex", ctypes.c_short),
                ("dmYResolution", ctypes.c_short),
                ("dmTTOption", ctypes.c_short),
                ("dmCollate", ctypes.c_short),
                ("dmFormName", ctypes.c_wchar * 32),
                ("dmLogPixels", ctypes.c_ushort),
                ("dmBitsPerPel", ctypes.c_uint),
                ("dmPelsWidth", ctypes.c_uint),
                ("dmPelsHeight", ctypes.c_uint),
                ("dmDisplayFlags", ctypes.c_uint),
                ("dmDisplayFrequency", ctypes.c_uint),
                ("dmICMMethod", ctypes.c_uint),
                ("dmICMIntent", ctypes.c_uint),
                ("dmMediaType", ctypes.c_uint),
                ("dmDitherType", ctypes.c_uint),
                ("dmReserved1", ctypes.c_uint),
                ("dmReserved2", ctypes.c_uint),
                ("dmPanningWidth", ctypes.c_uint),
                ("dmPanningHeight", ctypes.c_uint)]


MAX_REFRESH_HZ = 144
_refresh_cache = {"value": 0}


def display_refresh_hz() -> int:
    """当前显示器刷新率（Hz），取不到就按 60 算，最高 144。"""
    if _refresh_cache["value"]:
        return _refresh_cache["value"]
    hz = 0
    try:
        mode = _DevModeW()
        mode.dmSize = ctypes.sizeof(_DevModeW)
        if USER32.EnumDisplaySettingsW(None, -1, ctypes.byref(mode)):  # ENUM_CURRENT_SETTINGS
            hz = int(mode.dmDisplayFrequency)
    except Exception:
        hz = 0
    if hz < 30 or hz > 360:      # 1 表示“硬件默认”，按 60 处理
        hz = 60
    hz = min(hz, MAX_REFRESH_HZ)
    _refresh_cache["value"] = hz
    return hz


def frame_interval_ms() -> int:
    """跟随显示器刷新率的一帧时长（毫秒），最低 6ms。"""
    return max(6, int(round(1000.0 / display_refresh_hz())))



# ---------------------------------------------------------------- 输入法

GCS_COMPSTR = 0x0008

try:
    IMM32 = ctypes.WinDLL("imm32") if os.name == "nt" else None
except OSError:  # pragma: no cover
    IMM32 = None

if IMM32 is not None:
    try:
        IMM32.ImmGetContext.restype = ctypes.c_void_p
        IMM32.ImmGetContext.argtypes = [ctypes.c_void_p]
        IMM32.ImmReleaseContext.restype = ctypes.c_int
        IMM32.ImmReleaseContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        IMM32.ImmGetCompositionStringW.restype = ctypes.c_long
        IMM32.ImmGetCompositionStringW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                                  ctypes.c_void_p, ctypes.c_uint]
    except (AttributeError, OSError):  # pragma: no cover
        IMM32 = None


def ime_composing() -> bool:
    """前台窗口的输入法是否正在拼字（候选/组字中）。"""
    if IMM32 is None:
        return False
    hwnd = foreground_window()
    if not hwnd:
        return False
    for target in (hwnd, _focused_child(hwnd)):
        if not target:
            continue
        himc = None
        try:
            himc = IMM32.ImmGetContext(ctypes.c_void_p(target))
            if not himc:
                continue
            length = IMM32.ImmGetCompositionStringW(himc, GCS_COMPSTR, None, 0)
            if length and length > 0:
                return True
        except Exception:
            continue
        finally:
            try:
                if himc:
                    IMM32.ImmReleaseContext(ctypes.c_void_p(target), himc)
            except Exception:
                pass
    return False


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("flags", ctypes.c_uint),
                ("hwndActive", ctypes.c_void_p), ("hwndFocus", ctypes.c_void_p),
                ("hwndCapture", ctypes.c_void_p), ("hwndMenuOwner", ctypes.c_void_p),
                ("hwndMoveSize", ctypes.c_void_p), ("hwndCaret", ctypes.c_void_p),
                ("rcCaret", ctypes.wintypes.RECT)]


def _thread_gui_info(tid: int):
    info = _GuiThreadInfo()
    info.cbSize = ctypes.sizeof(_GuiThreadInfo)
    try:
        if USER32.GetGUIThreadInfo(tid, ctypes.byref(info)):
            return info
    except Exception:
        pass
    return None


def _focused_child(hwnd) -> int:
    """前台窗口里真正吃键盘的那个子窗口（比如编辑框）。"""
    if not hwnd:
        return 0
    pid = window_pid(hwnd)
    import win32process  # 局部导入，避免模块加载期开销
    try:
        tid = win32process.GetWindowThreadProcessId(hwnd)[0]
    except Exception:
        return 0
    info = _thread_gui_info(tid)
    if info is not None and info.hwndFocus:
        return int(info.hwndFocus)
    return int(hwnd)


def caret_visible() -> bool:
    """前台窗口里有没有文字光标（hwndCaret 非空且 rcCaret 有面积）。"""
    hwnd = foreground_window()
    if not hwnd:
        return False
    import win32process
    try:
        tid = win32process.GetWindowThreadProcessId(hwnd)[0]
    except Exception:
        return False
    info = _thread_gui_info(tid)
    if info is None or not info.hwndCaret:
        return False
    rc = info.rcCaret
    return (rc.right - rc.left) > 0 and (rc.bottom - rc.top) > 0


_typing_cache = {"at": 0.0, "value": False}
_TYPING_TTL = 0.12


def text_input_active() -> bool:
    """前台是否正在文字输入（有光标或输入法拼字中）。

    注意：这个判断只在「打字时不响应」开关打开时才会被调用，而那个开关目前默认
    关闭（见 settings.py 的「敬请期待」说明）。

    结果缓存 120ms：连点线程每 1ms 都可能问一次，不能每次都走 Win32。
    """
    now = time.perf_counter()
    if now - _typing_cache["at"] < _TYPING_TTL:
        return bool(_typing_cache["value"])
    value = False
    try:
        value = caret_visible() or ime_composing()
    except Exception:
        value = False
    _typing_cache["at"] = now
    _typing_cache["value"] = value
    return bool(value)



_SKIP_PROCESSES = {
    "textinputhost.exe", "applicationframehost.exe", "searchapp.exe",
    "shellexperiencehost.exe", "startmenuexperiencehost.exe", "dwm.exe",
    "csrss.exe", "winlogon.exe", "lockapp.exe", "taskmgr.exe",
    "systemsettings.exe", "useroobebroker.exe",
}


def _iter_gui_windows(include_self: bool = False) -> List[int]:
    result: List[int] = []
    if win32gui is None:
        return result
    self_pid = os.getpid()

    def _callback(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                return True
            if not window_title(hwnd):
                return True
            ex_style = win32gui.GetWindowLong(hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_TOOLWINDOW:
                return True
            if not include_self and window_pid(hwnd) == self_pid:
                return True
            if client_area(hwnd) < 400:
                return True
            if (process_name(window_pid(hwnd)) or "").lower() in _SKIP_PROCESSES:
                return True
            result.append(int(hwnd))
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_callback, None)
    except Exception:
        pass
    return result


def find_target_window(process_name_wanted: str) -> int:
    """按进程名找可见窗口，取客户区最大的那个（与 AutoCk.py 的实现一致）。

    只做两件事：窗口可见 + psutil 读到的进程名等于目标名。
    """
    proc_name = str(process_name_wanted or "").strip().lower()
    if not proc_name or psutil is None:
        return 0
    best, best_area = 0, 0

    def callback(hwnd, extra):
        nonlocal best, best_area
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid or pid == os.getpid():
                return True
            try:
                name = psutil.Process(pid).name()
            except Exception:
                return True
            if not _proc_matches(name, proc_name):
                return True
            rect = win32gui.GetClientRect(hwnd)
            area = max(0, int(rect[2])) * max(0, int(rect[3]))
            if area >= best_area:
                best, best_area = hwnd, area
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        pass
    return best


def find_window_by_pid(pid: int) -> int:
    best, best_area = 0, 0
    for hwnd in _iter_gui_windows():
        if window_pid(hwnd) != pid:
            continue
        area = client_area(hwnd)
        if area > best_area:
            best, best_area = hwnd, area
    return best


def list_gui_processes() -> List[dict]:
    """列出所有有可见窗口的进程：{proc, pid, hwnd, title, area}，按窗口面积降序。"""
    rows: List[dict] = []
    for hwnd in _iter_gui_windows():
        pid = window_pid(hwnd)
        if not pid:
            continue
        rows.append({
            "pid": pid,
            "hwnd": hwnd,
            "proc": process_name(pid),
            "title": window_title(hwnd),
            "area": client_area(hwnd),
        })
    rows.sort(key=lambda row: row["area"], reverse=True)
    return rows


JAVA_PROCESS_NAMES = ("javaw.exe", "java.exe", "javaw", "java", "minecraft.exe", "hmcl.exe", "pcl.exe")


def detect_java_target() -> Optional[dict]:
    """自动挑选要连点的 Java 程序。

    优先级：
    1. 拥有当前前台窗口的那个 java.exe / javaw.exe（游戏正在前台时直接命中）
    2. 面积最大的 java.exe / javaw.exe 窗口
    """
    candidates = [row for row in list_gui_processes()
                  if _strip_exe(row["proc"]) in {_strip_exe(n) for n in JAVA_PROCESS_NAMES}]
    if not candidates:
        return None
    front = foreground_window()
    front_pid = window_pid(front) if front else 0
    if front_pid:
        for row in candidates:
            if row["pid"] == front_pid:
                return row
    return candidates[0]


# ---------------------------------------------------------------- 投递点击

def send_mouse_click(hwnd, button: str = "left", sync: bool = False) -> bool:
    """把一次按下 + 抬起投递给目标窗口（后台消息，不移动真实光标）。"""
    if win32gui is None or not is_window(hwnd):
        return False
    spec = MOUSE_DOWN_UP.get(button)
    if not spec:
        return False
    down_msg, up_msg, wparam = spec
    try:
        # 用它真实的鼠标位置换算客户区坐标（与 AutoCk.py 一致）：点在哪个控件上就投到哪里
        cx, cy = win32gui.ScreenToClient(int(hwnd), win32api.GetCursorPos())
        point = win32api.MAKELONG(int(cx) & 0xFFFF, int(cy) & 0xFFFF)
        poster = win32gui.SendMessage if sync else win32gui.PostMessage
        poster(hwnd, down_msg, wparam, point)
        poster(hwnd, up_msg, 0, point)
        return True
    except Exception:
        return False


def click_payload(hwnd) -> Optional[int]:
    if not is_window(hwnd):
        return None
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        return win32api.MAKELONG(max(0, (right - left) // 2), max(0, (bottom - top) // 2))
    except Exception:
        return None


# ---------------------------------------------------------------- 窗口小工具

def set_click_through(hwnd, enabled: bool) -> None:
    """让悬浮窗不接收鼠标（点击穿透）。"""
    if USER32 is None or not hwnd:
        return
    try:
        style = USER32.GetWindowLongW(int(hwnd), GWL_EXSTYLE)
        if enabled:
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
            style |= WS_EX_LAYERED
        USER32.SetWindowLongW(int(hwnd), GWL_EXSTYLE, style)
    except Exception:
        pass


def set_tool_window(hwnd, enabled: bool = True) -> None:
    if USER32 is None or not hwnd:
        return
    try:
        style = USER32.GetWindowLongW(int(hwnd), GWL_EXSTYLE)
        if enabled:
            style = (style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
        else:
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        USER32.SetWindowLongW(int(hwnd), GWL_EXSTYLE, style)
    except Exception:
        pass


def apply_dark_titlebar(hwnd, dark: bool = True) -> None:
    if os.name != "nt" or not hwnd:
        return
    try:
        value = ctypes.c_int(1 if dark else 0)
        dwm = ctypes.windll.dwmapi
        for attribute in (DWMWA_USE_IMMERSIVE_DARK_MODE, 19):
            if dwm.DwmSetWindowAttribute(int(hwnd), attribute,
                                         ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        flags = SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
        ctypes.windll.user32.SetWindowPos(int(hwnd), 0, 0, 0, 0, 0, flags)
    except Exception:
        pass


def set_app_user_model_id(app_id: str = "VexRush.Clicker.1") -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000


def register_hotkey(hwnd: int, hotkey_id: int, vk: int) -> bool:
    """注册系统级热键：即使焦点在别的程序、甚至全局钩子被拦，也能收到 WM_HOTKEY。"""
    try:
        return bool(USER32.RegisterHotKey(int(hwnd), int(hotkey_id), MOD_NOREPEAT, int(vk)))
    except Exception:
        return False


def unregister_hotkey(hwnd: int, hotkey_id: int) -> None:
    try:
        USER32.UnregisterHotKey(int(hwnd), int(hotkey_id))
    except Exception:
        pass


# -- 原始输入（Raw Input）------------------------------------------------
# 低级键盘钩子依赖「输入队列与完整性级别」，前台是全屏独占/游戏窗口时可能收不到。
# 原始输入用 RIDEV_INPUTSINK 注册到我们自己的窗口，即使窗口不在前台，按键也会投递
# 成 WM_INPUT，是这类工具最稳的一条通道。
WM_INPUT = 0x00FF
RIDEV_REMOVE = 0x00000001
RIDEV_INPUTSINK = 0x00000100
RID_INPUT = 0x10000003
RIM_TYPEKEYBOARD = 1
RI_KEY_BREAK = 0x01
RI_KEY_E0 = 0x02
RI_KEY_E1 = 0x04


class _RawInputDevice(ctypes.Structure):
    _fields_ = [("usUsagePage", ctypes.c_ushort),
                ("usUsage", ctypes.c_ushort),
                ("dwFlags", ctypes.c_uint),
                ("hwndTarget", ctypes.c_void_p)]


class _RawInputHeader(ctypes.Structure):
    _fields_ = [("dwType", ctypes.c_uint),
                ("dwSize", ctypes.c_uint),
                ("hDevice", ctypes.c_void_p),
                ("wParam", ctypes.c_void_p)]


class _RawKeyboard(ctypes.Structure):
    _fields_ = [("MakeCode", ctypes.c_ushort),
                ("Flags", ctypes.c_ushort),
                ("Reserved", ctypes.c_ushort),
                ("VKey", ctypes.c_ushort),
                ("Message", ctypes.c_uint),
                ("ExtraInformation", ctypes.c_void_p)]


class _RawInput(ctypes.Structure):
    _fields_ = [("header", _RawInputHeader), ("keyboard", _RawKeyboard)]


def _init_raw_input() -> None:
    USER32.RegisterRawInputDevices.restype = ctypes.c_bool
    USER32.RegisterRawInputDevices.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
    USER32.GetRawInputData.restype = ctypes.c_uint
    USER32.GetRawInputData.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
                                       ctypes.POINTER(ctypes.c_uint), ctypes.c_uint]


def register_keyboard_raw_input(hwnd: int) -> bool:
    """把键盘注册成 RIDEV_INPUTSINK：窗口不在前台也能收到按键。"""
    if os.name != "nt":
        return False
    try:
        _init_raw_input()
        device = _RawInputDevice(1, 6, RIDEV_INPUTSINK, ctypes.c_void_p(int(hwnd)))
        return bool(USER32.RegisterRawInputDevices(
            ctypes.byref(device), 1, ctypes.sizeof(_RawInputDevice)))
    except Exception:
        return False


def unregister_keyboard_raw_input(hwnd: int) -> None:
    try:
        device = _RawInputDevice(1, 6, RIDEV_REMOVE, ctypes.c_void_p(int(hwnd)))
        USER32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(_RawInputDevice))
    except Exception:
        pass


def read_raw_keyboard(lparam: int) -> int:
    """从 WM_INPUT 的 lParam 取按键的虚拟键码；不是「按下」就返回 0。"""
    if os.name != "nt" or not lparam:
        return 0
    try:
        size = ctypes.c_uint(0)
        header_size = ctypes.sizeof(_RawInputHeader)
        USER32.GetRawInputData.restype = ctypes.c_uint
        if USER32.GetRawInputData(ctypes.c_void_p(int(lparam)), RID_INPUT, None,
                                  ctypes.byref(size), header_size) != 0:
            return 0
        if not size.value or size.value > 1024:
            return 0
        buffer = ctypes.create_string_buffer(size.value)
        got = USER32.GetRawInputData(ctypes.c_void_p(int(lparam)), RID_INPUT, buffer,
                                     ctypes.byref(size), header_size)
        if got == 0xFFFFFFFF or not got:
            return 0
        raw = ctypes.cast(buffer, ctypes.POINTER(_RawInput)).contents
        if raw.header.dwType != RIM_TYPEKEYBOARD:
            return 0
        flags = raw.keyboard.Flags
        if flags & RI_KEY_BREAK or flags & RI_KEY_E1:
            return 0
        if raw.keyboard.Message not in (0x0100, 0x0104):      # WM_KEYDOWN / WM_SYSKEYDOWN
            return 0
        return int(raw.keyboard.VKey)
    except Exception:
        return 0


_VK_NAMES = {}


RI_MOUSE_BUTTON_1_DOWN = 0x0001
RI_MOUSE_BUTTON_1_UP = 0x0002
RI_MOUSE_BUTTON_2_DOWN = 0x0004
RI_MOUSE_BUTTON_2_UP = 0x0008
RI_MOUSE_BUTTON_3_DOWN = 0x0010
RI_MOUSE_BUTTON_3_UP = 0x0020

_RAW_MOUSE_BUTTONS = (
    (RI_MOUSE_BUTTON_1_DOWN, "m:left", True),
    (RI_MOUSE_BUTTON_1_UP, "m:left", False),
    (RI_MOUSE_BUTTON_2_DOWN, "m:right", True),
    (RI_MOUSE_BUTTON_2_UP, "m:right", False),
    (RI_MOUSE_BUTTON_3_DOWN, "m:middle", True),
    (RI_MOUSE_BUTTON_3_UP, "m:middle", False),
)


def register_mouse_raw_input(hwnd: int) -> bool:
    """鼠标也注册成 RIDEV_INPUTSINK：窗口不在前台时仍能收到按键状态。"""
    if os.name != "nt":
        return False
    try:
        _init_raw_input()
        device = _RawInputDevice(1, 2, RIDEV_INPUTSINK, ctypes.c_void_p(int(hwnd)))
        return bool(USER32.RegisterRawInputDevices(
            ctypes.byref(device), 1, ctypes.sizeof(_RawInputDevice)))
    except Exception:
        return False


def unregister_mouse_raw_input(hwnd: int) -> None:
    try:
        device = _RawInputDevice(1, 2, RIDEV_REMOVE, ctypes.c_void_p(int(hwnd)))
        USER32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(_RawInputDevice))
    except Exception:
        pass


def read_raw_mouse(lparam: int):
    """从 WM_INPUT 里取鼠标按键变化，返回 [(spec, 按下与否), ...]。"""
    if os.name != "nt" or not lparam:
        return []
    try:
        size = ctypes.c_uint(0)
        header_size = ctypes.sizeof(_RawInputHeader)
        if USER32.GetRawInputData(ctypes.c_void_p(int(lparam)), RID_INPUT, None,
                                  ctypes.byref(size), header_size) != 0:
            return []
        if not size.value or size.value > 1024:
            return []
        buffer = ctypes.create_string_buffer(size.value)
        got = USER32.GetRawInputData(ctypes.c_void_p(int(lparam)), RID_INPUT, buffer,
                                     ctypes.byref(size), header_size)
        if got in (0, 0xFFFFFFFF):
            return []
        header = ctypes.cast(buffer, ctypes.POINTER(_RawInputHeader)).contents
        if header.dwType != 0:                      # 0 = RIM_TYPEMOUSE
            return []
        # RAWMOUSE 里第 2 个字段是按钮标志位（usButtonFlags）
        flags = ctypes.cast(
            ctypes.addressof(buffer) + ctypes.sizeof(_RawInputHeader) + 4,
            ctypes.POINTER(ctypes.c_ushort)).contents.value
        events = []
        for bit, spec, down in _RAW_MOUSE_BUTTONS:
            if flags & bit:
                events.append((spec, down))
        return events
    except Exception:
        return []


def vk_name(vk: int) -> str:
    """虚拟键码 → 按键名（与 canon_key 的写法一致）。"""
    if not _VK_NAMES:
        for name, code in _VK_BY_NAME.items():
            # 同一个键码可能有多个名字（return/enter、esc/escape…），保留第一个即可
            _VK_NAMES.setdefault(code, name)
    return _VK_NAMES.get(int(vk), "")


def bring_to_front(hwnd) -> None:
    if not hwnd or win32gui is None:
        return
    try:
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass


# ---------------------------------------------------------------- 计时精度

class PrecisionClock:
    """引用计数的 timeBeginPeriod(1)，只在真的有连点在跑时才提高系统计时精度。"""

    def __init__(self, period: int = 1) -> None:
        self.period = period
        self._count = 0
        self._winmm = ctypes.WinDLL("winmm") if os.name == "nt" else None
        if self._winmm is not None:
            try:
                self._winmm.timeBeginPeriod(0)  # 先探测可用
                self._winmm.timeEndPeriod(0)
            except Exception:
                self._winmm = None

    def acquire(self) -> None:
        self._count += 1
        if self._count == 1 and self._winmm is not None:
            try:
                self._winmm.timeBeginPeriod(self.period)
            except Exception:
                pass

    def release(self) -> None:
        if self._count <= 0:
            return
        self._count -= 1
        if self._count == 0 and self._winmm is not None:
            try:
                self._winmm.timeEndPeriod(self.period)
            except Exception:
                pass

    def close(self) -> None:
        while self._count > 0:
            self.release()


def sleep_until(deadline: float, stop_event=None) -> None:
    """等到 deadline（time.perf_counter 口径），期间可被 stop_event 打断。"""
    while True:
        remain = deadline - time.perf_counter()
        if remain <= 0:
            return
        if remain > 0.0016 and stop_event is not None:
            if stop_event.wait(remain - 0.0010):
                return
        else:
            time.sleep(0)
