"""
notifications.py — Toast notification wrapper for Project Organizer.

Uses winotify for Windows 10/11 toast notifications.  If winotify is not
installed the function degrades gracefully by printing to stdout (useful
during development / testing without the GUI stack).

The optional open_folder argument adds an "Open Folder" action button to
the toast so the user can jump straight to the destination folder.
"""

import subprocess
from pathlib import Path

try:
    from winotify import Notification, audio as wn_audio
    _WINOTIFY_OK = True
except ImportError:
    _WINOTIFY_OK = False

# ---------------------------------------------------------------------------
# Module-level config — set by main.py after the icon is written to disk.
# ---------------------------------------------------------------------------

APP_ID = "ProjectOrganizer"
_icon_path: str = ""       # Full path to the .ico file; set via set_icon_path()


def set_icon_path(path: str) -> None:
    """
    Register the .ico file path used by all subsequent toast notifications.

    Args:
        path: Absolute path to a valid .ico file.
    """
    global _icon_path
    _icon_path = path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def show_toast(
    title: str,
    message: str,
    open_folder: str = "",
    duration: str = "short",
) -> None:
    """
    Display a Windows toast notification.

    Args:
        title:       Notification title text.
        message:     Notification body text.
        open_folder: If non-empty and the path exists, adds an "Open Folder"
                     action button that opens that directory in Explorer.
        duration:    "short" (approx. 7 s) or "long" (approx. 25 s).
    """
    if not _WINOTIFY_OK:
        # Development fallback — print so errors are still visible.
        print(f"[Toast] {title}: {message}")
        if open_folder:
            print(f"  → Open folder: {open_folder}")
        return

    icon = _icon_path if _icon_path and Path(_icon_path).exists() else ""

    toast = Notification(
        app_id=APP_ID,
        title=title,
        msg=message,
        duration=duration,
        icon=icon,
    )

    if open_folder:
        folder = Path(open_folder)
        if folder.exists():
            # Use a file:// URI — Windows Shell will open it in Explorer.
            uri = folder.as_uri()
            toast.add_actions(label="Open Folder", launch=uri)

    toast.set_audio(wn_audio.Default, loop=False)

    try:
        toast.show()
    except Exception as exc:
        # Never let a notification failure crash the organiser.
        print(f"[Toast error] {exc}")


def open_folder_in_explorer(folder_path: str) -> None:
    """
    Open a folder in Windows Explorer.

    Args:
        folder_path: Absolute path to the directory.
    """
    path = Path(folder_path)
    if path.exists():
        subprocess.Popen(["explorer", str(path)])


def open_folder_in_dopus(folder_path: str, dopusrt_path: str) -> None:
    """
    Open a folder in a new Directory Opus lister.

    Args:
        folder_path:  Absolute path to the directory.
        dopusrt_path: Full path to dopusrt.exe.
    """
    path = Path(folder_path)
    if not (path.exists() and dopusrt_path):
        return
    dopus_exe = Path(dopusrt_path).parent / "dopus.exe"
    subprocess.Popen([str(dopus_exe), str(path)])
