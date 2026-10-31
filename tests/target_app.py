# -*- coding: utf-8 -*-
"""端到端测试用的"靶子"程序：一个真实的可见窗口，统计收到的点击消息。

它自己的进程是独立的 python.exe，所以连点器可以按进程名把它认成目标。
计数每 80ms 落盘到 tests/_target_state.txt，格式：down,up,rdown,rup
"""

import os
import sys
import threading
import time

import win32api
import win32con
import win32gui

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "_target_state.txt")
HWND_FILE = os.path.join(HERE, "_target_hwnd.txt")

CLASS_NAME = "DualClickTargetV2"

counts = {"down": 0, "up": 0, "rdown": 0, "rup": 0}
lock = threading.Lock()


def writer():
    while True:
        time.sleep(0.08)
        with lock:
            payload = "%d,%d,%d,%d" % (
                counts["down"], counts["up"], counts["rdown"], counts["rup"])
        try:
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, STATE_FILE)
        except Exception:
            pass


def wndproc(hwnd, msg, wparam, lparam):
    if msg == win32con.WM_LBUTTONDOWN:
        with lock:
            counts["down"] += 1
            current = counts["down"]
        if current % 25 == 0:      # 标题只在整 25 次时刷一下，别拖慢消息处理
            win32gui.SetWindowText(hwnd, "靶子 · 左键 %d" % current)
    elif msg == win32con.WM_LBUTTONUP:
        with lock:
            counts["up"] += 1
    elif msg == win32con.WM_RBUTTONDOWN:
        with lock:
            counts["rdown"] += 1
    elif msg == win32con.WM_RBUTTONUP:
        with lock:
            counts["rup"] += 1
    elif msg == win32con.WM_CLOSE:
        win32gui.PostQuitMessage(0)
        return 0
    return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


def main():
    threading.Thread(target=writer, name="state-writer", daemon=True).start()

    wc = win32gui.WNDCLASS()
    wc.hInstance = win32api.GetModuleHandle(None)
    wc.lpszClassName = CLASS_NAME
    wc.lpfnWndProc = wndproc
    wc.hbrBackground = win32gui.GetStockObject(win32con.WHITE_BRUSH)
    atom = win32gui.RegisterClass(wc)

    hwnd = win32gui.CreateWindowEx(
        0, atom, "靶子 · 左键 0",
        win32con.WS_OVERLAPPEDWINDOW | win32con.WS_VISIBLE,
        120, 120, 620, 420, 0, 0, wc.hInstance, None)
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
    with open(HWND_FILE, "w", encoding="utf-8") as fh:
        fh.write(str(hwnd))
    print("target hwnd=%s" % hwnd, flush=True)
    win32gui.PumpMessages()


if __name__ == "__main__":
    sys.exit(main() or 0)
