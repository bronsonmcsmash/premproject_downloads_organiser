"""
config.py — Configuration management for Project Organizer.

Handles loading and saving the JSON config file stored at:
  %APPDATA%\\ProjectOrganizer\\config.json

Default values are merged in for any keys missing from the saved file,
so the config is always forward-compatible with new settings fields.
"""

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(os.environ.get("APPDATA", "~")) / "ProjectOrganizer"
CONFIG_FILE = CONFIG_DIR / "config.json"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    "project_folder": "",
    "hotkey": "ctrl+shift+c",
    "mode": "copy",            # "copy" or "move"
    "overwrite_duplicates": False,
    "file_type_labels": {},    # overrides for folder names, e.g. {"Video": "Footage"}
    "use_subfolders": True,    # prompt for subfolder (footage/sfx/etc.) on each organise
    "use_date_folder": True,   # create YYYY-MM-DD_HH timestamp subfolder
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """
    Load the config from disk, merging with defaults for any missing keys.

    Returns:
        A dict with all expected config keys populated.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            loaded: dict = json.load(fh)

        # Start from defaults so any new keys added in future versions are
        # available even if the saved file predates them.
        merged = DEFAULT_CONFIG.copy()
        merged.update(loaded)
        return merged

    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable file — return defaults and don't crash.
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """
    Persist config dict to disk as pretty-printed JSON.

    Args:
        config: The full configuration dict to save.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
