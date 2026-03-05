"""
organizer.py — Core file-sorting logic for Project Organizer.

Responsibilities:
  1. Locate dopusrt.exe (Directory Opus command runner).
  2. Get the user's currently selected files from Directory Opus via
     dopusrt, falling back to the Windows clipboard (CF_HDROP) if
     dopusrt is unavailable or returns nothing.
  3. Sort files into typed subfolders under the active project root,
     each inside a timestamped sub-subfolder (YYYY-MM-DD_HH-MM-SS).
  4. Handle copy vs. move and duplicate-file renaming.

Directory Opus integration notes
---------------------------------
dopusrt.exe /cmd "Copy CLIPBOARD NOPROGRESS" instructs DOpus to copy
whatever is currently selected in its active lister onto the Windows
clipboard in CF_HDROP (file-drop) format — exactly the same data
structure that Explorer's Ctrl+C produces.  We then read that clipboard
data with win32clipboard.

The clipboard sequence number is checked before and after the command
to detect whether DOpus actually wrote anything new.
"""

import os
import shutil
import subprocess
import time
import winreg
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import win32clipboard
import win32con

# ---------------------------------------------------------------------------
# File type → destination folder mapping
# ---------------------------------------------------------------------------

FILE_TYPES: dict = {
    "Video":      [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".mxf", ".m4v",
                   ".flv", ".webm", ".mpg", ".mpeg"],
    "Audio":      [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma",
                   ".aiff", ".alac"],
    "Images":     [".jpg", ".jpeg", ".png", ".gif", ".tiff", ".tif", ".bmp",
                   ".raw", ".cr2", ".nef", ".heic", ".webp"],
    "Docs":       [".doc", ".docx", ".pdf", ".txt", ".rtf", ".odt",
                   ".xls", ".xlsx", ".ppt", ".pptx"],
    "Compressed": [".zip", ".rar", ".7z", ".gz", ".tar", ".bz2"],
    "PSD":        [".psd"],
    "AI":         [".ai"],
    "MOGRT":      [".mogrt"],
    "Subtitles":  [".srt"],
}

# Fast extension → folder-name lookup built once at import time.
_EXT_MAP: dict = {
    ext.lower(): folder
    for folder, exts in FILE_TYPES.items()
    for ext in exts
}

# Default dopusrt install path.
_DOPUS_DEFAULT = r"C:\Program Files\GPSoftware\Directory Opus\dopusrt.exe"


# ---------------------------------------------------------------------------
# dopusrt discovery
# ---------------------------------------------------------------------------

def find_dopusrt() -> Optional[str]:
    """
    Locate dopusrt.exe by checking the default install path and the registry.

    Checks:
      1. Hard-coded default: C:\\Program Files\\GPSoftware\\Directory Opus\\dopusrt.exe
      2. HKLM\\SOFTWARE\\GPSoftware\\Directory Opus\\InstallDir  (64-bit)
      3. HKLM\\SOFTWARE\\WOW6432Node\\GPSoftware\\Directory Opus\\InstallDir  (32-bit)

    Returns:
        Absolute path string to dopusrt.exe if found, otherwise None.
    """
    if Path(_DOPUS_DEFAULT).exists():
        return _DOPUS_DEFAULT

    registry_lookups = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\GPSoftware\Directory Opus"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\GPSoftware\Directory Opus"),
    ]

    for hive, key_path in registry_lookups:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                candidate = Path(install_dir) / "dopusrt.exe"
                if candidate.exists():
                    return str(candidate)
        except OSError:
            continue

    return None


# ---------------------------------------------------------------------------
# Clipboard helpers
# ---------------------------------------------------------------------------

def _read_clipboard_hdrop() -> List[str]:
    """
    Read CF_HDROP file paths from the Windows clipboard.

    Returns:
        List of absolute file-path strings; empty list if nothing applicable
        is on the clipboard or any error occurs.
    """
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_HDROP):
                data = win32clipboard.GetClipboardData(win32con.CF_HDROP)
                return list(data) if data else []
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass
    return []


def _snapshot_clipboard_sequence() -> int:
    """
    Return the current clipboard sequence number.

    Windows increments this counter every time the clipboard changes.
    We use it to detect whether DOpus actually wrote anything new.

    Returns:
        The current sequence number, or -1 on failure.
    """
    try:
        import ctypes
        return ctypes.windll.user32.GetClipboardSequenceNumber()
    except Exception:
        return -1


# ---------------------------------------------------------------------------
# Directory Opus file retrieval
# ---------------------------------------------------------------------------

def _get_files_via_dopus(dopusrt_path: str) -> List[str]:
    """
    Ask Directory Opus to copy the active lister's selected files to the
    Windows clipboard, then read the clipboard.

    Strategy:
      1. Record the clipboard sequence number before the command.
      2. Run:  dopusrt.exe /cmd "Copy CLIPBOARD NOPROGRESS"
      3. Wait 350 ms for DOpus to populate the clipboard.
      4. If the sequence number changed, read CF_HDROP from the clipboard.
         Otherwise DOpus didn't touch the clipboard (nothing was selected).

    Note: The clipboard is intentionally overwritten — the user triggered
    the organiser hotkey specifically to capture their DOpus selection,
    so clobbering the existing clipboard content is expected behaviour.

    Args:
        dopusrt_path: Absolute path to dopusrt.exe.

    Returns:
        List of selected file-path strings; empty if nothing was selected or
        if an error occurred.
    """
    seq_before = _snapshot_clipboard_sequence()

    try:
        subprocess.run(
            [dopusrt_path, "/cmd", "Clipboard", "COPY"],
            timeout=5,
            capture_output=True,
        )
        # Give DOpus time to write to the clipboard.
        time.sleep(0.35)

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []

    # If the sequence number did not change, DOpus wrote nothing.
    seq_after = _snapshot_clipboard_sequence()
    if seq_after == seq_before and seq_before != -1:
        return []

    return _read_clipboard_hdrop()


# ---------------------------------------------------------------------------
# Public file-retrieval entry point
# ---------------------------------------------------------------------------

def get_selected_files(
    dopusrt_path: Optional[str] = None,
) -> Tuple[List[str], bool]:
    """
    Return the files currently selected by the user.

    Source priority:
      1. Internet Download Manager — if IDM is the foreground window and has
         a selected download whose file exists on disk.
      2. Directory Opus — via dopusrt if available.
      3. Clipboard fallback — CF_HDROP data already on the clipboard.

    Args:
        dopusrt_path: Path to dopusrt.exe.  If None, auto-detected.

    Returns:
        Tuple of (file_paths, used_fallback).
        used_fallback is True when the clipboard-fallback path was taken.
    """
    # ── 1. IDM ───────────────────────────────────────────────────────────
    try:
        from idm_source import get_idm_selected_file, is_idm_foreground
        if is_idm_foreground():
            idm_file = get_idm_selected_file()
            if idm_file:
                return [idm_file], False
    except Exception:
        pass

    # ── 2. Directory Opus ────────────────────────────────────────────────
    if dopusrt_path is None:
        dopusrt_path = find_dopusrt()

    if dopusrt_path:
        try:
            files = _get_files_via_dopus(dopusrt_path)
            if files:
                return files, False
        except Exception:
            pass

    # ── 3. Clipboard fallback ────────────────────────────────────────────
    return _read_clipboard_hdrop(), True


# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------

def classify_file(file_path: Path) -> str:
    """
    Return the destination folder name for a file based on its extension.

    Args:
        file_path: Path object for the source file.

    Returns:
        A folder name string such as "Video", "Audio", "Images", or "Other".
    """
    return _EXT_MAP.get(file_path.suffix.lower(), "Other")


# ---------------------------------------------------------------------------
# Duplicate handling
# ---------------------------------------------------------------------------

def _unique_path(dest: Path) -> Path:
    """
    Return dest if it does not exist, otherwise append _1, _2, … until
    a non-existing path is found.

    Args:
        dest: Desired destination path.

    Returns:
        A Path that does not currently exist on disk.
    """
    if not dest.exists():
        return dest

    stem   = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1

    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Chunked copy helper
# ---------------------------------------------------------------------------

_CHUNK = 4 * 1024 * 1024  # 4 MB per read/write


def _copy_with_progress(
    src: Path,
    dst: Path,
    callback: Optional[Callable[[int, int], None]],
) -> None:
    """
    Copy src → dst in chunks, calling callback(bytes_done, total_bytes) after
    each chunk.  Metadata (timestamps, permissions) is preserved via copystat.
    """
    total = src.stat().st_size
    copied = 0
    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            buf = fsrc.read(_CHUNK)
            if not buf:
                break
            fdst.write(buf)
            copied += len(buf)
            if callback is not None:
                callback(copied, total)
    shutil.copystat(str(src), str(dst))


# ---------------------------------------------------------------------------
# Core organiser
# ---------------------------------------------------------------------------

def organise_files(
    file_paths: List[str],
    project_folder: str,
    mode: str = "copy",
    overwrite_duplicates: bool = False,
    file_type_labels: Optional[dict] = None,
    subfolder_choices: Optional[dict] = None,
    use_date_folder: bool = True,
    progress_callback: Optional[Callable] = None,
) -> Tuple[int, str, List[str]]:
    """
    Copy or move a list of files into the structured project folder.

    Each file is placed inside:
      <project_folder>/<TypeFolder>[/<SubFolder>][/<YYYY-MM-DD_HH>]/<filename>

    SubFolder is included when subfolder_choices maps the file's type to a
    subfolder name (e.g. {"Video": "footage", "Audio": "sfx"}).
    The date layer is included when use_date_folder is True.

    The timestamp is computed once for the entire batch so all files from
    a single hotkey invocation land in the same subfolder.

    Args:
        file_paths:          Absolute paths of the source files to process.
        project_folder:      Root path of the active project.
        mode:                "copy" (default) or "move".
        overwrite_duplicates: If True, overwrite existing files with the same
                              name.  If False (default), auto-rename instead.
        subfolder_choices:   Optional dict mapping canonical type name to a
                             chosen subfolder string, e.g. {"Video": "footage"}.
        use_date_folder:     If True (default), nest files in a YYYY-MM-DD_HH
                             timestamped folder.
        progress_callback:   Optional callable(event, *args).  Events:
                               ("file",     idx, name, size_bytes)
                               ("progress", bytes_done, size_bytes)
                               ("file_done",)
                               ("done",)

    Returns:
        Tuple of (success_count, last_dest_folder, errors).
          success_count    — number of files successfully processed.
          last_dest_folder — destination subfolder of the last successful
                             file (used for the "Open Folder" toast action).
          errors           — list of human-readable error strings.
    """
    timestamp     = datetime.now().strftime("%Y-%m-%d_%H")
    project_root  = Path(project_folder)
    labels        = file_type_labels or {}
    choices       = subfolder_choices or {}
    success_count = 0
    last_dest_dir = ""
    errors: List[str] = []

    cb = progress_callback  # short alias

    for file_idx, src_str in enumerate(file_paths, start=1):
        src = Path(src_str)

        # Skip non-existent paths and directories (only handle files).
        if not src.exists():
            errors.append(f"Source not found: {src.name}")
            continue
        if not src.is_file():
            continue

        file_size = src.stat().st_size
        if cb is not None:
            cb("file", file_idx, src.name, file_size)

        canonical   = classify_file(src)
        type_folder = labels.get(canonical, canonical)
        dest_dir    = project_root / type_folder
        if canonical in choices:
            dest_dir = dest_dir / choices[canonical]
        if use_date_folder:
            dest_dir = dest_dir / timestamp
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_path = dest_dir / src.name
        if not overwrite_duplicates:
            dest_path = _unique_path(dest_path)

        def _progress_cb(done: int, total: int) -> None:
            if cb is not None:
                cb("progress", done, total)

        try:
            if mode == "move":
                # Try a same-drive rename first (instant, no progress needed).
                try:
                    os.rename(str(src), str(dest_path))
                    if cb is not None:
                        cb("progress", file_size, file_size)
                except OSError:
                    # Cross-drive move: copy with progress then delete source.
                    _copy_with_progress(src, dest_path, _progress_cb)
                    src.unlink()
            else:
                _copy_with_progress(src, dest_path, _progress_cb)

            success_count += 1
            last_dest_dir  = str(dest_dir)
            if cb is not None:
                cb("file_done")

        except PermissionError as exc:
            errors.append(f"Permission denied — {src.name}: {exc}")
        except shutil.Error as exc:
            errors.append(f"File error — {src.name}: {exc}")
        except OSError as exc:
            errors.append(f"OS error — {src.name}: {exc}")

    if cb is not None:
        cb("done")

    return success_count, last_dest_dir, errors
