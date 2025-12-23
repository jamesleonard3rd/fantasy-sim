import json
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).parent.parent
GAME_SETTINGS_PATH = PROJECT_DIR / "game_data" / "config" / "game_settings.json"

_SETTINGS_CACHE: dict[str, Any] | None = None


def get_game_settings(force_reload: bool = False) -> dict[str, Any]:

    global _SETTINGS_CACHE

    if _SETTINGS_CACHE is not None and not force_reload:
        return _SETTINGS_CACHE

    try:
        content = GAME_SETTINGS_PATH.read_text()
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError(f"Game settings must be a JSON object: {GAME_SETTINGS_PATH}")
        _SETTINGS_CACHE = data
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"Game settings file not found: {GAME_SETTINGS_PATH}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in game settings file {GAME_SETTINGS_PATH}: {e}")
    except Exception as e:
        raise RuntimeError(f"Error loading game settings from {GAME_SETTINGS_PATH}: {e}")

