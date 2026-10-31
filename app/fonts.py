"""字体：内置寒蝉半圆体（ChillRound M，OFL 协议）+ 系统字体选择。

内置字体族名是 ``ChillRoundM``；配置里存的是语义值：
    ""            -> 跟随内置字体（内置字体没加载成功时回退到系统默认）
    "builtin"     -> 同上
    "sys:<族名>"  -> 用系统里的某个字体族
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Tuple

from PyQt5.QtGui import QFontDatabase
from .i18n import tr

FALLBACK_FAMILY = "Microsoft YaHei UI"
BUILTIN_KEY = "builtin"
SYSTEM_PREFIX = "sys:"

# (内部名, 文件名) —— 打包时这些文件必须一起带上
BUNDLED_FILES: Tuple[Tuple[str, str], ...] = (
    ("builtin", "ChillRoundM.otf"),
)

_state: Dict[str, object] = {"loaded": False, "families": {}}


def asset_dir(*parts: str) -> str:
    """资源目录（兼容 PyInstaller 解包目录与源码目录）。"""
    base = getattr(sys, "_MEIPASS", None)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if base:
        candidate = os.path.join(base, "assets", *parts)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(root, "assets", *parts)


def _gui_ready() -> bool:
    """QFontDatabase 必须有 QGuiApplication 才能用，否则会直接崩（0xC0000005）。"""
    try:
        from PyQt5.QtGui import QGuiApplication
    except Exception:
        return False
    return QGuiApplication.instance() is not None


def load_bundled() -> Dict[str, str]:
    """把内置字体注册进 Qt，返回 {内部名: 实际族名}。"""
    if not _gui_ready():
        return {}
    if _state["loaded"]:
        return dict(_state["families"])  # type: ignore[arg-type]
    families: Dict[str, str] = {}
    folder = asset_dir("fonts")
    for key, filename in BUNDLED_FILES:
        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            continue
        try:
            font_id = QFontDatabase.addApplicationFont(path)
            names = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if names:
                families[key] = names[0]
        except Exception:
            continue
    _state["loaded"] = True
    _state["families"] = families
    return dict(families)


def builtin_family() -> str:
    return load_bundled().get("builtin", "")


def resolve_family(setting: str) -> str:
    """把配置里的字体设置解析成真正的字体族名。"""
    setting = (setting or "").strip()
    bundled = load_bundled()
    if not setting or setting == BUILTIN_KEY:
        return bundled.get("builtin") or FALLBACK_FAMILY
    if setting.startswith(SYSTEM_PREFIX):
        return setting[len(SYSTEM_PREFIX):].strip() or FALLBACK_FAMILY
    # 也允许直接写族名
    return setting


def display_name(setting: str) -> str:
    """设置项在界面上的显示名。"""
    setting = (setting or "").strip()
    bundled = load_bundled()
    if not setting or setting == BUILTIN_KEY:
        name = bundled.get("builtin")
        shown = tr("内置 · 寒蝉半圆体")
        return ("%s · %s" % (shown, name)) if name else tr("内置字体（未加载）")
    if setting.startswith(SYSTEM_PREFIX):
        return tr("系统 · %s") % setting[len(SYSTEM_PREFIX):]
    return setting


def system_families(limit: int = 400) -> List[str]:
    """系统可用字体族（去掉内置字体自己与纯符号字体）。"""
    db = QFontDatabase()
    bundled = set(load_bundled().values())
    out: List[str] = []
    for name in db.families():
        if name in bundled:
            continue
        if out.count(name):
            continue
        out.append(name)
        if len(out) >= limit:
            break
    return out
