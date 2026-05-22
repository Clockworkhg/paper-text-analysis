# -*- coding: utf-8 -*-
"""Shared Tkinter support code for the integrated desktop app."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
from pathlib import Path


def configure_tcl_tk_env() -> None:
    tcl_root = Path(sys.base_prefix) / "tcl"
    tcl_dir = tcl_root / "tcl8.6"
    tk_dir = tcl_root / "tk8.6"
    if tcl_dir.exists():
        os.environ.setdefault("TCL_LIBRARY", str(tcl_dir))
    if tk_dir.exists():
        os.environ.setdefault("TK_LIBRARY", str(tk_dir))


configure_tcl_tk_env()

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


logger = logging.getLogger(__name__)

COLORS = {
    "ink": "#093C5D",
    "steel": "#3B7597",
    "aqua": "#6FD1D7",
    "mint": "#5DF8D8",
    "bg": "#EAF8FA",
    "panel": "#ffffff",
    "surface": "#F7FCFD",
    "nav": "#093C5D",
    "nav_hover": "#3B7597",
    "nav_active": "#6FD1D7",
    "nav_text": "#D7EEF3",
    "nav_active_text": "#093C5D",
    "text": "#093C5D",
    "muted": "#5F7F90",
    "border": "#B8DCE2",
    "accent": "#3B7597",
    "accent_soft": "#D9F6F8",
    "progress": "#5DF8D8",
    "soft": "#F0FBFC",
}


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative_path


def set_window_icon(window: tk.Tk) -> None:
    ico_path = resource_path("assets/icon.ico")
    png_path = resource_path("assets/logo-32.png")
    try:
        if ico_path.exists():
            window.iconbitmap(str(ico_path))
    except tk.TclError:
        logger.debug("Failed to set ICO window icon", exc_info=True)
    try:
        if png_path.exists():
            icon_image = tk.PhotoImage(file=str(png_path))
            window.iconphoto(True, icon_image)
            window._icon_image = icon_image
    except tk.TclError:
        logger.debug("Failed to set PNG window icon", exc_info=True)


class WorkerMixin:
    def __init__(self):
        self._wq = queue.Queue()

    def _poll_worker(self, widget, interval=120):
        try:
            while True:
                item = self._wq.get_nowait()
                kind = item[0]
                if kind == "progress":
                    self._w_on_progress(*item[1:])
                elif kind == "log":
                    self._w_on_log(item[1])
                elif kind == "done":
                    self._w_on_done(*item[1:])
                elif kind == "error":
                    self._w_on_error(item[1])
                elif kind == "preview":
                    self._w_on_preview(item[1])
        except queue.Empty:
            pass
        widget.after(interval, lambda: self._poll_worker(widget, interval))

    def _w_put(self, *args):
        self._wq.put(args)

    def _w_on_progress(self, msg, frac):
        pass

    def _w_on_log(self, msg):
        pass

    def _w_on_done(self, msg):
        pass

    def _w_on_error(self, msg):
        pass

    def _w_on_preview(self, text):
        pass


class LogPanel(ttk.Frame):
    def __init__(self, master, height=12):
        super().__init__(master)
        self.text = tk.Text(
            self,
            height=height,
            wrap="word",
            state="normal",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            insertbackground=COLORS["accent"],
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            font=("Consolas", 9),
        )
        sb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def log(self, msg):
        self.text.insert("end", msg + "\n")
        self.text.see("end")

    def clear(self):
        self.text.delete("1.0", "end")


class FileRow(ttk.Frame):
    def __init__(self, master, label, mode="open", filetypes=None, var=None):
        super().__init__(master)
        self.var = var or tk.StringVar()
        ttk.Label(self, text=label, width=18, anchor="e").pack(side="left", padx=(0, 6))
        ttk.Entry(self, textvariable=self.var, style="Field.TEntry").pack(side="left", fill="x", expand=True)
        if mode == "open":
            ttk.Button(self, text="Browse", width=8, style="Ghost.TButton", command=self._open).pack(side="left", padx=(6, 0))
        elif mode == "dir":
            ttk.Button(self, text="Browse", width=8, style="Ghost.TButton", command=self._dir).pack(side="left", padx=(6, 0))
        else:
            ttk.Button(self, text="Save as", width=8, style="Ghost.TButton", command=self._save).pack(side="left", padx=(6, 0))
        self._filetypes = filetypes or [("All", "*.*")]

    def _open(self):
        path = filedialog.askopenfilename(filetypes=self._filetypes)
        if path:
            self.var.set(path)

    def _dir(self):
        path = filedialog.askdirectory()
        if path:
            self.var.set(path)

    def _save(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=self._filetypes)
        if path:
            self.var.set(path)

    def get(self):
        return self.var.get().strip()


class ToolTab(ttk.Frame, WorkerMixin):
    """Base for tool tabs with file inputs, progress, and a log panel."""

    def __init__(self, master):
        ttk.Frame.__init__(self, master)
        WorkerMixin.__init__(self)
        self.columnconfigure(0, weight=1)
        self.running = False
        self._pad = {"padx": 8, "pady": 4}

    def _finish(self, progress_mode="indeterminate", log_height=14):
        self._pbar_mode = progress_mode
        if progress_mode:
            self.pbar = ttk.Progressbar(self, mode=progress_mode)
            self.pbar.grid(row=98, column=0, sticky="ew", **self._pad)
        self.log = LogPanel(self, height=log_height)
        self.log.grid(row=99, column=0, sticky="nsew", **self._pad)
        self.rowconfigure(99, weight=1)
        self._poll_worker(self)

    def _validate(self):
        return True

    def _worker_impl(self):
        pass

    def _start(self, btn=None):
        if self.running:
            return
        if not self._validate():
            return
        self.running = True
        if btn:
            btn.config(state="disabled")
            self._run_btn = btn
        self.log.clear()
        if hasattr(self, "pbar") and self._pbar_mode == "indeterminate":
            self.pbar.start(10)
        threading.Thread(target=self._worker_impl, daemon=True).start()

    def _w_on_log(self, msg):
        self.log.log(msg)

    def _w_on_progress(self, msg, frac):
        if hasattr(self, "pbar") and self._pbar_mode == "determinate":
            self.pbar["value"] = max(0, min(100, int(frac)))

    def _w_on_done(self, msg):
        if hasattr(self, "pbar"):
            if self._pbar_mode == "indeterminate":
                self.pbar.stop()
            self.pbar["value"] = 100 if self._pbar_mode == "determinate" else 0
        self.running = False
        if hasattr(self, "_run_btn"):
            self._run_btn.config(state="normal")
        self.log.log(msg)
        messagebox.showinfo("Done", msg)

    def _w_on_error(self, msg):
        if hasattr(self, "pbar"):
            self.pbar.stop()
        self.running = False
        if hasattr(self, "_run_btn"):
            self._run_btn.config(state="normal")
        self.log.log(f"Error: {msg}")
        messagebox.showerror("Error", msg)
