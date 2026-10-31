# -*- coding: utf-8 -*-
"""对打包好的 exe 做验收：启动、截图、配置保存、重启后还原、悬浮窗。

用法：python tests\\exe_check.py [exe 路径]
前提：先 `python -m PyInstaller --noconfirm dual_clicker.spec`
"""

import ctypes
import json
import os
import subprocess
import sys
import time

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # 物理像素，坐标才和截图对得上
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import win32con
import win32gui
import win32process
from PIL import ImageGrab

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist")
EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DIST, "VexRush.exe")
CONFIG = os.path.join(os.path.dirname(EXE), "config.json")
TMP = os.path.join(ROOT, "_tmp")
SHOT = os.path.join(ROOT, "__exe_real.png")

FAILURES = []


def check(name, ok, detail=""):
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, ("  -> " + detail) if detail else ""),
          flush=True)
    if not ok:
        FAILURES.append(name)
    return ok


def kill_leftovers():
    """onefile 模式会有一个父进程 + 一个子进程，按进程名把它们都清掉。"""
    import psutil
    names = {"VexRush.exe"}
    killed = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info.get("name") or "").lower() in names:
                proc.kill()
                killed += 1
        except Exception:
            pass
    if killed:
        print("    (先清掉了 %d 个残留进程)" % killed, flush=True)
    time.sleep(0.8)


def find_window(timeout=45.0):
    """onefile 的子进程 pid 和 Popen 的 pid 不一样，所以按窗口标题 + 进程路径来认。"""
    import psutil
    end = time.time() + timeout
    while time.time() < end:
        found = []

        def callback(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                    return True
                if win32gui.GetParent(hwnd):
                    return True
                if not win32gui.GetWindowText(hwnd).startswith("VexRush"):
                    return True
                if win32gui.GetClassName(hwnd) == "#32770":
                    print("    (出现了「已经在运行」对话框：先清掉残留实例)", flush=True)
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    return True
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                if ex & win32con.WS_EX_TOOLWINDOW:      # 跳过悬浮窗
                    return True
                pid = win32process.GetWindowThreadProcessId(hwnd)[1]
                if (psutil.Process(pid).exe() or "").lower() != EXE.lower():
                    return True
                found.append((hwnd, pid))
            except Exception:
                pass
            return True

        win32gui.EnumWindows(callback, None)
        if found:
            return found[0]
        time.sleep(0.3)
    return (None, None)


def launch():
    env = dict(os.environ)
    env["TEMP"] = TMP          # 沙箱里子进程没法在真实 %TEMP% 建目录，指到工程内
    env["TMP"] = TMP
    return subprocess.Popen([EXE], cwd=os.path.dirname(EXE), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def close(proc, hwnd):
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    try:
        proc.wait(timeout=20)
    except Exception:
        proc.kill()
    kill_leftovers()
    time.sleep(0.4)


def grab(hwnd, path):
    try:
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.9)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    ImageGrab.grab(bbox=(left, top, right, bottom)).save(path)
    try:
        win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
    except Exception:
        pass
    return (left, top, right, bottom)


def count_windows(pid):
    rows = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        try:
            if win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
                rows.append(hwnd)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(callback, None)
    return rows


def main():
    if not os.path.exists(EXE):
        print("找不到 exe：%s" % EXE)
        return 1
    os.makedirs(TMP, exist_ok=True)
    for path in (CONFIG, SHOT):
        try:
            os.remove(path)
        except Exception:
            pass

    print("exe = %s（%.1f MB）" % (EXE, os.path.getsize(EXE) / 1048576.0), flush=True)
    kill_leftovers()

    # ---- 第一次运行：窗口出来、截图、关掉后应写出 config.json
    proc = launch()
    hwnd, app_pid = find_window()
    if not check("exe 启动后窗口出现", bool(hwnd), "hwnd=%s pid=%s" % (hwnd, app_pid)):
        proc.kill()
        kill_leftovers()
        return 1
    rect1 = grab(hwnd, SHOT)
    title = win32gui.GetWindowText(hwnd)
    check("窗口标题正确", title.startswith("VexRush"), repr(title))
    check("截图已保存", os.path.exists(SHOT) and os.path.getsize(SHOT) > 20000,
          "%d 字节" % (os.path.getsize(SHOT) if os.path.exists(SHOT) else 0))
    check("窗口大小随 175% 缩放（逻辑约 830x360）",
          abs((rect1[2] - rect1[0]) - 1453) < 60 and abs((rect1[3] - rect1[1]) - 640) < 80,
          "物理尺寸 %dx%d" % (rect1[2] - rect1[0], rect1[3] - rect1[1]))

    win32gui.MoveWindow(hwnd, 60, 80, rect1[2] - rect1[0], rect1[3] - rect1[1], True)
    time.sleep(0.6)
    moved = win32gui.GetWindowRect(hwnd)
    close(proc, hwnd)

    cfg = None
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except Exception as exc:
            print("    配置文件读不出来：%r" % (exc,))
    if not check("关闭后配置文件已写出", cfg is not None, CONFIG):
        return 1
    check("配置是 v2 结构（两路通道）", len(cfg.get("channels") or []) == 2,
          "channels=%d" % len(cfg.get("channels") or []))
    check("配置里记录了窗口位置几何", bool(cfg.get("geometry")), "geometry 长度 %s"
          % (len(cfg.get("geometry") or "")))
    check("外观配置已写入", bool((cfg.get("appearance") or {}).get("theme")),
          "theme=%s" % (cfg.get("appearance") or {}).get("theme"))

    # ---- 第二次运行：窗口应回到上次的位置/大小
    proc = launch()
    hwnd2, pid2 = find_window()
    if not check("第二次启动窗口出现", bool(hwnd2)):
        proc.kill()
        kill_leftovers()
        return 1
    time.sleep(1.2)
    rect2 = win32gui.GetWindowRect(hwnd2)
    check("窗口位置/大小被还原",
          abs(rect2[0] - moved[0]) <= 6 and abs(rect2[1] - moved[1]) <= 40
          and abs((rect2[2] - rect2[0]) - (moved[2] - moved[0])) <= 6,
          "上次 (%d,%d) %dx%d / 这次 (%d,%d) %dx%d"
          % (moved[0], moved[1], moved[2] - moved[0], moved[3] - moved[1],
             rect2[0], rect2[1], rect2[2] - rect2[0], rect2[3] - rect2[1]))
    close(proc, hwnd2)

    print("-" * 62)
    if FAILURES:
        print("失败 %d 项：%s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("exe 验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
