"""
idm_source.py — Internet Download Manager integration for Project Organizer.

When the foreground window is IDM, reads the selected download's file path
directly from IDM's ListView via cross-process Win32 memory access.

IDM is a 32-bit process (WoW64), so LVITEMW uses 32-bit pointers.

Column layout (discovered empirically on IDM 6.42):
  col[ 0] = filename
  col[ 9] = path relative to %USERPROFILE% (e.g. "Downloads\\Programs\\foo.exe")

Full path = os.environ['USERPROFILE'] / col[9]
Fallback  = registry LocalPathW / col[0]
"""

import ctypes
import os
import struct
import winreg
from pathlib import Path
from typing import Optional

import win32gui
import win32process

# ---------------------------------------------------------------------------
# IDM window constants
# ---------------------------------------------------------------------------

_IDM_CLASS        = '#32770'
_IDM_TITLE_SUBSTR = 'Internet Download Manager'
_IDM_LV_CLASS     = 'SysListView32'
_IDM_LV_NAME      = 'List2'

# ---------------------------------------------------------------------------
# ListView message constants
# ---------------------------------------------------------------------------

_LVM_FIRST        = 0x1000
_LVM_GETITEMCOUNT = _LVM_FIRST + 4
_LVM_GETNEXTITEM  = _LVM_FIRST + 12
_LVM_GETITEMTEXTW = _LVM_FIRST + 115
_LVNI_SELECTED    = 2
_LVIF_TEXT        = 1

# LVITEMW field offsets for a 32-bit process (IDM is WoW64):
#   mask(4)  iItem(4)  iSubItem(4)  state(4)  stateMask(4)
#   pszText(4 — 32-bit ptr)  cchTextMax(4)  ...
_OFF_MASK       =  0
_OFF_IITEM      =  4
_OFF_ISUBITEM   =  8
_OFF_PSZTEXT    = 20   # 32-bit pointer
_OFF_CCHTEXTMAX = 24
_STRUCT_SIZE    = 40   # total LVITEMW size for 32-bit


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_idm_hwnd() -> Optional[int]:
    """Return the hwnd of IDM's main window, or None if not found."""
    result = [None]

    def _cb(hwnd, _):
        if (win32gui.GetClassName(hwnd) == _IDM_CLASS
                and _IDM_TITLE_SUBSTR in win32gui.GetWindowText(hwnd)):
            result[0] = hwnd
        return True

    win32gui.EnumWindows(_cb, None)
    return result[0]


def _idm_download_dir() -> str:
    """Return IDM's configured download directory from the registry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\DownloadManager') as k:
            raw, _ = winreg.QueryValueEx(k, 'LocalPathW')
            if isinstance(raw, bytes):
                return raw.decode('utf-16-le').rstrip('\x00')
            return str(raw)
    except OSError:
        return str(Path.home() / 'Downloads')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_idm_foreground() -> bool:
    """
    Return True if the currently focused window is IDM or a child of IDM.

    Walks up the parent-window chain from the foreground window so that
    dialogs and sub-panels within IDM are also recognised.
    """
    idm_hwnd = _find_idm_hwnd()
    if not idm_hwnd:
        return False

    hwnd = win32gui.GetForegroundWindow()
    while hwnd:
        if hwnd == idm_hwnd:
            return True
        hwnd = win32gui.GetParent(hwnd)
    return False


def get_idm_selected_file() -> Optional[str]:
    """
    Return the full path of the currently selected download in IDM.

    Strategy:
      1. Find IDM's main window and its SysListView32 download list.
      2. Get the selected row index via LVM_GETNEXTITEM.
      3. Read col[9] (USERPROFILE-relative path) and col[0] (filename)
         from the remote 32-bit process using VirtualAllocEx + ReadProcessMemory.
      4. Reconstruct the absolute path and verify the file exists on disk.
         Primary:  USERPROFILE / col[9]
         Fallback: IDM download dir / col[0]

    Returns:
        Absolute path string if found on disk, otherwise None.
    """
    idm_hwnd = _find_idm_hwnd()
    if not idm_hwnd:
        return None

    lv = win32gui.FindWindowEx(idm_hwnd, 0, _IDM_LV_CLASS, _IDM_LV_NAME)
    if not lv:
        return None

    sel = ctypes.windll.user32.SendMessageW(lv, _LVM_GETNEXTITEM, -1, _LVNI_SELECTED)
    if sel < 0:
        return None

    pid = win32process.GetWindowThreadProcessId(lv)[1]
    KERNEL32 = ctypes.windll.kernel32
    hproc = KERNEL32.OpenProcess(0x001F0FFF, False, pid)
    if not hproc:
        return None

    BUF_CHARS = 512
    TXT_SIZE  = BUF_CHARS * 2          # UTF-16 bytes
    total     = _STRUCT_SIZE + TXT_SIZE
    remote    = KERNEL32.VirtualAllocEx(hproc, None, total, 0x3000, 0x04)
    if not remote:
        KERNEL32.CloseHandle(hproc)
        return None

    try:
        def _read_col(col: int) -> str:
            buf     = bytearray(total)
            txt_ptr = remote + _STRUCT_SIZE

            struct.pack_into('<I', buf, _OFF_MASK,       _LVIF_TEXT)
            struct.pack_into('<i', buf, _OFF_IITEM,      sel)
            struct.pack_into('<i', buf, _OFF_ISUBITEM,   col)
            struct.pack_into('<I', buf, _OFF_PSZTEXT,    txt_ptr)
            struct.pack_into('<i', buf, _OFF_CCHTEXTMAX, BUF_CHARS)

            written = ctypes.c_size_t(0)
            KERNEL32.WriteProcessMemory(
                hproc, remote, bytes(buf), total, ctypes.byref(written))
            ctypes.windll.user32.SendMessageW(lv, _LVM_GETITEMTEXTW, sel, remote)

            out  = (ctypes.c_char * TXT_SIZE)()
            read = ctypes.c_size_t(0)
            KERNEL32.ReadProcessMemory(
                hproc, remote + _STRUCT_SIZE, out, TXT_SIZE, ctypes.byref(read))
            return bytes(out).decode('utf-16-le', errors='replace').rstrip('\x00')

        rel_path = _read_col(9)   # e.g. "Downloads\Programs\foo.exe"
        filename  = _read_col(0)  # e.g. "foo.exe"

    finally:
        KERNEL32.VirtualFreeEx(hproc, remote, 0, 0x8000)
        KERNEL32.CloseHandle(hproc)

    # Primary: USERPROFILE / col[9]
    if rel_path:
        full = Path(os.environ.get('USERPROFILE', str(Path.home()))) / rel_path
        if full.is_file():
            return str(full)

    # Fallback: IDM download dir / filename
    if filename:
        full = Path(_idm_download_dir()) / filename
        if full.is_file():
            return str(full)

    return None
