"""Small persistent settings file.

Deliberately a plain JSON file rather than GSettings: a GSettings schema
has to be compiled and installed system-wide before the app can even read
its own defaults, which would make ``./bin/appsweep`` from a checkout fail
in a way that has nothing to do with what the user asked for.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

APP_DIR_NAME = "appsweep"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / APP_DIR_NAME


def config_file() -> Path:
    return config_dir() / "settings.json"


def load() -> dict[str, Any]:
    try:
        with open(config_file(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict[str, Any]) -> bool:
    """Write settings atomically. Returns False if it could not be saved."""
    try:
        config_dir().mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(config_dir()), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, config_file())
    except OSError:
        return False
    return True


def get(key: str, default: Any = None) -> Any:
    return load().get(key, default)


def set(key: str, value: Any) -> bool:            # noqa: A001 - mirrors get
    data = load()
    data[key] = value
    return save(data)
