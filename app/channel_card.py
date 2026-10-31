"""一路连点卡片：间隔 / 触发 / 折叠的高级项 / 折叠的速率。"""
from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLineEdit, QSizePolicy, QVBoxLayout, QWidget

from . import config as cfg_mod
from . import engine, widgets as w, winapi
from .config import ChannelConfig
from .i18n import tr
from .textfmt import fmt as _fmt


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
