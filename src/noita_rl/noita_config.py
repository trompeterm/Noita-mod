"""Edit Noita's own settings (save_shared/config.xml) so training can run in the background."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

# Noita keeps simulating when it isn't the active window, in a window that doesn't minimize.
BACKGROUND_SETTINGS = {"application_pause_when_unfocused": "0", "fullscreen": "0"}


def default_config_path() -> Path:
    base = Path(os.environ.get("USERPROFILE", Path.home()))
    return base / "AppData" / "LocalLow" / "Nolla_Games_Noita" / "save_shared" / "config.xml"


def read_settings(text: str, names) -> dict[str, str | None]:
    found = {}
    for name in names:
        match = re.search(rf'\b{name}="([^"]*)"', text)
        found[name] = match.group(1) if match else None
    return found


def apply_settings(text: str, settings: dict[str, str]) -> str:
    for name, value in settings.items():
        pattern = rf'\b{name}="[^"]*"'
        if not re.search(pattern, text):
            raise ValueError(f"{name} not found in Noita's config.xml")
        text = re.sub(pattern, f'{name}="{value}"', text, count=1)
    return text


def configure(path: Path, settings: dict[str, str] = BACKGROUND_SETTINGS) -> tuple[dict, Path | None]:
    """Apply settings; back up the original once (config.xml.noita_rl_backup). Returns the
    previous values and the backup path (None if nothing changed)."""
    text = path.read_text(encoding="utf-8")
    before = read_settings(text, settings)
    updated = apply_settings(text, settings)
    if updated == text:
        return before, None
    backup = path.with_name(path.name + ".noita_rl_backup")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(updated, encoding="utf-8")
    return before, backup
