from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PREFERENCES_FILENAME = "preferences.json"


@dataclass(frozen=True)
class AppPreferences:
    output_dir: str = ""
    update_check_on_startup: bool = False


def preferences_dir() -> Path:
    if sys.platform.startswith("win"):
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "EmployeurD-MegaGest"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "EmployeurD-MegaGest"
    root = os.environ.get("XDG_CONFIG_HOME")
    if root:
        return Path(root) / "employeurd-megagest"
    return Path.home() / ".config" / "employeurd-megagest"


def preferences_path() -> Path:
    return preferences_dir() / PREFERENCES_FILENAME


def load_preferences(path: Path | None = None) -> AppPreferences:
    target = path or preferences_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppPreferences()
    if not isinstance(data, dict):
        return AppPreferences()
    return AppPreferences(
        output_dir=_clean_string(data.get("output_dir", "")),
        update_check_on_startup=bool(data.get("update_check_on_startup", False)),
    )


def save_preferences(preferences: AppPreferences, path: Path | None = None) -> Path:
    target = path or preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "output_dir": preferences.output_dir,
        "update_check_on_startup": preferences.update_check_on_startup,
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def remember_output_dir(output_dir: str, path: Path | None = None) -> Path:
    current = load_preferences(path)
    return save_preferences(
        AppPreferences(output_dir=_clean_string(output_dir), update_check_on_startup=current.update_check_on_startup),
        path=path,
    )


def remember_update_check_on_startup(enabled: bool, path: Path | None = None) -> Path:
    current = load_preferences(path)
    return save_preferences(AppPreferences(output_dir=current.output_dir, update_check_on_startup=enabled), path=path)


def _clean_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
