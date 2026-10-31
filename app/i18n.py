"""极简 i18n：中文是源码里的原始文案，英文查表替换。

用法：
    from .i18n import tr
    label = tr("间隔")                 # zh 原样返回，en 查表
    text = tr("已保存 %s") % stamp     # 带占位符的先翻译再格式化
"""
from __future__ import annotations

from typing import Dict

FALLBACK = "zh"
SUPPORTED = ("zh", "en")

_lang = FALLBACK

try:  # 英文表由 _strings_en.json 生成，缺失也不影响中文运行
    from .i18n_en import EN as _EN  # type: ignore
except Exception:  # pragma: no cover
    _EN: Dict[str, str] = {}


def set_language(language: str) -> str:
    global _lang
    value = (language or "").strip().lower()
    if value.startswith("en"):
        _lang = "en"
    elif value.startswith("zh"):
        _lang = "zh"
    else:
        _lang = FALLBACK
    return _lang


def language() -> str:
    return _lang


def is_english() -> bool:
    return _lang == "en"


def tr(text: str) -> str:
    """把中文文案翻成当前语言；没翻译就原样返回。"""
    if _lang == "zh" or not text:
        return text
    return _EN.get(text, text)


def tr_all(seq):
    return [tr(item) for item in seq]
