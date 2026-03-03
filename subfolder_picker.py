"""
subfolder_picker.py — Centred popup for choosing a subfolder per file type.

Shown when the organiser hotkey fires and use_subfolders is enabled.
Only displays rows for file-type categories present in the current batch
(Video, Audio, Images).  Other types skip the prompt entirely.

Usage:
    picker = SubfolderPicker({"Video", "Audio"})
    result = picker.show()
    # result -> {"Video": "footage", "Audio": "sfx"}  or None if cancelled
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, Set


# Subfolder options per file-type category.  First entry is the default.
SUBFOLDER_OPTIONS: Dict[str, list] = {
    "Video":  ["footage", "renders", "exports"],
    "Audio":  ["vo", "sfx", "music"],
    "Images": ["psds", "pngs", "jpgs"],
}

# Display order for the popup rows.
_TYPE_ORDER = ["Video", "Audio", "Images"]


class SubfolderPicker:
    """
    Modal popup that lets the user pick a subfolder for each relevant file type.

    Args:
        types_present: Set of file-type category names (e.g. {"Video", "Audio"})
                       that were found in the current batch.  Only types with
                       entries in SUBFOLDER_OPTIONS are shown.
    """

    def __init__(self, types_present: Set[str]) -> None:
        self._types = [t for t in _TYPE_ORDER if t in types_present]
        self._result: Optional[Dict[str, str]] = None
        self._combos: Dict[str, ttk.Combobox] = {}

        self.root = tk.Tk()
        self.root.title("Choose Subfolder")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self._build_ui()

        # Bind keyboard shortcuts
        self.root.bind("<Return>", lambda _: self._confirm())
        self.root.bind("<Escape>", lambda _: self._cancel())
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

        # Centre on screen
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
        outer = {"padx": 16, "pady": 8}
        pad   = {"padx": 8,  "pady": 5}

        # Type rows
        f_rows = tk.Frame(self.root)
        f_rows.grid(row=0, column=0, **outer)

        for i, type_name in enumerate(self._types):
            options = SUBFOLDER_OPTIONS[type_name]

            tk.Label(
                f_rows,
                text=f"{type_name} files:",
                anchor="w",
                width=14,
            ).grid(row=i, column=0, **pad, sticky="w")

            var = tk.StringVar(value=options[0])
            combo = ttk.Combobox(
                f_rows,
                textvariable=var,
                values=options,
                state="readonly",
                width=14,
            )
            combo.grid(row=i, column=1, **pad, sticky="w")
            self._combos[type_name] = combo

        # Separator
        ttk.Separator(self.root, orient="horizontal").grid(
            row=1, column=0, sticky="ew", padx=16
        )

        # Buttons
        f_btns = tk.Frame(self.root)
        f_btns.grid(row=2, column=0, pady=10)

        ok_btn = tk.Button(
            f_btns, text="OK", width=12,
            bg="#3498db", fg="white", relief="flat",
            command=self._confirm,
        )
        ok_btn.pack(side="left", padx=8)
        ok_btn.focus_set()

        tk.Button(
            f_btns, text="Cancel", width=12,
            command=self._cancel,
        ).pack(side="left", padx=8)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _confirm(self) -> None:
        self._result = {
            type_name: combo.get()
            for type_name, combo in self._combos.items()
        }
        self.root.destroy()

    def _cancel(self) -> None:
        self._result = None
        self.root.destroy()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def show(self) -> Optional[Dict[str, str]]:
        """
        Display the picker and block until the user confirms or cancels.

        Returns:
            Dict mapping type name to chosen subfolder string, or None if
            the user cancelled (window closed or Escape pressed).
        """
        self.root.mainloop()
        return self._result
