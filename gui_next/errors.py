# -*- coding: utf-8 -*-
"""User-facing error surfaces (Phase 4B #19/#22/#23).

Two responsibilities:

1. `friendly_io_error()` — map raw OSError/PermissionError (incl. the
   Windows file-locked-by-Excel/WPS case) to researcher-readable text;
   technical detail belongs in diagnostics, not in the message.

2. `install_exception_handler()` — a global sys.excepthook so an uncaught
   exception shows "CADS Workbench encountered an unexpected error" with
   [Copy diagnostics] / [Open logs] / [Continue] / [Exit], logs itself to
   application.log, and marks the session-crashed flag (#20). Exceptions
   are never swallowed silently.
"""

from __future__ import annotations

import errno
import sys
import traceback
from typing import Optional

from PySide6.QtWidgets import QMessageBox

_WINERROR_LOCKED = {32, 33}  # ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION


def friendly_io_error(exc: BaseException) -> str:
    """Researcher-readable message for filesystem failures."""
    if isinstance(exc, PermissionError):
        # winerror (Windows) is authoritative when present: 32/33 mean the
        # file is locked by another process (Excel/WPS); 5 means permissions.
        code = getattr(exc, "winerror", None)
        if code is None:
            code = getattr(exc, "errno", None)
        if code in _WINERROR_LOCKED or code == errno.EBUSY:
            return ("无法写入:目标文件正被其他程序占用"
                    "(例如正在用 Excel / WPS 打开该工作簿)。"
                    "请关闭相关文件后重试。")
        return "无法写入:没有该目录或文件的写权限。请检查项目文件夹是否为只读。"
    if isinstance(exc, OSError):
        if exc.errno == errno.ENOSPC:
            return "磁盘空间不足,无法完成写入。请释放空间后重试。"
        if exc.errno in (errno.ENOENT, errno.ENOTDIR):
            return "目标路径不存在或已被移动。"
    text = str(exc)
    return text if text.strip() else exc.__class__.__name__


class ErrorReport:
    """One uncaught-exception record: user text + technical detail."""

    def __init__(self, exc_type, exc, tb):
        self.exc_type = exc_type.__name__ if exc_type else "Error"
        self.message = str(exc)
        self.traceback = "".join(traceback.format_exception(exc_type, exc, tb))

    def diagnostics_text(self) -> str:
        from gui_next.version import version_line
        return (f"{version_line()}\n\n{self.exc_type}: {self.message}\n\n"
                f"{self.traceback}")


_handler_installed = False
_active_dialog: Optional[QMessageBox] = None


def install_exception_handler() -> None:
    """Replace sys.excepthook; safe to call multiple times."""
    global _handler_installed
    if _handler_installed:
        return
    _handler_installed = True

    def hook(exc_type, exc, tb) -> None:
        report = ErrorReport(exc_type, exc, tb)
        _log_crash(report)
        _show_error_dialog(report)

    sys.excepthook = hook


def _log_crash(report: ErrorReport) -> None:
    try:
        import logging
        logging.getLogger("app").error(
            "Uncaught exception: %s: %s\n%s",
            report.exc_type, report.message, report.traceback)
        from gui_next.appdata import mark_session_crashed
        mark_session_crashed()
    except Exception:
        pass


def _show_error_dialog(report: ErrorReport) -> None:
    """Dialog with escape hatches; never silently drops the error."""
    global _active_dialog
    if _active_dialog is not None:  # one at a time; log the rest
        return
    try:
        from PySide6.QtWidgets import QApplication
        from gui_next import theme
        from gui_next.widgets import show_toast

        box = QMessageBox()
        box.setWindowTitle("CADS Workbench")
        box.setIcon(QMessageBox.Critical)
        box.setText("CADS Workbench encountered an unexpected error.")
        box.setInformativeText(f"{report.exc_type}: {report.message}\n\n"
                               "技术详情可复制诊断信息;应用日志已记录本次错误。")
        copy_btn = box.addButton("Copy diagnostics", QMessageBox.ActionRole)
        logs_btn = box.addButton("Open logs", QMessageBox.ActionRole)
        continue_btn = box.addButton("继续", QMessageBox.AcceptRole)
        exit_btn = box.addButton("退出", QMessageBox.DestructiveRole)
        _active_dialog = box
        box.exec()
        _active_dialog = None

        clicked = box.clickedButton()
        if clicked is copy_btn:
            QApplication.clipboard().setText(report.diagnostics_text())
            if QApplication.activeWindow() is not None:
                show_toast(QApplication.activeWindow(), "诊断信息已复制")
        elif clicked is logs_btn:
            import os
            import platform
            import subprocess
            from gui_next.appdata import logs_dir
            path = str(logs_dir())
            if platform.system() == "Windows":
                os.startfile(path)  # noqa: S606
            elif platform.system() == "Darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        elif clicked is exit_btn:
            from gui_next.appdata import clear_crash_flag
            clear_crash_flag()
            QApplication.instance().quit() if QApplication.instance() else sys.exit(1)
        del continue_btn
    except Exception:
        # The error dialog itself failed — fall back to stderr so the
        # exception is still visible somewhere.
        sys.stderr.write(report.diagnostics_text())
