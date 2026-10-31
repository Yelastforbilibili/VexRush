# -*- coding: utf-8 -*-
"""v2 端到端验收：真实靶子窗口 + 真实按键 + 程序真实运行。

做的事：
  A. 用临时配置启动靶子程序与连点器（subprocess 里跑真实 main.py，带 --multi）
  B. 模拟按住 F19 → 靶子应收到约 100 次左键（配置 10ms）
  C. 模拟真实右键按住 → 靶子应收到右键连点
  D. 连点器窗口在前台时按住 F19 → 不应误伤靶子（前台保护）
  E. 关掉程序 → config.json 应该被写回（间隔 10、几何存在）
  F. 悬浮显示开启时，程序应多出一个无边框小窗

用法：python tests/e2e_test.py
"""

import ctypes
import json
import os
import subprocess
import sys
import time

import win32api
import win32con
import win32gui
import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app import config as cfg_mod          # noqa: E402

TARGET_PY = os.path.join(HERE, "target_app.py")
MAIN_PY = os.path.join(ROOT, "main.py")
TEST_APPDATA = os.path.join(ROOT, "__appdata_e2e")
CONFIG = os.path.join(TEST_APPDATA, "VexRush", "config.json")
BACKUP = os.path.join(HERE, "_config_backup.json")
STATE = os.path.join(HERE, "_target_state.txt")
HWND_FILE = os.path.join(HERE, "_target_hwnd.txt")
TARGET_CLASS = "DualClickTargetV2"

VK_F19 = 0x82
VK_X = 0x58

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, ("  -> " + detail) if detail else ""))


def skip(name, why):
    RESULTS.append((name, True, "SKIP: " + why))
    print("[SKIP] %s  -> %s" % (name, why))


def dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


# ---------------------------------------------------------------- 窗口工具
def find_by_pid(pid, skip_tool=True):
    found = []

    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return True
        if psutil_process_pid(hwnd) != pid:
            return True
        ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if skip_tool and (ex & win32con.WS_EX_TOOLWINDOW):
            return True
        found.append(hwnd)
        return True

    win32gui.EnumWindows(visit, None)
    return found


def psutil_process_pid(hwnd):
    try:
        return win32process_pid(hwnd)
    except Exception:
        return 0


def win32process_pid(hwnd):
    import win32process
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return pid


def force_foreground(hwnd):
    try:
        fg = win32gui.GetForegroundWindow()
        t1 = win32process_thread(fg)
        t2 = win32process_thread(hwnd)
        cur = win32api.GetCurrentThreadId()
        for tid in (t1, t2):
            if tid:
                try:
                    ctypes.windll.user32.AttachThreadInput(cur, tid, True)
                except Exception:
                    pass
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        for tid in (t1, t2):
            if tid:
                try:
                    ctypes.windll.user32.AttachThreadInput(cur, tid, False)
                except Exception:
                    pass
    except Exception as exc:
        print("  (force_foreground 失败: %s)" % exc)


def win32process_thread(hwnd):
    import win32process
    tid, _ = win32process.GetWindowThreadProcessId(hwnd)
    return tid


def wait_for(fn, timeout, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        value = fn()
        if value:
            return value
        time.sleep(step)
    return fn()


def hold_key_and_watch_foreground(hwnd, vk, seconds):
    """按住 vk 一段时间，同时一直确认前台窗口还是 hwnd；被抢走就返回 False。"""
    import win32process
    key_event(vk, True)
    ok = True
    end = time.time() + seconds
    while time.time() < end:
        fg = win32gui.GetForegroundWindow()
        if fg != hwnd:
            try:
                _, pid = win32process.GetWindowThreadProcessId(fg)
                title = win32gui.GetWindowText(fg)
            except Exception:
                pid, title = 0, ""
            print("  (按住期间前台被抢走: hwnd=%s pid=%s %r)" % (fg, pid, title))
            ok = False
            break
        time.sleep(0.03)
    key_event(vk, False)
    return ok


# ---------------------------------------------------------------- 输入模拟
def key_event(vk, down):
    flags = 0
    win32api.keybd_event(vk, 0, flags if down else win32con.KEYEVENTF_KEYUP, 0)


def press_key_for(vk, seconds):
    key_event(vk, True)
    time.sleep(seconds)
    key_event(vk, False)


def mouse_event(flag):
    win32api.mouse_event(flag, 0, 0, 0, 0)


def hold_mouse_for(down_flag, up_flag, seconds):
    mouse_event(down_flag)
    time.sleep(seconds)
    mouse_event(up_flag)


# ---------------------------------------------------------------- 配置 / 进程
def write_test_config():
    if os.path.exists(CONFIG) and not os.path.exists(BACKUP):
        with open(CONFIG, "rb") as src, open(BACKUP, "wb") as dst:
            dst.write(src.read())
    cfg = cfg_mod.AppConfig()
    cfg.target_process = "python.exe"
    cfg.send_mode = "post"
    cfg.auto_detect = False
    cfg.geometry = ""

    left = cfg.channels[0]
    left.enabled = True
    left.interval_ms = 10
    left.trigger_kind = "key"
    left.trigger_key = "f19"
    left.trigger_mouse = "left"
    left.sim_mouse = "left"
    left.hotkey = "x"          # 用户报过：热键设成字母就不生效

    right = cfg.channels[1]
    right.enabled = True
    right.interval_ms = 20
    right.trigger_kind = "mouse"
    right.trigger_mouse = "right"
    right.sim_mouse = "right"
    right.hotkey = "f4"

    cfg.overlay.enabled = True
    cfg_mod.save_config(cfg, CONFIG)


def restore_config():
    if os.path.exists(BACKUP):
        with open(BACKUP, "rb") as src, open(CONFIG, "wb") as dst:
            dst.write(src.read())
        os.remove(BACKUP)


def saved_enabled(index: int):
    """读程序刚写回的配置里某一路的开关状态。"""
    try:
        with open(CONFIG, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return bool(data["channels"][index]["enabled"])
    except Exception:
        return None


def read_counts_settled(gap: float = 0.22, tries: int = 8):
    """读两次数值一样才算稳定，避免拿旧基线导致差 1 次的假失败。"""
    last = read_counts()
    for _ in range(tries):
        time.sleep(gap)
        now = read_counts()
        if now == last:
            return now
        last = now
    return last


def read_counts():
    try:
        with open(STATE, "r", encoding="utf-8") as fh:
            parts = [int(x) for x in fh.read().strip().split(",")]
        return {"down": parts[0], "up": parts[1], "rdown": parts[2], "rup": parts[3]}
    except Exception:
        return {"down": 0, "up": 0, "rdown": 0, "rup": 0}


def launch_target():
    for path in (STATE, HWND_FILE):
        if os.path.exists(path):
            os.remove(path)
    proc = subprocess.Popen([sys.executable, TARGET_PY], cwd=HERE)
    hwnd = wait_for(lambda: read_int_file(HWND_FILE), 10.0)
    return proc, int(hwnd or 0)


def read_int_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
        return int(text or 0)
    except Exception:
        return 0


def launch_app():
    env = dict(os.environ)
    env["APPDATA"] = TEST_APPDATA
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    proc = subprocess.Popen([sys.executable, MAIN_PY, "--multi"], cwd=ROOT, env=env)
    hwnd = wait_for(lambda: (find_by_pid(proc.pid) or [0])[0], 20.0)
    return proc, int(hwnd or 0)


def kill(proc):
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------- 主流程
def main():
    dpi_aware()
    target = app = None
    try:
        write_test_config()
        target, target_hwnd = launch_target()
        check("靶子窗口已创建", bool(target_hwnd), "hwnd=%s" % target_hwnd)

        app, app_hwnd = launch_app()
        check("连点器已启动并显示窗口", bool(app_hwnd), "hwnd=%s" % app_hwnd)
        if not target_hwnd or not app_hwnd:
            return finish()

        win32gui.SetWindowPos(target_hwnd, win32con.HWND_TOP, 120, 120, 620, 420,
                              win32con.SWP_SHOWWINDOW)
        force_foreground(target_hwnd)
        time.sleep(0.6)

        # ---- B. 键盘触发左键连点
        base = read_counts()
        press_key_for(VK_F19, 1.0)
        time.sleep(1.2)
        first = read_counts()
        gained = first["down"] - base["down"]
        check("按住 F19 一秒左键连点约 100 次", 45 <= gained <= 160, "%d 次（10ms/次）" % gained)
        check("按下与抬起成对", first["up"] - base["up"] == gained,
              "down=%d up=%d" % (gained, first["up"] - base["up"]))
        time.sleep(0.5)
        check("松手后立即停止", read_counts()["down"] - first["down"] == 0,
              "又多了 %d 次" % (read_counts()["down"] - first["down"]))

        # ---- B2. 字母热键（用户复现：热键设成 x 时按了没反应）
        before = saved_enabled(0)
        key_event(VK_X, True)
        time.sleep(0.06)
        key_event(VK_X, False)
        time.sleep(1.0)
        after = saved_enabled(0)
        check("字母热键 x 能切换这一路", after is not None and after != before,
              "%s -> %s" % (before, after))
        # 再按一次切回开启，后面的用例还要用它
        key_event(VK_X, True)
        time.sleep(0.06)
        key_event(VK_X, False)
        time.sleep(1.0)
        restored = saved_enabled(0)
        check("再按一次 x 能切回来", restored == before, str(restored))

        # ---- C. 真实右键 → 右键连点
        left_before = read_counts_settled()
        win32gui.SetWindowPos(target_hwnd, win32con.HWND_TOPMOST, 120, 120, 620, 420,
                              win32con.SWP_SHOWWINDOW)
        force_foreground(target_hwnd)
        time.sleep(0.3)
        l, t, r, b = win32gui.GetWindowRect(target_hwnd)
        cx, cy = (l + r) // 2, (t + b) // 2
        try:
            win32api.SetCursorPos((cx, cy))
        except Exception:
            pass
        time.sleep(0.25)
        pos = win32api.GetCursorPos()
        cursor_ok = abs(pos[0] - cx) <= 4 and abs(pos[1] - cy) <= 4
        safe = cursor_ok and belongs_to(hwnd_at(cx, cy), target_hwnd)
        if not cursor_ok:
            skip("按住真实鼠标右键触发第 2 路连点", "光标被别的程序占用（多半在玩游戏），本次跳过")
        else:
            check("光标下就是靶子窗口（不误伤别的程序）", safe, "window=%s" % hwnd_at(cx, cy))
        if safe:
            hold_mouse_for(win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP, 0.8)
            time.sleep(1.0)
            after = read_counts()
            gained_r = after["rdown"] - left_before["rdown"]
            gained_l = after["down"] - left_before["down"]
            check("按住鼠标右键触发第 2 路连点", gained_r >= 10, "%d 次（20ms/次）" % gained_r)
            check("左键那一路没有被带起来", gained_l == 0, "左键多了 %d 次" % gained_l)
            win32gui.SetWindowPos(target_hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

        # ---- D. 前台保护
        force_foreground(app_hwnd)
        time.sleep(0.5)
        guard_base = read_counts_settled()
        hold_ok = hold_key_and_watch_foreground(app_hwnd, VK_F19, 0.7)
        time.sleep(0.8)
        guarded = read_counts()["down"] - guard_base["down"]
        if hold_ok:
            check("本窗口在前台时不往外连点", guarded == 0, "多了 %d 次" % guarded)
        else:
            print("[SKIP] 本窗口在前台时不往外连点  ->  前台被别的窗口抢走，"
                  "这次测不了（多了 %d 次）" % guarded)

        # ---- F. 悬浮显示
        windows = [h for h in all_windows_of(app.pid) if h != app_hwnd]
        check("悬浮显示窗口存在", bool(windows), "%d 个附加窗口" % len(windows))

        # ---- E. 关闭后配置写回
        win32gui.PostMessage(app_hwnd, win32con.WM_CLOSE, 0, 0)
        deadline = time.time() + 8.0
        while time.time() < deadline and app.poll() is None:
            time.sleep(0.1)
        check("关窗后进程退出", app.poll() is not None, "exit=%s" % app.poll())
        try:
            with open(CONFIG, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            check("配置已写回文件", True, "version=%s" % data.get("version"))
            check("间隔设置被保存", data["channels"][0]["interval_ms"] == 10,
                  "interval=%s" % data["channels"][0]["interval_ms"])
            check("窗口位置被保存", bool(data.get("geometry")), "geometry=%d 字符"
                  % len(data.get("geometry") or ""))
        except Exception as exc:
            check("配置已写回文件", False, repr(exc))
    finally:
        kill(app)
        kill(target)
        for path in (STATE, HWND_FILE):
            try:
                os.remove(path)
            except Exception:
                pass
    return finish()


def all_windows_of(pid):
    rows = []

    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if win32process_pid(hwnd) != pid:
            return True
        rows.append(hwnd)
        return True

    win32gui.EnumWindows(visit, None)
    return rows


def hwnd_at(x, y):
    return win32gui.WindowFromPoint((x, y))


def belongs_to(hwnd, target):
    try:
        root = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
    except Exception:
        root = hwnd
    return root == target or hwnd == target


def finish():
    restore_config()
    total = len(RESULTS)
    failed = [row for row in RESULTS if not row[1]]
    print("-" * 62)
    if failed:
        print("失败 %d 项（共 %d 项）：" % (len(failed), total))
        for name, _, detail in failed:
            print("  - %s  %s" % (name, detail))
    else:
        print("全部通过（共 %d 项）" % total)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
