"""数字与文字的短小格式化工具（多个界面模块共用）。"""
from __future__ import annotations

from typing import Optional


def fmt(value: float, digits: int) -> str:
    if digits <= 0:
        return "{:,}".format(int(round(value)))
    return "{:,.{d}f}".format(float(value), d=digits)


def shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"
