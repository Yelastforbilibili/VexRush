# -*- coding: utf-8 -*-
"""更新窗口：显示版本信息与更新内容，测速、下载、校验后替换安装包。"""
from __future__ import annotations

import os
import sys

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QPalette, QTextCursor
from PyQt5.QtWidgets import (QDialog, QHBoxLayout, QProgressBar, QPushButton, QTextBrowser,
                             QVBoxLayout, QWidget)

from . import config as cfg_mod
from . import debug
from . import updater
from . import widgets as w
from .i18n import tr


class CheckWorker(QThread):
    """后台查询 latest release。"""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            info = updater.fetch_latest()
        except Exception as exc:                      # 网络错误全部收敛成一个提示
            debug.log("update", "check failed: %s" % exc)
            self.failed.emit(str(exc))
            return
        self.done.emit(info)


class DownloadWorker(QThread):
    """测速选线路、下载、校验 SHA-256。"""

    status = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, release, dest: str, parent=None) -> None:
        super().__init__(parent)
        self.release = release
        self.dest = dest
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            urls = updater.candidate_urls(self.release.asset_url)
            self.status.emit("update_testing", "")
            ranked = updater.rank_candidates(urls)
            order = [url for url, _speed in ranked] or urls
            if ranked:
                fastest, speed = ranked[0]
                self.status.emit("update_fastest_line", "%s · %s/s" % (
                    updater._label(fastest), updater.format_size(int(speed))))
                debug.log("update", "fastest line %s %.0f B/s" % (fastest, speed))
                order = [fastest] + [url for url in order if url != fastest]
            self.status.emit("update_downloading", "")
            last = {"done": 0, "total": 0}

            def on_progress(done: int, total: int) -> None:
                last["done"] = done
                last["total"] = total
                self.progress.emit(done, total)

            self.progress.emit(0, self.release.asset_size)
            updater.download(order, self.dest, self.release.sha256,
                             progress=on_progress, cancel=lambda: self._cancel)
            self.status.emit("update_verifying", "")
            if self.release.sha256:
                actual = updater.sha256_file(self.dest)
                if actual != self.release.sha256.lower():
                    os.remove(self.dest)
                    raise updater.UpdateError(tr("update_verify_failed"))
            self.status.emit("update_verified", "")
            self.done.emit(self.dest)
        except Exception as exc:
            debug.log("update", "download failed: %s" % exc)
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    """一个版本的更新说明与安装入口。"""

    installed = pyqtSignal()

    def __init__(self, release, parent: QWidget = None, auto_download: bool = False) -> None:
        super().__init__(parent)
        self.release = release
        self._checker = None
        self._worker = None
        self._saved = ""
        self.setWindowTitle(tr("check_update"))
        self.setMinimumWidth(560)
        self.resize(600, 620)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget(self)
        head.setObjectName("Header")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(20, 14, 20, 12)
        head_layout.addWidget(w.label(tr("check_update"), "PageTitle"))
        head_layout.addStretch(1)
        head_layout.addWidget(w.label(release.tag or release.version_text, "Hint"))
        root.addWidget(head)

        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(20, 14, 20, 16)
        layout.setSpacing(10)

        info = QWidget(body)
        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(18)
        info_layout.addWidget(w.label(tr("update_current"), "FieldLabel"))
        info_layout.addWidget(w.label("v%s" % cfg_mod.APP_VERSION, "Body"))
        info_layout.addSpacing(10)
        info_layout.addWidget(w.label(tr("update_new"), "FieldLabel"))
        info_layout.addWidget(w.label("v%s" % release.version_text, "Body"))
        info_layout.addStretch(1)
        layout.addWidget(info)

        sub = QWidget(body)
        sub_layout = QHBoxLayout(sub)
        sub_layout.setContentsMargins(0, 0, 0, 0)
        sub_layout.setSpacing(18)
        if release.published_at:
            sub_layout.addWidget(w.label(release.published_at[:10], "Hint"))
        sub_layout.addWidget(w.label("%s %s · %s" % (tr("update_size"), updater.format_size(release.asset_size),
                                                     release.source), "Hint"))
        sub_layout.addStretch(1)
        layout.addWidget(sub)

        layout.addWidget(w.label(tr("update_notes"), "FieldLabel"))
        self.notes = QTextBrowser(body)
        self.notes.setOpenExternalLinks(True)
        self.notes.setFrameShape(QTextBrowser.NoFrame)
        # 颜色取自当前调色板，深浅主题都不会出现「深底浅字」或反过来的情况
        palette = self.notes.palette()
        base = palette.color(QPalette.Base).name()
        accent_text = palette.color(QPalette.Text).name()
        border = palette.color(QPalette.Mid).name()
        self.notes.setStyleSheet(
            "QTextBrowser{background-color:%s; color:%s; border:1px solid %s;"
            " border-radius:8px; padding:8px; selection-background-color:%s;}"
            % (base, accent_text, border, palette.color(QPalette.Highlight).name()))
        document = self.notes.document()
        document.setDocumentMargin(10)
        document.setDefaultStyleSheet(
            "h1,h2,h3{font-size:11.5pt; font-weight:600;} p{margin:4px 0;}"
            " li{margin:2px 0;} ul{margin:4px 0;}")
        document.setMarkdown(release.notes or "")
        self.notes.moveCursor(QTextCursor.Start)
        font = self.notes.font()
        font.setPointSizeF(max(9.0, font.pointSizeF()))
        self.notes.setFont(font)
        layout.addWidget(self.notes, 1)

        self.bar = QProgressBar(body)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.hide()
        layout.addWidget(self.bar)

        status_row = QWidget(body)
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)
        self.spinner = w.MiniSpinner(status_row)
        self.lbl_status = w.label("", "Hint")
        status_layout.addWidget(self.spinner)
        status_layout.addWidget(self.lbl_status, 1)
        layout.addWidget(status_row)

        root.addWidget(body, 1)

        footer = QWidget(self)
        footer.setObjectName("Footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        self.lbl_hint = w.label(tr("update_install_hint") % ("v%s" % release.version_text), "Caption")
        footer_layout.addWidget(self.lbl_hint)
        footer_layout.addStretch(1)
        self.btn_page = QPushButton(tr("open_release_page"), footer)
        self.btn_page.setProperty("variant", "ghost")
        self.btn_page.setCursor(Qt.PointingHandCursor)
        self.btn_page.clicked.connect(self._open_page)
        footer_layout.addWidget(self.btn_page)
        self.btn_later = QPushButton(tr("download_later"), footer)
        self.btn_later.setProperty("variant", "ghost")
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(self._on_later)
        footer_layout.addWidget(self.btn_later)
        self.btn_go = QPushButton(tr("download_install"), footer)
        self.btn_go.setProperty("variant", "primary")
        self.btn_go.setCursor(Qt.PointingHandCursor)
        self.btn_go.clicked.connect(self._on_go)
        footer_layout.addWidget(self.btn_go)
        root.addWidget(footer)

        if auto_download:
            self.start_download()

    # ---------------------------------------------------------------- 行为
    def update_dir(self) -> str:
        path = os.path.join(cfg_mod.data_dir(), "update")
        os.makedirs(path, exist_ok=True)
        return path

    def _open_page(self) -> None:
        if self.release.html_url:
            QDesktopServices.openUrl(self.release.html_url)

    def _on_later(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
        self.close()

    def _on_go(self) -> None:
        if self._saved:
            self.install()
            return
        self.start_download()

    def start_download(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        name = "%s-%s.exe" % (os.path.splitext(self.release.asset_name)[0] or "VexRush",
                              self.release.version_text)
        dest = os.path.join(self.update_dir(), name)
        self.btn_go.setEnabled(False)
        self.btn_go.setText(tr("update_downloading_short"))
        self.bar.show()
        self.bar.setValue(0)
        self.spinner.start()
        self.lbl_status.setText(tr("update_testing"))

        worker = DownloadWorker(self.release, dest, self)
        self._worker = worker
        worker.status.connect(self._on_status)
        worker.progress.connect(self._on_progress)
        worker.done.connect(self._on_downloaded)
        worker.failed.connect(self._on_failed)
        worker.start()

    def _on_status(self, key: str, arg: str) -> None:
        text = tr(key)
        if arg:
            text = "%s %s" % (text, arg)
        self.lbl_status.setText(text)

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.bar.setValue(int(min(1000, done * 1000 / total)))
            self.lbl_status.setText("%s %s / %s" % (tr("update_downloading"),
                                                    updater.format_size(done),
                                                    updater.format_size(total)))
        else:
            self.bar.setValue(0)
            self.lbl_status.setText("%s %s" % (tr("update_downloading"), updater.format_size(done)))

    def _on_downloaded(self, path: str) -> None:
        self._saved = path
        self.spinner.stop()
        self.bar.setValue(1000)
        self.lbl_status.setText(tr("update_ready"))
        self.btn_go.setEnabled(True)
        self.btn_go.setText(tr("install_now"))

    def _on_failed(self, message: str) -> None:
        self.spinner.stop()
        self.bar.hide()
        self.lbl_status.setText("%s：%s" % (tr("update_failed"), message))
        self.btn_go.setEnabled(True)
        self.btn_go.setText(tr("download_install"))

    def install(self) -> None:
        if not self._saved or not os.path.exists(self._saved):
            return
        if not getattr(sys, "frozen", False):
            self.lbl_status.setText(tr("update_dev_mode") % self._saved)
            return
        target = sys.executable
        try:
            updater.install_and_restart(self._saved, target, os.getpid())
        except Exception as exc:
            self.lbl_status.setText("%s：%s" % (tr("update_failed"), exc))
            debug.log("update", "install failed: %s" % exc)
            return
        self.installed.emit()
        from PyQt5.QtWidgets import QApplication
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2500)
        super().closeEvent(event)


def check_in_background(parent, on_done, on_failed) -> CheckWorker:
    """给调用方省掉线程样板：返回 worker（调用方需要持有引用）。"""
    worker = CheckWorker(parent)
    worker.done.connect(on_done)
    worker.failed.connect(on_failed)
    worker.start()
    return worker
