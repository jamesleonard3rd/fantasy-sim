import copy
import json
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[3]
GAME_SETTINGS_PATH = PROJECT_DIR / "game_data" / "config" / "game_settings.json"

_SETTINGS_CACHE: dict[str, Any] | None = None


def _load_game_settings_file() -> dict[str, Any]:
    """Read and parse ``game_settings.json`` from disk (does not touch the cache)."""
    try:
        content = GAME_SETTINGS_PATH.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError(f"Game settings must be a JSON object: {GAME_SETTINGS_PATH}")
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"Game settings file not found: {GAME_SETTINGS_PATH}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in game settings file {GAME_SETTINGS_PATH}: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Error loading game settings from {GAME_SETTINGS_PATH}: {e}") from e


def _write_game_settings_file(data: dict[str, Any]) -> None:
    GAME_SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _deep_merge_inplace(base: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            _deep_merge_inplace(base[key], value)
        else:
            base[key] = value


def merge_game_settings_in_memory(patch: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of on-disk settings merged with ``patch`` (no I/O)."""
    if not isinstance(patch, dict):
        raise TypeError("patch must be a dict")
    merged = copy.deepcopy(_load_game_settings_file())
    _deep_merge_inplace(merged, patch)
    return merged


def commit_game_settings(merged: dict[str, Any]) -> None:
    """Persist ``merged`` to disk and replace the in-memory cache."""
    _write_game_settings_file(merged)
    global _SETTINGS_CACHE
    _SETTINGS_CACHE = merged


def merge_and_save_game_settings(patch: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``patch`` into the file on disk and refresh the in-memory cache."""
    merged = merge_game_settings_in_memory(patch)
    commit_game_settings(merged)
    return merged


def get_game_settings(force_reload: bool = False) -> dict[str, Any]:
    global _SETTINGS_CACHE

    if _SETTINGS_CACHE is not None and not force_reload:
        return _SETTINGS_CACHE

    try:
        data = _load_game_settings_file()
        _SETTINGS_CACHE = data
        return data
    except FileNotFoundError:
        raise
    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Error loading game settings from {GAME_SETTINGS_PATH}: {e}") from e
