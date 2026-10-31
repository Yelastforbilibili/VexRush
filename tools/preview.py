"""离屏渲染界面截图，用于视觉检查。

用法：
    python tools/preview.py --out shots/main.png
    python tools/preview.py --out shots/dark.png --theme dark --accent cyan
    python tools/preview.py --out shots/overlay.png --overlay --demo
    python tools/preview.py --out shots/settings.png --settings
"""
from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtCore import Qt, QTimer  # noqa: E402
from PyQt5.QtGui import QFont  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import main as entry  # noqa: E402
from app import config as cfg_mod  # noqa: E402
from app import theme as theme_mod  # noqa: E402


def build(args) -> tuple:
    entry.enable_high_dpi()
    app = QApplication(sys.argv[:1])
    app.setFont(QFont(theme_mod.FONT_FAMILY, 10))

    cfg = cfg_mod.AppConfig().normalize()
    cfg.appearance.theme = args.theme
    cfg.appearance.accent = args.accent
    cfg.appearance.font_scale = args.font
    cfg.target_process = "javaw.exe"
    cfg.send_mode = args.mode
    cfg.channels[0].enabled = args.demo
    cfg.channels[0].interval_ms = 15
    cfg.channels[1].interval_ms = 20
    if args.demo:
        cfg.channels[1].trigger_kind = "key"
        cfg.channels[1].trigger_key = "f6"
    if args.expand:
        for pair in cfg.expanded:
            pair[0] = True
            pair[1] = True
    cfg.overlay.enabled = bool(args.overlay)

    from app.mainwindow import MainWindow
    window = MainWindow(cfg)
    window.resize(args.size[0], args.size[1])
    window.show()
    return app, window


def fake_stats(window) -> None:
    """伪造一段“正在连点”的数据，让截图有内容。"""
    for card in window._card_widgets:      # noqa: SLF001
        channel = card.channel
        channel.worker.clicks = 1284 if card.index == 0 else 842
        channel._cps = 66.4 if card.index == 0 else 49.8      # noqa: SLF001
        channel._last_count = channel.worker.clicks          # noqa: SLF001
        card.lbl_count.setText("已连点 {:,} 次".format(channel.worker.clicks))
        card.lbl_live.setText("%.1f 次/秒" % channel._cps)    # noqa: SLF001
        for step in range(56):
            value = 60.0 + 10.0 * ((step // 7) % 3) if card.index == 0 else 44.0 + 8.0 * ((step // 9) % 2)
            card.spark.push(value, 80.0)
    if window.cfg.overlay.enabled:
        rows = [{
            "title": window.cfg.channels[0].name, "enabled": True, "clicking": True,
            "cps": 66.4, "count": 1284, "interval": 15,
        }, {
            "title": window.cfg.channels[1].name, "enabled": True, "clicking": False,
            "cps": 0.0, "count": 842, "interval": 20,
        }]
        window.overlay.set_rows(rows)
        window.overlay.show()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--size", default="860x560")
    parser.add_argument("--theme", default="light")
    parser.add_argument("--accent", default="blue")
    parser.add_argument("--font", default="normal")
    parser.add_argument("--mode", default="post")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--expand", action="store_true")
    parser.add_argument("--overlay", action="store_true")
    parser.add_argument("--overlay-layout", default="v")
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--overlay-settings", action="store_true")
    parser.add_argument("--overlay-only", action="store_true")
    parser.add_argument("--lang", default="zh")
    args = parser.parse_args()
    import app.i18n as i18n_mod
    i18n_mod.set_language(args.lang)
    width, height = (int(part) for part in args.size.lower().split("x"))
    args.size = (width, height)

    app, window = build(args)
    window.cfg.overlay.layout = args.overlay_layout
    if args.overlay or args.overlay_only or args.overlay_settings:
        window.cfg.overlay.enabled = True
    if args.demo:
        fake_stats(window)
    app.processEvents()

    target = window
    if args.overlay_only:
        target = window.overlay
    if args.settings:
        dialog = window._ensure_settings()      # noqa: SLF001
        dialog.show()
        app.processEvents()
        target = dialog
    if args.overlay_settings:
        dialog = window._open_overlay_settings()      # noqa: SLF001
        window._overlay_settings.show()               # noqa: SLF001
        window._overlay_settings.raise_()             # noqa: SLF001
        app.processEvents()
        target = window._overlay_settings             # noqa: SLF001

    def shot() -> None:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        pixmap = target.grab()
        pixmap.save(args.out, "PNG")
        print("saved %s  %dx%d" % (args.out, pixmap.width(), pixmap.height()))
        app.quit()

    QTimer.singleShot(420, shot)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
