import queue
import threading
import tkinter as tk
from tkinter import messagebox


class BaseApp:
    def __init__(self):
        self._q = queue.Queue()

    def setup_polling(self, widget: tk.Widget, interval_ms: int = 120):
        widget.after(interval_ms, self._poll)

    def _poll(self):
        try:
            while True:
                item = self._q.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, msg, frac = item
                    self.on_progress(msg, frac)
                elif kind == "log":
                    _, msg = item
                    self.on_log(msg)
                elif kind == "done":
                    _, msg = item
                    self.on_done(msg)
                elif kind == "error":
                    _, msg = item
                    self.on_error(msg)
                elif kind == "warn":
                    _, msg = item
                    self.on_warn(msg)
        except queue.Empty:
            pass
        finally:
            pass

    def put_progress(self, msg: str, frac: float):
        self._q.put(("progress", msg, frac))

    def put_log(self, msg: str):
        self._q.put(("log", msg))

    def put_done(self, msg: str):
        self._q.put(("done", msg))

    def put_error(self, msg: str):
        self._q.put(("error", msg))

    def put_warn(self, msg: str):
        self._q.put(("warn", msg))

    def on_progress(self, msg: str, frac: float):
        pass

    def on_log(self, msg: str):
        pass

    def on_done(self, msg: str):
        pass

    def on_error(self, msg: str):
        pass

    def on_warn(self, msg: str):
        pass
