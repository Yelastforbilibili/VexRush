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
        super().__init__(tr("hud_settings_2"), 580, 580, parent)
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
        box = self._section(tr("display"), "display")

        self.sw_enabled = self._switch_row(box, tr("show_hud"), tr("shows_both_channels_in_a_screen_corner"))
        self.sw_enabled.toggled.connect(lambda checked: self._set("enabled", checked))

        self.seg_layout = w.Segmented((("v", tr("vertical")), ("h", tr("horizontal"))), self.cfg.overlay.layout, self)
        self.seg_layout.changed.connect(lambda key: self._set_value("layout", key))
        self._row(box, tr("layout"), self.seg_layout)

        self.sw_title = self._switch_row(box, tr("title_text"), tr("the_small_heading_at_the_top_can_be_turn"))
        self.sw_title.toggled.connect(lambda checked: self._set("show_title", checked))

        self.ed_title = QLineEdit(self)
        self.ed_title.setMaxLength(12)
        self.ed_title.setPlaceholderText(cfg_mod.DEFAULT_OVERLAY_TITLE)
        self.ed_title.textEdited.connect(self._on_title_text)
        self._row(box, tr("title"), self.ed_title)

    def _on_title_text(self, text: str) -> None:
        self.cfg.overlay.title_text = text.strip()[:12] or cfg_mod.DEFAULT_OVERLAY_TITLE
        self._commit("overlay")

    # ------------------------------------------------------------ 内容
    def _build_content(self) -> None:
        box = self._section(tr("per_channel_content"), "content")
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._chips = {}
        for field_name, text in (("show_state", tr("status")), ("show_cps", tr("rate")),
                                 ("show_count", tr("clicks_2")), ("show_interval", tr("interval"))):
            chip = QPushButton(text, row)
            chip.setProperty("variant", "chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda checked, name=field_name: self._set(name, checked))
            layout.addWidget(chip)
            self._chips[field_name] = chip
        layout.addStretch(1)
        self._row(box, tr("content"), row)

        self.seg_anim = w.Segmented((("fade", tr("fade")), ("slide", tr("slide")), ("pulse", tr("pulse")), ("none", tr("none"))),
                                    self.cfg.overlay.animation, self)
        self.seg_anim.changed.connect(lambda key: self._set_value("animation", key))
        self._row(box, tr("transition"), self.seg_anim)

        anim_items = [(key, tr(label)) for key, label in cfg_mod.OVERLAY_ANIM_ITEMS]
        self.seg_anim_in = w.Segmented(anim_items, self.cfg.overlay.anim_in, self)
        self.seg_anim_in.changed.connect(lambda key: self._set_value("anim_in", key))
        self._row(box, tr("enter_animation"), self.seg_anim_in)
        self.seg_anim_out = w.Segmented(anim_items, self.cfg.overlay.anim_out, self)
        self.seg_anim_out.changed.connect(lambda key: self._set_value("anim_out", key))
        self._row(box, tr("exit_animation"), self.seg_anim_out)

        hz = winapi.display_refresh_hz()
        self.lbl_fps = w.label(tr("animation_follows_the_display_hz_ms_per")
                               % (hz, winapi.frame_interval_ms()), "Hint")
        box.addWidget(self.lbl_fps)

    # ------------------------------------------------------------ 样式
    def _build_style(self) -> None:
        box = self._section(tr("appearance"), "style")

        self.sl_scale = self._slider_row(box, tr("font_size"), self.cfg.overlay.scale, 70, 200,
                                         lambda v: "%d%%" % v,
                                         lambda v: self._set_value("scale", v))
        self.sl_bg_alpha = self._slider_row(box, tr("background_opacity"), self.cfg.overlay.bg_opacity, 0, 100,
                                            lambda v: "%d%%" % v,
                                            lambda v: self._set_value("bg_opacity", v))
        self.sl_alpha = self._slider_row(box, tr("overall_opacity"), self.cfg.overlay.opacity, 25, 100,
                                         lambda v: "%d%%" % v,
                                         lambda v: self._set_value("opacity", v))
        self.sl_off = self._slider_row(box, tr("dim_when_idle"), self.cfg.overlay.off_opacity, 10, 100,
                                       lambda v: "%d%%" % v,
                                       lambda v: self._set_value("off_opacity", v))
        self.sl_radius = self._slider_row(box, tr("corner_radius"), self.cfg.overlay.radius, 0, 24,
                                          lambda v: "%d px" % v,
                                          lambda v: self._set_value("radius", v))
        self.sl_padding = self._slider_row(box, tr("padding"), self.cfg.overlay.padding, 4, 28,
                                           lambda v: "%d px" % v,
                                           lambda v: self._set_value("padding", v))
        self.sl_gap = self._slider_row(box, tr("row_gap"), self.cfg.overlay.gap, 0, 24,
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
        colors_layout.addWidget(w.label(tr("background"), "Caption"))
        colors_layout.addWidget(self.btn_bg)
        colors_layout.addSpacing(10)
        colors_layout.addWidget(w.label(tr("text_2"), "Caption"))
        colors_layout.addWidget(self.btn_fg)
        colors_layout.addStretch(1)
        self._row(box, tr("colors"), colors)

        accent = QWidget(self)
        accent_layout = QHBoxLayout(accent)
        accent_layout.setContentsMargins(0, 0, 0, 0)
        accent_layout.setSpacing(8)
        self.cb_accent_mode = w.Combo(accent)
        self.cb_accent_mode.add_items((("theme", tr("follow_theme")), ("channel", tr("per_channel")),
                                       ("custom", tr("custom"))), self.cfg.overlay.accent_mode)
        self.cb_accent_mode.currentIndexChanged.connect(self._on_accent_mode)
        self.btn_accent = w.ColorButton(self.cfg.overlay.custom_accent, accent)
        self.btn_accent.colorChanged.connect(lambda value: self._set_value("custom_accent", value))
        accent_layout.addWidget(self.cb_accent_mode, 1)
        accent_layout.addWidget(self.btn_accent)
        accent_layout.addStretch(1)
        self._row(box, tr("accent"), accent)

        self.sw_rainbow = self._switch_row(box, tr("rainbow_flow"), tr("active_channels_get_a_flowing_rainbow_ti"))
        self.sw_rainbow.toggled.connect(lambda checked: self._set("rainbow", checked))
        self.sl_rainbow = self._slider_row(box, tr("flow_speed"), self.cfg.overlay.rainbow_speed, 16, 200,
                                          lambda v: "%d ms" % v,
                                          lambda v: self._set_value("rainbow_speed", v))

    def _on_accent_mode(self, _index: int) -> None:
        if self._loading:
            return
        self.cfg.overlay.accent_mode = self.cb_accent_mode.current_data() or "theme"
        self._commit("overlay")

    # ------------------------------------------------------------ 窗口
    def _build_window(self) -> None:
        box = self._section(tr("window"), "window")

        self.sw_click = self._switch_row(box, tr("click_through"), tr("mouse_events_pass_through_the_hud_so_gam"))
        self.sw_click.toggled.connect(lambda checked: self._set("click_through", checked))
        self.sw_lock = self._switch_row(box, tr("lock_position"), tr("cannot_be_dragged_while_locked"))
        self.sw_lock.toggled.connect(lambda checked: self._set("locked", checked))

        self.sw_drag = self._switch_row(box, tr("smooth_drag"), tr("the_hud_eases_toward_the_cursor_while_dr"))
        self.sw_drag.toggled.connect(lambda checked: self._set("drag_smooth", checked))
        self.sl_drag = self._slider_row(box, tr("drag_easing"), self.cfg.overlay.drag_ease, 6, 60,
                                        lambda v: "%d" % v,
                                        lambda v: self._set_value("drag_ease", v))
        self.sw_inertia = self._switch_row(box, tr("release_inertia"), tr("after_a_quick_flick_it_glides_a_little_f"))
        self.sw_inertia.toggled.connect(lambda checked: self._set("drag_inertia", checked))

        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        preview = QPushButton(tr("replay_animation"), row)
        preview.setCursor(Qt.PointingHandCursor)
        preview.setToolTip(tr("replay_animation_hint"))
        preview.clicked.connect(self.requestPreview.emit)
        reset_pos = QPushButton(tr("reset_position"), row)
        reset_pos.setCursor(Qt.PointingHandCursor)
        reset_pos.clicked.connect(self._reset_pos)
        reset_style = QPushButton(tr("reset_style"), row)
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
