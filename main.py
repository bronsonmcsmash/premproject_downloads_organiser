"""
main.py — Entry point for Project Organizer.

Responsibilities:
  • Generate and cache the tray icon (.ico for winotify, PIL Image for pystray).
  • Register a silent Windows auto-start registry key on first run.
  • Register the global hotkey listener in a background thread.
  • Build and manage the system tray icon and right-click menu.
  • Orchestrate the file-organise workflow when the hotkey fires.

Run with:
    pythonw.exe main.py
(pythonw suppresses the console window on Windows.)
"""

import os
import queue as _queue
import sys
import threading
import winreg
from pathlib import Path
from typing import Optional

import keyboard
import pystray

import notifications
from config import load_config, save_config
from icon import create_tray_icon, save_icon_ico
from notifications import show_toast
from organizer import find_dopusrt, get_selected_files, organise_files
from progress_window import ProgressWindow
from settings import SettingsWindow

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME   = "ProjectOrganizer"

# When frozen by PyInstaller (--onefile), __file__ points to a read-only
# temp dir.  Write the icon to %APPDATA% instead, which is always writable.
if getattr(sys, 'frozen', False):
    ICON_DIR = Path(os.environ.get("APPDATA", "~")) / APP_NAME / "assets"
else:
    ICON_DIR = Path(__file__).parent / "assets"

ICON_PATH  = ICON_DIR / "icon.ico"

REGISTRY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


# ---------------------------------------------------------------------------
# Registry auto-start helpers
# ---------------------------------------------------------------------------

def _register_autostart() -> None:
    """
    Write a Run registry key so the app launches silently at Windows login.

    Uses pythonw.exe (no console window) if the current interpreter is
    python.exe; otherwise uses the interpreter as-is (handles frozen .exe).
    """
    try:
        exe = sys.executable
        if exe.lower().endswith("python.exe"):
            exe = exe[:-10] + "pythonw.exe"

        script  = str(Path(__file__).resolve())
        value   = f'"{exe}" "{script}"'

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, value)

    except OSError:
        # Non-fatal — the user can add it manually.  Don't crash.
        pass


def _is_autostart_registered() -> bool:
    """Return True if a Run registry entry for this app already exists."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REGISTRY_RUN_KEY,
            0,
            winreg.KEY_READ,
        ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class ProjectOrganizer:
    """Main application controller."""

    def __init__(self) -> None:
        self.config: dict = load_config()
        self.tray: Optional[pystray.Icon] = None

        self._dopusrt:             Optional[str] = find_dopusrt()
        self._hotkey_handler                     = None    # return value of keyboard.add_hotkey
        self._fallback_warned:     bool          = False
        self._settings_open:       bool          = False   # guard against double-open

    # ------------------------------------------------------------------
    # Icon initialisation
    # ------------------------------------------------------------------

    def _init_icon(self) -> pystray.Icon:
        """
        Generate the icon assets and return a configured pystray Icon.

        The .ico file is written to assets/icon.ico so winotify can use it
        for toast notifications.
        """
        ICON_DIR.mkdir(parents=True, exist_ok=True)

        if not ICON_PATH.exists():
            save_icon_ico(ICON_PATH)

        notifications.set_icon_path(str(ICON_PATH))

        pil_image = create_tray_icon(size=64)

        return pystray.Icon(
            name=APP_NAME,
            icon=pil_image,
            title="Project Organizer",
            menu=self._build_menu(),
        )

    # ------------------------------------------------------------------
    # Tray menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        """Build (or rebuild) the right-click tray context menu."""
        folder      = self.config.get("project_folder", "")
        proj_label  = Path(folder).name if folder else "Not set"

        return pystray.Menu(
            pystray.MenuItem(
                f"Active Project: {proj_label}",
                action=None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Change Project Folder",
                self._menu_change_folder,
            ),
            pystray.MenuItem(
                "Settings",
                self._menu_open_settings,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._menu_quit),
        )

    def _refresh_menu(self) -> None:
        """Update the tray menu to reflect changed config."""
        if self.tray:
            self.tray.menu = self._build_menu()
            self.tray.update_menu()

    # ------------------------------------------------------------------
    # Hotkey management
    # ------------------------------------------------------------------

    def _register_hotkey(self) -> None:
        """
        Register the global hotkey from config.

        Any previously registered binding is removed first.  Errors (e.g.
        invalid key name) are surfaced via toast instead of crashing.
        """
        if self._hotkey_handler is not None:
            try:
                keyboard.remove_hotkey(self._hotkey_handler)
            except (KeyError, ValueError):
                pass
            self._hotkey_handler = None

        hotkey = self.config.get("hotkey", "ctrl+shift+c")
        try:
            self._hotkey_handler = keyboard.add_hotkey(hotkey, self._hotkey_callback)
        except Exception as exc:
            show_toast(
                "Project Organizer",
                f"⚠️ Could not register hotkey '{hotkey}': {exc}",
            )

    def _hotkey_callback(self) -> None:
        """
        Called by the keyboard library when the hotkey fires.

        Dispatches the organise workflow to a daemon thread so the keyboard
        listener is never blocked.
        """
        threading.Thread(target=self._run_organiser, daemon=True).start()

    # ------------------------------------------------------------------
    # Core organise workflow
    # ------------------------------------------------------------------

    def _run_organiser(self) -> None:
        """
        Fetch selected files from Directory Opus (or clipboard), organise
        them into the project folder, and show a result toast.

        All errors are surfaced via toast — this method never raises.
        """
        project_folder = self.config.get("project_folder", "")

        if not project_folder:
            show_toast(
                "Project Organizer",
                "⚠️ No project folder set. Click the tray icon to set one.",
            )
            return

        # ── Get selected files ───────────────────────────────────────────
        files, used_fallback = get_selected_files(self._dopusrt)

        # Show clipboard-fallback warning once per session.
        if used_fallback and not self._fallback_warned:
            self._fallback_warned = True
            if not self._dopusrt:
                show_toast(
                    "Project Organizer",
                    "⚠️ dopusrt.exe not found — clipboard fallback active.\n"
                    "Select files in Directory Opus and press Ctrl+C, "
                    "then press the organiser hotkey.",
                    duration="long",
                )
                if not files:
                    return

        if not files:
            show_toast("Project Organizer", "⚠️ No files selected in File Explorer")
            return

        # ── Subfolder prompt ─────────────────────────────────────────────
        subfolder_choices = None
        if self.config.get("use_subfolders", True):
            from organizer import classify_file
            from subfolder_picker import SUBFOLDER_OPTIONS, SubfolderPicker

            types_present = {
                classify_file(Path(f))
                for f in files
                if classify_file(Path(f)) in SUBFOLDER_OPTIONS
            }

            if types_present:
                picker = SubfolderPicker(types_present)
                subfolder_choices = picker.show()
                if subfolder_choices is None:   # user cancelled
                    return

        # ── Organise ────────────────────────────────────────────────────
        mode      = self.config.get("mode", "copy")
        overwrite = self.config.get("overwrite_duplicates", False)
        action    = "copied" if mode == "copy" else "moved"
        proj_name = Path(project_folder).name

        # Show a progress window for large batches (≥ 10 MB total).
        _THRESHOLD = 10 * 1024 * 1024
        total_size = sum(
            Path(f).stat().st_size for f in files if Path(f).is_file()
        )
        prog_q: Optional[_queue.Queue] = None
        if total_size >= _THRESHOLD:
            valid_count = sum(1 for f in files if Path(f).is_file())
            prog_q = _queue.Queue()
            pw = ProgressWindow(prog_q, valid_count)
            threading.Thread(target=pw.run, daemon=True).start()

        def _progress(event, *args):
            if prog_q is not None:
                prog_q.put((event, *args))

        success, last_dir, errors = organise_files(
            file_paths=files,
            project_folder=project_folder,
            mode=mode,
            overwrite_duplicates=overwrite,
            file_type_labels=self.config.get("file_type_labels", {}),
            subfolder_choices=subfolder_choices,
            use_date_folder=self.config.get("use_date_folder", True),
            progress_callback=_progress,
        )

        # ── Report results ───────────────────────────────────────────────
        for err in errors:
            show_toast("Project Organizer", f"❌ Error: {err}")

        if success > 0:
            label = "file" if success == 1 else "files"
            show_toast(
                "Project Organizer",
                f"✅ {success} {label} {action} to {proj_name}",
                open_folder=last_dir,
            )
        elif not errors:
            show_toast("Project Organizer", "⚠️ No files were processed.")

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def _menu_change_folder(self, _icon=None, _item=None) -> None:
        """Quick folder-picker accessible directly from the tray menu."""
        def _pick():
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            root.lift()

            chosen = filedialog.askdirectory(
                parent=root,
                title="Select Active Project Folder",
            )
            root.destroy()

            if chosen:
                self.config["project_folder"] = chosen
                save_config(self.config)
                self._refresh_menu()
                show_toast(
                    "Project Organizer",
                    f"✅ Project folder set to: {Path(chosen).name}",
                )

        threading.Thread(target=_pick, daemon=True).start()

    def _menu_open_settings(self, _icon=None, _item=None) -> None:
        """Launch the Settings window from the tray menu."""
        if self._settings_open:
            return
        threading.Thread(target=self._show_settings_window, daemon=True).start()

    def _show_settings_window(self) -> None:
        """Run the settings window on a dedicated thread (tkinter mainloop)."""
        self._settings_open = True
        try:
            win = SettingsWindow(
                config=self.config,
                on_save=self._on_settings_saved,
            )
            win.show()
        finally:
            self._settings_open = False

    def _on_settings_saved(self, new_config: dict) -> None:
        """
        Persist updated settings and re-register the hotkey if it changed.

        Args:
            new_config: The complete config dict returned by the settings window.
        """
        old_hotkey = self.config.get("hotkey")
        self.config.update(new_config)
        save_config(self.config)

        if new_config.get("hotkey") != old_hotkey:
            self._register_hotkey()

        self._refresh_menu()

    def _menu_quit(self, _icon=None, _item=None) -> None:
        """Shut down cleanly: unhook all keys and stop the tray."""
        keyboard.unhook_all()
        if self.tray:
            self.tray.stop()

    # ------------------------------------------------------------------
    # Application entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Start up the application:
          1. Register auto-start (silent, first-run only).
          2. Register the global hotkey.
          3. Show a welcome toast if no project folder is configured.
          4. Start the pystray event loop (blocks until Quit).
        """
        # Auto-start — do this silently, once.
        if not _is_autostart_registered():
            _register_autostart()

        # Hotkey
        self._register_hotkey()

        # Onboarding toast
        if not self.config.get("project_folder"):
            show_toast(
                "Project Organizer",
                "No project folder set. Right-click the tray icon to get started.",
                duration="long",
            )

        # Tray icon
        self.tray = self._init_icon()
        self.tray.run()   # blocks until _menu_quit() calls tray.stop()


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ProjectOrganizer().run()
