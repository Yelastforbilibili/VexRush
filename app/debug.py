"""极小的调试日志：只有设置了环境变量 VEXRUSH_DEBUG 才写文件。

排查线上问题时用，正常运行时一个字节都不写。
"""
from __future__ import annotations

import os
import time

_PATH = os.environ.get("VEXRUSH_DEBUG", "")
_HANDLE = None


def enabled() -> bool:
    return bool(_PATH)


def log(channel: str, text: str) -> None:
    global _HANDLE
    if not _PATH:
        return
    try:
        if _HANDLE is None:
            _HANDLE = open(_PATH, "a", encoding="utf-8", buffering=1)
        _HANDLE.write("%.3f [%s] %s\n" % (time.perf_counter(), channel, text))
    except Exception:
        pass
