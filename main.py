"""VexRush · 入口。

用法：
    python main.py              正常启动
    python main.py --multi      允许多开（调试用）
"""
from __future__ import annotations

import ctypes
import sys
from app.i18n import tr


def enable_high_dpi() -> None:
    """必须在 QApplication 之前调用，否则 175% 缩放下会糊。"""
    from PyQt5.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    try:
        from PyQt5.QtGui import QGuiApplication
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass


def _acquire_instance_lock():
    """单实例：返回互斥量句柄；已被占用时返回 None。"""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Local\\VexRush.SingleInstance")
        if not handle:
            return True
        if kernel32.GetLastError() == 183:      # ERROR_ALREADY_EXISTS
            return None
        return handle
    except Exception:
        return True


def main(argv=None) -> int:
    args = list(sys.argv if argv is None else argv)
    enable_high_dpi()

    from PyQt5.QtWidgets import QApplication, QMessageBox

    from app import config as cfg_mod
    from app import fonts as fonts_mod
    from app import icon as icon_mod
    from app import i18n
    from app import winapi
    from app.mainwindow import MainWindow

    config = cfg_mod.load_config()
    i18n.set_language(config.appearance.language)

    app = QApplication(args)          # 必须先有 app，QFontDatabase 才能用
    fonts_mod.load_bundled()
    app.setApplicationName(cfg_mod.APP_NAME)
    app.setApplicationDisplayName(cfg_mod.APP_NAME)
    app.setApplicationVersion(cfg_mod.APP_VERSION)
    app.setOrganizationName(cfg_mod.APP_ID)
    app.setWindowIcon(icon_mod.app_icon())
    app.setQuitOnLastWindowClosed(True)

    guard = None
    if "--multi" not in args:
        guard = _acquire_instance_lock()
        if guard is None:
            QMessageBox.information(None, cfg_mod.APP_NAME,
                                    tr("%s 已经在运行了。") % cfg_mod.APP_NAME)
            return 0

    winapi.set_app_user_model_id(cfg_mod.APP_ID)
    window = MainWindow(config)
    window.show()
    code = app.exec_()
    del guard
    return code


if __name__ == "__main__":
    sys.exit(main())
