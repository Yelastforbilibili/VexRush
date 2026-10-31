"""主窗口：两路连点 + 目标选择 + 设置入口。"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import math
import time
from typing import List, Optional

from PyQt5.QtCore import QEasingCurve, QRect, Qt, QTimer, QVariantAnimation, pyqtSignal
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

WM_SIZING = 0x0214
WM_MOVING = 0x0216
WM_EXITSIZEMOVE = 0x0232
EASE_RATE = 26.0

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
        if getattr(self, "_easing", False) or getattr(self, "_width_guard", False):
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
        need = self._min_width_for_cards()
        if self.width() < need:
            self._animate_width(need)

    # ------------------------------------------------- 拖动/缩放时窗口缓动跟随
    def nativeEvent(self, event_type, message):
        """接管 WM_SIZING / WM_MOVING：先记账，再由定时器缓动靠过去。"""
        if not getattr(self.cfg, "smooth_window", False):
            return super().nativeEvent(event_type, message)
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
        except Exception:
            return super().nativeEvent(event_type, message)
        if msg.message in (WM_SIZING, WM_MOVING):
            try:
                values = ctypes.cast(msg.lParam, ctypes.POINTER(ctypes.c_long * 4)).contents
                left, top, right, bottom = (int(values[0]), int(values[1]),
                                            int(values[2]), int(values[3]))
            except Exception:
                return super().nativeEvent(event_type, message)
            self._ease_to(QRect(left, top, max(320, right - left), max(200, bottom - top)))
            return True, 1                      # 拦下系统默认的瞬间贴合
        if msg.message == WM_EXITSIZEMOVE:
            self._ease_finish()
        return super().nativeEvent(event_type, message)

    def _ease_to(self, target: QRect) -> None:
        self._ease_target = target
        timer = getattr(self, "_ease_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setTimerType(Qt.PreciseTimer)
            timer.setInterval(winapi.frame_interval_ms())
            timer.timeout.connect(self._ease_step)
            self._ease_timer = timer
        if not timer.isActive():
            self._ease_stamp = time.perf_counter()
            timer.start()

    def _ease_finish(self) -> None:
        timer = getattr(self, "_ease_timer", None)
        target = getattr(self, "_ease_target", None)
        if timer is not None:
            timer.stop()
        if target is not None:
            self._easing = True
            try:
                self.setGeometry(target)
            finally:
                self._easing = False
        self._ease_target = None
        self._fit_height(allow_shrink=False, animate=True)

    def _ease_step(self) -> None:
        target = getattr(self, "_ease_target", None)
        timer = getattr(self, "_ease_timer", None)
        if target is None or timer is None:
            if timer is not None:
                timer.stop()
            return
        now = time.perf_counter()
        dt = min(0.05, max(0.001, now - getattr(self, "_ease_stamp", now)))
        self._ease_stamp = now
        current = self.geometry()
        k = min(0.5, 1.0 - math.exp(-dt * EASE_RATE))
        left = current.x() + (target.x() - current.x()) * k
        top = current.y() + (target.y() - current.y()) * k
        width = current.width() + (target.width() - current.width()) * k
        height = current.height() + (target.height() - current.height()) * k
        close = (abs(target.x() - left) < 1.0 and abs(target.y() - top) < 1.0
                 and abs(target.width() - width) < 1.0 and abs(target.height() - height) < 1.0)
        if close:
            left, top, width, height = (target.x(), target.y(), target.width(), target.height())
        self._easing = True
        try:
            self.setGeometry(QRect(int(round(left)), int(round(top)),
                                   int(round(width)), int(round(height))))
        finally:
            self._easing = False
        if close:
            timer.stop()

    def _fit_height(self, allow_shrink: bool = False, animate: bool = True) -> None:
        """让窗口高度贴合卡片内容：挤到就长高，多出空白就收一点。"""
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
        if not getattr(self, "_dwm_done", False):
            self._dwm_done = True
            winapi.apply_dark_titlebar(int(self.winId()), theme_mod.is_dark(self.cfg.appearance.theme))
        if not getattr(self, "_first_fit_done", False):
            self._first_fit_done = True
            if not self.cfg.geometry:
                # 第一次打开（没有保存过窗口几何）：直接贴合内容，不留空白
                QTimer.singleShot(0, lambda: self._fit_height(allow_shrink=True, animate=False))

    def closeEvent(self, event: QCloseEvent) -> None:
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
