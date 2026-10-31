# -*- coding: utf-8 -*-
"""多语言：JSON 语言包（键是语义 ID，值是译文）。

查找顺序与 Minecraft 的做法一致：

* 内置语言包放在 ``assets/lang``（打包后在 ``sys._MEIPASS`` 里）；
* 用户语言包放在 ``<数据目录>/lang``，同名文件会覆盖内置的；
* 想加一门非官方语言，只要往那个目录扔一份 ``xxx.json`` 就行，键名照抄
  ``example.json``，``_name`` 写这门语言自己的名字。

``tr()`` 拿到 key 后：当前语言 → 回退语言（简体中文）→ key 本身。
"""
from __future__ import annotations

import io
import json
import os
import shutil
from typing import Dict, List, Tuple

FALLBACK = "zh_cn"
OFFICIAL = ("zh_cn", "en_us")
TEMPLATE = "example"
NAME_KEY = "_name"

_state: Dict[str, object] = {"code": FALLBACK, "tables": {}, "labels": {}, "loaded": False}


def _read(path: str) -> Dict[str, str]:
    try:
        with io.open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if isinstance(value, str)}


def builtin_dir() -> str:
    from . import fonts as fonts_mod

    return fonts_mod.asset_dir("lang")


def _scan(directory: str) -> List[Tuple[str, Dict[str, str]]]:
    found: List[Tuple[str, Dict[str, str]]] = []
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return found
    for name in names:
        if not name.lower().endswith(".json"):
            continue
        code = os.path.splitext(name)[0]
        table = _read(os.path.join(directory, name))
        if table:
            found.append((code, table))
    return found


def ensure_user_files() -> None:
    """把内置语言包复制到用户目录，方便照着改（不覆盖已存在的）。"""
    from . import config as cfg_mod

    target = cfg_mod.lang_dir()
    for code, _table in _scan(builtin_dir()):
        destination = os.path.join(target, code + ".json")
        if os.path.exists(destination):
            continue
        try:
            shutil.copyfile(os.path.join(builtin_dir(), code + ".json"), destination)
        except OSError:
            pass


def load() -> None:
    from . import config as cfg_mod

    tables: Dict[str, Dict[str, str]] = {}
    labels: Dict[str, str] = {}
    for code, table in _scan(builtin_dir()):
        tables[code] = table
        labels[code] = table.get(NAME_KEY, code)
    for code, table in _scan(cfg_mod.lang_dir()):
        merged = dict(tables.get(code, {}))
        merged.update(table)
        tables[code] = merged
        labels[code] = table.get(NAME_KEY, labels.get(code, code))
    _state["tables"] = tables
    _state["labels"] = labels
    _state["loaded"] = True
    if _state["code"] not in tables:
        _state["code"] = FALLBACK


def available() -> List[Tuple[str, str, bool]]:
    """[(code, 显示名, 是否官方)]，官方语言排在前面。"""
    if not _state["loaded"]:
        load()
    tables: Dict[str, Dict[str, str]] = _state["tables"]  # type: ignore[assignment]
    labels: Dict[str, str] = _state["labels"]  # type: ignore[assignment]
    rows: List[Tuple[str, str, bool]] = []
    for code in OFFICIAL:
        if code in tables:
            rows.append((code, labels.get(code, code), True))
    for code in sorted(tables):
        if code in OFFICIAL or code == TEMPLATE:
            continue
        rows.append((code, labels.get(code, code), False))
    if not rows:
        rows.append((FALLBACK, FALLBACK, True))
    return rows


def set_language(code: str) -> str:
    if not _state["loaded"]:
        load()
    tables: Dict[str, Dict[str, str]] = _state["tables"]  # type: ignore[assignment]
    value = str(code or "").strip()
    if value not in tables:
        load()
        tables = _state["tables"]  # type: ignore[assignment]
    if value in tables:
        _state["code"] = value
    elif FALLBACK in tables:
        _state["code"] = FALLBACK
    return str(_state["code"])


def language() -> str:
    return str(_state["code"])


def is_english() -> bool:
    return str(_state["code"]).lower().startswith("en")


def tr(key: str) -> str:
    """按当前语言翻译；查不到就退中文包，再退 key 本身。"""
    text = str(key)
    if not _state["loaded"]:
        load()
    tables: Dict[str, Dict[str, str]] = _state["tables"]  # type: ignore[assignment]
    current = tables.get(str(_state["code"])) or {}
    value = current.get(text)
    if value is not None:
        return value
    fallback = tables.get(FALLBACK) or {}
    value = fallback.get(text)
    if value is not None:
        return value
    return text


def tr_all(keys) -> List[str]:
    return [tr(key) for key in keys]


def prepare() -> None:
    """启动时调用一次：复制模板并加载语言包。"""
    ensure_user_files()
    load()
