from __future__ import annotations

import sys
from pathlib import Path


def application_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path.cwd()


def default_config_dir() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        bundled_config = Path(frozen_root) / "config"
        if bundled_config.exists():
            return bundled_config

    cwd_config = Path.cwd() / "config"
    if cwd_config.exists():
        return cwd_config
    bundled_config = application_root() / "config"
    if bundled_config.exists():
        return bundled_config
    return cwd_config
