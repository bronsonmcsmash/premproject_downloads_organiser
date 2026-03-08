"""
drop_zone.py — Taskbar-anchored drag-and-drop target window for Project Organizer.

Displays a small always-on-top borderless panel just above the system tray,
toggled by left-clicking the tray icon.  The user can drag any folder from
Explorer or Directory Opus onto it to set it as the active project folder.

Drag-and-drop is handled by tkinterdnd2 (wraps the tkdnd Tcl extension),
which works natively with tkinter windows.
"""

import ctypes
import ctypes.wintypes
import os
import threading
import tkinter as tk
from typing import Callable, Optional

from tkinterdnd2 import DND_FILES, TkinterDnD

# ---------------------------------------------------------------------------
# Win32 constants (used only for WS_EX_NOACTIVATE, not for DnD)
# ---------------------------------------------------------------------------

GWL_EXSTYLE      = -20
WS_EX_NOACTIVATE = 0x08000000

_user32 = ctypes.windll.user32

_GetWindowLongPtr = _user32.GetWindowLongPtrW
_GetWindowLongPtr.restype = ctypes.c_ssize_t

_SetWindowLongPtr = _user32.SetWindowLongPtrW
_SetWindowLongPtr.restype = ctypes.c_ssize_t

# ---------------------------------------------------------------------------
# Panel dimensions
# ---------------------------------------------------------------------------

_W = 230
_H = 70
_BG = "#2c3e50"


def _get_panel_position(w: int, h: int):
    """Return (x, y) to position the panel just above the taskbar, right-aligned."""
    try:
        import win32api
        import win32gui
        taskbar = win32gui.FindWindow("Shell_TrayWnd", None)
        _tl, tt, _tr, _tb = win32gui.GetWindowRect(taskbar)
        sw = win32api.GetSystemMetrics(0)   # screen width
        x = sw - w - 12
        y = tt - h - 6                      # just above taskbar top edge
    except Exception:
        sw, sh = 1920, 1080                 # safe fallback
        x = sw - w - 12
        y = sh - h - 50
    return x, y


# ---------------------------------------------------------------------------
# Drop zone window
# ---------------------------------------------------------------------------

class DropZoneWindow:
    """
    A small panel anchored above the system tray that accepts dropped folders.

    Args:
        on_folder_dropped: Called with the folder path whenever a folder is
                           successfully dropped onto the window.
    """

    def __init__(self, on_folder_dropped: Callable[[str], None]) -> None:
        self._callback = on_folder_dropped
        self._root: Optional[TkinterDnD.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._visible = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Show the drop zone (no-op if already visible)."""
        if self._visible:
            return
        self._visible = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def hide(self) -> None:
        """Destroy the drop zone window."""
        self._visible = False
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass
            self._root = None

    def toggle(self) -> None:
        """Show if hidden; hide if visible."""
        if self._visible:
            self.hide()
        else:
            self.show()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Build and run the tkinter window (called on a daemon thread)."""
        x, y = _get_panel_position(_W, _H)

        root = TkinterDnD.Tk()
        self._root = root

        root.title("Drop Zone")
        root.geometry(f"{_W}x{_H}+{x}+{y}")
        root.attributes("-topmost", True)
        root.overrideredirect(True)          # borderless
        root.configure(bg=_BG)

        # ── Main label (also the drop target) ────────────────────────
        lbl = tk.Label(
            root,
            text="\U0001f4c1 Drop folder here\nto set as project",
            bg=_BG,
            fg="white",
            font=("TkDefaultFont", 11),
            justify="center",
            padx=10,
            pady=8,
        )
        lbl.pack(fill="both", expand=True)

        # ── tkinterdnd2 drop binding ──────────────────────────────────
        def _on_dnd_drop(event) -> None:
            # event.data is a Tcl list string; splitlist handles spaces in paths
            paths = root.tk.splitlist(event.data)
            for p in paths:
                p = p.strip("{}")
                if os.path.isdir(p):
                    self._callback(p)
                    break

        lbl.drop_target_register(DND_FILES)
        lbl.dnd_bind("<<Drop>>", _on_dnd_drop)

        # ── Close button (top-right) ─────────────────────────────────
        close_btn = tk.Button(
            root,
            text="\u2715",
            bg="#e74c3c",
            fg="white",
            bd=0,
            padx=3,
            pady=1,
            font=("TkDefaultFont", 8),
            cursor="hand2",
            command=self.hide,
        )
        close_btn.place(relx=1.0, rely=0.0, x=-2, y=2, anchor="ne")

        root.protocol("WM_DELETE_WINDOW", self.hide)

        # ── WS_EX_NOACTIVATE: don't steal focus from DOpus/Explorer ──
        root.update()   # ensure native window exists before touching HWND
        hwnd = root.winfo_id()
        current_ex = _GetWindowLongPtr(hwnd, GWL_EXSTYLE)
        _SetWindowLongPtr(hwnd, GWL_EXSTYLE, current_ex | WS_EX_NOACTIVATE)

        root.mainloop()

        # Mainloop exited — mark as hidden
        self._visible = False
        self._root    = None
