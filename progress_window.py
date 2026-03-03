"""
progress_window.py — Tkinter progress window for large file copy/move operations.

Runs in its own daemon thread.  The caller communicates via a queue.Queue:

    ("file",     file_index, filename, file_size_bytes)  — starting a new file
    ("progress", bytes_done, file_size_bytes)            — chunk written
    ("done",)                                            — all files finished

The window closes automatically when it receives ("done",).
"""

import queue
import tkinter as tk
from tkinter import ttk


# Maximum characters to display for a filename before truncating with ellipsis.
_MAX_NAME = 48


def _truncate(name: str, limit: int = _MAX_NAME) -> str:
    return name if len(name) <= limit else name[: limit - 1] + "…"


class ProgressWindow:
    """
    Small always-on-top window showing copy/move progress.

    Parameters
    ----------
    q : queue.Queue
        Queue fed by the copy thread (see module docstring for message format).
    total_files : int
        Total number of files being processed (used to size the overall bar).
    """

    def __init__(self, q: queue.Queue, total_files: int) -> None:
        self._q = q
        self._total_files = total_files
        self._files_done = 0

    # ------------------------------------------------------------------
    # Public API — call from a daemon thread
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Build the UI and block on mainloop until the window is closed."""
        root = tk.Tk()
        root.title("Project Organizer")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        # ── Layout ────────────────────────────────────────────────────
        pad = {"padx": 10, "pady": 4}

        self._label = tk.Label(
            root,
            text="Preparing…",
            anchor="w",
            width=52,
        )
        self._label.grid(row=0, column=0, sticky="ew", **pad)

        tk.Label(root, text="File:", anchor="w").grid(
            row=1, column=0, sticky="w", padx=10, pady=(2, 0)
        )
        self._bar_file = ttk.Progressbar(root, length=360, mode="determinate")
        self._bar_file.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 4))

        tk.Label(root, text="Overall:", anchor="w").grid(
            row=3, column=0, sticky="w", padx=10, pady=(2, 0)
        )
        self._bar_overall = ttk.Progressbar(
            root,
            length=360,
            mode="determinate",
            maximum=max(self._total_files, 1),
        )
        self._bar_overall.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 8))

        # ── Centre on screen ──────────────────────────────────────────
        root.update_idletasks()
        w = root.winfo_reqwidth()
        h = root.winfo_reqheight()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        # ── Start polling ─────────────────────────────────────────────
        self._root = root
        root.after(50, self._poll)
        root.mainloop()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        """Drain the queue and update UI; reschedule itself every 50 ms."""
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg[0]

                if kind == "done":
                    self._root.destroy()
                    return

                elif kind == "file":
                    _, idx, name, file_size = msg
                    label_text = (
                        f"File {idx} of {self._total_files}"
                        f" — {_truncate(name)}"
                    )
                    self._label.config(text=label_text)
                    # Reset per-file bar
                    self._bar_file.config(maximum=max(file_size, 1), value=0)

                elif kind == "progress":
                    _, bytes_done, file_size = msg
                    self._bar_file.config(
                        maximum=max(file_size, 1), value=bytes_done
                    )

                elif kind == "file_done":
                    self._files_done += 1
                    self._bar_overall.config(value=self._files_done)

        except queue.Empty:
            pass

        self._root.after(50, self._poll)
