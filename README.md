# Project Organizer

A lightweight Windows system tray app for video editors and creatives working
with Adobe Premiere Pro.  Select files in **Directory Opus**, press a global
hotkey, and they are instantly sorted into your project's folder structure —
no dialogs, no friction.

---

## Features

| | |
|---|---|
| **One-key import** | Press `Ctrl+Shift+C` to copy selected DOpus files straight into your project |
| **Smart sorting** | Automatically routes files to `Video/`, `Audio/`, `Images/`, `Docs/`, `PSD/`, `AI/`, `MOGRT/`, `Compressed/`, or `Other/` |
| **Timestamped batches** | Each import lands in a `YYYY-MM-DD_HH-MM-SS` subfolder — no accidental overwrites |
| **Copy or Move** | Choose per-project whether to keep or remove source files |
| **Duplicate handling** | Auto-rename (`file_1.mp4`) or overwrite — configurable |
| **Toast feedback** | Windows notifications confirm every action; click to open the destination folder |
| **Silent auto-start** | Registers itself to run at login via the Windows registry |

---

## Requirements

- **Windows 10 or 11**
- **Python 3.10+** — download from [python.org](https://www.python.org/downloads/)
- **Directory Opus** — installed at the default path, or via a registry entry
  (`HKLM\SOFTWARE\GPSoftware\Directory Opus\InstallDir`)

---

## Installation

```bash
# 1. Clone or download the project
cd path\to\ProjectOrganizer

# 2. (Recommended) create a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Dependencies installed

| Package | Purpose |
|---|---|
| `pystray` | System tray icon and menu |
| `Pillow` | Programmatic icon generation |
| `keyboard` | Global hotkey listener |
| `pywin32` | Windows clipboard (CF_HDROP) and registry access |
| `winotify` | Windows 10/11 toast notifications |

---

## Running

```bash
# With a console window (development / testing)
python main.py

# Without a console window (normal use)
pythonw main.py
```

On first launch the app:

1. Silently registers itself in
   `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` so it starts with Windows.
2. Reads (or creates) its config file at `%APPDATA%\ProjectOrganizer\config.json`.
3. Sits in the system tray near the clock — look for the blue folder icon.
4. Shows a toast if no project folder has been set yet.

---

## Configuration

Right-click the tray icon and choose **Settings** to open the settings window.

| Setting | Default | Description |
|---|---|---|
| **Project Folder** | *(empty)* | Root directory of your active Premiere project |
| **Keyboard Shortcut** | `Ctrl+Shift+C` | Click the shortcut box, then press any combo |
| **File Mode** | Copy | Copy = originals preserved; Move = originals deleted after import |
| **Overwrite Duplicates** | Off | Off = auto-rename (`file_1.mp4`); On = silently overwrite |

Settings are saved to `%APPDATA%\ProjectOrganizer\config.json`.

---

## Folder structure created

```
MyPremiereProject/
  Video/
    2026-02-22_14-35-07/
      footage.mp4
  Audio/
    2026-02-22_14-35-07/
      voiceover.wav
  Images/
    2026-02-22_14-35-07/
      thumbnail.png
  Docs/
    2026-02-22_14-35-07/
      brief.pdf
  Compressed/
    2026-02-22_14-35-07/
      assets.zip
  PSD/
    2026-02-22_14-35-07/
      design.psd
  AI/
    2026-02-22_14-35-07/
      logo.ai
  MOGRT/
    2026-02-22_14-35-07/
      title.mogrt
  Other/
    2026-02-22_14-35-07/
      unknownfile.xyz
```

### File type mapping

| Folder | Extensions |
|---|---|
| Video | `.mp4` `.mov` `.avi` `.mkv` `.wmv` `.mxf` `.m4v` `.flv` `.webm` `.mpg` `.mpeg` |
| Audio | `.mp3` `.wav` `.aac` `.flac` `.ogg` `.m4a` `.wma` `.aiff` `.alac` |
| Images | `.jpg` `.jpeg` `.png` `.gif` `.tiff` `.tif` `.bmp` `.raw` `.cr2` `.nef` `.heic` `.webp` |
| Docs | `.doc` `.docx` `.pdf` `.txt` `.rtf` `.odt` `.xls` `.xlsx` `.ppt` `.pptx` |
| Compressed | `.zip` `.rar` `.7z` `.gz` `.tar` `.bz2` |
| PSD | `.psd` |
| AI | `.ai` |
| MOGRT | `.mogrt` |
| Other | *(everything else)* |

---

## Directory Opus integration

The hotkey uses `dopusrt.exe` to copy the currently selected files in the
active DOpus lister onto the Windows clipboard (CF_HDROP format), then reads
that clipboard data.

**Auto-detection order:**

1. `C:\Program Files\GPSoftware\Directory Opus\dopusrt.exe`
2. Registry key `HKLM\SOFTWARE\GPSoftware\Directory Opus\InstallDir`
3. Registry key `HKLM\SOFTWARE\WOW6432Node\GPSoftware\Directory Opus\InstallDir`

**Clipboard fallback** — if `dopusrt.exe` is not found, the app reads
whatever `CF_HDROP` data is already on the clipboard.  A one-time toast warns
you, and you can work around it by selecting your files in DOpus, pressing
`Ctrl+C`, and *then* pressing the organiser hotkey.

---

## Building a standalone .exe with PyInstaller

```bash
pip install pyinstaller

pyinstaller ^
  --onefile ^
  --windowed ^
  --icon assets\icon.ico ^
  --name ProjectOrganizer ^
  --add-data "assets;assets" ^
  main.py
```

The compiled executable will be in the `dist\` folder.
Update the auto-start registry value to point to `dist\ProjectOrganizer.exe`
instead of the Python script.

> **Note:** On Windows, PyInstaller `--windowed` (`-w`) produces a `.exe` that
> behaves like `pythonw` — no console window.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tray icon doesn't appear | Ensure pystray and Pillow are installed; check for error in a console with `python main.py` |
| Hotkey not responding | Run with elevated rights; some security software blocks global hooks |
| Toast notifications not showing | Ensure Windows notification settings allow Python / winotify |
| "dopusrt not found" toast | Install DOpus to the default path, or verify registry entry |
| Files not detected | Make sure files are selected (highlighted) in the *active* DOpus lister before pressing the hotkey |
| `pywin32` import error | Run `pip install pywin32` then `python Scripts/pywin32_postinstall.py -install` |

---

## Project structure

```
ProjectOrganizer/
  main.py          — Entry point: tray, hotkey, auto-start, workflow coordination
  organizer.py     — File sorting logic, DOpus integration, clipboard fallback
  settings.py      — Tkinter settings window
  config.py        — JSON config load/save
  notifications.py — winotify toast wrapper
  icon.py          — Programmatic icon generation (PIL)
  requirements.txt — pip dependencies
  README.md        — This file
  assets/
    icon.ico       — Generated automatically on first run
```

---

## License

MIT — free to use, modify, and distribute.
