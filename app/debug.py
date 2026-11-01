"""极小的诊断日志。

默认写到 ``%APPDATA%\\VexRush\\logs\\app.log``，单文件上限 512 KB，超了就滚动一份
``app.1.log``；只记状态变化与错误，正常运行每分钟也就几行。
设置环境变量 ``VEXRUSH_DEBUG`` 可以改写到别的文件（调试时用），设为 ``off`` 则完全关闭。

写入是**非阻塞**的：文本先进内存队列，由后台线程每 150 ms 落地一次。
键盘/鼠标钩子的回调里绝对不能做磁盘 I/O —— 回调超时会被 Windows 直接摘掉钩子。
"""
from __future__ import annotations

import collections
import os
import threading
import time

_MAX_BYTES = 512 * 1024
_FLUSH_MS = 150
_QUEUE_LIMIT = 4000

_PATH = ""
_RESOLVED = False
_HANDLE = None
_LOCK = threading.Lock()
_QUEUE = collections.deque()
_WRITER = None
_STOP = threading.Event()


def _default_path() -> str:
    folder = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                          "VexRush", "logs")
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        return ""
    return os.path.join(folder, "app.log")


def _resolve_path() -> str:
    override = (os.environ.get("VEXRUSH_DEBUG") or "").strip()
    if override.lower() in ("off", "0", "false"):
        return ""
    if override:
        return override
    return _default_path()


def _rotate(path: str) -> None:
    try:
        if os.path.getsize(path) < _MAX_BYTES:
            return
    except OSError:
        return
    try:
        backup = path + ".1"
        if os.path.exists(backup):
            os.unlink(backup)
        os.replace(path, backup)
    except Exception:
        pass


def path() -> str:
    global _PATH, _RESOLVED
    if not _RESOLVED:
        _PATH = _resolve_path()
        _RESOLVED = True
    return _PATH


def enabled() -> bool:
    return bool(path())


def _open() -> None:
    global _HANDLE
    target = path()
    if not target:
        return
    if _HANDLE is None:
        _rotate(target)
        _HANDLE = open(target, "a", encoding="utf-8", buffering=8192)


def _flush() -> None:
    global _HANDLE
    with _LOCK:
        pending = list(_QUEUE)
        _QUEUE.clear()
    if not pending:
        return
    try:
        _open()
        if _HANDLE is None:
            return
        _HANDLE.write("".join(pending))
        _HANDLE.flush()
    except Exception:
        pass


def _writer_loop() -> None:
    while not _STOP.wait(_FLUSH_MS / 1000.0):
        _flush()


def _ensure_writer() -> None:
    global _WRITER
    if _WRITER is not None and _WRITER.is_alive():
        return
    with _LOCK:
        if _WRITER is not None and _WRITER.is_alive():
            return
        _STOP.clear()
        _WRITER = threading.Thread(target=_writer_loop, name="debug-writer", daemon=True)
        _WRITER.start()


def log(channel: str, text: str) -> None:
    """记一行日志。只入内存队列，真正的写盘在后台线程里做。"""
    if not enabled():
        return
    line = "%s %.3f [%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                  time.perf_counter(), channel, text)
    with _LOCK:
        if len(_QUEUE) >= _QUEUE_LIMIT:
            return          # 队列爆了就丢，绝不阻塞调用方（钩子回调）
        _QUEUE.append(line)
    _ensure_writer()


def close() -> None:
    """退出前把队列落盘。"""
    _flush()
    _STOP.set()
