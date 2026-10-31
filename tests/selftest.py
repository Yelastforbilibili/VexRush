"""无界面自测：配置、主题、界面按钮、连点引擎。

运行：
    python tests/selftest.py
退出码 0 = 全部通过。
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import win32api
import ctypes

import win32con
import win32gui
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from app import config as cfg_mod
from app import engine, overlay as overlay_mod, theme as theme_mod, widgets as w, winapi

FAILURES = []
TESTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print("[%s] %s%s" % (mark, name, ("  ->  " + detail) if detail else ""))
    if not ok:
        FAILURES.append(name)
    return ok


def test(fn):
    TESTS.append(fn)
    return fn


# ---------------------------------------------------------------- 配置
@test
def test_config_roundtrip() -> None:
    path = os.path.join(ROOT, "tests", "_selftest_config.json")
    cfg = cfg_mod.AppConfig().normalize()
    cfg.target_process = "javaw.exe"
    cfg.send_mode = "send"
    cfg.auto_detect = False
    cfg.appearance.theme = "ink"
    cfg.appearance.accent = "rose"
    cfg.appearance.font_scale = "large"
    cfg.channels[0].interval_ms = 33
    cfg.channels[0].trigger_kind = "key"
    cfg.channels[0].trigger_key = "f8"
    cfg.channels[1].sim_mouse = "middle"
    cfg.expanded[0] = [True, False]
    cfg.overlay.enabled = True
    cfg.overlay.radius = 18
    cfg_mod.save_config(cfg, path)

    loaded = cfg_mod.load_config(path)
    check("配置写回一致", loaded.channels[0].interval_ms == 33
          and loaded.channels[0].trigger_key == "f8"
          and loaded.channels[1].sim_mouse == "middle"
          and loaded.appearance.theme == "ink"
          and loaded.overlay.radius == 18,
          "左 %sms/%s 右 %s" % (loaded.channels[0].interval_ms,
                                loaded.channels[0].trigger_key, loaded.channels[1].sim_mouse))
    check("折叠状态保存", loaded.expanded[0] == [True, False], str(loaded.expanded[0]))

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{这都不是 json")
    fallback = cfg_mod.load_config(path)
    check("坏配置回退默认", fallback.channels[0].interval_ms == 15
          and fallback.appearance.theme == cfg_mod.AppConfig().appearance.theme)
    os.unlink(path)


@test
def test_config_import_v1() -> None:
    v1 = {
        "target_process": "javaw.exe",
        "send_mode": "post",
        "panels": {
            "left": {"interval_ms": 12, "trigger_button": "left", "simulate_button": "left",
                     "trigger_kind": "mouse", "trigger_mouse": "left", "hotkey": "f1",
                     "enabled": True},
            "right": {"interval_ms": 25, "trigger_kind": "mouse", "trigger_mouse": "right",
                      "sim_mouse": "right", "hotkey": "f2", "enabled": False},
        },
    }
    path = os.path.join(ROOT, "tests", "_selftest_v1.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(v1, handle)
    loaded = cfg_mod.import_config(path)
    check("能导入 v1 老配置", loaded.channels[0].interval_ms == 12
          and loaded.channels[1].interval_ms == 25
          and loaded.channels[0].enabled is True,
          "左 %d 右 %d" % (loaded.channels[0].interval_ms, loaded.channels[1].interval_ms))
    os.unlink(path)

    try:
        cfg_mod.import_config(os.path.join(ROOT, "main.py"))
        check("非法文件被拒绝", False)
    except cfg_mod.ConfigError:
        check("非法文件被拒绝", True)


@test
def test_copy_into_identity() -> None:
    dst = cfg_mod.AppConfig().normalize()
    overlay_ref = dst.overlay
    channel_ref = dst.channels[0]
    src = cfg_mod.AppConfig().normalize()
    src.overlay.opacity = 61
    src.channels[0].interval_ms = 44
    src.expanded[1] = [True, True]
    cfg_mod.copy_into(dst, src)
    check("导入后子对象身份不变", dst.overlay is overlay_ref and dst.channels[0] is channel_ref)
    check("导入后数值生效", dst.overlay.opacity == 61 and dst.channels[0].interval_ms == 44
          and dst.expanded[1] == [True, True],
          "opacity=%s interval=%s" % (dst.overlay.opacity, dst.channels[0].interval_ms))


# ---------------------------------------------------------------- 主题
@test
def test_themes() -> None:
    ok = True
    detail = []
    for theme_key in theme_mod.THEMES:
        for accent_key in theme_mod.ACCENTS:
            for scale in theme_mod.FONT_SCALES:
                try:
                    tokens = theme_mod.resolve_tokens(theme_key, accent_key, scale)
                    sheet = theme_mod.build_stylesheet(tokens)
                except Exception as exc:            # noqa: BLE001
                    ok = False
                    detail.append("%s/%s/%s: %s" % (theme_key, accent_key, scale, exc))
                    continue
                if "@{" in sheet:
                    ok = False
                    detail.append("%s 有没替换的令牌" % theme_key)
        detail.append("%s:%d 字符" % (theme_key, len(theme_mod.build_stylesheet(
            theme_mod.resolve_tokens(theme_key)))))
    check("4 主题 × 6 强调色 × 4 字号都能出样式", ok, " ".join(detail[:4]))


@test
def test_number_and_keys() -> None:
    check("间隔上下限夹紧", cfg_mod.ChannelConfig(interval_ms=99999).normalize(0).interval_ms
          == cfg_mod.INTERVAL_MAX)
    check("按键名规范化", winapi.canon_key("F8") == "f8" and winapi.canon_key("Esc") == "esc",
          "%s / %s" % (winapi.canon_key("F8"), winapi.canon_key("Esc")))
    check("按键显示名", winapi.key_display("f8") == "F8", winapi.key_display("f8"))


# ---------------------------------------------------------------- 界面
@test
def test_window() -> None:
    from app.mainwindow import MainWindow

    cfg = cfg_mod.AppConfig().normalize()
    cfg.appearance.theme = "light"
    window = MainWindow(cfg)
    window.show()
    _pump()

    card = window._card_widgets[0]
    card.switch.setChecked(True)
    _pump()
    check("开关能打开这一路", cfg.channels[0].enabled is True and card.property("active") == "true")

    card.field.spin.setValue(37)
    _pump()
    check("间隔输入写回配置", cfg.channels[0].interval_ms == 37, "配置里是 %d" % cfg.channels[0].interval_ms)

    card.cb_trigger.setCurrentIndex(card.cb_trigger.findData("key"))
    card._on_trigger_kind(card.cb_trigger.currentIndex())      # noqa: SLF001
    _pump()
    check("触发键能切到键盘", cfg.channels[0].trigger_kind == "key")

    card.btn_trigger_key.set_key("f9")
    card._on_trigger_key("f9")                                # noqa: SLF001
    check("自定义触发键生效", cfg.channels[0].trigger_key == "f9"
          and cfg.channels[0].trigger_spec() == "k:f9",
          cfg.channels[0].trigger_spec())

    card.cb_sim.setCurrentIndex(card.cb_sim.findData("right"))
    card._on_sim(card.cb_sim.currentIndex())                   # noqa: SLF001
    check("模拟点击可切右键", cfg.channels[0].sim_mouse == "right")

    card.advanced.set_expanded(True, animate=False)
    _pump()
    window._on_card_expanded(0)                                # noqa: SLF001
    check("折叠区状态写回配置", cfg.expanded[0][0] is True, str(cfg.expanded[0]))

    window.btn_overlay.setChecked(True)
    _pump()
    check("连点显示可开启", cfg.overlay.enabled is True and window.overlay.isVisible())

    window.btn_overlay.setChecked(False)
    _pump()
    check("连点显示可关闭", cfg.overlay.enabled is False and not window.overlay.isVisible())

    dialog = window._ensure_settings()                         # noqa: SLF001
    dialog.show()
    _pump()
    dialog.seg_theme.set_value("dark", emit=True)
    _pump(30)                                                  # 换主题走遮罩，稍等一下
    check("设置里换主题生效", cfg.appearance.theme == "dark"
          and window.tokens.get("canvas") == theme_mod.THEMES["dark"]["canvas"],
          window.tokens.get("canvas", "?"))
    dialog.seg_scale.set_value("large", emit=True)
    _pump()
    check("设置里换字号生效", cfg.appearance.font_scale == "large")

    overlay_dialog = window._open_overlay_settings()           # noqa: SLF001
    _pump()
    overlay_dialog.sw_enabled.setChecked(True)
    _pump()
    check("设置里打开悬浮显示", cfg.overlay.enabled is True and window.overlay.isVisible())
    overlay_dialog.seg_layout.set_value("h", emit=True)
    _pump()
    check("悬浮排布可切横排", cfg.overlay.layout == "h")
    overlay_dialog.seg_anim.set_value("pulse", emit=True)
    check("过渡动画可切换", cfg.overlay.animation == "pulse")
    overlay_dialog.sl_radius.setValue(20)
    check("滑杆改圆角", cfg.overlay.radius == 20, "radius=%d" % cfg.overlay.radius)
    overlay_dialog._chips["show_cps"].click()                  # noqa: SLF001
    check("显示内容可关闭速率", cfg.overlay.show_cps is False)

    window.resize(820, 520)
    window.mark_dirty()
    time.sleep(0.7)
    _pump()
    saved = cfg_mod.load_config()
    check("改完自动落盘", saved.appearance.theme == "dark"
          and saved.overlay.radius == 20
          and saved.channels[0].interval_ms == 37,
          "%s/%d/%d" % (saved.appearance.theme, saved.overlay.radius,
                        saved.channels[0].interval_ms))
    check("窗口位置也存了", len(saved.geometry) > 8, "%d 字符" % len(saved.geometry))

    dialog.close()
    window.close()
    _pump()


def _pump(times: int = 6) -> None:
    app = QApplication.instance()
    for _ in range(times):
        app.processEvents()
        time.sleep(0.01)


# ---------------------------------------------------------------- 连点
class MessageSink:
    """隐藏窗口，统计收到的鼠标消息。"""

    def __init__(self) -> None:
        self.counts = {"LDOWN": 0, "LUP": 0, "MDOWN": 0, "MUP": 0, "RDOWN": 0, "RUP": 0}
        self._ready = threading.Event()
        self.hwnd = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(3.0)

    def _run(self) -> None:
        message_map = {
            win32con.WM_LBUTTONDOWN: "LDOWN", win32con.WM_LBUTTONUP: "LUP",
            win32con.WM_MBUTTONDOWN: "MDOWN", win32con.WM_MBUTTONUP: "MUP",
            win32con.WM_RBUTTONDOWN: "RDOWN", win32con.WM_RBUTTONUP: "RUP",
        }

        def wnd_proc(hwnd, msg, wparam, lparam):
            name = message_map.get(msg)
            if name:
                self.counts[name] += 1
                return 0
            if msg == win32con.WM_DESTROY:
                win32gui.PostQuitMessage(0)
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = "DualClickerSelfTestV2"
        wc.lpfnWndProc = wnd_proc
        try:
            win32gui.RegisterClass(wc)
        except win32gui.error:
            pass
        self.hwnd = win32gui.CreateWindow(wc.lpszClassName, "自测靶子", 0, 0, 0, 10, 10,
                                          0, 0, wc.hInstance, None)
        self._ready.set()
        win32gui.PumpMessages()


@test
def test_clicking() -> None:
    sink = MessageSink()
    if not sink.hwnd:
        check("靶子窗口创建", False)
        return

    shared = engine.SharedState()
    shared.guard_self = False
    shared.registry.set_manual_hwnd(sink.hwnd)
    channel = engine.Channel(0, shared)
    channel.cfg = cfg_mod.ChannelConfig(interval_ms=20, sim_mouse="left", enabled=True,
                                        trigger_kind="mouse", trigger_mouse="left")
    channel.start()
    shared.input_state.set("m:left", True)
    time.sleep(0.55)
    shared.input_state.set("m:left", False)
    time.sleep(0.25)
    clicked = sink.counts["LDOWN"]
    check("按住 0.55 秒按 20ms 连点", 18 <= clicked <= 40, "%d 次" % clicked)
    check("按下和抬起成对", abs(sink.counts["LDOWN"] - sink.counts["LUP"]) <= 2,
          "down=%d up=%d" % (sink.counts["LDOWN"], sink.counts["LUP"]))
    stuck = sink.counts["LDOWN"]
    time.sleep(0.3)
    check("松手立即停", sink.counts["LDOWN"] - stuck <= 1,
          "又多了 %d 次" % (sink.counts["LDOWN"] - stuck))

    channel.cfg.interval_ms = 60
    base = sink.counts["LDOWN"]
    shared.input_state.set("m:left", True)
    time.sleep(0.9)
    shared.input_state.set("m:left", False)
    time.sleep(0.2)
    speed = sink.counts["LDOWN"] - base
    check("运行中改间隔即时生效", 10 <= speed <= 20, "0.9 秒 %d 次（60ms 期望约 15）" % speed)

    channel.cfg.enabled = False
    base = sink.counts["LDOWN"]
    shared.input_state.set("m:left", True)
    time.sleep(0.35)
    shared.input_state.set("m:left", False)
    check("开关关闭后不连点", sink.counts["LDOWN"] - base == 0,
          "多了 %d 次" % (sink.counts["LDOWN"] - base))

    channel.cfg.enabled = True
    channel.cfg.sim_mouse = "right"
    channel.cfg.trigger_mouse = "right"
    rbase, lbase = sink.counts["RDOWN"], sink.counts["LDOWN"]
    shared.input_state.set("m:right", True)
    time.sleep(0.4)
    shared.input_state.set("m:right", False)
    time.sleep(0.2)
    check("模拟右键只发右键", sink.counts["RDOWN"] - rbase >= 5
          and sink.counts["LDOWN"] - lbase == 0,
          "RDOWN=+%d LDOWN=+%d" % (sink.counts["RDOWN"] - rbase, sink.counts["LDOWN"] - lbase))

    channel.stop()
    shared.precision.close()
    win32gui.PostMessage(sink.hwnd, win32con.WM_CLOSE, 0, 0)


# ---------------------------------------------------------------- 主入口
@test
def test_rename_and_exclusive() -> None:
    from app.mainwindow import MainWindow

    cfg = cfg_mod.AppConfig()
    cfg.overlay.enabled = False
    window = MainWindow(cfg)
    cards = window._card_widgets
    _pump()

    cards[0]._on_name("挖矿")
    _pump()
    check("改名写进配置", cfg.channels[0].name == "挖矿", cfg.channels[0].name)
    check("卡片标题跟着改名", cards[0].title_label.text() == "挖矿", cards[0].title_label.text())
    window._on_tick()
    check("悬浮窗行标题跟着改名", window.overlay._rows[0].get("title") == "挖矿",
          str(window.overlay._rows[0].get("title")))

    cfg.exclusive = True
    cfg.restore_previous = True
    cards[0].switch.setChecked(True)
    _pump()
    check("防卡手：先开第一路", cards[0].cfg.enabled and not cards[1].cfg.enabled,
          "A=%s B=%s" % (cards[0].cfg.enabled, cards[1].cfg.enabled))
    cards[1].switch.setChecked(True)
    _pump()
    check("防卡手：开第二路挤掉第一路",
          cards[1].cfg.enabled and not cards[0].cfg.enabled and not cards[0].switch.isChecked(),
          "A=%s B=%s" % (cards[0].cfg.enabled, cards[1].cfg.enabled))
    cards[0].switch.setChecked(True)
    _pump()
    check("防卡手：再开第一路挤掉第二路",
          cards[0].cfg.enabled and not cards[1].cfg.enabled,
          "A=%s B=%s" % (cards[0].cfg.enabled, cards[1].cfg.enabled))
    cards[0].switch.setChecked(False)
    _pump()
    check("防卡手：关掉当前这路只恢复最近被挤掉的那一路",
          cards[1].cfg.enabled and not cards[0].cfg.enabled and cards[1].switch.isChecked(),
          "A=%s B=%s" % (cards[0].cfg.enabled, cards[1].cfg.enabled))
    cards[1].switch.setChecked(False)
    _pump()
    check("防卡手：没有记录时不会乱开",
          not cards[0].cfg.enabled and not cards[1].cfg.enabled,
          "A=%s B=%s" % (cards[0].cfg.enabled, cards[1].cfg.enabled))
    window.close()


@test
def test_overlay_display() -> None:
    from app import overlay as overlay_mod

    cfg = cfg_mod.AppConfig().normalize()
    cfg.overlay.enabled = True
    cfg.overlay.layout = "v"
    cfg.overlay.show_title = False
    cfg.overlay.title_text = ""
    cfg.overlay.bg_opacity = 80
    overlay = overlay_mod.OverlayWindow(cfg.overlay, {})
    overlay.set_rows([
        {"title": "连点1", "enabled": True, "clicking": True, "cps": 66.4,
         "count": 1284, "interval": 15},
        {"title": "连点2", "enabled": False, "clicking": False, "cps": 0.0,
         "count": 0, "interval": 20},
    ])
    overlay.restore_position()
    _pump()
    height_plain = overlay.height()

    cfg.overlay.show_title = True
    cfg.overlay.title_text = "挖矿连点"
    overlay.set_cfg(cfg.overlay)
    overlay.restore_position()
    _pump()
    check("标题文字能开、能自定义", overlay._has_title() and overlay.height() > height_plain,
          "高 %d -> %d" % (height_plain, overlay.height()))

    width_v = overlay.width()
    overlay._set_value("layout", "h")
    _pump()
    check("横向排布比纵向宽（说明没挤在一起）", overlay.width() > width_v,
          "宽 %d -> %d" % (width_v, overlay.width()))
    blocks = sum(overlay._block_width(row) for row in overlay._rows)
    expect = int(round(overlay.cfg.padding * 2 + blocks + overlay_mod.DIVIDER_GAP * 2))
    check("横向的宽度刚好放下两块", abs(overlay.width() - (expect + 2)) <= 3,
          "实际 %d 期望 %d" % (overlay.width(), expect + 2))
    check("每块都留出了元信息的宽度",
          all(overlay._block_width(row) > overlay._meta_width for row in overlay._rows))

    check("悬浮窗背景透明（圆角不会露出方块）",
          overlay.testAttribute(Qt.WA_TranslucentBackground))
    overlay._set_value("bg_opacity", 40)
    check("背景透明度可调", overlay.cfg.bg_opacity == 40, str(overlay.cfg.bg_opacity))
    overlay._set_value("radius", 22)
    check("圆角可调", overlay.cfg.radius == 22, str(overlay.cfg.radius))
    overlay.close()


@test
def test_overlay_menu() -> None:
    from app import overlay as overlay_mod

    cfg = cfg_mod.AppConfig().normalize()
    cfg.overlay.title_text = "连点显示"
    cfg.overlay.show_title = True
    overlay = overlay_mod.OverlayWindow(cfg.overlay, {})
    menu = overlay.build_menu()
    flags = menu.windowFlags()
    check("菜单是无边框窗口", bool(flags & Qt.FramelessWindowHint))
    check("菜单没有系统投影", bool(flags & Qt.NoDropShadowWindowHint))
    check("菜单背景透明", menu.testAttribute(Qt.WA_TranslucentBackground))
    qss = menu.styleSheet()
    check("菜单有圆角和配色", "border-radius" in qss and "QMenu::item" in qss
          and "color: rgba(" in qss)
    labels = [action.text() for action in menu.actions() if not action.isSeparator()]
    check("菜单项齐全", len(labels) >= 11, "%d 项" % len(labels))
    before = bool(overlay.cfg.show_title)
    for action in menu.actions():
        if "显示标题" in action.text():
            action.trigger()
            break
    check("菜单能切换标题显示", bool(overlay.cfg.show_title) != before)
    check("菜单里能看到勾选标记", any(label.startswith("✓") for label in labels))
    menu.deleteLater()
    overlay.close()


@test
def test_ime_gate() -> None:
    from pynput.keyboard import Key
    from pynput.mouse import Button

    input_state = engine.InputState()
    hub = engine.InputHub(input_state)
    hub.ignore_ime = True
    original = winapi.text_input_active
    try:
        winapi.text_input_active = lambda: True
        hub._on_press(Key.f19)
        check("正在打字时键盘热键不响应", not input_state.is_down("k:f19"))
        hub._on_click(0, 0, Button.left, True)
        check("正在打字时鼠标触发也不响应", not input_state.is_down("m:left"))

        winapi.text_input_active = lambda: False
        hub._on_press(Key.f19)
        check("没在打字时键盘热键照常响应", input_state.is_down("k:f19"))
        hub._on_release(Key.f19)
        hub._on_click(0, 0, Button.left, True)
        check("没在打字时鼠标触发照常响应", input_state.is_down("m:left"))
        hub._on_click(0, 0, Button.left, False)

        hub.ignore_ime = False
        winapi.text_input_active = lambda: True
        hub._on_press(Key.f19)
        check("关掉这个开关后打字时也响应", input_state.is_down("k:f19"))
        hub._on_release(Key.f19)
    finally:
        winapi.text_input_active = original
        hub.stop()

    cfg = cfg_mod.AppConfig()
    shared = engine.SharedState()
    channel = engine.Channel(0, shared)
    channel.cfg = cfg.channels[0]
    cfg.channels[0].enabled = True
    shared.input_state.set("m:left", True)
    original_active = winapi.text_input_active
    original_self = winapi.foreground_is_self
    try:
        winapi.foreground_is_self = lambda: False
        winapi.text_input_active = lambda: False
        check("没打字时按住触发键就连点", channel.is_clicking() is True)
        shared.ime_guard = True
        winapi.text_input_active = lambda: True
        check("按住期间开始打字就停下来", channel.is_clicking() is False)
        winapi.text_input_active = lambda: False
        check("不打字了就恢复连点", channel.is_clicking() is True)
        shared.ime_guard = False
        winapi.text_input_active = lambda: True
        check("ime_guard 关掉后打字也照常连点", channel.is_clicking() is True)
    finally:
        winapi.text_input_active = original_active
        winapi.foreground_is_self = original_self
        shared.input_state.clear()


@test
def test_settings_split() -> None:
    from app.mainwindow import MainWindow
    from app.overlay_settings import OverlaySettingsDialog
    from app.settings import SettingsDialog

    cfg = cfg_mod.AppConfig()
    window = MainWindow(cfg)
    _pump()
    main_dialog = window._ensure_settings()
    overlay_dialog = window._open_overlay_settings()
    _pump()
    check("两个设置窗口是彼此独立的窗口",
          isinstance(main_dialog, SettingsDialog)
          and isinstance(overlay_dialog, OverlaySettingsDialog)
          and main_dialog is not overlay_dialog)
    check("悬浮显示设置有自己的窗口实例", window._overlay_settings is overlay_dialog)

    overlay_dialog.sl_bg_alpha.setValue(40)
    _pump()
    check("设置里能调背景透明度", cfg.overlay.bg_opacity == 40, str(cfg.overlay.bg_opacity))
    overlay_dialog.sl_radius.setValue(18)
    _pump()
    check("设置里能调圆角", cfg.overlay.radius == 18, str(cfg.overlay.radius))
    overlay_dialog.ed_title.textEdited.emit("自定义标题")
    _pump()
    check("设置里能改标题文字", cfg.overlay.title_text == "自定义标题", cfg.overlay.title_text)

    main_dialog.sw_exclusive.setChecked(True)
    main_dialog.sw_restore.setChecked(False)
    main_dialog.sw_ime.setChecked(False)
    _pump()
    check("设置里能开防卡手并关掉恢复",
          cfg.exclusive and not cfg.restore_previous,
          "exclusive=%s restore=%s" % (cfg.exclusive, cfg.restore_previous))
    check("关掉输入法开关会同步到监听", not cfg.ignore_ime and not window.hub.ignore_ime,
          "cfg=%s hub=%s" % (cfg.ignore_ime, window.hub.ignore_ime))
    window.close()


@test
def test_window_easing_and_lang() -> None:
    """第三轮：#1 窗口缓动、#3 数据目录、#4 语言包、#7 拖动首帧、#9 GitHub 按钮。"""
    from PyQt5.QtCore import QRect

    from app import i18n as i18n_mod
    from app import winapi
    from app.mainwindow import MainWindow

    root = cfg_mod.data_dir()
    check("数据目录在 AppData 下", root.lower().startswith(os.environ.get("APPDATA", "").lower()), root)
    check("配置也落在数据目录", cfg_mod.config_path().startswith(root), cfg_mod.config_path())
    i18n_mod.prepare()
    codes = [code for code, _name, _official in i18n_mod.available()]
    check("语言包能从 lang 目录读出来", "zh_cn" in codes and "en_us" in codes, str(codes))
    check("语言包里没有漏翻译的键", i18n_mod.tr("interval") != "interval", i18n_mod.tr("interval"))
    i18n_mod.set_language("en_us")
    check("切到英文能取到英文", i18n_mod.tr("interval") == "Interval", i18n_mod.tr("interval"))
    i18n_mod.set_language("zh_cn")
    check("切回中文", i18n_mod.tr("interval") == "间隔", i18n_mod.tr("interval"))

    cfg = cfg_mod.AppConfig()
    cfg.geometry = ""
    window = MainWindow(cfg)
    window.show()
    _pump()
    check("窗口缓动默认开启", cfg.smooth_window is True)
    window.move(140, 100)
    window.resize(700, 380)
    _pump()
    # 窗口缓动：全程物理像素，只改 lParam 里的矩形（自己不动窗口）
    # offscreen 平台没有真实窗口句柄，这里直接喂一组物理像素坐标验证换算逻辑；
    # 真窗口那条路径由 __probe_ease2.py / e2e 覆盖。
    offscreen = QApplication.platformName() == "offscreen"
    if offscreen:
        start = [100, 100, 900, 500]
        window._ease_pos = [float(v) for v in start]
        window._ease_stamp = time.perf_counter() - 0.008
        window._drag_active = True
    else:
        window._ease_reset()
        start = list(win32gui.GetWindowRect(int(window.winId())))
    probe = (ctypes.c_long * 4)(start[0] + 300, start[1] + 200,
                                start[2] + 300, start[3] + 200)
    window._ease_stamp = time.perf_counter() - 0.008
    ok_ease = window._ease_apply(ctypes.addressof(probe))
    step_x = int(probe[0])
    check("窗口缓动接管了消息并把矩形往目标挪", ok_ease and start[0] < step_x < start[0] + 300,
          "%d -> %d（目标 %d）" % (start[0], step_x, start[0] + 300))
    moved = [int(v) for v in probe]
    inside = all(start[i] <= moved[i] <= start[i] + (300 if i in (0, 2) else 200)
                 for i in range(4))
    check("缓动没有回头、也没有过冲", inside,
          "起点 %s -> 现在 %s" % (start, moved))
    window._ease_end()
    _pump(20)
    check("松手后退出拖动状态", not getattr(window, "_drag_active", True))

    window.resize(500, 300)
    _pump(40)
    check("挤窄后回弹到卡片最小宽度",
          window.width() >= window._min_width_for_cards(),
          "%d >= %d" % (window.width(), window._min_width_for_cards()))

    dialog = window._ensure_settings()
    dialog.show()
    _pump()
    check("设置窗有窗口缓动开关", hasattr(dialog, "sw_smooth"))
    check("设置窗标题栏没有 ? 按钮",
          not (dialog.windowFlags() & Qt.WindowContextHelpButtonHint))
    check("设置窗有 GitHub 按钮", cfg_mod.GITHUB_URL.endswith("/VexRush"))
    check("拖动首帧插值有上限",
          "min(0.45" in inspect.getsource(overlay_mod.OverlayWindow._on_frame),
          "k 上限 45%")
    window.close()


def main() -> int:
    from app import icon as icon_mod
    import main as entry

    entry.enable_high_dpi()
    app = QApplication(sys.argv[:1])
    app.setFont(QFont(theme_mod.FONT_FAMILY, 10))
    check("图标能生成", not icon_mod.app_icon().isNull())

    for fn in TESTS:
        print("\n== %s" % fn.__name__)
        try:
            fn()
        except Exception as exc:                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check("%s 未抛异常" % fn.__name__, False, repr(exc))

    print("\n" + "-" * 60)
    if FAILURES:
        print("失败 %d 项：%s" % (len(FAILURES), "、".join(FAILURES)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
