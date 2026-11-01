"""连点器设置窗口：外观 / 使用（含防卡手与输入法冲突）/ 配置文件。

悬浮显示的自有选项拆到了 overlay_settings.OverlaySettingsDialog。
"""
from __future__ import annotations

import os

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QColorDialog
from PyQt5.QtWidgets import (QAbstractButton, QButtonGroup, QFileDialog, QHBoxLayout, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from . import config as cfg_mod
from . import debug as debug_mod
from . import i18n as i18n_mod
from . import fonts as fonts_mod
from . import theme as theme_mod
from . import widgets as w
from .config import AppConfig
from .dialogbase import SectionDialog
from .i18n import tr


class AccentSwatch(QAbstractButton):
    """强调色圆点。"""

    def __init__(self, key: str, hex_color: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.key = key
        self._color = hex_color
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(24, 24)
        self.setToolTip(tr(theme_mod.ACCENTS[key]["label"]))

    def paintEvent(self, _event) -> None:
        from PyQt5.QtCore import QRectF, Qt as QtNS
        from PyQt5.QtGui import QBrush, QColor, QPainter, QPen
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(3.5, 3.5, 17.0, 17.0)
        painter.setBrush(QBrush(QColor(self._color)))
        painter.setPen(QPen(QColor(255, 255, 255, 210), 1.6) if self.isChecked() else QtNS.NoPen)
        painter.drawEllipse(rect)
        if self.isChecked():
            painter.setPen(QPen(QColor(self._color), 1.6))
            painter.setBrush(QtNS.NoBrush)
            painter.drawEllipse(QRectF(1.0, 1.0, 22.0, 22.0))
        painter.end()


class SettingsDialog(SectionDialog):
    changed = pyqtSignal(str)          # appearance | general | config | all
    requestOverlay = pyqtSignal()      # 打开「悬浮显示设置」

    def __init__(self, app_cfg: AppConfig, parent: QWidget = None) -> None:
        super().__init__(tr("settings"), 640, 560, parent)
        self.cfg = app_cfg
        self._hub = getattr(parent, "hub", None)
        self._check_worker = None
        self._release = None
        self._update_dialog = None
        self.add_header_button(tr("github_repo"), self._open_repo)
        self.btn_update = self.add_header_button(tr("check_update"), self._on_check_update)
        self.spinner_update = w.MiniSpinner(self)
        self.lbl_update = w.label("", "Hint")
        self._head_layout.addWidget(self.spinner_update)
        self._head_layout.addWidget(self.lbl_update)
        self._build_appearance()
        self._build_general()
        self._build_config()
        self.body_layout.addStretch(1)
        self._loading = False
        self.sync_from_config()

    # ------------------------------------------------------------ 外观
    def _build_appearance(self) -> None:
        box = self._section(tr("appearance"), "appearance")

        theme_options = [(key, tr(value["label"])) for key, value in theme_mod.THEMES.items()]
        self.seg_theme = w.Segmented(theme_options, self.cfg.appearance.theme, self)
        self.seg_theme.changed.connect(self._on_theme)
        self._row(box, tr("theme"), self.seg_theme)

        accent_row = QWidget(self)
        accent_layout = QHBoxLayout(accent_row)
        accent_layout.setContentsMargins(0, 0, 0, 0)
        accent_layout.setSpacing(6)
        self.accent_group = QButtonGroup(self)
        self.accent_group.setExclusive(True)
        self._accent_swatches = {}
        for key, value in theme_mod.ACCENTS.items():
            swatch = AccentSwatch(key, value["swatch"], accent_row)
            self.accent_group.addButton(swatch)
            self._accent_swatches[key] = swatch
            accent_layout.addWidget(swatch)
            swatch.clicked.connect(lambda _=False, k=key: self._on_accent(k))
        self.btn_custom_accent = QPushButton(tr("custom_2"), accent_row)
        self.btn_custom_accent.setCursor(Qt.PointingHandCursor)
        self.btn_custom_accent.clicked.connect(self._pick_custom_accent)
        accent_layout.addWidget(self.btn_custom_accent)
        accent_layout.addStretch(1)
        self._row(box, tr("accent"), accent_row)

        scale_options = [(key, tr(value[0])) for key, value in theme_mod.FONT_SCALES.items()]
        self.seg_scale = w.Segmented(scale_options, self.cfg.appearance.font_scale, self)
        self.seg_scale.changed.connect(self._on_font_scale)
        self._row(box, tr("ui_font_size"), self.seg_scale)

        self.cb_font = w.Combo(self)
        self.cb_font.add_items(self._font_items(), self.cfg.appearance.font_family)
        self.cb_font.currentIndexChanged.connect(self._on_font)
        self._row(box, tr("font"), self.cb_font)

        lang_options = []
        for code, label, official in i18n_mod.available():
            lang_options.append((code, label if official else "%s · %s" % (label, tr("unofficial"))))
        self.seg_lang = w.Segmented(lang_options, self.cfg.appearance.language, self)
        self.seg_lang.changed.connect(self._on_language)
        self._row(box, tr("language"), self.seg_lang)

    def _font_items(self):
        items = [(fonts_mod.BUILTIN_KEY, fonts_mod.display_name(fonts_mod.BUILTIN_KEY))]
        for name in fonts_mod.system_families():
            items.append((fonts_mod.SYSTEM_PREFIX + name, fonts_mod.display_name(fonts_mod.SYSTEM_PREFIX + name)))
        return items

    def _pick_custom_accent(self) -> None:
        color = QColorDialog.getColor(QColor(self.cfg.appearance.custom_accent), self,
                                      tr("custom_accent_color"))
        if not color.isValid():
            return
        self.cfg.appearance.custom_accent = color.name()
        self.cfg.appearance.accent = "custom"
        self._sync_accent()
        self._commit("appearance")

    def _on_font(self, _index: int) -> None:
        if self._loading:
            return
        self.cfg.appearance.font_family = self.cb_font.current_data() or fonts_mod.BUILTIN_KEY
        self._commit("appearance")

    def _on_language(self, key: str) -> None:
        if self._loading:
            return
        self.cfg.appearance.language = key
        self._commit("language")

    def _on_theme(self, key: str) -> None:
        self.cfg.appearance.theme = key
        self._commit("appearance")

    def _on_accent(self, key: str) -> None:
        self.cfg.appearance.accent = key
        self._sync_accent()
        self._commit("appearance")

    def _on_font_scale(self, key: str) -> None:
        self.cfg.appearance.font_scale = key
        self._commit("appearance")

    # ------------------------------------------------------------ 使用
    def _build_general(self) -> None:
        box = self._section(tr("target_app"), "general")

        self.sw_auto = self._switch_row(box, tr("auto_detect"), tr("prefers_java_exe_javaw_exe_in_the_foregr"))
        self.sw_auto.toggled.connect(self._on_auto)

        self.cb_mode = w.Combo(self)
        self.cb_mode.add_items((("post", tr("postmessage_background")), ("send", tr("sendmessage_sync"))),
                               self.cfg.send_mode)
        self.cb_mode.currentIndexChanged.connect(self._on_mode)
        self._row(box, tr("send_mode"), self.cb_mode)

        box = self._section(tr("exclusive_mode"), "exclusive")
        self.sw_exclusive = self._switch_row(box, tr("only_one_channel"),
                                            tr("turning_one_channel_on_turns_the_other_o"))
        self.sw_exclusive.toggled.connect(self._on_exclusive)
        self.sw_restore = self._switch_row(box, tr("restore_previous"), tr("turning_this_channel_off_re_enables_the"))
        self.sw_restore.toggled.connect(self._on_restore)

        self.sw_smooth = self._switch_row(box, tr("smooth_window"), tr("smooth_window_hint"))
        self.sw_smooth.toggled.connect(self._on_smooth)

        self.sw_updates = self._switch_row(box, tr("check_on_startup"), tr("check_on_startup_hint"))
        self.sw_updates.toggled.connect(self._on_updates)

        box = self._section(tr("ime"), "ime")
        # 这一项暂时下线：输入框/输入法的判定在各家程序里都不可靠，做不干净就先别给用户。
        # 保持可见但整行变灰，写清「敬请期待」，避免用户以为是自己没设置对。
        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        row_layout.addWidget(w.label(tr("ignore_while_typing"), "FieldLabel"))
        badge = w.label(tr("coming_soon"), "Hint")
        row_layout.addWidget(badge)
        row_layout.addStretch(1)
        self.sw_ime = w.Switch(parent=self)
        self.sw_ime.setChecked(False)
        self.sw_ime.setEnabled(False)
        row_layout.addWidget(self.sw_ime)
        row.setEnabled(False)
        box.addWidget(row)
        hint = self._hint_label(tr("ime_unavailable_hint"), self)
        hint.setEnabled(False)
        box.addWidget(hint)

        box = self._section(tr("input_test"), "input_test")
        self.lbl_input = w.label(tr("input_none"), "Hint")
        self.lbl_input.setWordWrap(True)
        self.lbl_input.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.lbl_input)
        self.btn_log = QPushButton(tr("open_log"), self)
        self.btn_log.setProperty("variant", "ghost")
        self.btn_log.clicked.connect(self._open_log)
        box.addWidget(self.btn_log)
        self._input_timer = QTimer(self)
        self._input_timer.setInterval(250)
        self._input_timer.timeout.connect(self._pump_input)

        box = self._section(tr("hud"), "overlay")
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        open_button = QPushButton(tr("open_hud_settings"), row)
        open_button.setCursor(Qt.PointingHandCursor)
        open_button.clicked.connect(self.requestOverlay.emit)
        layout.addWidget(open_button)
        layout.addStretch(1)
        self._row(box, "", row)

    # ------------------------------------------------------------ 输入测试
    def _pretty_input(self, label: str) -> str:
        label = label or ""
        if label.startswith("k:"):
            return label[2:]
        if label.startswith("m:"):
            key = label[2:]
            for name, text_key in cfg_mod.MOUSE_BUTTONS:
                if name == key:
                    return tr(text_key)
        return label

    def _pump_input(self) -> None:
        hub = getattr(self, "_hub", None)
        recent = list(getattr(hub, "recent", ()) or ())
        if not recent:
            self.lbl_input.setText(tr("input_none"))
            return
        sources = {"hook": tr("source_hook"), "raw": tr("source_raw"), "poll": tr("source_poll")}
        rows = ["%s  %s  %s" % (stamp, sources.get(source, source), self._pretty_input(label))
                for stamp, source, label in recent[-6:]]
        self.lbl_input.setText("\n".join(rows))

    def _open_log(self) -> None:
        target = debug_mod.path()
        try:
            if target and os.path.exists(target):
                os.startfile(target)
                return
        except Exception:
            pass
        QMessageBox.warning(self, tr("open_log"), tr("open_failed"))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._hub is not None:
            self._pump_input()
            self._input_timer.start()

    def hideEvent(self, event) -> None:
        try:
            self._input_timer.stop()
        except Exception:
            pass
        super().hideEvent(event)

    def _on_auto(self, checked: bool) -> None:
        if self._loading:
            return
        self.cfg.auto_detect = bool(checked)
        self._commit("general")

    def _on_mode(self, _index: int) -> None:
        if self._loading:
            return
        self.cfg.send_mode = self.cb_mode.current_data() or "post"
        self._commit("general")

    def _on_exclusive(self, checked: bool) -> None:
        if self._loading:
            return
        self.cfg.exclusive = bool(checked)
        self._commit("general")

    def _on_restore(self, checked: bool) -> None:
        if self._loading:
            return
        self.cfg.restore_previous = bool(checked)
        self._commit("general")

    def _on_smooth(self, checked: bool) -> None:
        if self._loading:
            return
        self.cfg.smooth_window = bool(checked)
        self._commit("general")

    # ------------------------------------------------------------ 配置文件
    # ------------------------------------------------------------ 更新
    def _on_updates(self, checked: bool) -> None:
        self.cfg.check_updates = bool(checked)
        self._commit("general")

    def _on_check_update(self) -> None:
        from . import update_dialog
        if self._check_worker is not None and self._check_worker.isRunning():
            return
        self.spinner_update.start()
        self.lbl_update.setText(tr("checking_update"))
        self.btn_update.setEnabled(False)
        self._check_worker = update_dialog.check_in_background(
            self, self._on_update_found, self._on_update_failed)

    def _on_update_found(self, release) -> None:
        from . import updater
        self.spinner_update.stop()
        self.btn_update.setEnabled(True)
        self._release = release
        if updater.is_newer(cfg_mod.APP_VERSION, release.version_text):
            self.lbl_update.setText(tr("update_available"))
            self.open_release(release)
        else:
            self.lbl_update.setText(tr("update_latest"))

    def _on_update_failed(self, message: str) -> None:
        from . import debug
        debug.log("update", "check failed in settings: %s" % message)
        self.spinner_update.stop()
        self.btn_update.setEnabled(True)
        self.lbl_update.setText(tr("update_failed"))

    def open_release(self, release=None):
        """打开某个版本的更新窗口（外部也可以直接调用）。"""
        from . import update_dialog
        release = release if release is not None else self._release
        if release is None:
            return None
        if self._update_dialog is not None:
            try:
                self._update_dialog.close()
            except Exception:
                pass
        dialog = update_dialog.UpdateDialog(release, self)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._update_dialog = dialog
        return dialog

    def _build_config(self) -> None:
        box = self._section(tr("config_file"), "config")
        path = cfg_mod.config_path()
        path_label = w.label(self._elide(path, 52), "Caption")
        path_label.setToolTip(path)
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._row(box, tr("location"), path_label)

        buttons = QWidget(self)
        buttons_layout = QVBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(8)
        # 分两行摆，英文下也不会把窗口顶宽
        for group in (((tr("open_data_folder"), self._open_data_dir),),
                      ((tr("import_config_2"), self._import_config),
                       (tr("export_config_2"), self._export_config),
                       (tr("reset_to_defaults"), self._reset_all))):
            line = QHBoxLayout()
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(8)
            for text, slot in group:
                button = QPushButton(text, buttons)
                button.setCursor(Qt.PointingHandCursor)
                button.clicked.connect(slot)
                line.addWidget(button)
            line.addStretch(1)
            buttons_layout.addLayout(line)
        self._row(box, "", buttons)

    def _open_repo(self) -> None:
        import webbrowser

        webbrowser.open(cfg_mod.GITHUB_URL)

    def _open_data_dir(self) -> None:
        folder = cfg_mod.data_dir()
        try:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
        except OSError:
            QMessageBox.warning(self, tr("could_not_open"), folder)

    def _import_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("import_config"), os.path.expanduser("~"),
                                              tr("config_files_json_all_files"))
        if not path:
            return
        try:
            loaded = cfg_mod.import_config(path)
        except cfg_mod.ConfigError as exc:
            QMessageBox.warning(self, tr("import_failed"), str(exc))
            return
        cfg_mod.copy_into(self.cfg, loaded)
        self.sync_from_config()
        self._commit("all")

    def _export_config(self) -> None:
        default = os.path.join(os.path.expanduser("~"), tr("clicker_config_json"))
        path, _ = QFileDialog.getSaveFileName(self, tr("export_config"), default,
                                              tr("config_files_json_all_files"))
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            cfg_mod.export_config(self.cfg, path)
        except cfg_mod.ConfigError as exc:
            QMessageBox.warning(self, tr("export_failed"), str(exc))
            return
        QMessageBox.information(self, tr("export_complete"), tr("config_saved_to") % path)

    def _reset_all(self) -> None:
        answer = QMessageBox.question(self, tr("reset_to_defaults"), tr("reset_all_settings_to_their_defaults"),
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        keep_pos = self.cfg.overlay.pos
        cfg_mod.copy_into(self.cfg, cfg_mod.reset_config())
        self.cfg.overlay.pos = keep_pos
        self.sync_from_config()
        self._commit("all")

    # ------------------------------------------------------------ 同步
    def _sync_accent(self) -> None:
        for key, swatch in self._accent_swatches.items():
            swatch.setChecked(key == self.cfg.appearance.accent)
        custom = self.cfg.appearance.accent == "custom"
        self.btn_custom_accent.setText(self.cfg.appearance.custom_accent.upper() if custom
                                       else tr("custom_2"))
        self.btn_custom_accent.setProperty("variant", "primary" if custom else "")
        self.btn_custom_accent.style().unpolish(self.btn_custom_accent)
        self.btn_custom_accent.style().polish(self.btn_custom_accent)

    def sync_from_config(self) -> None:
        self._loading = True
        try:
            self.seg_theme.set_value(self.cfg.appearance.theme)
            self.seg_scale.set_value(self.cfg.appearance.font_scale)
            self._sync_accent()
            self.sw_auto.setChecked(self.cfg.auto_detect)
            self.cb_mode.select_data(self.cfg.send_mode)
            self.sw_exclusive.setChecked(self.cfg.exclusive)
            self.sw_restore.setChecked(self.cfg.restore_previous)
            self.sw_ime.setChecked(False)          # 功能下线，恒为关
            self.sw_smooth.setChecked(self.cfg.smooth_window)
            self.sw_updates.setChecked(bool(self.cfg.check_updates))
            self.cb_font.select_data(self.cfg.appearance.font_family)
            self.seg_lang.set_value(self.cfg.appearance.language)
        finally:
            self._loading = False
