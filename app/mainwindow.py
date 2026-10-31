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
from PyQt5.QtGui import QCloseEvent, QShowEvent
from PyQt5.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLineEdit, QMainWindow,
                             QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from . import config as cfg_mod
from . import engine, fonts as fonts_mod, i18n as i18n_mod, theme as theme_mod, widgets as w, winapi
from .config import AppConfig, ChannelConfig
from .dialogbase import SectionDialog
from .overlay import OverlayWindow
from .overlay_settings import OverlaySettingsDialog
from .settings import SettingsDialog
from .i18n import tr

WM_ENTERSIZEMOVE = 0x0231
WM_EXITSIZEMOVE = 0x0232
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONDBLCLK = 0x00A3
WM_MOUSEMOVE = 0x0200
WM_LBUTTONUP = 0x0201
WM_CAPTURECHANGED = 0x0215
HTCAPTION = 2
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
DRAG_RATE = 20.0
USER32 = ctypes.WinDLL("user32", use_last_error=True)
WM_KEYDOWN = 0x0100


class _WindowDragFilter(QAbstractNativeEventFilter):
    """应用级原生消息钩子。

    为什么要绕这一层：点标题栏产生的是 WM_NCLBUTTONDOWN（非客户区消息），
    Qt 不会把它转给 QWidget.nativeEvent（实测 nativeEvent 一条都收不到），
    所以只能在消息进入 Qt 的分发之前拦下来，才能接管拖动。
    """

    def __init__(self, window) -> None:
        super().__init__()
        self._window = window

    def nativeEventFilter(self, event_type, message):
        window = self._window
        if window is None:
            return False, 0
        try:
            result = window.filter_native(message)
        except Exception:
            result = None
        if result is None:
            return False, 0
        return True, result



SAVE_DELAY_MS = 400
TICK_MS = 110


class ChannelCard(w.Card):
    """一路连点：间隔 / 触发 / 折叠的高级项 / 折叠的速率。"""

    changed = pyqtSignal()
    expandedChanged = pyqtSignal(int, int)
    enabledChanged = pyqtSignal(int, bool)
    renamed = pyqtSignal(int, str)

    def __init__(self, index: int, channel: engine.Channel, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.index = index
        self.channel = channel
        self.cfg: ChannelConfig = channel.cfg
        self._suppress = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.dot = w.StatusDot(self)
        head.addWidget(self.dot)
        self.title_label = w.label(cfg_mod.display_channel_name(self.index, self.cfg.name), "CardTitle")
        head.addWidget(self.title_label)
        head.addStretch(1)
        self.switch = w.Switch(parent=self)
        head.addWidget(self.switch)
        root.addLayout(head)

        interval_row = QHBoxLayout()
        interval_row.setSpacing(8)
        interval_row.addWidget(w.label(tr("interval"), "FieldLabel"))
        self.field = w.NumberField(int(self.cfg.interval_ms), cfg_mod.INTERVAL_MIN,
                                   cfg_mod.INTERVAL_MAX, 1, "ms", self)
        interval_row.addWidget(self.field)
        self.lbl_rate_hint = w.label("", "Hint")
        interval_row.addWidget(self.lbl_rate_hint)
        interval_row.addStretch(1)
        root.addLayout(interval_row)

        trigger_row = QHBoxLayout()
        trigger_row.setSpacing(8)
        trigger_row.addWidget(w.label(tr("trigger"), "FieldLabel"))
        self.cb_trigger = w.Combo(self)
        items = [("m:" + key, tr(text)) for key, text in cfg_mod.MOUSE_BUTTONS]
        items.append(("key", tr("custom_key")))
        self.cb_trigger.add_items(items, "key" if self.cfg.trigger_kind == "key"
                                  else "m:" + self.cfg.trigger_mouse)
        trigger_row.addWidget(self.cb_trigger, 1)
        self.btn_trigger_key = w.KeyButton(self.cfg.trigger_key or "", self)
        self.btn_trigger_key.setFixedWidth(96)
        trigger_row.addWidget(self.btn_trigger_key)
        root.addLayout(trigger_row)

        self.advanced, adv_body = self._collapsible(tr("advanced"))
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(w.label(tr("name"), "FieldLabel"))
        self.ed_name = QLineEdit(self.cfg.name or "", self)
        self.ed_name.setMaxLength(8)
        self.ed_name.setPlaceholderText(self._default_name())
        name_row.addWidget(self.ed_name, 1)
        adv_body.addLayout(name_row)

        sim_row = QHBoxLayout()
        sim_row.setSpacing(8)
        sim_row.addWidget(w.label(tr("simulate"), "FieldLabel"))
        self.cb_sim = w.Combo(self)
        self.cb_sim.add_items([(key, tr(text)) for key, text in cfg_mod.MOUSE_BUTTONS],
                              self.cfg.sim_mouse)
        sim_row.addWidget(self.cb_sim, 1)
        adv_body.addLayout(sim_row)

        hot_row = QHBoxLayout()
        hot_row.setSpacing(8)
        hot_row.addWidget(w.label(tr("toggle_hotkey"), "FieldLabel"))
        self.btn_hotkey = w.KeyButton(self.cfg.hotkey or "", self)
        self.btn_hotkey.setFixedWidth(96)
        hot_row.addWidget(self.btn_hotkey)
        hot_row.addStretch(1)
        adv_body.addLayout(hot_row)
        root.addWidget(self.advanced)

        self.stats, stat_body = self._collapsible(tr("rate"))
        self.spark = w.Sparkline(parent=self)
        stat_body.addWidget(self.spark)
        stat_row = QHBoxLayout()
        stat_row.setSpacing(8)
        self.lbl_count = w.label(tr("clicked_0_times"), "Caption")
        self.lbl_live = w.label(tr("0_0_clicks_s"), "Caption")
        stat_row.addWidget(self.lbl_count)
        stat_row.addStretch(1)
        stat_row.addWidget(self.lbl_live)
        stat_body.addLayout(stat_row)
        root.addWidget(self.stats)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        self.switch.toggled.connect(self._on_enabled)
        self.field.valueChanged.connect(self._on_interval)
        self.cb_trigger.activated.connect(self._on_trigger_kind)
        self.cb_sim.activated.connect(self._on_sim)
        self.btn_trigger_key.keyChanged.connect(self._on_trigger_key)
        self.btn_hotkey.keyChanged.connect(self._on_hotkey)
        self.ed_name.textEdited.connect(self._on_name)

        self.sync_from_config()

    def _default_name(self) -> str:
        return tr("click") % (self.index + 1)

    # ------------------------------------------------------------- 结构
    def _collapsible(self, title: str):
        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 6, 0, 2)
        layout.setSpacing(8)
        box = w.Collapsible(body, title, self)
        # 折叠区自己的 toggle 先跑，这里再读状态算高度增量给窗口做同帧动画
        box.header.clicked.connect(lambda: self._on_box_clicked(box))
        return box, layout

    def _on_box_clicked(self, box) -> None:
        height = box.body_height()
        self.expandedChanged.emit(self.index, height if box.is_expanded() else -height)

    # ------------------------------------------------------------- 同步
    def sync_from_config(self) -> None:
        self._suppress = True
        try:
            self.switch.setChecked(bool(self.cfg.enabled))
            self.field.setValue(int(self.cfg.interval_ms))
            if self.cfg.trigger_kind == "key":
                self.cb_trigger.select_data("key")
            else:
                self.cb_trigger.select_data("m:" + self.cfg.trigger_mouse)
            self.cb_sim.select_data(self.cfg.sim_mouse)
            self.btn_trigger_key.set_key(self.cfg.trigger_key or "")
            self.btn_hotkey.set_key(self.cfg.hotkey or "")
            name = self.cfg.name or self._default_name()
            self.title_label.setText(cfg_mod.display_channel_name(self.index, name))
            self.ed_name.setText(name)
            self._sync_trigger_key_visibility()
            self._update_rate_hint()
            self.set_active(bool(self.cfg.enabled))
        finally:
            self._suppress = False

    def set_expanded_state(self, advanced: bool, stats: bool) -> None:
        self.advanced.set_expanded(bool(advanced), animate=False)
        self.stats.set_expanded(bool(stats), animate=False)

    def expanded_state(self) -> List[bool]:
        return [self.advanced.is_expanded(), self.stats.is_expanded()]

    def _sync_trigger_key_visibility(self) -> None:
        self.btn_trigger_key.setVisible(self.cfg.trigger_kind == "key")

    def _update_rate_hint(self) -> None:
        interval = max(1, int(self.cfg.interval_ms))
        self.lbl_rate_hint.setText(tr("clicks_s") % _fmt(1000.0 / interval, 1))

    # ------------------------------------------------------------- 回调
    def _on_enabled(self, checked: bool) -> None:
        self.cfg.enabled = bool(checked)
        if not checked:
            self.spark.reset()
        self.set_active(bool(checked))
        self.enabledChanged.emit(self.index, bool(checked))
        self._emit()

    def _on_name(self, text: str) -> None:
        name = (text or "").strip()[:8] or self._default_name()
        self.cfg.name = name
        self.title_label.setText(cfg_mod.display_channel_name(self.index, name))
        self.renamed.emit(self.index, name)
        self._emit()

    def _on_interval(self, value: int) -> None:
        self.cfg.interval_ms = int(value)
        self._update_rate_hint()
        self._emit()

    def _on_trigger_kind(self, _index: int) -> None:
        key = self.cb_trigger.current_data() or "m:left"
        if key == "key":
            self.cfg.trigger_kind = "key"
        else:
            self.cfg.trigger_kind = "mouse"
            self.cfg.trigger_mouse = key.split(":", 1)[1]
        self._sync_trigger_key_visibility()
        self._emit()

    def _on_trigger_key(self, name: str) -> None:
        self.cfg.trigger_key = name
        self.cfg.trigger_kind = "key"
        self.cb_trigger.select_data("key")
        self._sync_trigger_key_visibility()
        self._emit()

    def _on_sim(self, _index: int) -> None:
        self.cfg.sim_mouse = self.cb_sim.current_data() or "left"
        self._emit()

    def _on_hotkey(self, name: str) -> None:
        self.cfg.hotkey = winapi.canon_key(name)
        self.btn_hotkey.set_key(self.cfg.hotkey)
        self._emit()

    def _emit(self) -> None:
        if self._suppress:
            return
        self.changed.emit()

    # ------------------------------------------------------------- 显示
    def tick(self) -> None:
        cps = self.channel.sample_cps()
        ceiling = max(10.0, 1000.0 / max(1, int(self.cfg.interval_ms)) * 1.15)
        self.spark.push(cps, ceiling)
        self.lbl_count.setText(tr("clicked_times") % _fmt(self.channel.clicks, 0))
        self.lbl_live.setText(tr("clicks_s_2") % _fmt(cps, 1))
        if self.channel.is_clicking():
            self.dot.set_color(w.color("accent"))
        elif self.cfg.enabled:
            self.dot.set_color(w.color("text3"))
        else:
            self.dot.set_color(w.color("border_strong", 0.9))


class MainWindow(QMainWindow):
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
        self._hwnd = 0
        self._drag_filter = _WindowDragFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._drag_filter)

    def _build_cards(self) -> None:
        for channel in self.channels:
            card = ChannelCard(channel.index, channel, self)
            card.changed.connect(self.mark_dirty)
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
        self.cfg.overlay.enabled = bool(checked)
        self.overlay.set_cfg(self.cfg.overlay)
        if checked:
            self.overlay.apply_display()
            self.overlay.restore_position()
            self.overlay.show()
        else:
            self.overlay.hide()
        if self._settings is not None:
            self._settings.sync_from_config()
        if self._overlay_settings is not None:
            self._overlay_settings.sync_from_config()
        self.mark_dirty()

    def _on_overlay_moved(self, pos: str) -> None:
        self.cfg.overlay.pos = pos
        self.mark_dirty()

    def _open_overlay_settings(self) -> None:
        if self._overlay_settings is None:
            dialog = OverlaySettingsDialog(self.cfg, self)
            dialog.changed.connect(self._on_settings_changed)
            dialog.requestPreview.connect(self._replay_overlay)
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
        if self._applying_lock:
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

    def _on_card_renamed(self, index: int, name: str) -> None:
        self.mark_dirty()
        self._on_tick()

    # ------------------------------------------------------------- 交互
    def _on_hotkey(self, name: str) -> None:
        pressed = winapi.canon_key(name)
        for card in self._card_widgets:
            if card.cfg.hotkey and winapi.canon_key(card.cfg.hotkey) == pressed:
                card.switch.setChecked(not card.switch.isChecked())
                self.overlay.flash(card.index)

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
        """换主题要重建整套样式表（实测 90~140ms），先用遮罩挡住再干活。

        用户是在设置窗里点外观，主窗口多半被设置窗盖着——遮罩要盖在设置窗上才有用。
        """
        source = self.sender()
        target = source if isinstance(source, SectionDialog) else None
        self._busy_target = target
        if target is not None:
            target.show_busy(tr("applying_appearance"))
        else:
            self._busy.show_busy(tr("applying_appearance"))
        QTimer.singleShot(60, self._apply_theme_now)

    def _apply_theme_now(self) -> None:
        self.apply_theme()
        target = getattr(self, "_busy_target", None)
        self._busy_target = None
        if target is not None:
            try:
                target.hide_busy()
            except RuntimeError:
                pass
            return
        self._sync_busy_geometry()
        self._busy.hide_busy()

    def _sync_busy_geometry(self) -> None:
        host = self.centralWidget()
        if host is not None:
            self._busy.setGeometry(host.rect())
            if self._busy.isVisible():
                self._busy.raise_()

    def _animate_height(self, target: int, duration: int = 210) -> None:
        """窗口高度平滑过渡（展开折叠区时和卡片动画同帧）。"""
        floor = max(self.minimumHeight(), self.minimumSizeHint().height())
        target = int(max(floor, min(target, self._max_height())))
        if target == self.height() or duration <= 0:
            return
        anim = getattr(self, "_height_anim", None)
        if anim is not None:
            anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(float(self.height()))
        anim.setEndValue(float(target))
        anim.setDuration(int(duration))
        anim.setEasingCurve(QEasingCurve.InOutCubic)
        anim.valueChanged.connect(lambda value: self.resize(self.width(), int(value)))
        anim.finished.connect(lambda: self.resize(self.width(), target))
        self._height_anim = anim
        anim.start()

    def _max_height(self) -> int:
        screen = QApplication.desktop().availableGeometry(self)
        return max(320, screen.height() - 80)

    def _animate_width(self, target: int, duration: int = 260) -> None:
        anim = getattr(self, "_width_anim", None)
        if anim is not None:
            anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(float(self.width()))
        anim.setEndValue(float(int(target)))
        anim.setDuration(int(duration))
        anim.setEasingCurve(QEasingCurve.OutBack)        # 回弹
        anim.valueChanged.connect(lambda value: self.resize(int(value), self.height()))
        anim.finished.connect(lambda: self.resize(int(target), self.height()))
        self._width_anim = anim
        anim.start()

    def _min_width_for_cards(self) -> int:
        """卡片并排时窗口不能再窄的宽度（再窄就会互相挤压）。"""
        host = self.cards_host.minimumSizeHint().width()
        margins = self.centralWidget().layout().contentsMargins()
        chrome = margins.left() + margins.right() + 4
        return int(max(self.minimumWidth(), host + chrome))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_busy_geometry()
        if (getattr(self, "_drag_active", False) or getattr(self, "_easing", False)
                or getattr(self, "_width_guard", False)):
            return
        # 用户手动改窗口大小后，若卡片被挤掉就重新贴合高度（#5）
        if getattr(self, "_fit_timer", None) is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._fit_height(allow_shrink=False, animate=True))
            self._fit_timer = timer
        self._fit_timer.start(240)
        need = self._min_width_for_cards()
        if self.width() < need and not self.isMaximized():
            guard = getattr(self, "_squeeze_timer", None)
            if guard is None:
                guard = QTimer(self)
                guard.setSingleShot(True)
                guard.timeout.connect(self._spring_back_width)
                self._squeeze_timer = guard
            guard.start(160)

    def _spring_back_width(self) -> None:
        if self.isMaximized() or self.isFullScreen():
            return
        if getattr(self, "_caption_drag", False) or getattr(self, "_drag_active", False):
            return
        need = self._min_width_for_cards()
        if self.width() < need:
            self._animate_width(need)

    # ------------------------------------------------- 窗口拖动缓动（自己接管标题栏）
    # 为什么要自己接管：Windows 的拖动是「模态移动循环」，它发来的 WM_MOVING
    # 里的矩形是相对**当前窗口位置**算出来的增量。在里面做插值只会让窗口
    # 以 k 倍速度爬行（实测 k≈0.34 时，光标走 240px 窗口只走 82px），
    # 表现就是「难拖动」。所以拖动这一路改成自己跑：按下标题栏时拿到鼠标
    # 抓取点，每帧按指数缓动把窗口位置往「光标 - 抓取点」逼近，跟悬浮窗
    # 那套插值完全一致。缩放（拖边框）交给系统原生，保持即时跟手。
    def _drag_log(self, text: str) -> None:
        path = os.environ.get("VEXRUSH_DRAG_LOG")
        if not path:
            return
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("%.3f %s\n" % (time.perf_counter(), text))
        except Exception:
            pass

    def _caption_start(self) -> bool:
        """标题栏按下：接管拖动。返回 True 表示已经处理，不再走系统默认。"""
        if self.isMaximized() or self.isFullScreen():
            return False
        try:
            hwnd = int(self.winId())
            rect = win32gui.GetWindowRect(hwnd)
            cursor = win32api.GetCursorPos()
        except Exception:
            return False
        for name in ("_fit_timer", "_squeeze_timer"):
            timer = getattr(self, name, None)
            if timer is not None:
                timer.stop()
        anim = getattr(self, "_width_anim", None)
        if anim is not None:
            anim.stop()
        self._drag_grab = (cursor[0] - rect[0], cursor[1] - rect[1])
        self._drag_pos = [float(rect[0]), float(rect[1])]
        self._drag_target = (float(rect[0]), float(rect[1]))
        self._drag_stamp = time.perf_counter()
        self._drag_active = True
        self._caption_drag = True
        try:
            USER32.SetCapture(hwnd)
        except Exception:
            pass
        if not self.isActiveWindow():
            try:
                winapi.bring_to_front(hwnd)
            except Exception:
                pass
        timer = getattr(self, "_drag_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setTimerType(Qt.PreciseTimer)
            timer.setInterval(winapi.frame_interval_ms())
            timer.timeout.connect(self._caption_step)
            self._drag_timer = timer
        timer.start()
        self._drag_log("start pos=%s grab=%s" % (self._drag_pos, self._drag_grab))
        return True

    def _caption_step(self) -> None:
        if not getattr(self, "_caption_drag", False):
            return
        try:
            hwnd = int(self.winId())
            cursor = win32api.GetCursorPos()
        except Exception:
            return
        grab = getattr(self, "_drag_grab", (0, 0))
        target = (float(cursor[0] - grab[0]), float(cursor[1] - grab[1]))
        pos = getattr(self, "_drag_pos", [target[0], target[1]])
        now = time.perf_counter()
        dt = min(0.05, max(0.002, now - getattr(self, "_drag_stamp", now)))
        self._drag_stamp = now
        dx, dy = target[0] - pos[0], target[1] - pos[1]
        if abs(dx) + abs(dy) > 2000.0:      # 光标瞬移（切显示器等）就直接对齐
            pos = [target[0], target[1]]
            dx = dy = 0.0
        else:
            k = min(0.55, 1.0 - math.exp(-dt * DRAG_RATE))
            pos = [pos[0] + dx * k, pos[1] + dy * k]
            if abs(target[0] - pos[0]) < 0.6:
                pos[0] = target[0]
            if abs(target[1] - pos[1]) < 0.6:
                pos[1] = target[1]
        self._drag_pos = pos
        self._drag_target = target
        self._drag_log("step target=%s pos=%s" % (target, (round(pos[0], 1), round(pos[1], 1))))
        try:
            win32gui.SetWindowPos(hwnd, 0, int(round(pos[0])), int(round(pos[1])), 0, 0,
                                  SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception:
            pass

    def _caption_end(self, snap: bool = True) -> None:
        if snap and getattr(self, "_caption_drag", False):
            try:
                hwnd = int(self.winId())
                target = getattr(self, "_drag_target", None)
                if target is not None:
                    win32gui.SetWindowPos(hwnd, 0, int(round(target[0])),
                                          int(round(target[1])), 0, 0,
                                          SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            except Exception:
                pass
        timer = getattr(self, "_drag_timer", None)
        if timer is not None:
            timer.stop()
        if getattr(self, "_caption_drag", False):
            try:
                if USER32.GetCapture() == int(self.winId()):
                    USER32.ReleaseCapture()
            except Exception:
                pass
        self._caption_drag = False
        self._drag_active = False
        self._drag_log("end snap=%s target=%s" % (snap, getattr(self, "_drag_target", None)))
        self.mark_dirty()
        QTimer.singleShot(70, lambda: self._fit_height(allow_shrink=False, animate=True))

    def filter_native(self, message):
        """应用级过滤器调到这里；返回 None 表示不拦，返回数字表示吃掉并返回它。"""
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
        except Exception:
            return None
        handled = self._handle_native_msg(msg)
        if not handled:
            return None
        return handled[1]

    def nativeEvent(self, event_type, message):
        """兜底：万一某条消息走到了窗口过程，这里同样处理一遍。"""
        if event_type != b"windows_generic_MSG":
            return super().nativeEvent(event_type, message)
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
        except Exception:
            return super().nativeEvent(event_type, message)
        handled = self._handle_native_msg(msg)
        if handled:
            return True, handled[1]
        return super().nativeEvent(event_type, message)

    def _handle_native_msg(self, msg):
        """返回 (True, 返回值) 表示吃掉这条消息；返回 None 表示放行。"""
        own = getattr(self, "_hwnd", 0)
        if not own:
            return None
        command = msg.message
        smooth = bool(getattr(self.cfg, "smooth_window", False))
        same_window = (int(msg.hWnd) == own)
        if command == WM_NCLBUTTONDOWN and same_window:
            if smooth and msg.wParam == HTCAPTION and self._caption_start():
                return True, 1
            return None
        if command == WM_NCLBUTTONDBLCLK and same_window:
            if smooth and msg.wParam == HTCAPTION:
                if self.isMaximized():
                    self.showNormal()
                else:
                    self.showMaximized()
                return True, 1
            return None
        if getattr(self, "_caption_drag", False) and same_window:
            if command == WM_MOUSEMOVE:
                return True, 0
            if command == WM_LBUTTONUP:
                self._drag_log("lbuttonup")
                self._caption_end(snap=True)
                return True, 0
            if command == WM_KEYDOWN and msg.wParam == 0x1B:      # Esc 取消这次拖动
                self._caption_end(snap=True)
                return True, 0
            if command == WM_CAPTURECHANGED:
                self._caption_end(snap=False)
                return None
        # 系统模态循环（拖边框缩放）：期间不能让自动贴合插一脚，否则会互相推
        if command == WM_ENTERSIZEMOVE and same_window:
            self._drag_active = True
            for name in ("_fit_timer", "_squeeze_timer"):
                timer = getattr(self, name, None)
                if timer is not None:
                    timer.stop()
            return None
        if command == WM_EXITSIZEMOVE and same_window:
            self._drag_active = False
            QTimer.singleShot(80, lambda: self._fit_height(allow_shrink=False, animate=True))
            if self.width() < self._min_width_for_cards():
                QTimer.singleShot(140, self._spring_back_width)
            return None
        return None

    def _fit_height(self, allow_shrink: bool = False, animate: bool = True) -> None:
        """让窗口高度贴合卡片内容：挤到就长高，多出空白就收一点。"""
        if getattr(self, "_caption_drag", False) or getattr(self, "_drag_active", False):
            return
        viewport = self.cards_scroll.viewport().height()
        content = self.cards_host.sizeHint().height()
        if viewport <= 0 or content <= 0:
            return
        delta = content - viewport
        if abs(delta) <= 2:
            return
        if delta < 0 and not allow_shrink:
            return
        target = min(self.height() + delta, self._max_height())
        if target == self.height():
            return
        if abs(delta) <= 2:
            return
        if animate:
            self._animate_height(target, 150)
        else:
            self.resize(self.width(), int(target))

    # ------------------------------------------------------------- 心跳
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


def _fmt(value: float, digits: int) -> str:
    if digits <= 0:
        return "{:,}".format(int(round(value)))
    return "{:,.{d}f}".format(float(value), d=digits)


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def _app():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance()
