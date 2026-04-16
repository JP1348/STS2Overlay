"""
find_save.py
Auto-detects the STS2 save directory on Windows and Linux.

Confirmed save path structure (from real install):
  Windows: C:\\Users\\<user>\\AppData\\Roaming\\SlayTheSpire2\\steam\\<steam_id>\\profile1\\saves
  Linux:   ~/.local/share/Steam/... (Proton) or similar
"""

import os
import sys
from pathlib import Path
from glob import glob


def find_save_dir() -> str | None:
    """
    Return the most likely STS2 save directory for the current OS.
    Returns None if not found.
    """
    if sys.platform == "win32":
        return _find_windows()
    else:
        return _find_linux()


def _find_windows() -> str | None:
    base = Path(os.environ.get("APPDATA", "")) / "SlayTheSpire2" / "steam"
    if not base.exists():
        return None

    # Find the Steam ID subfolder (numeric directory)
    steam_id_dirs = [d for d in base.iterdir() if d.is_dir() and d.name.isdigit()]
    if not steam_id_dirs:
        return None

    # Use the first (usually only) Steam ID
    steam_id_dir = steam_id_dirs[0]

    # Find profile dirs (profile1, profile2, etc.)
    profile_dirs = sorted(steam_id_dir.glob("profile*"))
    if not profile_dirs:
        return None

    saves_dir = profile_dirs[0] / "saves"
    if saves_dir.exists():
        return str(saves_dir)

    return str(profile_dirs[0])


def _find_linux() -> str | None:
    # Proton/Steam on Linux — STS2 stores saves in the Windows AppData path
    # inside the Proton prefix
    search_roots = [
        Path.home() / ".steam" / "steam" / "steamapps" / "compatdata",
        Path.home() / ".local" / "share" / "Steam" / "steamapps" / "compatdata",
    ]

    for root in search_roots:
        if not root.exists():
            continue
        # Search all Proton prefixes for SlayTheSpire2 saves
        matches = list(root.glob(
            "*/pfx/drive_c/users/steamuser/AppData/Roaming/SlayTheSpire2/steam"
        ))
        if matches:
            steam_dir = matches[0]
            steam_id_dirs = [d for d in steam_dir.iterdir()
                             if d.is_dir() and d.name.isdigit()]
            if steam_id_dirs:
                profile_dirs = sorted(steam_id_dirs[0].glob("profile*"))
                if profile_dirs:
                    saves = profile_dirs[0] / "saves"
                    return str(saves if saves.exists() else profile_dirs[0])

    return None


def find_active_run_save(saves_dir: str) -> str | None:
    """
    Find the most recently modified .save file in the saves dir that
    represents an active run (not progress.save or settings.save).
    Returns None if no active run file found.
    """
    saves_path = Path(saves_dir)

    # Look for run save files — exclude profile/settings saves
    # Active run save name TBD until confirmed from a mid-run capture.
    # Current best candidates based on STS1 conventions:
    candidates = []
    for pattern in ["*.save", "*.autosave", "run.save", "current.save"]:
        candidates += list(saves_path.glob(pattern))

    # Exclude known non-run files
    excluded = {"progress.save", "settings.save",
                "progress.save.backup", "settings.save.backup"}
    candidates = [f for f in candidates if f.name not in excluded]

    if not candidates:
        return None

    return str(max(candidates, key=lambda f: f.stat().st_mtime))
