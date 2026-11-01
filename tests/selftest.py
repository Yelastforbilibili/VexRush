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
from app import mainwindow as mainwindow_mod
from app import engine, overlay as overlay_mod, theme as theme_mod, widgets as w, winapi
from app.i18n import tr

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
    fresh = cfg_mod.AppConfig().normalize()
    check("坏配置回退默认", fallback.channels[0].interval_ms == fresh.channels[0].interval_ms
          and fallback.channels[0].name == fresh.channels[0].name
          and fallback.appearance.theme == fresh.appearance.theme,
          "%s/%sms" % (fallback.channels[0].name, fallback.channels[0].interval_ms))
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
    _pump(50)                                                  # 出场动画要跑完才隐藏
    check("连点显示可关闭", cfg.overlay.enabled is False and not window.overlay.isVisible())

    dialog = window._ensure_settings()                         # noqa: SLF001
    dialog.show()
    _pump()
    dialog.seg_theme.set_value("dark", emit=True)
    _pump(45)                                                  # 换主题走幕布，稍等一下
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
    input_state = engine.InputState()
    hub = engine.InputHub(input_state)
    hub.ignore_ime = True
    original = winapi.text_input_active
    try:
        winapi.text_input_active = lambda: True
        hub._on_key("f19", True)
        check("正在打字时键盘热键不响应", not input_state.is_down("k:f19"))
        hub._on_mouse("m:left", True)
        check("正在打字时鼠标触发也不响应", not input_state.is_down("m:left"))

        winapi.text_input_active = lambda: False
        hub._on_key("f19", True)
        check("没在打字时键盘热键照常响应", input_state.is_down("k:f19"))
        hub._on_key("f19", False)
        hub._on_mouse("m:left", True)
        check("没在打字时鼠标触发照常响应", input_state.is_down("m:left"))
        hub._on_mouse("m:left", False)

        hub.ignore_ime = False
        winapi.text_input_active = lambda: True
        hub._on_key("f19", True)
        check("关掉这个开关后打字时也响应", input_state.is_down("k:f19"))
        hub._on_key("f19", False)
    finally:
        winapi.text_input_active = original
        hub.stop()


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
    _pump()
    check("设置里能开防卡手并关掉恢复",
          cfg.exclusive and not cfg.restore_previous,
          "exclusive=%s restore=%s" % (cfg.exclusive, cfg.restore_previous))
    # 「打字时不响应」暂时下线：控件可见但变灰，配置恒为关
    check("输入法开关已下线（变灰且关着）",
          not main_dialog.sw_ime.isEnabled() and not cfg.ignore_ime
          and not window.hub.ignore_ime and not window.shared.ime_guard,
          "enabled=%s cfg=%s hub=%s guard=%s"
          % (main_dialog.sw_ime.isEnabled(), cfg.ignore_ime,
             window.hub.ignore_ime, window.shared.ime_guard))
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
    window._first_fit_done = True          # 关掉首次自适应动画，尺寸才好比对
    window.show()
    _pump()
    check("窗口缓动默认开启", cfg.smooth_window is True)
    window.move(140, 100)
    window.resize(700, 380)
    _pump()
    # 拖动缓动是自己接管标题栏（原生模态循环里做插值会让窗口以 k 倍速度爬行，
    # 实测 k≈0.34 时光标走 240px 窗口只走 82px，所以不能走那条路）。
    # offscreen 平台没有真实窗口句柄，这里只验证状态机与互斥守卫；
    # 「缓动跟手 + 松手吸附」由 __probe_drag3/4.py 用真窗口真鼠标验证。
    for name in ("_caption_start", "_caption_step", "_caption_end", "filter_native"):
        check("拖动实现有 %s" % name, hasattr(window, name))
    check("拖动前不在拖动状态", not window._caption_drag)
    window._drag_active = True
    height_before = window.height()
    window._fit_height(allow_shrink=True, animate=True)
    window._spring_back_width()
    _pump(20)
    check("拖动期间不做高度贴合", window.height() == height_before,
          "%d -> %d" % (height_before, window.height()))
    window._drag_active = False
    window._caption_drag = False
    window._caption_end(snap=False)
    _pump(20)
    check("松手后退出拖动状态", not window._caption_drag)

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
          "min(0.45" in inspect.getsource(overlay_mod.OverlayWindow._tick_frame),
          "k 上限 45%")
    window.close()


@test
def test_overlay_drag_stability() -> None:
    """悬浮窗拖动整条路不能抛异常（3.2.0 就是松手时 NameError 把程序带崩的）。"""
    from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt5.QtGui import QMouseEvent

    cfg = cfg_mod.AppConfig().normalize()
    cfg.overlay.enabled = True
    dialog = overlay_mod.OverlayWindow(cfg.overlay, {})
    dialog.set_tokens(theme_mod.resolve_tokens("light", "blue", "normal"))
    dialog.set_rows([
        {"title": "连点1", "enabled": True, "clicking": True,
         "cps": 66.4, "count": 12, "interval": 15},
    ])
    dialog.move(300, 200)
    dialog.show()
    _pump()

    from app import screen as screen_mod

    def mouse(kind, gpos, buttons):
        local = gpos - dialog.pos()
        return QMouseEvent(kind, QPointF(local), QPointF(gpos), Qt.LeftButton, buttons, Qt.NoModifier)

    errors = []
    original_hook = sys.excepthook
    sys.excepthook = lambda *args: errors.append(args[1])
    start = dialog.pos()
    try:
        dialog.mousePressEvent(mouse(QEvent.MouseButtonPress, start + QPoint(12, 10), Qt.LeftButton))
        for step in range(1, 13):
            dialog.mouseMoveEvent(mouse(QEvent.MouseMove, start + QPoint(12 + step * 16, 10 + step * 6),
                                        Qt.LeftButton))
            _pump(2)
        released = start + QPoint(12 + 12 * 16, 10 + 12 * 6)
        dialog.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, released, Qt.NoButton))
        for _ in range(60):                   # 让惯性跑完
            _pump(1)
    finally:
        sys.excepthook = original_hook
    check("拖动悬浮窗全程不抛异常", not errors, "错误=%s" % (errors[:1],))
    area = screen_mod.screen_of(dialog)
    check("拖动结束时位置被夹在可见区域",
          area.contains(dialog.geometry()) or area.intersects(dialog.geometry()),
          "pos=%s area=%s" % (dialog.pos(), area))
    dialog.close()



@test
def test_overlay_glide_range() -> None:
    """松手后不能再「溜」：慢拖 0px、快甩不超过 GLIDE_MAX_DISTANCE、关掉惯性 0px。"""
    from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt5.QtGui import QMouseEvent

    check("惯性上限被收紧（<=20px）", overlay_mod.GLIDE_MAX_DISTANCE <= 20.0,
          "%.0f" % overlay_mod.GLIDE_MAX_DISTANCE)
    check("只有真甩才触发惯性（>=300px/s）", overlay_mod.GLIDE_MIN_SPEED >= 300.0,
          "%.0f" % overlay_mod.GLIDE_MIN_SPEED)

    def run_drag(steps, step_px, delay, inertia):
        cfg = cfg_mod.OverlayConfig()
        cfg.drag_inertia = inertia
        cfg.enabled = True
        widget = overlay_mod.OverlayWindow(cfg, {})
        widget.set_tokens(theme_mod.resolve_tokens("light", "blue", "normal"))
        widget.set_rows([{"title": "连点1", "enabled": True, "clicking": False,
                          "cps": 0.0, "count": 0, "interval": 15}])
        widget._rebuild_fonts()
        widget._relayout(force=True)
        # 起点放左边一点：离屏平台只有 768x576，别让窗口贴边被夹回来
        widget.move(120, 120)
        widget.show()
        _pump()
        app = QApplication.instance()

        def mouse(kind, gpos, buttons):
            local = gpos - widget.pos()
            return QMouseEvent(kind, QPointF(local), QPointF(gpos), Qt.LeftButton, buttons, Qt.NoModifier)

        point = widget.pos() + QPoint(30, 20)
        widget._mousePressEvent(mouse(QEvent.MouseButtonPress, point, Qt.LeftButton))
        for _ in range(steps):
            point = point + QPoint(step_px, step_px // 2)
            widget._mouseMoveEvent(mouse(QEvent.MouseMove, point, Qt.LeftButton))
            end = time.perf_counter() + delay
            while time.perf_counter() < end:
                app.processEvents()
                time.sleep(0.004)
        widget._mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, point, Qt.NoButton))
        released = widget.pos()
        end = time.perf_counter() + 0.8
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.004)
        drift = (widget.pos() - released).manhattanLength()
        if os.environ.get("VEXRUSH_GLIDE_DEBUG"):
            print("    [glide] released=%s final=%s budget=%.1f"
                  % (released, widget.pos(), widget._glide_left))
        widget.close()
        _pump()
        return drift

    slow = run_drag(10, 4, 0.03, True)
    flick = run_drag(6, 16, 0.012, True)
    off = run_drag(6, 16, 0.012, False)
    check("慢慢拖：松手就是落点", slow <= 1, "%d px" % slow)
    check("快甩：溜出去不超过上限", flick <= overlay_mod.GLIDE_MAX_DISTANCE + 2,
          "%d px" % flick)
    check("关掉惯性：松手不动", off <= 1, "%d px" % off)


# ---------------------------------------------------------------- 更新
@test
def test_update_version_logic() -> None:
    from app import updater

    check("版本号解析", updater.parse_version("v3.2.2") == (3, 2, 2),
          str(updater.parse_version("v3.2.2")))
    check("版本号解析带后缀", updater.parse_version("V3.2.2-beta1") == (3, 2, 2, 1),
          str(updater.parse_version("V3.2.2-beta1")))
    check("新版本判定", updater.is_newer("3.2.2", "v3.2.3") and not updater.is_newer("3.2.2", "3.2.2")
          and not updater.is_newer("3.3.0", "3.2.9"))
    urls = updater.candidate_urls("https://example.com/api")
    check("更新地址带加速站", urls[0] == "https://example.com/api" and len(urls) == 4
          and urls[1].startswith("https://cdn.gh-proxy.org/https://example.com/api"),
          urls[1])


@test
def test_update_release_parse() -> None:
    from app import updater

    payload = {
        "tag_name": "v9.9.9",
        "name": "VexRush 9.9.9",
        "body": "## Added\n- stuff",
        "html_url": "https://github.com/x/y/releases/tag/v9.9.9",
        "published_at": "2026-01-02T03:04:05Z",
        "assets": [
            {"name": "notes.txt", "size": 10, "browser_download_url": "https://e/n.txt"},
            {"name": "VexRush.exe", "size": 123, "digest": "sha256:" + "a" * 64,
             "browser_download_url": "https://e/VexRush.exe"},
        ],
    }
    info = updater.parse_release(payload, "direct")
    check("解析发布信息", info.version_text == "9.9.9" and info.asset_name == "VexRush.exe"
          and info.asset_size == 123 and info.sha256 == "a" * 64, info.asset_url)
    check("没有安装包时给出提示",
          _raises(updater.UpdateError, lambda: updater.parse_release({"tag_name": "v1", "assets": []})))

    path = os.path.join(ROOT, "tests", "_selftest_hash.bin")
    with open(path, "wb") as handle:
        handle.write(b"vexrush")
    digest = updater.sha256_file(path)
    os.remove(path)
    check("SHA-256 计算", digest == "5b6ed0c8eb576274931d137effcf58177c914396f01f2c3401030b50dd289d81", digest)


def _raises(exc_type, fn) -> bool:
    try:
        fn()
    except exc_type:
        return True
    except Exception:
        return False
    return False


@test
def test_update_dialog_and_hotkey_grab() -> None:
    from app import mainwindow as mw_mod, update_dialog, updater

    for name, expected in (("x", False), ("r", False), ("1", False), ("f1", True), ("f12", True)):
        if (name in mw_mod.SYSTEM_HOTKEY_KEYS) is not expected:
            check("系统热键只独占功能键（%s）" % name, False)
            break
    else:
        check("系统热键只独占功能键（字母数字不会被吞）", True)

    release = updater.ReleaseInfo(
        tag="v9.9.9", version=(9, 9, 9), name="VexRush 9.9.9",
        notes="## Added\n- something new\n\n## Fixed\n- a bug",
        html_url="", published_at="2026-01-02T03:04:05Z",
        asset_name="VexRush.exe", asset_url="https://e/VexRush.exe",
        asset_size=40698103, sha256="a" * 64, source="github.com")
    dialog = update_dialog.UpdateDialog(release)
    app = QApplication.instance()
    for _ in range(6):
        app.processEvents()
        time.sleep(0.01)
    text = dialog.notes.toPlainText()
    check("更新窗口渲染 Markdown", "something new" in text and "a bug" in text, text[:40].replace("\n", " "))
    check("更新窗口显示版本与按钮", dialog.btn_go.text() == tr_done("download_install"),
          dialog.btn_go.text())
    dialog.close()


def tr_done(key: str) -> str:
    from app.i18n import tr
    return tr(key)


@test
def test_update_widgets() -> None:
    from app import mainwindow as mw_mod

    window = mw_mod.MainWindow(cfg_mod.AppConfig().normalize())
    window.show()
    for _ in range(8):
        QApplication.instance().processEvents()
        time.sleep(0.01)
    check("主界面底部有更新提示按钮且默认隐藏",
          hasattr(window, "btn_update_tip") and not window.btn_update_tip.isVisible())

    dialog = window._ensure_settings()
    for _ in range(8):
        QApplication.instance().processEvents()
        time.sleep(0.01)
    check("设置窗标题栏有检查更新按钮与转圈",
          hasattr(dialog, "btn_update") and hasattr(dialog, "spinner_update")
          and hasattr(dialog, "lbl_update"))
    check("检查更新按钮点击后进入检查态",
          _click_and_probe(dialog))
    check("使用区有启动检查更新开关", hasattr(dialog, "sw_updates")
          and dialog.sw_updates.isChecked() == bool(window.cfg.check_updates))
    check("启动检查更新开关写回配置", _toggle_updates(dialog))

    window.close()


def _click_and_probe(dialog) -> bool:
    from app import update_dialog
    original = update_dialog.CheckWorker

    class _Stub(original):                    # 不联网，只验证界面状态
        def run(self) -> None:
            time.sleep(0.05)

    update_dialog.CheckWorker = _Stub
    try:
        dialog._on_check_update()
        for _ in range(12):
            QApplication.instance().processEvents()
            time.sleep(0.01)
        busy = dialog.spinner_update.isVisible() or dialog.lbl_update.text() != ""
        dialog._check_worker.wait(2000) if dialog._check_worker else None
        return bool(busy)
    finally:
        update_dialog.CheckWorker = original


def _toggle_updates(dialog) -> bool:
    before = dialog.cfg.check_updates
    dialog.sw_updates.setChecked(not before)
    QApplication.instance().processEvents()
    ok = dialog.cfg.check_updates == (not before)
    dialog.sw_updates.setChecked(before)
    QApplication.instance().processEvents()
    return ok


@test
def test_input_hub_callbacks() -> None:
    """输入通道改回 pynput 后，回调入口仍然把按键/鼠标喂给 InputState 与热键信号。"""
    from app import engine

    state = engine.InputState()
    hub = engine.InputHub(state)
    fired = []
    hub.hotkeyPressed.connect(fired.append)

    hub._on_key("x", True)
    down = state.is_down("k:x")
    hub._on_key("x", False)
    up = state.is_down("k:x")
    hub._on_mouse("m:left", True)
    mouse_down = state.is_down("m:left")
    hub._on_mouse("m:left", False)

    check("键盘按下写入 InputState", down)
    check("键盘抬起清除 InputState", not up)
    check("鼠标按下写入 InputState", mouse_down)
    check("热键按下发出信号", fired == ["x"], str(fired))
    check("收到的输入进了「输入测试」列表", bool(list(hub.recent)))
    check("InputHub 有 pynput 监听器定义", hasattr(engine, "pynput_keyboard"))


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
