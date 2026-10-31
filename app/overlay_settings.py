"""「悬浮显示」独立设置窗口：只放连点显示（HUD）相关的选项。"""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

from . import config as cfg_mod
from . import widgets as w
from . import winapi
from .config import AppConfig, OverlayConfig
from .dialogbase import SectionDialog
from .i18n import tr


class OverlaySettingsDialog(SectionDialog):
    """悬浮显示设置：外观、排布、内容、动效、窗口行为。"""

    changed = pyqtSignal(str)
    requestPreview = pyqtSignal()

    def __init__(self, app_cfg: AppConfig, parent: QWidget = None) -> None:
        super().__init__(tr("悬浮显示设置"), 580, 580, parent)
        self.cfg = app_cfg
        self.commit_kind = "overlay"
        self._build_display()
        self._build_content()
        self._build_style()
        self._build_window()
        self.body_layout.addStretch(1)
        self._loading = False
        self.sync_from_config()

    # ------------------------------------------------------------ 显示
    def _build_display(self) -> None:
        box = self._section(tr("显示"), "display")

        self.sw_enabled = self._switch_row(box, tr("显示悬浮窗"), tr("在屏幕角落显示两路连点的状态"))
        self.sw_enabled.toggled.connect(lambda checked: self._set("enabled", checked))

        self.seg_layout = w.Segmented((("v", tr("纵向")), ("h", tr("横向"))), self.cfg.overlay.layout, self)
        self.seg_layout.changed.connect(lambda key: self._set_value("layout", key))
        self._row(box, tr("排布"), self.seg_layout)

        self.sw_title = self._switch_row(box, tr("标题文字"), tr("顶部那行小标题可以关掉"))
        self.sw_title.toggled.connect(lambda checked: self._set("show_title", checked))

        self.ed_title = QLineEdit(self)
        self.ed_title.setMaxLength(12)
        self.ed_title.setPlaceholderText(cfg_mod.DEFAULT_OVERLAY_TITLE)
        self.ed_title.textEdited.connect(self._on_title_text)
        self._row(box, tr("标题内容"), self.ed_title)

    def _on_title_text(self, text: str) -> None:
        self.cfg.overlay.title_text = text.strip()[:12] or cfg_mod.DEFAULT_OVERLAY_TITLE
        self._commit("overlay")

    # ------------------------------------------------------------ 内容
    def _build_content(self) -> None:
        box = self._section(tr("每路显示内容"), "content")
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._chips = {}
        for field_name, text in (("show_state", tr("状态")), ("show_cps", tr("速率")),
                                 ("show_count", tr("次数")), ("show_interval", tr("间隔"))):
            chip = QPushButton(text, row)
            chip.setProperty("variant", "chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda checked, name=field_name: self._set(name, checked))
            layout.addWidget(chip)
            self._chips[field_name] = chip
        layout.addStretch(1)
        self._row(box, tr("显示内容"), row)

        self.seg_anim = w.Segmented((("fade", tr("淡入")), ("slide", tr("滑入")), ("pulse", tr("呼吸")), ("none", tr("无"))),
                                    self.cfg.overlay.animation, self)
        self.seg_anim.changed.connect(lambda key: self._set_value("animation", key))
        self._row(box, tr("过渡动画"), self.seg_anim)

        anim_items = [(key, tr(label)) for key, label in cfg_mod.OVERLAY_ANIM_ITEMS]
        self.seg_anim_in = w.Segmented(anim_items, self.cfg.overlay.anim_in, self)
        self.seg_anim_in.changed.connect(lambda key: self._set_value("anim_in", key))
        self._row(box, tr("入场动画"), self.seg_anim_in)
        self.seg_anim_out = w.Segmented(anim_items, self.cfg.overlay.anim_out, self)
        self.seg_anim_out.changed.connect(lambda key: self._set_value("anim_out", key))
        self._row(box, tr("出场动画"), self.seg_anim_out)

        hz = winapi.display_refresh_hz()
        self.lbl_fps = w.label(tr("动画跟随显示器刷新：%d Hz（约 %d ms 一帧）")
                               % (hz, winapi.frame_interval_ms()), "Hint")
        box.addWidget(self.lbl_fps)

    # ------------------------------------------------------------ 样式
    def _build_style(self) -> None:
        box = self._section(tr("外观"), "style")

        self.sl_scale = self._slider_row(box, tr("字号"), self.cfg.overlay.scale, 70, 200,
                                         lambda v: "%d%%" % v,
                                         lambda v: self._set_value("scale", v))
        self.sl_bg_alpha = self._slider_row(box, tr("背景不透明度"), self.cfg.overlay.bg_opacity, 0, 100,
                                            lambda v: "%d%%" % v,
                                            lambda v: self._set_value("bg_opacity", v))
        self.sl_alpha = self._slider_row(box, tr("整体不透明度"), self.cfg.overlay.opacity, 25, 100,
                                         lambda v: "%d%%" % v,
                                         lambda v: self._set_value("opacity", v))
        self.sl_off = self._slider_row(box, tr("未开启淡化"), self.cfg.overlay.off_opacity, 10, 100,
                                       lambda v: "%d%%" % v,
                                       lambda v: self._set_value("off_opacity", v))
        self.sl_radius = self._slider_row(box, tr("圆角"), self.cfg.overlay.radius, 0, 24,
                                          lambda v: "%d px" % v,
                                          lambda v: self._set_value("radius", v))
        self.sl_padding = self._slider_row(box, tr("内边距"), self.cfg.overlay.padding, 4, 28,
                                           lambda v: "%d px" % v,
                                           lambda v: self._set_value("padding", v))
        self.sl_gap = self._slider_row(box, tr("间距"), self.cfg.overlay.gap, 0, 24,
                                       lambda v: "%d px" % v,
                                       lambda v: self._set_value("gap", v))

        colors = QWidget(self)
        colors_layout = QHBoxLayout(colors)
        colors_layout.setContentsMargins(0, 0, 0, 0)
        colors_layout.setSpacing(8)
        self.btn_bg = w.ColorButton(self.cfg.overlay.bg_color, colors)
        self.btn_bg.colorChanged.connect(lambda value: self._set_value("bg_color", value))
        self.btn_fg = w.ColorButton(self.cfg.overlay.fg_color, colors)
        self.btn_fg.colorChanged.connect(lambda value: self._set_value("fg_color", value))
        colors_layout.addWidget(w.label(tr("底色"), "Caption"))
        colors_layout.addWidget(self.btn_bg)
        colors_layout.addSpacing(10)
        colors_layout.addWidget(w.label(tr("文字"), "Caption"))
        colors_layout.addWidget(self.btn_fg)
        colors_layout.addStretch(1)
        self._row(box, tr("配色"), colors)

        accent = QWidget(self)
        accent_layout = QHBoxLayout(accent)
        accent_layout.setContentsMargins(0, 0, 0, 0)
        accent_layout.setSpacing(8)
        self.cb_accent_mode = w.Combo(accent)
        self.cb_accent_mode.add_items((("theme", tr("跟随主题")), ("channel", tr("按通道")),
                                       ("custom", tr("自定义"))), self.cfg.overlay.accent_mode)
        self.cb_accent_mode.currentIndexChanged.connect(self._on_accent_mode)
        self.btn_accent = w.ColorButton(self.cfg.overlay.custom_accent, accent)
        self.btn_accent.colorChanged.connect(lambda value: self._set_value("custom_accent", value))
        accent_layout.addWidget(self.cb_accent_mode, 1)
        accent_layout.addWidget(self.btn_accent)
        accent_layout.addStretch(1)
        self._row(box, tr("强调色"), accent)

        self.sw_rainbow = self._switch_row(box, tr("彩虹流光"), tr("开启中的通道用彩色流光显示"))
        self.sw_rainbow.toggled.connect(lambda checked: self._set("rainbow", checked))
        self.sl_rainbow = self._slider_row(box, tr("流光周期"), self.cfg.overlay.rainbow_speed, 16, 200,
                                          lambda v: "%d ms" % v,
                                          lambda v: self._set_value("rainbow_speed", v))

    def _on_accent_mode(self, _index: int) -> None:
        if self._loading:
            return
        self.cfg.overlay.accent_mode = self.cb_accent_mode.current_data() or "theme"
        self._commit("overlay")

    # ------------------------------------------------------------ 窗口
    def _build_window(self) -> None:
        box = self._section(tr("窗口"), "window")

        self.sw_click = self._switch_row(box, tr("点击穿透"), tr("鼠标事件穿过悬浮窗，不影响游戏操作"))
        self.sw_click.toggled.connect(lambda checked: self._set("click_through", checked))
        self.sw_lock = self._switch_row(box, tr("锁定位置"), tr("锁定后不能用鼠标拖动"))
        self.sw_lock.toggled.connect(lambda checked: self._set("locked", checked))

        self.sw_drag = self._switch_row(box, tr("拖动跟手"), tr("拖动时有插值跟随，关掉则鼠标指哪到哪"))
        self.sw_drag.toggled.connect(lambda checked: self._set("drag_smooth", checked))
        self.sl_drag = self._slider_row(box, tr("跟手强度"), self.cfg.overlay.drag_ease, 6, 60,
                                        lambda v: "%d" % v,
                                        lambda v: self._set_value("drag_ease", v))
        self.sw_inertia = self._switch_row(box, tr("松手惯性"), tr("快速甩动后稍微滑一小段再停"))
        self.sw_inertia.toggled.connect(lambda checked: self._set("drag_inertia", checked))

        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        preview = QPushButton(tr("预览一下"), row)
        preview.setCursor(Qt.PointingHandCursor)
        preview.clicked.connect(self.requestPreview.emit)
        reset_pos = QPushButton(tr("重置位置"), row)
        reset_pos.setCursor(Qt.PointingHandCursor)
        reset_pos.clicked.connect(self._reset_pos)
        reset_style = QPushButton(tr("恢复默认样式"), row)
        reset_style.setCursor(Qt.PointingHandCursor)
        reset_style.clicked.connect(self._reset_style)
        layout.addStretch(1)
        layout.addWidget(preview)
        layout.addWidget(reset_pos)
        layout.addWidget(reset_style)
        self._row(box, "", row)

    def _reset_pos(self) -> None:
        self.cfg.overlay.pos = ""
        self._commit("overlay")

    def _reset_style(self) -> None:
        fresh = OverlayConfig()
        keep = (self.cfg.overlay.enabled, self.cfg.overlay.pos)
        for name, value in fresh.to_dict().items():
            setattr(self.cfg.overlay, name, value)
        self.cfg.overlay.enabled, self.cfg.overlay.pos = keep
        self.sync_from_config()
        self._commit("overlay")

    # ------------------------------------------------------------ 通用回调
    def _set(self, name: str, checked: bool) -> None:
        if self._loading:
            return
        setattr(self.cfg.overlay, name, bool(checked))
        self._commit("overlay")

    def _set_value(self, name: str, value) -> None:
        if self._loading:
            return
        setattr(self.cfg.overlay, name, value)
        self._commit("overlay")

    # ------------------------------------------------------------ 同步
    def sync_from_config(self) -> None:
        over = self.cfg.overlay
        self._loading = True
        try:
            self.sw_enabled.setChecked(over.enabled)
            self.seg_layout.set_value(over.layout)
            self.sw_title.setChecked(over.show_title)
            self.ed_title.setText(over.title_text)
            for name, chip in self._chips.items():
                chip.setChecked(bool(getattr(over, name)))
            self.seg_anim.set_value(over.animation)
            self.sw_rainbow.setChecked(over.rainbow)
            self.seg_anim_in.set_value(over.anim_in)
            self.seg_anim_out.set_value(over.anim_out)
            self.sw_drag.setChecked(bool(over.drag_smooth))
            self.sl_drag.setValue(int(over.drag_ease))
            self.sw_inertia.setChecked(bool(over.drag_inertia))
            self.sw_click.setChecked(over.click_through)
            self.sw_lock.setChecked(over.locked)
            self.cb_accent_mode.select_data(over.accent_mode)
            self.btn_bg.set_value(over.bg_color)
            self.btn_fg.set_value(over.fg_color)
            self.btn_accent.set_value(over.custom_accent)
            for slider, value in ((self.sl_scale, over.scale), (self.sl_bg_alpha, over.bg_opacity),
                                  (self.sl_alpha, over.opacity), (self.sl_off, over.off_opacity),
                                  (self.sl_radius, over.radius), (self.sl_padding, over.padding),
                                  (self.sl_gap, over.gap), (self.sl_rainbow, over.rainbow_speed)):
                slider.setValue(int(value))
        finally:
            self._loading = False
