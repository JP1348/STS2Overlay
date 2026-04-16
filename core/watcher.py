"""
watcher.py
Watches the STS2 save directory for file changes and triggers callbacks
when the autosave file is updated (i.e., the player advanced a floor).
"""

import os
import time
import threading
import traceback
from pathlib import Path


# Common STS2 save locations
SAVE_PATH_CANDIDATES = [
    # Windows — confirmed path from AppData\Roaming\SlayTheSpire2
    Path.home() / "AppData/Roaming/SlayTheSpire2/steam",
    Path.home() / "AppData/Roaming/SlayTheSpire2",
    # Linux / Proton
    Path.home() / ".steam/steam/steamapps/compatdata",
    # WSL
    Path("/mnt/c/Users"),
]


class SaveFileWatcher:
    def __init__(self, save_path: str, on_change_callback):
        """
        save_path: full path to the STS2 save directory or autosave file
        on_change_callback: function called with the new file path when a change is detected
        """
        self.save_path = Path(save_path)
        self.on_change = on_change_callback
        self._last_modified = 0
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        print(f"[Watcher] Monitoring: {self.save_path}")

    def stop(self):
        self._running = False

    def _watch_loop(self):
        while self._running:
            try:
                target = self._resolve_target()
                if target and target.exists():
                    mtime = target.stat().st_mtime
                    if mtime != self._last_modified:
                        self._last_modified = mtime
                        print(f"[Watcher] Change detected: {target}")
                        self.on_change(str(target))
            except Exception as e:
                print(f"[Watcher] Error: {e}")
                traceback.print_exc()
            time.sleep(0.4)  # poll every 0.4 seconds

    def _resolve_target(self) -> Path:
        """If given a directory, find the most recently modified active run .save file."""
        if self.save_path.is_file():
            return self.save_path
        if self.save_path.is_dir():
            # STS2 uses .save files. Exclude known non-run files.
            excluded = {"progress.save", "settings.save", "prefs.save",
                        "progress.save.backup", "settings.save.backup",
                        "prefs.save.backup"}
            saves = [
                f for f in self.save_path.glob("**/*.save")
                if f.name not in excluded
            ]
            if saves:
                return max(saves, key=lambda f: f.stat().st_mtime)
        return None
