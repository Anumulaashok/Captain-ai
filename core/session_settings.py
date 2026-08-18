"""
Small persisted app settings — currently just the session-logging toggle.
Stored separately from config/api_keys.json since this isn't a secret.
"""
import json
import sys
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


SETTINGS_PATH = _get_base_dir() / "config" / "app_settings.json"

_DEFAULTS = {"save_logs": True}


def _load() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return {**_DEFAULTS, **data}
    except Exception:
        return dict(_DEFAULTS)


def _save(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_save_logs_enabled() -> bool:
    return bool(_load().get("save_logs", True))


def set_save_logs_enabled(enabled: bool) -> None:
    data = _load()
    data["save_logs"] = bool(enabled)
    _save(data)
