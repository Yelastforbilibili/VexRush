# -*- coding: utf-8 -*-
"""把程序内的矢量图标导出成多尺寸 icon.ico（打包 exe 用）。

用法：python tools/make_icon.py [输出路径]
"""

import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice   # noqa: E402
from PyQt5.QtGui import QGuiApplication                   # noqa: E402

from app import icon as icon_mod                          # noqa: E402


def png_bytes(pixmap):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def build_ico(sizes):
    images = []
    for size in sizes:
        pixmap = icon_mod.icon_pixmap(size)
        images.append((size, png_bytes(pixmap)))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = []
    payload = b""
    for size, blob in images:
        entries.append(struct.pack("<BBBBHHII",
                                   0 if size >= 256 else size,
                                   0 if size >= 256 else size,
                                   0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
        payload += blob
    return header + b"".join(entries) + payload


def main(argv):
    app = QGuiApplication(argv[:1])          # noqa: F841  (QPainter 需要 QGuiApplication)
    out = argv[1] if len(argv) > 1 else os.path.join(ROOT, "icon.ico")
    sizes = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
    with open(out, "wb") as fh:
        fh.write(build_ico(sizes))
    print("saved %s（%d 字节，%d 个尺寸）" % (out, os.path.getsize(out), len(sizes)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
