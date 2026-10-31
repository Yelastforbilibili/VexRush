"""连点器设置窗口：外观 / 使用（含防卡手与输入法冲突）/ 配置文件。

悬浮显示的自有选项拆到了 overlay_settings.OverlaySettingsDialog。
"""
from __future__ import annotations

import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QColorDialog
from PyQt5.QtWidgets import (QAbstractButton, QButtonGroup, QFileDialog, QHBoxLayout, QMessageBox,
                             QPushButton, QWidget)

from . import config as cfg_mod
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
        super().__init__(tr("设置"), 600, 540, parent)
        self.cfg = app_cfg
        self._build_appearance()
        self._build_general()
        self._build_config()
        self.body_layout.addStretch(1)
        self._loading = False
        self.sync_from_config()

    # ------------------------------------------------------------ 外观
    def _build_appearance(self) -> None:
        box = self._section(tr("外观"), "appearance")

        theme_options = [(key, tr(value["label"])) for key, value in theme_mod.THEMES.items()]
        self.seg_theme = w.Segmented(theme_options, self.cfg.appearance.theme, self)
        self.seg_theme.changed.connect(self._on_theme)
        self._row(box, tr("主题"), self.seg_theme)

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
        self.btn_custom_accent = QPushButton(tr("自定义…"), accent_row)
        self.btn_custom_accent.setCursor(Qt.PointingHandCursor)
        self.btn_custom_accent.clicked.connect(self._pick_custom_accent)
        accent_layout.addWidget(self.btn_custom_accent)
        accent_layout.addStretch(1)
        self._row(box, tr("强调色"), accent_row)

        scale_options = [(key, tr(value[0])) for key, value in theme_mod.FONT_SCALES.items()]
        self.seg_scale = w.Segmented(scale_options, self.cfg.appearance.font_scale, self)
        self.seg_scale.changed.connect(self._on_font_scale)
        self._row(box, tr("界面字号"), self.seg_scale)

        self.cb_font = w.Combo(self)
        self.cb_font.add_items(self._font_items(), self.cfg.appearance.font_family)
        self.cb_font.currentIndexChanged.connect(self._on_font)
        self._row(box, tr("界面字体"), self.cb_font)

        lang_options = [(key, value) for key, value in cfg_mod.LANGUAGES.items()]
        self.seg_lang = w.Segmented(lang_options, self.cfg.appearance.language, self)
        self.seg_lang.changed.connect(self._on_language)
        self._row(box, tr("界面语言"), self.seg_lang)

    def _font_items(self):
        items = [(fonts_mod.BUILTIN_KEY, fonts_mod.display_name(fonts_mod.BUILTIN_KEY))]
        for name in fonts_mod.system_families():
            items.append((fonts_mod.SYSTEM_PREFIX + name, fonts_mod.display_name(fonts_mod.SYSTEM_PREFIX + name)))
        return items

    def _pick_custom_accent(self) -> None:
        color = QColorDialog.getColor(QColor(self.cfg.appearance.custom_accent), self,
                                      tr("自定义强调色"))
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
        box = self._section(tr("目标程序"), "general")

        self.sw_auto = self._switch_row(box, tr("自动识别"), tr("优先选择前台窗口里的 java.exe / javaw.exe"))
        self.sw_auto.toggled.connect(self._on_auto)

        self.cb_mode = w.Combo(self)
        self.cb_mode.add_items((("post", tr("后台消息 PostMessage")), ("send", tr("同步消息 SendMessage"))),
                               self.cfg.send_mode)
        self.cb_mode.currentIndexChanged.connect(self._on_mode)
        self._row(box, tr("发送方式"), self.cb_mode)

        box = self._section(tr("防卡手"), "exclusive")
        self.sw_exclusive = self._switch_row(box, tr("只允许开一路"),
                                            tr("开启一路时自动关掉另一路，避免两路同时猛点"))
        self.sw_exclusive.toggled.connect(self._on_exclusive)
        self.sw_restore = self._switch_row(box, tr("关闭后恢复"), tr("关掉当前这路时，把刚才被挤掉的那路重新打开"))
        self.sw_restore.toggled.connect(self._on_restore)

        box = self._section(tr("输入法"), "ime")
        self.sw_ime = self._switch_row(box, tr("打字时不响应"),
                                       tr("光标在文字输入框里（或输入法正在拼字）时，热键、鼠标和键盘触发都不生效"))
        self.sw_ime.toggled.connect(self._on_ime)

        box = self._section(tr("悬浮显示"), "overlay")
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        open_button = QPushButton(tr("打开悬浮显示设置…"), row)
        open_button.setCursor(Qt.PointingHandCursor)
        open_button.clicked.connect(self.requestOverlay.emit)
        layout.addWidget(open_button)
        layout.addStretch(1)
        self._row(box, "", row)

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

    def _on_ime(self, checked: bool) -> None:
        if self._loading:
            return
        self.cfg.ignore_ime = bool(checked)
        self._commit("general")

    # ------------------------------------------------------------ 配置文件
    def _build_config(self) -> None:
        box = self._section(tr("配置文件"), "config")
        path = cfg_mod.config_path()
        path_label = w.label(self._elide(path, 52), "Caption")
        path_label.setToolTip(path)
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._row(box, tr("保存位置"), path_label)

        buttons = QWidget(self)
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(8)
        for text, slot in ((tr("打开数据目录"), self._open_data_dir),
                           (tr("导入配置…"), self._import_config),
                           (tr("导出配置…"), self._export_config),
                           (tr("恢复默认"), self._reset_all)):
            button = QPushButton(text, buttons)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(slot)
            buttons_layout.addWidget(button)
        buttons_layout.addStretch(1)
        self._row(box, "", buttons)

    def _open_data_dir(self) -> None:
        try:
            os.startfile(cfg_mod.app_dir())
        except OSError:
            QMessageBox.warning(self, tr("打开失败"), cfg_mod.app_dir())

    def _import_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("导入配置"), os.path.expanduser("~"),
                                              tr("配置文件 (*.json);;所有文件 (*.*)"))
        if not path:
            return
        try:
            loaded = cfg_mod.import_config(path)
        except cfg_mod.ConfigError as exc:
            QMessageBox.warning(self, tr("导入失败"), str(exc))
            return
        cfg_mod.copy_into(self.cfg, loaded)
        self.sync_from_config()
        self._commit("all")

    def _export_config(self) -> None:
        default = os.path.join(os.path.expanduser("~"), tr("连点器配置.json"))
        path, _ = QFileDialog.getSaveFileName(self, tr("导出配置"), default,
                                              tr("配置文件 (*.json);;所有文件 (*.*)"))
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            cfg_mod.export_config(self.cfg, path)
        except cfg_mod.ConfigError as exc:
            QMessageBox.warning(self, tr("导出失败"), str(exc))
            return
        QMessageBox.information(self, tr("已导出"), tr("配置已保存到：\n%s") % path)

    def _reset_all(self) -> None:
        answer = QMessageBox.question(self, tr("恢复默认"), tr("要把所有设置恢复成默认值吗？"),
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
                                       else tr("自定义…"))
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
            self.sw_ime.setChecked(self.cfg.ignore_ime)
            self.cb_font.select_data(self.cfg.appearance.font_family)
            self.seg_lang.set_value(self.cfg.appearance.language)
        finally:
            self._loading = False
