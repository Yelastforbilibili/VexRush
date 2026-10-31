"""主窗口：两路连点 + 目标选择 + 设置入口。"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import math
import os
import time
from typing import List, Optional

import win32api
import win32gui

from PyQt5.QtCore import (QAbstractNativeEventFilter, QEasingCurve, QRect, Qt,
                            QTimer, QVariantAnimation, pyqtSignal)
from PyQt5.QtGui import QCloseEvent, QColor, QShowEvent
from PyQt5.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLineEdit, QMainWindow,
                             QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from . import config as cfg_mod
from . import debug
from . import engine, fonts as fonts_mod, i18n as i18n_mod, theme as theme_mod, widgets as w, winapi
from . import switcher as switch_mod
from .config import AppConfig, ChannelConfig
from .channel_card import ChannelCard
from .dialogbase import SectionDialog
from .overlay import OverlayWindow
from .overlay_settings import OverlaySettingsDialog
from .settings import SettingsDialog
from .window_drag import CaptionDragMixin, _WindowDragFilter

SAVE_DELAY_MS = 400
TICK_MS = 110
from .i18n import tr
from .textfmt import fmt as _fmt
from .textfmt import shorten as _shorten



class MainWindow(CaptionDragMixin, QMainWindow):
    def __init__(self, cfg: Optional[AppConfig] = None) -> None:
        super().__init__()
        self.cfg = cfg if cfg is not None else cfg_mod.load_config()
        self.tokens = {}
        self._settings: Optional[SettingsDialog] = None
        self._overlay_settings: Optional[OverlaySettingsDialog] = None
        self._lock_prev: Optional[int] = None      # 防卡手：被挤掉的那一路（最多记一条）
        self._applying_lock = False
        self._card_widgets: List[ChannelCard] = []

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self._save_now)

        self.setWindowTitle(cfg_mod.APP_NAME)
        self.setMinimumSize(660, 340)
        self.resize(830, 360)

        self.shared = engine.SharedState()
        self.shared.send_mode = self.cfg.send_mode
        self.registry = self.shared.registry
        self.hub = engine.InputHub(self.shared.input_state, self)
        self.channels = []
        for index in range(cfg_mod.CHANNEL_COUNT):
            channel = engine.Channel(index, self.shared)
            channel.cfg = self.cfg.channels[index]
            self.channels.append(channel)

        self.overlay = OverlayWindow(self.cfg.overlay, {})
        self.overlay.positionChanged.connect(self._on_overlay_moved)
        self.overlay.styleChanged.connect(self.mark_dirty)
        self.overlay.requestSettings.connect(self._open_overlay_settings)
        self.overlay.requestHide.connect(lambda: self.btn_overlay.setChecked(False))

        self._build_ui()
        self._build_cards()
        for channel in self.channels:
            channel.start()

        self.registry.changed.connect(self._on_target_changed)
        self.hub.hotkeyPressed.connect(self._on_hotkey)
        self.hub.failed.connect(self._on_input_failed)
        self.hub.ignore_ime = bool(self.cfg.ignore_ime)
        self.shared.ime_guard = bool(self.cfg.ignore_ime)

        self.apply_config()
        self.registry.start()
        self.hub.start()
        self.overlay.restore_position()
        if self.cfg.overlay.enabled:
            self.overlay.show()

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(TICK_MS)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start()

    # ------------------------------------------------------------- 界面
    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("Root")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(w.label(cfg_mod.APP_NAME, "PageTitle"), 0, Qt.AlignVCenter)
        header.addStretch(1)
        self.btn_overlay = QPushButton(tr("click_hud"), central)
        self.btn_overlay.setProperty("variant", "ghost")
        self.btn_overlay.setCheckable(True)
        self.btn_overlay.setCursor(Qt.PointingHandCursor)
        self.btn_overlay.toggled.connect(self._toggle_overlay)
        self.btn_settings = QPushButton(tr("settings"), central)
        self.btn_settings.setProperty("variant", "ghost")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.clicked.connect(self._open_settings)
        header.addWidget(self.btn_overlay)
        header.addWidget(self.btn_settings)
        layout.addLayout(header)

        bar = QFrame(central)
        bar.setObjectName("Toolbar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 7, 12, 7)
        bar_layout.setSpacing(8)
        bar_layout.addWidget(w.label(tr("target_app"), "FieldLabel"))
        self.cb_target = w.Combo(bar)
        self.cb_target.setEditable(True)
        self.cb_target.setMinimumWidth(180)
        if self.cb_target.lineEdit() is not None:
            self.cb_target.lineEdit().setPlaceholderText("javaw.exe")
            self.cb_target.lineEdit().editingFinished.connect(self._on_target_typed)
        self.cb_target.activated.connect(self._on_target_pick)
        bar_layout.addWidget(self.cb_target, 1)
        self.btn_refresh = QPushButton(tr("refresh"), bar)
        self.btn_refresh.setProperty("variant", "ghost")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(lambda: self._refresh_targets(self.cfg.target_process))
        bar_layout.addWidget(self.btn_refresh)
        self.lbl_target = w.label("", "Hint")
        self.lbl_target.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_target.setMinimumWidth(140)
        bar_layout.addWidget(self.lbl_target)
        layout.addWidget(bar)

        self.cards_host = QWidget(central)
        self.cards_host.setObjectName("Canvas")
        self.cards_row = QHBoxLayout(self.cards_host)
        self.cards_row.setContentsMargins(0, 0, 0, 0)
        self.cards_row.setSpacing(10)
        self.cards_scroll = QScrollArea(central)
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.NoFrame)
        self.cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cards_scroll.setWidget(self.cards_host)
        layout.addWidget(self.cards_scroll, 1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self.lbl_saved = w.label("", "Hint")
        footer.addWidget(self.lbl_saved)
        footer.addStretch(1)
        footer.addWidget(w.label("v%s" % cfg_mod.APP_VERSION, "Hint"))
        layout.addLayout(footer)

        self.setCentralWidget(central)
        self._busy = w.BusyOverlay(central)
        self._caption_drag = False
        self._drag_grab = (0, 0)
        self._drag_pos = [0.0, 0.0]
        self._drag_target = None
        self._drag_stamp = 0.0
        self._drag_timer = None
        self._hotkey_ids = {}
        self._hotkey_map = {}
        self._hot_key = 0x4D00
        self._hot_last = ("", 0.0)
        self._hwnd = 0
        self._switcher = switch_mod.ThemeSwitcher(self)
        self._drag_filter = _WindowDragFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._drag_filter)

    def _build_cards(self) -> None:
        for channel in self.channels:
            card = ChannelCard(channel.index, channel, self)
            card.changed.connect(self._on_card_changed)
            card.expandedChanged.connect(self._on_card_expanded)
            card.enabledChanged.connect(self._on_card_enabled)
            card.renamed.connect(self._on_card_renamed)
            self.cards_row.addWidget(card, 1, Qt.AlignTop)
            self._card_widgets.append(card)

    # ------------------------------------------------------------- 主题
    def apply_theme(self) -> None:
        self.tokens = theme_mod.apply_theme(_app(), self.cfg.appearance.theme,
                                            self.cfg.appearance.accent,
                                            self.cfg.appearance.font_scale,
                                            fonts_mod.resolve_family(self.cfg.appearance.font_family),
                                            self.cfg.appearance.custom_accent)
        w.set_tokens(self.tokens)
        self.overlay.set_tokens(self.tokens)
        self.overlay.apply_display()
        for card in self._card_widgets:
            card.set_active(bool(card.cfg.enabled))
            card.update()
        self.update()

    def apply_config(self) -> None:
        self._loading_config = True
        try:
            self._apply_config_inner()
        finally:
            self._loading_config = False

    def _apply_config_inner(self) -> None:
        self.apply_theme()
        self._refresh_targets(self.cfg.target_process, autodetect=self.cfg.auto_detect)
        self.btn_overlay.blockSignals(True)
        self.btn_overlay.setChecked(bool(self.cfg.overlay.enabled))
        self.btn_overlay.blockSignals(False)
        if self.cfg.geometry:
            self._restore_geometry(self.cfg.geometry)
        for card in self._card_widgets:
            card.sync_from_config()
            pair = self.cfg.expanded[card.index]
            card.set_expanded_state(pair[0], pair[1])
        self._refresh_status()

    def _restore_geometry(self, encoded: str) -> None:
        try:
            raw = base64.b64decode(encoded.encode("ascii"))
        except Exception:
            return
        self.restoreGeometry(raw)

    def _encode_geometry(self) -> str:
        return base64.b64encode(bytes(self.saveGeometry())).decode("ascii")

    def mark_dirty(self) -> None:
        self._save_timer.start()

    def _save_now(self) -> None:
        self.cfg.geometry = self._encode_geometry()
        try:
            cfg_mod.save_config(self.cfg)
        except cfg_mod.ConfigError as exc:
            self.lbl_saved.setText(str(exc))
            return
        self.lbl_saved.setText(tr("saved") % time.strftime("%H:%M:%S"))

    def _refresh_status(self) -> None:
        self.lbl_saved.setText(tr("config_auto_saves"))
        self.lbl_saved.setToolTip(cfg_mod.config_path())

    # ------------------------------------------------------------- 目标
    def _refresh_targets(self, select: Optional[str] = None, autodetect: bool = False) -> None:
        wanted = (select or self.cfg.target_process or "").strip()
        if autodetect and not wanted:
            found = winapi.detect_java_target()
            if found:
                wanted = found["proc"]
        names = []
        for entry in winapi.list_gui_processes():
            if entry["proc"] not in names:
                names.append(entry["proc"])
        if wanted and wanted not in names:
            names.insert(0, wanted)
        if not names:
            names = ["javaw.exe"]
        self.cb_target.blockSignals(True)
        self.cb_target.clear()
        self.cb_target.add_items([(name, name) for name in names], wanted or names[0])
        self.cb_target.blockSignals(False)
        target = wanted or names[0]
        self.cfg.target_process = target
        self.registry.set_process(target)
        self._refresh_status()

    def _on_target_pick(self, _index: int) -> None:
        name = self.cb_target.currentText().strip()
        if name:
            self.cfg.target_process = name
            self.registry.set_process(name)
            self.mark_dirty()

    def _on_target_typed(self) -> None:
        name = self.cb_target.currentText().strip()
        if name and name != self.cfg.target_process:
            self.cfg.target_process = name
            self.registry.set_process(name)
            self.mark_dirty()

    def _on_target_changed(self, hwnd: int, proc: str, title: str) -> None:
        if hwnd:
            text = "%s · %s" % (proc, title or "")
            self.lbl_target.setText(_shorten(text, 26))
            self.lbl_target.setToolTip("%s\nhwnd=%s" % (text, hwnd))
        else:
            self.lbl_target.setText(tr("no_window_found"))
            self.lbl_target.setToolTip("")

    # ------------------------------------------------------------- 悬浮显示
    def _toggle_overlay(self, checked: bool) -> None:
        # 只改开关再交给 apply_display —— 入场/出场动画、定位都由它统一处理，
        # 这里再 show()/hide() 会把动画吃掉（之前主界面开关没有动画就是这个原因）。
        self.cfg.overlay.enabled = bool(checked)
        self.overlay.set_cfg(self.cfg.overlay)
        self.overlay.apply_display()
        if self._settings is not None:
            self._settings.sync_from_config()
        if self._overlay_settings is not None:
            self._overlay_settings.sync_from_config()
        self.mark_dirty()

    def _reset_overlay_position(self) -> None:
        """把悬浮窗挪回默认的右上角（设置里点了「重置位置」）。"""
        self.cfg.overlay.pos = ""
        self.overlay.set_cfg(self.cfg.overlay)
        self.overlay.restore_position()
        self.overlay.flash(0)
        self.mark_dirty()

    def _on_overlay_moved(self, pos: str) -> None:
        self.cfg.overlay.pos = pos
        self.mark_dirty()

    def _open_overlay_settings(self) -> None:
        if self._overlay_settings is None:
            dialog = OverlaySettingsDialog(self.cfg, self)
            dialog.changed.connect(self._on_settings_changed)
            dialog.requestPreview.connect(self._replay_overlay)
            dialog.requestResetPosition.connect(self._reset_overlay_position)
            self._overlay_settings = dialog
        dialog = self._overlay_settings
        dialog.sync_from_config()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def _replay_overlay(self) -> None:
        """试播一次入场动画：悬浮窗没开就先临时亮出来，3 秒后收回去。"""
        overlay = self.overlay
        overlay.set_cfg(self.cfg.overlay)
        if not overlay.isVisible():
            overlay.restore_position()
            overlay.show()
            QTimer.singleShot(3200, self._end_preview)
        overlay.flash(0)
        overlay.play_in()

    def _end_preview(self) -> None:
        if not self.cfg.overlay.enabled:
            self.overlay.hide()

    # ------------------------------------------------------------- 设置
    def _ensure_settings(self) -> SettingsDialog:
        if self._settings is None:
            self._settings = SettingsDialog(self.cfg, self)
            self._settings.changed.connect(self._on_settings_changed)
            self._settings.requestOverlay.connect(self._open_overlay_settings)
        return self._settings

    def _open_settings(self) -> None:
        dialog = self._ensure_settings()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_settings_changed(self, kind: str) -> None:
        if kind == "language":
            i18n_mod.set_language(self.cfg.appearance.language)
            self._reload_ui()
            self.mark_dirty()
            return
        if kind in ("appearance", "all"):
            self._apply_theme_with_busy()
        if kind in ("general", "all"):
            self.shared.send_mode = self.cfg.send_mode
            self.hub.ignore_ime = bool(self.cfg.ignore_ime)
            self.shared.ime_guard = bool(self.cfg.ignore_ime)
            self._refresh_targets(self.cfg.target_process, autodetect=self.cfg.auto_detect)
        if kind in ("overlay", "all"):
            self.overlay.set_cfg(self.cfg.overlay)
            self.overlay.apply_display()
            self.btn_overlay.blockSignals(True)
            self.btn_overlay.setChecked(bool(self.cfg.overlay.enabled))
            self.btn_overlay.blockSignals(False)
        if kind in ("config", "all"):
            for card in self._card_widgets:
                card.sync_from_config()
            self.btn_overlay.blockSignals(True)
            self.btn_overlay.setChecked(bool(self.cfg.overlay.enabled))
            self.btn_overlay.blockSignals(False)
            self.overlay.set_cfg(self.cfg.overlay)
            self.overlay.apply_display()
        self.mark_dirty()

    def _reload_ui(self) -> None:
        """切换语言后重建整个界面：引擎线程与配置对象原地复用。"""
        settings_was_open = self._settings is not None and self._settings.isVisible()
        overlay_settings_was_open = (self._overlay_settings is not None
                                     and self._overlay_settings.isVisible())
        for dialog in (self._settings, self._overlay_settings):
            if dialog is not None:
                dialog.close()
                dialog.deleteLater()
        self._settings = None
        self._overlay_settings = None

        was_ticking = self._tick_timer.isActive()
        self._tick_timer.stop()
        old = self.takeCentralWidget()
        if old is not None:
            old.setParent(None)
            old.deleteLater()
        self._card_widgets = []
        self._build_ui()
        self._build_cards()
        self.apply_theme()
        self._refresh_targets(self.cfg.target_process, autodetect=False)
        self.btn_overlay.blockSignals(True)
        self.btn_overlay.setChecked(bool(self.cfg.overlay.enabled))
        self.btn_overlay.blockSignals(False)
        for card in self._card_widgets:
            card.sync_from_config()
            pair = self.cfg.expanded[card.index]
            card.set_expanded_state(pair[0], pair[1])
        self._refresh_status()
        if was_ticking:
            self._tick_timer.start(TICK_MS)
        if settings_was_open:
            self._open_settings()
        if overlay_settings_was_open:
            self._open_overlay_settings()

    # ------------------------------------------------------------- 防卡手
    def _on_card_enabled(self, index: int, enabled: bool) -> None:
        if self._applying_lock or getattr(self, "_loading_config", False):
            # 程序自己在铺配置（启动 / 导入 / 切换语言重建）时不要触发防卡手：
            # 用户存下来的开关状态应该原样恢复，不能一启动就互相踢。
            return
        if enabled:
            if not self.cfg.exclusive:
                return
            other = 1 - index
            if 0 <= other < len(self._card_widgets) and self._card_widgets[other].cfg.enabled:
                self._set_channel_enabled(other, False)
                self._lock_prev = other        # 单槽：永远只记最近被挤掉的那一路
            return
        if not (self.cfg.exclusive and self.cfg.restore_previous):
            return
        prev = self._lock_prev
        self._lock_prev = None
        if prev is None or prev == index:
            return
        card = self._card_widgets[prev] if 0 <= prev < len(self._card_widgets) else None
        if card is not None and not card.cfg.enabled:
            self._set_channel_enabled(prev, True)

    def _set_channel_enabled(self, index: int, value: bool) -> None:
        """由程序改某一路的开关（不触发防卡手自身的联动）。"""
        if not 0 <= index < len(self._card_widgets):
            return
        card = self._card_widgets[index]
        self._applying_lock = True
        try:
            card.switch.setChecked(bool(value))
        finally:
            self._applying_lock = False

    def _on_card_changed(self) -> None:
        self.mark_dirty()
        self._sync_hotkeys()

    def _on_card_renamed(self, index: int, name: str) -> None:
        self.mark_dirty()
        self._on_tick()

    # ------------------------------------------------------------- 交互
    def _on_hotkey(self, name: str) -> None:
        pressed = winapi.canon_key(name)
        now = time.perf_counter()
        last_name, last_stamp = getattr(self, "_hot_last", ("", 0.0))
        if last_name == pressed and now - last_stamp < 0.16:
            return                      # 同一个键被两条通道各报了一次，只处理第一下
        self._hot_last = (pressed, now)
        debug.log("hotkey", "fire %s" % pressed)
        for card in self._card_widgets:
            if card.cfg.hotkey and winapi.canon_key(card.cfg.hotkey) == pressed:
                card.switch.setChecked(not card.switch.isChecked())
                self.overlay.flash(card.index)

    def _sync_hotkeys(self) -> None:
        """把两路的开关热键注册成系统级热键（作为全局钩子之外的兜底通道）。"""
        hwnd = getattr(self, "_hwnd", 0)
        if not hwnd:
            return
        wanted = []
        for card in self._card_widgets:
            name = winapi.canon_key(card.cfg.hotkey or "")
            if name and winapi.key_vk(name) and name not in wanted:
                wanted.append(name)
        if wanted == list(self._hotkey_ids.keys()):
            return                      # 热键没变，不用反复注册
        for hotkey_id in list(self._hotkey_ids.values()):
            winapi.unregister_hotkey(hwnd, hotkey_id)
        self._hotkey_ids = {}
        self._hotkey_map = {}
        for card in self._card_widgets:
            name = winapi.canon_key(card.cfg.hotkey or "")
            vk = winapi.key_vk(name)
            if not vk or name in self._hotkey_map.values():
                continue
            hotkey_id = self._hot_key + len(self._hotkey_ids)
            if winapi.register_hotkey(hwnd, hotkey_id, vk):
                self._hotkey_ids[name] = hotkey_id
                self._hotkey_map[hotkey_id] = name
                debug.log("hotkey", "registered %s id=%d ok" % (name, hotkey_id))
            else:
                debug.log("hotkey", "register %s failed (另一个程序占用了这个键？)" % name)

    def _clear_hotkeys(self) -> None:
        hwnd = getattr(self, "_hwnd", 0)
        if not hwnd:
            return
        for hotkey_id in list(self._hotkey_ids.values()):
            winapi.unregister_hotkey(hwnd, hotkey_id)
        self._hotkey_ids = {}
        self._hotkey_map = {}

    def _on_input_failed(self, message: str) -> None:
        self.lbl_target.setText(tr("input_hook_unavailable"))
        self.lbl_target.setToolTip(message)

    def _on_card_expanded(self, index: int, delta: int = 0) -> None:
        if not 0 <= index < len(self._card_widgets):
            return
        card = self._card_widgets[index]
        self.cfg.expanded[index] = card.expanded_state()
        self.mark_dirty()
        if delta:
            self._animate_height(self.height() + int(delta), w.COLLAPSE_MS)
        QTimer.singleShot(280, lambda: self._fit_height(allow_shrink=True))   # 动画后精修一次

    def _apply_theme_with_busy(self) -> None:
        """换主题要重建整套样式表（实测 90~140ms），这段时间界面必然卡一下。

        做法是障眼法：先把整块屏幕抓成模糊画面 + 旧配色蒙版盖上去，卡顿发生在这层
        幕布背后；重建完蒙版颜色缓动到新配色，再淡出露出新界面。悬浮显示窗同时用
        柔焦动画收起、换好之后再用柔焦动画回来，观感上就是「旧界面淡出 → 换色 → 新界面淡入」。
        """
        source = self.sender()
        target = source if isinstance(source, SectionDialog) else None
        old_color = QColor(self._canvas_color())
        new_color = QColor(self._preview_canvas_color())
        area = switch_mod.screen_area_for(target if target is not None else self)
        self._switcher.run(
            area,
            old_color,
            new_color,
            self.apply_theme,
            before=self._theme_switch_before,
            after=self._theme_switch_after,
            label=tr("applying_appearance"),
            contrast=QColor(str((self.tokens or {}).get("text") or "#111827")),
        )

    def _canvas_color(self) -> str:
        tokens = getattr(self, "tokens", None) or {}
        return str(tokens.get("canvas") or "#f4f6f9")

    def _preview_canvas_color(self) -> str:
        """只算令牌、不动控件，用来知道新配色长什么样。"""
        try:
            tokens = theme_mod.resolve_tokens(
                self.cfg.appearance.theme,
                self.cfg.appearance.accent,
                self.cfg.appearance.font_scale,
                self.cfg.appearance.custom_accent,
            )
            return str(tokens.get("canvas") or "#f4f6f9")
        except Exception:
            return self._canvas_color()

    def _theme_switch_before(self) -> None:
        """幕布盖上来之前：把悬浮显示用柔焦动画收起来。"""
        try:
            if self.overlay.isVisible():
                self.overlay.play_out(hide_after=False)
        except RuntimeError:
            pass
        self._busy.hide_busy()

    def _theme_switch_after(self) -> None:
        """幕布开始淡出时：新样式已经就位，把该出现的东西放回来。"""
        self._sync_busy_geometry()
        try:
            self.overlay.set_cfg(self.cfg.overlay)
            self.overlay.apply_display()
        except RuntimeError:
            pass
        self.update()

    def _sync_busy_geometry(self) -> None:
        host = self.centralWidget()
        if host is not None:
            self._busy.setGeometry(host.rect())
            if self._busy.isVisible():
                self._busy.raise_()

    def _on_tick(self) -> None:
        rows = []
        for card in self._card_widgets:
            card.tick()
            channel = card.channel
            rows.append({
                "title": cfg_mod.display_channel_name(card.index, card.cfg.name or card._default_name()),
                "enabled": bool(card.cfg.enabled),
                "clicking": channel.is_clicking(),
                "cps": channel.cps,
                "count": channel.clicks,
                "interval": int(card.cfg.interval_ms),
            })
        self.overlay.set_rows(rows)

    # ------------------------------------------------------------- 事件
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            self._hwnd = int(self.winId())
        except Exception:
            pass
        if not getattr(self, "_dwm_done", False):
            self._dwm_done = True
            winapi.apply_dark_titlebar(int(self.winId()), theme_mod.is_dark(self.cfg.appearance.theme))
        if not getattr(self, "_hotkeys_done", False):
            # 句柄有了才能注册系统级热键（两路开关热键的兜底通道）
            self._hotkeys_done = True
            self._sync_hotkeys()
        if not getattr(self, "_first_fit_done", False):
            self._first_fit_done = True
            if not self.cfg.geometry:
                # 第一次打开（没有保存过窗口几何）：直接贴合内容，不留空白
                QTimer.singleShot(0, lambda: self._fit_height(allow_shrink=True, animate=False))

    def closeEvent(self, event: QCloseEvent) -> None:
        filt = getattr(self, "_drag_filter", None)
        if filt is not None:
            app = QApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(filt)
            self._drag_filter = None
        if self._save_timer.isActive():
            self._save_timer.stop()
        self.cfg.geometry = self._encode_geometry()
        try:
            cfg_mod.save_config(self.cfg)
        except cfg_mod.ConfigError:
            pass
        self._clear_hotkeys()
        self._tick_timer.stop()
        self.overlay.hide()
        if self._settings is not None:
            self._settings.close()
        if self._overlay_settings is not None:
            self._overlay_settings.close()
        self.hub.stop()
        for channel in self.channels:
            channel.stop()
        self.shared.close()
        super().closeEvent(event)


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def _app():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance()
