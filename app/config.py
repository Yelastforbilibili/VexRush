"""配置模型与持久化。

设计要点：
* 配置文件固定在 exe 同目录（便携）。目录不可写时回退到 %APPDATA%\\VexRush。
* 任何改动立即写盘（调用方做 250ms 防抖），关闭窗口时再无条件写一次。
* 支持导出 / 导入 / 恢复默认，且导入会校验与夹紧数值。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from . import theme as theme_mod
from .i18n import tr

APP_NAME = "VexRush"
APP_ID = "VexRush.Clicker.1"
GITHUB_URL = "https://github.com/Yelastforbilibili/VexRush"
APP_VERSION = "3.2.0"
CONFIG_NAME = "config.json"
CONFIG_VERSION = 2

INTERVAL_MIN = 1
INTERVAL_MAX = 2000
CHANNEL_COUNT = 2

MOUSE_BUTTONS = (("left", "left_button"), ("right", "right_button"), ("middle", "middle_button"))

DEFAULT_OVERLAY_TITLE = "VexRush"


def default_channel_name(index: int) -> str:
    return tr("click") % (index + 1)


def display_channel_name(index: int, name: str) -> str:
    """没改过名的通道跟随界面语言显示，改过名的原样显示。"""
    plain = "连点%d" % (index + 1)
    return (tr("click") % (index + 1)) if (name or plain) == plain else name


def _clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def _clamp_float(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def _pick(value: Any, allowed, fallback):
    return value if value in allowed else fallback


def _color(value: Any, fallback: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        if len(text) == 7 and text.startswith("#"):
            try:
                int(text[1:], 16)
                return text.lower()
            except ValueError:
                pass
    return fallback


# ---------------------------------------------------------------- 路径

def app_dir() -> str:
    """程序所在目录（打包后是 exe 目录，源码运行时是项目根）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _dir_writable(path: str) -> bool:
    probe = os.path.join(path, ".write_test")
    try:
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def data_dir() -> str:
    """用户数据目录：%APPDATA%\\VexRush（配置、语言文件都放这里）。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    target = os.path.join(base, APP_NAME) if APP_NAME == "VexRush" else os.path.join(base, "VexRush")
    try:
        os.makedirs(target, exist_ok=True)
    except OSError:
        pass
    return target


def lang_dir() -> str:
    """语言文件目录：<数据目录>\\lang。"""
    target = os.path.join(data_dir(), "lang")
    try:
        os.makedirs(target, exist_ok=True)
    except OSError:
        pass
    return target


def config_path() -> str:
    """配置文件固定在数据目录里；老版本放在 exe 旁边，首次运行时搬过去。"""
    target = os.path.join(data_dir(), CONFIG_NAME)
    legacy = os.path.join(app_dir(), CONFIG_NAME)
    if not os.path.exists(target) and os.path.exists(legacy):
        try:
            with open(legacy, "rb") as source, open(target, "wb") as sink:
                sink.write(source.read())
        except OSError:
            pass
    return target


# ---------------------------------------------------------------- 通道

@dataclass
class ChannelConfig:
    name: str = ""                   # 空表示用默认名「连点N」
    interval_ms: int = 15
    trigger_kind: str = "mouse"      # mouse | key
    trigger_mouse: str = "left"
    trigger_key: str = ""
    sim_mouse: str = "left"
    hotkey: str = "f1"
    enabled: bool = False

    def normalize(self, index: int) -> "ChannelConfig":
        from .winapi import canon_key      # 惰性导入：config 与 winapi 互相引用

        self.name = (str(self.name or "").strip()[:8]) or default_channel_name(index)
        self.interval_ms = _clamp_int(self.interval_ms, INTERVAL_MIN, INTERVAL_MAX, 15)
        self.trigger_kind = _pick(self.trigger_kind, {"mouse", "key"}, "mouse")
        self.trigger_mouse = _pick(self.trigger_mouse, {b for b, _ in MOUSE_BUTTONS}, "left")
        self.sim_mouse = _pick(self.sim_mouse, {b for b, _ in MOUSE_BUTTONS},
                               "left" if index == 0 else "right")
        self.trigger_key = str(self.trigger_key or "").strip().lower()[:24]
        if self.trigger_kind == "key" and not self.trigger_key:
            self.trigger_kind = "mouse"
        if not self.trigger_key:
            self.trigger_kind = "mouse"
        self.hotkey = canon_key(str(self.hotkey or "")[:24]) or ("f1" if index == 0 else "f2")
        self.trigger_key = canon_key(str(self.trigger_key or ""))
        self.enabled = bool(self.enabled)
        return self

    def trigger_spec(self) -> str:
        if self.trigger_kind == "key" and self.trigger_key:
            return "k:" + self.trigger_key
        return "m:" + self.trigger_mouse

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any, index: int) -> "ChannelConfig":
        item = cls()
        if isinstance(data, dict):
            item.name = data.get("name", item.name)
            item.interval_ms = data.get("interval_ms", item.interval_ms)
            item.trigger_kind = data.get("trigger_kind", item.trigger_kind)
            item.trigger_mouse = data.get("trigger_mouse", item.trigger_mouse)
            item.trigger_key = data.get("trigger_key", item.trigger_key)
            item.sim_mouse = data.get("sim_mouse", item.sim_mouse)
            item.hotkey = data.get("hotkey", item.hotkey)
            item.enabled = data.get("enabled", item.enabled)
        item.sim_mouse = item.sim_mouse or ("left" if index == 0 else "right")
        return item.normalize(index)


def default_channels() -> List[ChannelConfig]:
    first = ChannelConfig(name="连点1", trigger_mouse="left", sim_mouse="left", hotkey="f1")
    second = ChannelConfig(name="连点2", trigger_mouse="right", sim_mouse="right", hotkey="f2")
    return [first, second]


# ---------------------------------------------------------------- 外观

LANGUAGES = {"zh_cn": "简体中文", "en_us": "English"}  # 仅作默认值，实际列表来自语言包

# 悬浮窗入场/出场动画可选值
OVERLAY_ANIM_ITEMS = (("fade", "fade"), ("scale", "scale"), ("slide", "slide"),
                      ("spring", "spring"), ("blur", "blur"), ("none", "none"))
OVERLAY_ANIMS = {key for key, _label in OVERLAY_ANIM_ITEMS}


@dataclass
class AppearanceConfig:
    theme: str = theme_mod.DEFAULT_THEME
    accent: str = theme_mod.DEFAULT_ACCENT
    custom_accent: str = "#3b82f6"
    font_scale: str = theme_mod.DEFAULT_FONT_SCALE
    font_family: str = "builtin"
    language: str = "zh"

    def normalize(self) -> "AppearanceConfig":
        accents = set(theme_mod.ACCENTS) | {"custom"}
        self.theme = _pick(self.theme, set(theme_mod.THEMES), theme_mod.DEFAULT_THEME)
        self.accent = _pick(self.accent, accents, theme_mod.DEFAULT_ACCENT)
        self.font_scale = _pick(self.font_scale, set(theme_mod.FONT_SCALES), theme_mod.DEFAULT_FONT_SCALE)
        self.language = str(self.language or "").strip() or "zh_cn"
        color = str(self.custom_accent or "").strip()
        if len(color) == 7 and color.startswith("#"):
            try:
                int(color[1:], 16)
            except ValueError:
                color = "#3b82f6"
        else:
            color = "#3b82f6"
        self.custom_accent = color.lower()
        self.font_family = str(self.font_family or "builtin").strip() or "builtin"
        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "AppearanceConfig":
        item = cls()
        if isinstance(data, dict):
            item.theme = data.get("theme", item.theme)
            item.accent = data.get("accent", item.accent)
            item.custom_accent = data.get("custom_accent", item.custom_accent)
            item.font_scale = data.get("font_scale", item.font_scale)
            item.font_family = data.get("font_family", item.font_family)
            item.language = data.get("language", item.language)
        return item.normalize()


# ---------------------------------------------------------------- 悬浮显示

@dataclass
class OverlayConfig:
    enabled: bool = False
    locked: bool = False
    click_through: bool = False
    layout: str = "v"              # v | h
    show_state: bool = True
    show_cps: bool = True
    show_count: bool = False
    show_interval: bool = False
    show_title: bool = True
    title_text: str = DEFAULT_OVERLAY_TITLE
    scale: int = 100               # 文本缩放百分比
    opacity: int = 100             # 整体不透明度百分比（影响文字与背景）
    bg_opacity: int = 92           # 背景不透明度百分比
    radius: int = 10
    padding: int = 10
    gap: int = 6
    bg_color: str = "#0d1420"
    fg_color: str = "#e9eff8"
    off_opacity: int = 45          # 未开启时文字的不透明度
    accent_mode: str = "theme"     # theme | channel | custom
    custom_accent: str = "#3b82f6"
    rainbow: bool = True
    rainbow_speed: int = 45        # 色相每步耗时 ms
    animation: str = "fade"        # 状态变化的过渡：fade | slide | pulse | none
    anim_in: str = "fade"          # 入场动画
    anim_out: str = "fade"         # 出场动画
    drag_smooth: bool = True       # 拖动时插值跟手
    drag_ease: int = 22            # 跟手速度（越大越贴手）
    drag_inertia: bool = True      # 松手后带一点惯性滑行
    pos: str = ""                  # "x,y"，空则用默认位置

    def normalize(self) -> "OverlayConfig":
        self.enabled = bool(self.enabled)
        self.locked = bool(self.locked)
        self.click_through = bool(self.click_through)
        self.layout = _pick(self.layout, {"v", "h"}, "v")
        self.show_state = bool(self.show_state)
        self.show_cps = bool(self.show_cps)
        self.show_count = bool(self.show_count)
        self.show_interval = bool(self.show_interval)
        self.show_title = bool(self.show_title)
        self.title_text = (str(self.title_text or "").strip()[:12]) or DEFAULT_OVERLAY_TITLE
        self.scale = _clamp_int(self.scale, 70, 200, 100)
        self.opacity = _clamp_int(self.opacity, 25, 100, 100)
        self.bg_opacity = _clamp_int(self.bg_opacity, 0, 100, 92)
        self.radius = _clamp_int(self.radius, 0, 24, 10)
        self.padding = _clamp_int(self.padding, 4, 28, 10)
        self.gap = _clamp_int(self.gap, 0, 24, 6)
        self.bg_color = _color(self.bg_color, "#0d1420")
        self.fg_color = _color(self.fg_color, "#e9eff8")
        self.off_opacity = _clamp_int(self.off_opacity, 10, 100, 45)
        self.accent_mode = _pick(self.accent_mode, {"theme", "channel", "custom"}, "theme")
        self.custom_accent = _color(self.custom_accent, "#3b82f6")
        self.rainbow = bool(self.rainbow)
        self.rainbow_speed = _clamp_int(self.rainbow_speed, 16, 200, 45)
        self.animation = _pick(self.animation, {"fade", "slide", "pulse", "none"}, "fade")
        self.anim_in = _pick(self.anim_in, OVERLAY_ANIMS, "fade")
        self.anim_out = _pick(self.anim_out, OVERLAY_ANIMS, "fade")
        self.drag_smooth = bool(self.drag_smooth)
        self.drag_ease = _clamp_int(self.drag_ease, 6, 60, 22)
        self.drag_inertia = bool(self.drag_inertia)
        if not isinstance(self.pos, str):
            self.pos = ""
        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "OverlayConfig":
        item = cls()
        if isinstance(data, dict):
            for field_name in item.to_dict().keys():
                if field_name in data:
                    setattr(item, field_name, data[field_name])
        return item.normalize()


# ---------------------------------------------------------------- 顶层配置

@dataclass
class AppConfig:
    target_process: str = ""
    send_mode: str = "post"        # post | send
    auto_detect: bool = True
    exclusive: bool = False        # 防卡手：同一时间只允许一路开启
    restore_previous: bool = True  # 防卡手：关闭后恢复上一路
    ignore_ime: bool = True        # 在输入框里打字时不响应热键与键盘触发
    smooth_window: bool = True     # 拖动边框/标题栏时窗口缓动跟随鼠标
    appearance: AppearanceConfig = field(default_factory=AppearanceConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    channels: List[ChannelConfig] = field(default_factory=default_channels)
    geometry: str = ""
    # 每路两个折叠区：[高级, 速率]
    expanded: List[List[bool]] = field(default_factory=lambda: [[False, False] for _ in range(CHANNEL_COUNT)])

    def normalize(self) -> "AppConfig":
        self.target_process = str(self.target_process or "").strip()[:80]
        self.send_mode = _pick(self.send_mode, {"post", "send"}, "post")
        self.auto_detect = bool(self.auto_detect)
        self.exclusive = bool(self.exclusive)
        self.restore_previous = bool(self.restore_previous)
        self.ignore_ime = bool(self.ignore_ime)
        self.smooth_window = bool(self.smooth_window)
        self.appearance = (self.appearance or AppearanceConfig()).normalize()
        self.overlay = (self.overlay or OverlayConfig()).normalize()
        channels = list(self.channels or [])
        while len(channels) < CHANNEL_COUNT:
            channels.append(ChannelConfig())
        self.channels = [channels[i].normalize(i) for i in range(CHANNEL_COUNT)]
        raw_expanded = list(self.expanded or [])
        expanded: List[List[bool]] = []
        for index in range(CHANNEL_COUNT):
            item = raw_expanded[index] if index < len(raw_expanded) else None
            if isinstance(item, (list, tuple)):
                pair = [bool(item[0]), bool(item[1])] if len(item) >= 2 else [bool(item[0]) if item else False, False]
            else:
                pair = [bool(item), False]
            expanded.append(pair)
        self.expanded = expanded
        self.geometry = str(self.geometry or "")
        return self

    @property
    def appearance_key(self) -> tuple:
        return (self.appearance.theme, self.appearance.accent, self.appearance.font_scale)

    def to_dict(self) -> dict:
        return {
            "version": CONFIG_VERSION,
            "app": APP_ID,
            "target_process": self.target_process,
            "send_mode": self.send_mode,
            "auto_detect": self.auto_detect,
            "exclusive": self.exclusive,
            "restore_previous": self.restore_previous,
            "ignore_ime": self.ignore_ime,
            "smooth_window": self.smooth_window,
            "appearance": self.appearance.to_dict(),
            "overlay": self.overlay.to_dict(),
            "channels": [channel.to_dict() for channel in self.channels],
            "geometry": self.geometry,
            "expanded": [list(pair) for pair in self.expanded],
        }

    @classmethod
    def from_dict(cls, data: Any) -> "AppConfig":
        item = cls()
        if not isinstance(data, dict):
            return item.normalize()
        item.target_process = data.get("target_process", item.target_process)
        item.send_mode = data.get("send_mode", item.send_mode)
        item.auto_detect = data.get("auto_detect", item.auto_detect)
        item.exclusive = data.get("exclusive", item.exclusive)
        item.restore_previous = data.get("restore_previous", item.restore_previous)
        item.ignore_ime = data.get("ignore_ime", item.ignore_ime)
        item.smooth_window = data.get("smooth_window", item.smooth_window)
        item.appearance = AppearanceConfig.from_dict(data.get("appearance"))
        item.overlay = OverlayConfig.from_dict(data.get("overlay"))
        item.geometry = data.get("geometry", item.geometry)
        item.expanded = data.get("expanded", item.expanded) or [[False, False] for _ in range(CHANNEL_COUNT)]

        # v1 兼容：panels.left / panels.right
        if isinstance(data.get("panels"), dict):
            panels = data["panels"]
            item.channels = [ChannelConfig.from_dict(panels.get("left"), 0),
                             ChannelConfig.from_dict(panels.get("right"), 1)]
        else:
            raw_channels = data.get("channels")
            if isinstance(raw_channels, list) and raw_channels:
                item.channels = [ChannelConfig.from_dict(raw_channels[i] if i < len(raw_channels) else None, i)
                                 for i in range(CHANNEL_COUNT)]
            else:
                item.channels = default_channels()
        # v1 没有 appearance / overlay，用默认值；theme 若为旧 dark 值也兼容
        return item.normalize()


# ---------------------------------------------------------------- 读写

class ConfigError(Exception):
    pass


def load_config(path: Optional[str] = None) -> AppConfig:
    target = path or config_path()
    try:
        with open(target, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return AppConfig().normalize()
    except (OSError, json.JSONDecodeError):
        return AppConfig().normalize()
    return AppConfig.from_dict(raw)


def save_config(cfg: AppConfig, path: Optional[str] = None) -> str:
    """原子写配置文件，返回写入的完整路径。"""
    target = path or config_path()
    folder = os.path.dirname(target) or "."
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        pass
    payload = json.dumps(cfg.normalize().to_dict(), ensure_ascii=False, indent=2)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder, prefix=".cfg-",
                                         suffix=".tmp", delete=False)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, target)
    except OSError as exc:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise ConfigError(tr("cannot_write_config_file") % exc) from exc
    return target


def export_config(cfg: AppConfig, target: str) -> str:
    return save_config(cfg, target)


def import_config(source: str) -> AppConfig:
    try:
        with open(source, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(tr("cannot_parse_config_file") % exc) from exc
    if not isinstance(raw, dict):
        raise ConfigError(tr("invalid_config_file_format"))
    if "channels" not in raw and "panels" not in raw:
        raise ConfigError(tr("this_is_not_a_vexrush_config_file"))
    return AppConfig.from_dict(raw)


def reset_config() -> AppConfig:
    return AppConfig().normalize()


def copy_into(dst: AppConfig, src: AppConfig) -> AppConfig:
    """把 src 的字段就地复制进 dst（保持子对象身份不变，便于界面/悬浮窗持有引用）。"""
    dst.target_process = src.target_process
    dst.send_mode = src.send_mode
    dst.auto_detect = src.auto_detect
    dst.exclusive = src.exclusive
    dst.restore_previous = src.restore_previous
    dst.ignore_ime = src.ignore_ime
    dst.smooth_window = src.smooth_window
    dst.geometry = src.geometry
    dst.expanded = [list(pair) for pair in src.expanded]

    for name, value in asdict(src.appearance).items():
        setattr(dst.appearance, name, value)
    for name, value in asdict(src.overlay).items():
        setattr(dst.overlay, name, value)
    while len(dst.channels) < CHANNEL_COUNT:
        dst.channels.append(ChannelConfig())
    for index in range(CHANNEL_COUNT):
        source = src.channels[index]
        target = dst.channels[index]
        for name, value in asdict(source).items():
            setattr(target, name, value)
    return dst.normalize()
