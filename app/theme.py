"""设计令牌 / 主题 / 全局样式表。

参考 B 端设计规范：0.5px 微边框、同心圆角、语义色令牌、中性灰带 2~4% 冷蓝倾向、
一个操作区只允许一个主按钮、Zero Fluff（不写占位式解释文案）。
"""
from __future__ import annotations

import re
from typing import Dict

from PyQt5.QtGui import QColor, QFont, QPalette
from .i18n import tr

# ---------------------------------------------------------------- 字体

FONT_FAMILY = "Microsoft YaHei UI"
FONT_FALLBACK = "Microsoft YaHei, Segoe UI, sans-serif"

# 字号档位（用户可调）。数值是 pt，Qt 会按 DPI 自动缩放。
FONT_SCALES = {
    "small": ("small", 0.92),
    "normal": ("standard", 1.0),
    "large": ("large", 1.12),
    "xlarge": ("extra_large", 1.24),
}

_BASE_FONT = {
    "page": 14.5,   # 顶部标题
    "title": 12.0,  # 卡片标题
    "body": 10.0,   # 正文
    "caption": 8.8,  # 辅助说明
    "metric": 13.0,  # 数字读数
    "mono": 10.5,
}

# ---------------------------------------------------------------- 主题

THEMES: Dict[str, dict] = {
    "light": {
        "label": "light",
        "dark": False,
        "canvas": "#f4f6f9",
        "surface": "#ffffff",
        "subtle": "#f1f5f9",
        "sunken": "#e9eef4",
        "text": "#0f172a",
        "text2": "#52627a",
        "text3": "#8a97a8",
        "text_disabled": "#b6c0cd",
        "border": "#e3e8ef",
        "border_soft": "#eef2f7",
        "border_strong": "#cbd5e1",
        "accent_fg": "#ffffff",
        "danger": "#dc2626",
        "success": "#16a34a",
        "warning": "#ea580c",
        "info": "#0284c7",
        "danger_bg": "#fef2f2",
        "success_bg": "#f0fdf4",
        "warning_bg": "#fff7ed",
        "info_bg": "#f0f9ff",
    },
    "dark": {
        "label": "dark",
        "dark": True,
        "canvas": "#0f1318",
        "surface": "#161b22",
        "subtle": "#1d242e",
        "sunken": "#0b0f14",
        "text": "#e8eef6",
        "text2": "#9fb0c4",
        "text3": "#6f8095",
        "text_disabled": "#4c5a6b",
        "border": "#252e39",
        "border_soft": "#1c242e",
        "border_strong": "#39465a",
        "accent_fg": "#ffffff",
        "danger": "#f87171",
        "success": "#4ade80",
        "warning": "#fb923c",
        "info": "#38bdf8",
        "danger_bg": "#2a1518",
        "success_bg": "#12261a",
        "warning_bg": "#2a1e12",
        "info_bg": "#0f2330",
    },
    "warm": {
        "label": "warm_sand",
        "dark": False,
        "canvas": "#f6f3ec",
        "surface": "#fffdf8",
        "subtle": "#f2ece1",
        "sunken": "#e9e2d5",
        "text": "#2a2419",
        "text2": "#6b6150",
        "text3": "#9a8f7c",
        "text_disabled": "#c3b9a6",
        "border": "#e7e0d2",
        "border_soft": "#f0ebe0",
        "border_strong": "#d5cbb8",
        "accent_fg": "#ffffff",
        "danger": "#c2410c",
        "success": "#15803d",
        "warning": "#b45309",
        "info": "#0369a1",
        "danger_bg": "#fdf1e7",
        "success_bg": "#eef6ec",
        "warning_bg": "#fbf3e3",
        "info_bg": "#eaf3f8",
    },
    "ink": {
        "label": "ink_blue",
        "dark": True,
        "canvas": "#0c1119",
        "surface": "#131a24",
        "subtle": "#1a2330",
        "sunken": "#080c12",
        "text": "#e6edf6",
        "text2": "#9db0c6",
        "text3": "#6b7e95",
        "text_disabled": "#455667",
        "border": "#22303f",
        "border_soft": "#1a2531",
        "border_strong": "#33475c",
        "accent_fg": "#ffffff",
        "danger": "#fb7185",
        "success": "#4ade80",
        "warning": "#fbbf24",
        "info": "#60a5fa",
        "danger_bg": "#2b1620",
        "success_bg": "#0f2620",
        "warning_bg": "#2a2313",
        "info_bg": "#102234",
    },
}

# 强调色：浅色主题用深一档，深色主题用亮一档
ACCENTS: Dict[str, dict] = {
    "blue": {"label": "blue", "light": "#2563eb", "dark": "#3b82f6", "swatch": "#2563eb"},
    "cyan": {"label": "cyan", "light": "#0e7490", "dark": "#22d3ee", "swatch": "#0891b2"},
    "green": {"label": "green", "light": "#15803d", "dark": "#34d399", "swatch": "#16a34a"},
    "violet": {"label": "violet", "light": "#6d28d9", "dark": "#a78bfa", "swatch": "#7c3aed"},
    "amber": {"label": "amber", "light": "#b45309", "dark": "#fbbf24", "swatch": "#d97706"},
    "rose": {"label": "rose", "light": "#be123c", "dark": "#fb7185", "swatch": "#e11d48"},
}

DEFAULT_THEME = "light"
DEFAULT_ACCENT = "blue"
DEFAULT_FONT_SCALE = "normal"


# ---------------------------------------------------------------- 颜色工具

def _c(value: str) -> QColor:
    return QColor(value)


def mix(a: str, b: str, t: float) -> str:
    """线性混合两个十六进制颜色，t=0 取 a，t=1 取 b。"""
    ca, cb = _c(a), _c(b)
    r = round(ca.red() + (cb.red() - ca.red()) * t)
    g = round(ca.green() + (cb.green() - ca.green()) * t)
    bl = round(ca.blue() + (cb.blue() - ca.blue()) * t)
    return "#%02x%02x%02x" % (r, g, bl)


def rgba(hex_color: str, alpha: float) -> str:
    c = _c(hex_color)
    return "rgba(%d, %d, %d, %.3f)" % (c.red(), c.green(), c.blue(), max(0.0, min(1.0, alpha)))


def readable_theme(key: str) -> str:
    return key if key in THEMES else DEFAULT_THEME


def readable_accent(key: str) -> str:
    return key if key in ACCENTS else DEFAULT_ACCENT


def _nudge_for_dark(hex_color: str) -> str:
    """自定义颜色在深色主题上稍微提亮，保证对比度。"""
    return mix(hex_color, "#ffffff", 0.18)


def is_dark(theme_key: str) -> bool:
    return bool(THEMES[readable_theme(theme_key)]["dark"])


# ---------------------------------------------------------------- 令牌解析

def resolve_tokens(theme_key: str = DEFAULT_THEME,
                   accent_key: str = DEFAULT_ACCENT,
                   font_scale: str = DEFAULT_FONT_SCALE,
                   custom_accent: str = "") -> dict:
    """把（主题, 强调色, 字号档位）解析成一份完整的样式令牌。"""
    theme_key = readable_theme(theme_key)
    base = dict(THEMES[theme_key])
    scale = FONT_SCALES.get(font_scale, FONT_SCALES[DEFAULT_FONT_SCALE])[1]
    dark = bool(base["dark"])

    if accent_key == "custom" and custom_accent:
        accent = _nudge_for_dark(custom_accent) if dark else custom_accent
    else:
        accent_key = readable_accent(accent_key)
        accent = ACCENTS[accent_key]["dark" if dark else "light"]
    surface = base["surface"]
    canvas = base["canvas"]

    base["accent"] = accent
    base["accent_hover"] = mix(accent, "#000000" if not dark else "#ffffff", 0.12)
    base["accent_press"] = mix(accent, "#000000" if not dark else "#ffffff", 0.22)
    base["accent_soft"] = mix(accent, surface, 0.88 if not dark else 0.82)
    base["accent_line"] = mix(accent, surface, 0.55 if not dark else 0.35)
    base["ring"] = rgba(accent, 0.28)
    base["canvas"] = canvas
    base["font_scale"] = scale

    for key, size in _BASE_FONT.items():
        base["fs_" + key] = round(size * scale, 2)

    base["radius_card"] = 12
    base["radius_field"] = 6
    base["radius_input"] = 6
    base["radius_chip"] = 6
    base["radius_pill"] = 999

    base["on_accent"] = "#ffffff" if _luma(accent) < 0.62 else "#0b1220"
    base["shadow"] = "0 1px 3px rgba(15, 23, 42, 0.04)"
    return base


def _luma(hex_color: str) -> float:
    c = _c(hex_color)
    return (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255.0


# ---------------------------------------------------------------- 样式表

_TOKEN_RE = re.compile(r"@\{(\w+)\}")


def build_stylesheet(tokens: dict, family: str = "") -> str:
    t = tokens
    qss = """
* { outline: 0; }

QWidget {
    color: @{text};
    font-family: "%(font_family)s";
    font-size: @{fs_body}pt;
}
QMainWindow, QDialog { background: @{canvas}; }
QWidget#Canvas { background: @{canvas}; }
QWidget#Header { background: @{surface}; border-bottom: 1px solid @{border}; }
QWidget#Footer { background: @{surface}; border-top: 1px solid @{border}; }

QLabel#PageTitle { font-size: @{fs_page}pt; font-weight: 600; color: @{text}; }
QLabel#CardTitle { font-size: @{fs_title}pt; font-weight: 600; color: @{text}; }
QLabel#FieldLabel { font-size: @{fs_body}pt; color: @{text2}; }
QLabel#Caption { font-size: @{fs_caption}pt; color: @{text3}; }
QLabel#Metric { font-size: @{fs_metric}pt; font-weight: 600; color: @{text}; }
QLabel#MetricSoft { font-size: @{fs_body}pt; font-weight: 600; color: @{text2}; }
QLabel#Hint { font-size: @{fs_caption}pt; color: @{text3}; }
QLabel#Danger { color: @{danger}; font-size: @{fs_caption}pt; }

QFrame#Card {
    background: @{surface};
    border: 1px solid @{border};
    border-radius: @{radius_card}px;
}
QFrame#Card[active="true"] { border-color: @{accent_line}; }
QFrame#Divider { background: @{border}; max-height: 1px; min-height: 1px; border: none; }
QFrame#VDivider { background: @{border}; max-width: 1px; min-width: 1px; border: none; }

/* ---------------- 按钮 ---------------- */
QPushButton {
    background: @{surface};
    color: @{text};
    border: 1px solid @{border};
    border-radius: @{radius_field}px;
    padding: 6px 14px;
    min-height: 18px;
}
QPushButton:hover { background: @{subtle}; border-color: @{border_strong}; }
QPushButton:pressed { background: @{sunken}; }
QPushButton:focus { border-color: @{accent}; }
QPushButton:disabled { color: @{text_disabled}; border-color: @{border_soft}; }

QPushButton[variant="primary"] {
    background: @{accent}; color: @{on_accent}; border: 1px solid @{accent};
}
QPushButton[variant="primary"]:hover { background: @{accent_hover}; border-color: @{accent_hover}; }
QPushButton[variant="primary"]:pressed { background: @{accent_press}; }
QPushButton[variant="primary"]:disabled { background: @{accent_soft}; border-color: @{accent_soft}; color: @{text3}; }

QPushButton[variant="ghost"] {
    background: transparent; border: 1px solid transparent; color: @{text2}; padding: 5px 10px;
}
QPushButton[variant="ghost"]:hover { background: @{subtle}; color: @{text}; }
QPushButton[variant="ghost"]:pressed { background: @{sunken}; }

QPushButton[variant="link"] {
    background: transparent; border: none; color: @{accent}; padding: 2px 4px;
}
QPushButton[variant="link"]:hover { color: @{accent_hover}; text-decoration: underline; }

QPushButton[variant="chip"] {
    background: @{subtle}; border: 1px solid transparent; color: @{text2};
    border-radius: @{radius_chip}px; padding: 3px 10px; font-size: @{fs_caption}pt;
}
QPushButton[variant="chip"]:hover { background: @{sunken}; color: @{text}; }
QPushButton[variant="chip"]:checked {
    background: @{accent_soft}; border-color: @{accent_line}; color: @{accent};
}

QPushButton#Quiet {
    background: transparent; border: 1px solid transparent; color: @{text3}; padding: 2px 6px;
}
QPushButton#Quiet:hover { background: @{subtle}; color: @{text}; border-radius: @{radius_field}px; }

/* ---------------- 输入 ---------------- */
QComboBox, QLineEdit {
    background: @{surface};
    color: @{text};
    border: 1px solid @{border};
    border-radius: @{radius_field}px;
    padding: 5px 10px;
    min-height: 18px;
    selection-background-color: @{accent}; selection-color: @{on_accent};
}
QComboBox:hover, QLineEdit:hover { border-color: @{border_strong}; }
QComboBox:focus, QLineEdit:focus { border-color: @{accent}; }
QComboBox:disabled, QLineEdit:disabled { color: @{text_disabled}; background: @{subtle}; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; width: 0; height: 0; }
QComboBox QAbstractItemView {
    background: @{surface};
    border: 1px solid @{border};
    border-radius: 8px;
    padding: 4px;
    color: @{text};
    selection-background-color: @{accent_soft};
    selection-color: @{accent};
    outline: none;
}
QComboBox QAbstractItemView::item { min-height: 22px; padding: 2px 8px; border-radius: 5px; }

QFrame#NumberField {
    background: @{surface};
    border: 1px solid @{border};
    border-radius: @{radius_field}px;
}
QFrame#NumberField:hover { border-color: @{border_strong}; }
QFrame#NumberField QSpinBox {
    background: transparent; border: none; padding: 0;
    font-size: @{fs_body}pt; font-weight: 600; color: @{text};
    selection-background-color: @{accent}; selection-color: @{on_accent};
}
QFrame#NumberField QSpinBox::up-button, QFrame#NumberField QSpinBox::down-button { width: 0; border: none; }
QFrame#NumberField QPushButton {
    background: transparent; border: none; color: @{text3};
    border-radius: 4px; padding: 0px; min-width: 20px; max-width: 20px; min-height: 20px; max-height: 20px;
    font-size: 12pt;
}
QFrame#NumberField QPushButton:hover { background: @{subtle}; color: @{text}; }

/* ---------------- 滚动条 ---------------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @{border_strong}; border-radius: 3px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: @{text3}; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: @{border_strong}; border-radius: 3px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ---------------- 滑杆 ---------------- */
QSlider { min-height: 20px; }
QSlider::groove:horizontal { height: 4px; background: @{sunken}; border-radius: 2px; }
QSlider::sub-page:horizontal { background: @{accent}; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 13px; height: 13px; margin: -5px 0; border-radius: 7px;
    background: @{surface}; border: 1px solid @{border_strong};
}
QSlider::handle:horizontal:hover { border-color: @{accent}; }

/* ---------------- 菜单 / 提示 ---------------- */
QMenu {
    background: @{surface}; border: 1px solid @{border}; border-radius: 8px; padding: 5px;
}
QMenu::item { padding: 6px 22px 6px 12px; border-radius: 6px; color: @{text}; }
QMenu::item:selected { background: @{subtle}; }
QMenu::item:disabled { color: @{text_disabled}; }
QMenu::separator { height: 1px; background: @{border}; margin: 5px 8px; }

QToolTip {
    background: @{surface}; color: @{text};
    border: 1px solid @{border}; border-radius: 6px; padding: 5px 9px;
    font-size: @{fs_caption}pt;
}

QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

QGroupBox { border: none; margin: 0; padding: 0; }

/* ---------------- 分段控件 ---------------- */
QWidget#Segmented {
    background: @{subtle};
    border: 1px solid @{border};
    border-radius: @{radius_field}px;
}
QWidget#Segmented QPushButton {
    background: transparent; border: 1px solid transparent; border-radius: 5px;
    color: @{text2}; padding: 4px 12px; font-size: @{fs_caption}pt;
}
QWidget#Segmented QPushButton:hover { color: @{text}; }
QWidget#Segmented QPushButton:checked {
    background: @{surface}; color: @{text};
    border: 1px solid @{border};
}
    """ % {"font_family": family or FONT_FAMILY}

    def sub(match: re.Match) -> str:
        key = match.group(1)
        value = t.get(key)
        return str(value) if value is not None else ""

    return _TOKEN_RE.sub(sub, qss)


def build_palette(tokens: dict) -> QPalette:
    pal = QPalette()
    base = QColor(tokens["surface"])
    text = QColor(tokens["text"])
    pal.setColor(QPalette.Window, QColor(tokens["canvas"]))
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, base)
    pal.setColor(QPalette.AlternateBase, QColor(tokens["subtle"]))
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, QColor(tokens["surface"]))
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.Highlight, QColor(tokens["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor(tokens["on_accent"]))
    pal.setColor(QPalette.ToolTipBase, base)
    pal.setColor(QPalette.ToolTipText, text)
    pal.setColor(QPalette.PlaceholderText, QColor(tokens["text3"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(tokens["text_disabled"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(tokens["text_disabled"]))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(tokens["text_disabled"]))
    return pal


def app_font(tokens: dict, family: str = "") -> QFont:
    font = QFont(family or FONT_FAMILY)
    font.setStyleHint(QFont.SansSerif)
    font.setPointSizeF(tokens["fs_body"])
    font.setHintingPreference(QFont.PreferFullHinting)
    return font


def apply_theme(app, theme_key: str, accent_key: str, font_scale: str,
                family: str = "", custom_accent: str = "") -> dict:
    """把主题应用到 QApplication，返回解析出的令牌（界面各处自行取色时用）。"""
    tokens = resolve_tokens(theme_key, accent_key, font_scale, custom_accent)
    app.setStyle("Fusion")
    app.setPalette(build_palette(tokens))
    app.setFont(app_font(tokens, family))
    app.setStyleSheet(build_stylesheet(tokens, family))
    return tokens
