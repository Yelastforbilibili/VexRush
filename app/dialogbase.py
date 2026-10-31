"""设置类对话框的公共骨架：标题栏 + 滚动正文 + 页脚。

两个设置窗口（连点器设置 / 悬浮显示设置）共用这里的排版工具，
保证控件间距、字段宽度、滑杆样式完全一致。
"""
from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from . import widgets as w
from .i18n import tr

LABEL_W = 96


class SectionDialog(QDialog):
    changed = pyqtSignal(str)

    def __init__(self, title: str, width: int, height: int, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._loading = True
        self._anchors = {}
        self._grids = []
        self._fitted = False
        self.commit_kind = "all"
        self.setWindowTitle(title)
        self.setMinimumSize(width, height)
        self.resize(width + 20, height + 80)
        self.setModal(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget(self)
        head.setObjectName("Header")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(20, 14, 20, 12)
        head_layout.setSpacing(8)
        head_layout.addWidget(w.label(title, "PageTitle"))
        head_layout.addStretch(1)
        root.addWidget(head)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll = scroll
        body = QWidget(scroll)
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(20, 14, 20, 20)
        self.body_layout.setSpacing(8)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        footer = QWidget(self)
        footer.setObjectName("Footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        footer_layout.addWidget(w.label(tr("改动会立刻保存"), "Caption"))
        footer_layout.addStretch(1)
        done = QPushButton(tr("完成"), footer)
        done.setProperty("variant", "primary")
        done.setCursor(Qt.PointingHandCursor)
        done.clicked.connect(self.close)
        footer_layout.addWidget(done)
        root.addWidget(footer)

    # ------------------------------------------------------------ 排版工具
    def _section(self, title: str, key: str = "") -> QVBoxLayout:
        head = QWidget(self)
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(0, 12, 0, 2)
        head_layout.setSpacing(6)
        caption = w.label(title, "FieldLabel")
        font = caption.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 0.2)
        caption.setFont(font)
        head_layout.addWidget(caption)
        head_layout.addStretch(1)
        self.body_layout.addWidget(head)
        if key:
            self._anchors[key] = head
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        self.body_layout.addLayout(box)
        self.body_layout.addWidget(w.hline())
        return box

    def _grid(self) -> QGridLayout:
        """两列/三列网格：列 0 是标签列，列 1 负责拉伸，列 2 放右对齐的尾巴。"""
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(0)
        grid.setColumnMinimumWidth(0, LABEL_W)
        grid.setColumnStretch(1, 1)
        self._grids.append(grid)
        return grid

    def _fit_label_column(self) -> None:
        """按当前语言实际文字宽度定标签列宽，避免英文标签被截断。"""
        widest = LABEL_W
        for grid in self._grids:
            for index in range(grid.count()):
                item = grid.itemAt(index)
                widget = item.widget() if item is not None else None
                if widget is not None and widget.property("fieldName"):
                    widest = max(widest, widget.sizeHint().width() + 2)
        for grid in self._grids:
            grid.setColumnMinimumWidth(0, widest)
        self._fitted = True

    def _hint_label(self, text: str, parent: QWidget) -> QLabel:
        """说明文字：太长就换行，不给窗口撑出横向宽度。"""
        hint = w.label(text, "Hint")
        hint.setWordWrap(True)
        hint.setMinimumWidth(0)
        hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        hint.setParent(parent)
        return hint

    def _name_cell(self, text: str, parent: QWidget) -> QLabel:
        name = w.label(text, "FieldLabel")
        name.setProperty("fieldName", True)
        name.setParent(parent)
        return name

    def _add_control(self, grid: QGridLayout, control: QWidget, row: int) -> None:
        """能撑满的控件（输入框/下拉/滑杆容器）铺满整列，窄控件左对齐。"""
        policy = control.sizePolicy().horizontalPolicy()
        if policy in (QSizePolicy.Expanding, QSizePolicy.MinimumExpanding):
            grid.addWidget(control, row, 1)
        else:
            grid.addWidget(control, row, 1, Qt.AlignLeft | Qt.AlignVCenter)

    def _row(self, layout: QVBoxLayout, text: str, control: QWidget,
             hint: str = "") -> QWidget:
        row = QWidget(self)
        grid = self._grid()
        grid.addWidget(self._name_cell(text, row), 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self._add_control(grid, control, 0)
        if hint:
            grid.addWidget(self._hint_label(hint, row), 0, 2, Qt.AlignRight | Qt.AlignVCenter)
            grid.setColumnStretch(2, 0)
        row.setLayout(grid)
        layout.addWidget(row)
        return row

    def _switch_row(self, layout: QVBoxLayout, text: str, hint: str = "") -> w.Switch:
        row = QWidget(self)
        grid = self._grid()
        grid.addWidget(self._name_cell(text, row), 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        if hint:
            grid.addWidget(self._hint_label(hint, row), 0, 1, Qt.AlignLeft | Qt.AlignVCenter)
        switch = w.Switch(parent=row)
        grid.addWidget(switch, 0, 2, Qt.AlignRight | Qt.AlignVCenter)
        row.setLayout(grid)
        layout.addWidget(row)
        return switch

    def _slider_row(self, layout: QVBoxLayout, text: str, value: int, minimum: int,
                    maximum: int, formatter: Callable[[int], str],
                    on_change: Callable[[int], None]) -> QSlider:
        row = QWidget(self)
        grid = self._grid()
        grid.addWidget(self._name_cell(text, row), 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        slider = QSlider(Qt.Horizontal, row)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.setCursor(Qt.PointingHandCursor)
        grid.addWidget(slider, 0, 1)
        value_label = w.label(formatter(value), "Caption")
        value_label.setFixedWidth(64)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid.addWidget(value_label, 0, 2, Qt.AlignRight | Qt.AlignVCenter)
        row.setLayout(grid)
        layout.addWidget(row)

        def _on_value(raw: int) -> None:
            value_label.setText(formatter(raw))
            if not self._loading:
                on_change(raw)
                self._commit(self.commit_kind)

        slider.valueChanged.connect(_on_value)
        return slider

    def _commit(self, kind: str) -> None:
        if self._loading:
            return
        self.changed.emit(kind)

    @staticmethod
    def _elide(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:18] + " … " + text[-24:]

    # ------------------------------------------------------------ 对外
    def focus_section(self, key: str) -> None:
        anchor = self._anchors.get(key)
        if anchor is not None:
            self._scroll.ensureWidgetVisible(anchor, 0, 16)

    def sync_from_config(self) -> None:  # pragma: no cover - 子类实现
        raise NotImplementedError

    def showEvent(self, event) -> None:
        self.sync_from_config()
        if not self._fitted:
            self._fit_label_column()
        super().showEvent(event)
