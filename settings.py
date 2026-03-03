"""
settings.py — Settings window for Project Organizer.

Built with tkinter.  Allows the user to configure:
  • Project folder path
  • Global keyboard shortcut
  • File mode (copy / move)
  • Duplicate-handling behaviour (overwrite vs. auto-rename)

The window is modal-style (always on top) and runs its own mainloop so it
can be safely launched from a daemon thread without blocking the tray.

Usage:
    win = SettingsWindow(config=current_config, on_save=callback)
    win.show()    # blocks until the window is closed
"""

import tkinter as tk
from tkinter import filedialog
from typing import Callable, Dict

from organizer import FILE_TYPES

DEFAULT_HOTKEY = "ctrl+shift+c"

# Modifier key keysym names — pressed alone these should not finalize a combo.
_MODIFIER_KEYSYMS = frozenset({
    "control_l", "control_r",
    "shift_l",   "shift_r",
    "alt_l",     "alt_r",
    "super_l",   "super_r",
    "caps_lock",  "num_lock", "scroll_lock",
})


class SettingsWindow:
    """
    Tkinter settings window.

    Args:
        config:   Current configuration dict.  Not mutated until Save is clicked.
        on_save:  Callback invoked with the updated config dict when the user
                  clicks Save.
    """

    def __init__(self, config: Dict, on_save: Callable[[Dict], None]) -> None:
        self._saved_config = config.copy()
        self._on_save = on_save
        self._capturing = False       # True while waiting for a key combo
        self._label_vars: Dict[str, tk.StringVar] = {}

        self.root = tk.Tk()
        self.root.title("Project Organizer — Settings")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        # Centre the window on screen.
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble all widget sections."""
        outer_pad = {"padx": 14, "pady": 8}
        frame_pad = {"padx": 8, "pady": 4}

        # ── Project Folder ────────────────────────────────────────────────
        f_folder = tk.LabelFrame(self.root, text="Project Folder", **outer_pad)
        f_folder.grid(row=0, column=0, sticky="ew", **outer_pad)
        f_folder.columnconfigure(0, weight=1)

        self._folder_var = tk.StringVar(
            value=self._saved_config.get("project_folder", "")
        )

        folder_lbl = tk.Label(
            f_folder, textvariable=self._folder_var,
            width=50, anchor="w", relief="sunken",
            bg="white", padx=4,
        )
        folder_lbl.grid(row=0, column=0, **frame_pad, sticky="ew")

        tk.Button(
            f_folder, text="Browse…", command=self._browse_folder
        ).grid(row=0, column=1, **frame_pad)

        # ── Keyboard Shortcut ─────────────────────────────────────────────
        f_key = tk.LabelFrame(self.root, text="Keyboard Shortcut", **outer_pad)
        f_key.grid(row=1, column=0, sticky="ew", **outer_pad)

        tk.Label(f_key, text="Shortcut:").grid(
            row=0, column=0, **frame_pad, sticky="w"
        )

        self._hotkey_var = tk.StringVar(
            value=self._saved_config.get("hotkey", DEFAULT_HOTKEY)
        )
        self._hotkey_entry = tk.Entry(
            f_key, textvariable=self._hotkey_var,
            width=22, state="readonly",
            readonlybackground="#f0f8ff", cursor="hand2",
        )
        self._hotkey_entry.grid(row=0, column=1, **frame_pad)
        self._hotkey_entry.bind("<Button-1>", self._start_capture)
        self._hotkey_entry.bind("<KeyPress>",  self._on_key_press)
        self._hotkey_entry.bind("<FocusOut>",  self._stop_capture)

        tk.Button(
            f_key, text="Reset to Default", command=self._reset_hotkey
        ).grid(row=0, column=2, **frame_pad)

        tk.Label(
            f_key,
            text="Click the box, then press your desired key combination.",
            fg="grey", font=("TkDefaultFont", 8),
        ).grid(row=1, column=0, columnspan=3, padx=8, sticky="w")

        # ── File Mode ─────────────────────────────────────────────────────
        f_mode = tk.LabelFrame(self.root, text="File Mode", **outer_pad)
        f_mode.grid(row=2, column=0, sticky="ew", **outer_pad)

        self._mode_var = tk.StringVar(
            value=self._saved_config.get("mode", "copy")
        )
        tk.Radiobutton(
            f_mode, text="Copy  (original files are kept in place)",
            variable=self._mode_var, value="copy",
        ).grid(row=0, column=0, **frame_pad, sticky="w")
        tk.Radiobutton(
            f_mode, text="Move  (original files are removed after copying)",
            variable=self._mode_var, value="move",
        ).grid(row=1, column=0, **frame_pad, sticky="w")

        # ── Duplicate Handling ────────────────────────────────────────────
        f_dup = tk.LabelFrame(self.root, text="Duplicate Handling", **outer_pad)
        f_dup.grid(row=3, column=0, sticky="ew", **outer_pad)

        self._overwrite_var = tk.BooleanVar(
            value=self._saved_config.get("overwrite_duplicates", False)
        )
        tk.Checkbutton(
            f_dup,
            text="Overwrite duplicates  (default: auto-rename  file_1.mp4, file_2.mp4 …)",
            variable=self._overwrite_var,
        ).grid(row=0, column=0, **frame_pad, sticky="w")

        # ── Folder Structure ──────────────────────────────────────────────
        f_struct = tk.LabelFrame(self.root, text="Folder Structure", **outer_pad)
        f_struct.grid(row=4, column=0, sticky="ew", **outer_pad)

        self._use_subfolders_var = tk.BooleanVar(
            value=self._saved_config.get("use_subfolders", True)
        )
        tk.Checkbutton(
            f_struct,
            text="Prompt for subfolder on each organise  (video → footage/renders/exports, "
                 "audio → vo/sfx/music, images → psds/pngs/jpgs)",
            variable=self._use_subfolders_var,
        ).grid(row=0, column=0, **frame_pad, sticky="w")

        self._use_date_var = tk.BooleanVar(
            value=self._saved_config.get("use_date_folder", True)
        )
        tk.Checkbutton(
            f_struct,
            text="Create date folder  (YYYY-MM-DD_HH)",
            variable=self._use_date_var,
        ).grid(row=1, column=0, **frame_pad, sticky="w")

        # ── File Type Labels ──────────────────────────────────────────────
        f_lbl = tk.LabelFrame(self.root, text="File Type Labels", **outer_pad)
        f_lbl.grid(row=5, column=0, sticky="ew", **outer_pad)

        tk.Label(
            f_lbl, text="Extensions (fixed)", fg="grey", font=("TkDefaultFont", 8)
        ).grid(row=0, column=0, padx=(8, 4), pady=(4, 2), sticky="w")
        tk.Label(
            f_lbl, text="Folder Name", fg="grey", font=("TkDefaultFont", 8)
        ).grid(row=0, column=2, padx=(4, 8), pady=(4, 2), sticky="w")

        saved_labels = self._saved_config.get("file_type_labels", {})
        for i, (key, exts) in enumerate(FILE_TYPES.items(), start=1):
            shown = exts[:6]
            ext_str = "  ".join(shown) + ("  …" if len(exts) > 6 else "")
            tk.Label(
                f_lbl, text=ext_str, fg="#777777",
                font=("TkFixedFont", 8), anchor="w",
            ).grid(row=i, column=0, padx=(8, 4), pady=2, sticky="w")

            tk.Label(f_lbl, text="→").grid(row=i, column=1, padx=6)

            var = tk.StringVar(value=saved_labels.get(key, key))
            self._label_vars[key] = var
            tk.Entry(f_lbl, textvariable=var, width=18).grid(
                row=i, column=2, padx=(4, 8), pady=2, sticky="w"
            )

        tk.Label(
            f_lbl,
            text="Edit the folder name. Extensions cannot be changed here.",
            fg="grey", font=("TkDefaultFont", 8),
        ).grid(row=len(FILE_TYPES) + 1, column=0, columnspan=3, padx=8, pady=(2, 6), sticky="w")

        # ── Buttons ───────────────────────────────────────────────────────
        f_btns = tk.Frame(self.root)
        f_btns.grid(row=6, column=0, pady=12)

        tk.Button(
            f_btns, text="Save", width=14,
            bg="#3498db", fg="white", relief="flat",
            command=self._save,
        ).pack(side="left", padx=10)

        tk.Button(
            f_btns, text="Cancel", width=14,
            command=self._cancel,
        ).pack(side="left", padx=10)

    # ------------------------------------------------------------------
    # Hotkey capture
    # ------------------------------------------------------------------

    def _start_capture(self, _event=None) -> None:
        """Begin capturing a new keyboard shortcut."""
        self._capturing = True
        self._hotkey_var.set("Press your shortcut now…")
        self._hotkey_entry.config(readonlybackground="#fffde7")
        self._hotkey_entry.focus_set()

    def _stop_capture(self, _event=None) -> None:
        """Cancel capture mode; restore the previous value if nothing was set."""
        if self._capturing:
            self._capturing = False
            current = self._hotkey_var.get()
            if current == "Press your shortcut now…":
                self._hotkey_var.set(
                    self._saved_config.get("hotkey", DEFAULT_HOTKEY)
                )
            self._hotkey_entry.config(readonlybackground="#f0f8ff")

    def _on_key_press(self, event: tk.Event) -> str:
        """
        Capture the key combination when the user presses a key while the
        entry widget is focused in capture mode.

        Modifier-only presses (Ctrl, Shift, Alt alone) are ignored until a
        non-modifier key is also pressed.
        """
        if not self._capturing:
            return "break"

        keysym = event.keysym.lower()

        # Ignore bare modifier key presses — wait for a real key.
        if keysym in _MODIFIER_KEYSYMS:
            return "break"

        parts: list = []

        # event.state bitmasks on Windows (tkinter):
        #   0x0001 = Shift
        #   0x0004 = Control
        #   0x0008 = Mod1  (Alt on most Windows systems)
        #   0x0080 = Mod4  (sometimes Win key)
        if event.state & 0x0004:
            parts.append("ctrl")
        if event.state & 0x0001:
            parts.append("shift")
        if event.state & 0x0008:
            parts.append("alt")

        parts.append(keysym)
        combo = "+".join(parts)

        self._hotkey_var.set(combo)
        self._capturing = False
        self._hotkey_entry.config(readonlybackground="#e8f5e9")
        return "break"

    def _reset_hotkey(self) -> None:
        """Reset the shortcut entry to the application default."""
        self._hotkey_var.set(DEFAULT_HOTKEY)
        self._capturing = False
        self._hotkey_entry.config(readonlybackground="#f0f8ff")

    # ------------------------------------------------------------------
    # Folder browser
    # ------------------------------------------------------------------

    def _browse_folder(self) -> None:
        """Open a native folder-chooser dialog and update the path label."""
        current = self._folder_var.get()
        chosen = filedialog.askdirectory(
            parent=self.root,
            title="Select Active Project Folder",
            initialdir=current if current else "/",
        )
        if chosen:
            self._folder_var.set(chosen)

    # ------------------------------------------------------------------
    # Save / Cancel
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Validate, persist, and invoke the on_save callback."""
        labels = {
            key: (var.get().strip() or key)
            for key, var in self._label_vars.items()
        }
        new_config = {
            "project_folder":      self._folder_var.get(),
            "hotkey":              self._hotkey_var.get(),
            "mode":                self._mode_var.get(),
            "overwrite_duplicates": self._overwrite_var.get(),
            "file_type_labels":    labels,
            "use_subfolders":      self._use_subfolders_var.get(),
            "use_date_folder":     self._use_date_var.get(),
        }
        self._on_save(new_config)
        self.root.destroy()

    def _cancel(self) -> None:
        """Close without saving."""
        self.root.destroy()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Display the settings window and block the calling thread until closed."""
        self.root.mainloop()
