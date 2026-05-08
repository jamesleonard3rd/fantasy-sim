import json
import random
from pathlib import Path
from typing import Any, cast
from ..config import get_game_settings

PROJECT_DIR = Path(__file__).resolve().parents[4]
GAME_DATA_DIR = PROJECT_DIR / "game_data"
RARITY_DIR = GAME_DATA_DIR / "rarity"
TRAITS_RARITY_DIR = RARITY_DIR / "traits"
NAMES_DIR = GAME_DATA_DIR / "names"
TRAITS_PATH = GAME_DATA_DIR / "traits" / "traits.json"
_NAMES_CACHE: dict[str, dict[str, list[str]]] = {}
_RARITY_CACHE: dict[str, dict[str, Any]] = {}
_TRAITS_CACHE: dict[str, Any] = {}  # master traits keyed by name
_TRAIT_WEIGHTS_CACHE: dict[str, dict[str, float]] = {}

def _format_race_key(race_name: str) -> str:
    return race_name.lower().replace(" ", "_")

def load_names_for_race(race_name: str) -> dict[str, list[str]]:
    cache_key = _format_race_key(race_name)
    if cache_key in _NAMES_CACHE:
        return _NAMES_CACHE[cache_key]

    path = NAMES_DIR / f"{cache_key}.json"
    if not path.exists():
        raise FileNotFoundError(f"No name file found for race '{race_name}' in {NAMES_DIR}")

    try:
        content = path.read_text()
        data = json.loads(content)
        names = cast(dict[str, list[str]], data)
        _NAMES_CACHE[cache_key] = names
        return names
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in names file {path}: {e}")
    except Exception as e:
        raise RuntimeError(f"Error loading names for race '{race_name}' from {path}: {e}")

def load_traits_master() -> dict[str, Any]:
    if _TRAITS_CACHE:
        return _TRAITS_CACHE

    try:
        content = TRAITS_PATH.read_text()
        data = json.loads(content)
        traits_list = data.get("traits", [])
        if not isinstance(traits_list, list):
            raise ValueError("Expected 'traits' to be a list in traits.json")
        for trait in traits_list:
            name = trait.get("name")
            if not isinstance(name, str):
                raise ValueError("Trait missing string 'name'")
            _TRAITS_CACHE[name] = trait
        return _TRAITS_CACHE
    except FileNotFoundError:
        raise FileNotFoundError(f"Traits file not found: {TRAITS_PATH}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in traits file {TRAITS_PATH}: {e}")
    except Exception as e:
        raise RuntimeError(f"Error loading traits from {TRAITS_PATH}: {e}")

def load_trait_weights_for_race(race_name: str) -> dict[str, float]:
    cache_key = _format_race_key(race_name)
    if cache_key in _TRAIT_WEIGHTS_CACHE:
        return _TRAIT_WEIGHTS_CACHE[cache_key]

    master = load_traits_master()

    weights: dict[str, float] = {}

    common_path = TRAITS_RARITY_DIR / "common.json"
    if common_path.exists():
        data = json.loads(common_path.read_text())
        weights.update(data.get("weights", {}))

    race_path = TRAITS_RARITY_DIR / f"{cache_key}.json"
    if not race_path.exists():
        raise FileNotFoundError(f"No trait rarity file found for race '{race_name}' in {TRAITS_RARITY_DIR}")
    race_data = json.loads(race_path.read_text())
    weights.update(race_data.get("weights", {}))

    blocked = set(race_data.get("blocked", []))
    for trait in blocked:
        weights.pop(trait, None)

    invalid = [name for name in weights.keys() if name not in master]
    if invalid:
        raise ValueError(f"Trait weights reference undefined traits: {invalid}")

    _TRAIT_WEIGHTS_CACHE[cache_key] = weights
    return weights

def load_rarity(category: str) -> dict[str, Any]:
    if category in _RARITY_CACHE:
        return _RARITY_CACHE[category]

    file_path = RARITY_DIR / f"{category}.json"
    try:
        content = file_path.read_text()
        data = json.loads(content)
        result = cast(dict[str, Any], data)
        _RARITY_CACHE[category] = result
        return result
    except FileNotFoundError:
        raise FileNotFoundError(f"Rarity file not found: {file_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in rarity file {file_path}: {e}")
    except Exception as e:
        raise RuntimeError(f"Error loading rarity data from {file_path}: {e}")

def get_magic_types_available(magic_result: dict[str, Any]) -> list[str]:
    return cast(list[str], magic_result["available_types"])

def weighted_choice(weights: dict[str, float]) -> str:
    items = list(weights.keys())
    probs = list(weights.values())
    return random.choices(items, weights=probs, k=1)[0]

def get_random_race() -> str:
    data: dict[str, Any] = load_rarity("races")
    return weighted_choice(data["weights"])

def get_starting_traits(race_name: str) -> list[str]:
    settings: dict[str, Any] = get_game_settings()
    trait_num_weights: dict[str, float] = settings["traits"]["starting_trait_counts"]
    num_starting_traits = int(weighted_choice(trait_num_weights))

    weights = load_trait_weights_for_race(race_name).copy()
    if not weights or num_starting_traits <= 0:
        return []

    picks: list[str] = []
    for _ in range(min(num_starting_traits, len(weights))):
        chosen = weighted_choice(weights)
        picks.append(chosen)
        weights.pop(chosen, None)

    return picks

def get_random_name(race: str) -> str:
    names = load_names_for_race(race)

    male = names.get("male", [])
    female = names.get("female", [])
    if not male and not female:
        raise ValueError(f"No first names found for race '{race}'")

    first_pools: list[list[str]] = []
    if male:
        first_pools.append(male)
    if female:
        first_pools.append(female)

    first_pool = random.choice(first_pools)
    first = random.choice(first_pool)

    surnames = names.get("surnames", [])
    if surnames:
        last = random.choice(surnames)
        return f"{first} {last}"
    return first

def get_random_magic(race: str) -> dict[str, Any]:
    data: dict[str, Any] = load_rarity("magic")

    race_counts = data.get("race_magic_counts", {})
    count_weights: dict[str, float] = race_counts.get(race, race_counts.get("default", {"0": 100}))
    magic_count = int(weighted_choice(count_weights))

    base_weights: dict[str, float] = {}

    for magic_type in data["types"]:
        base_weights[magic_type["name"]] = magic_type["weight"]

    if race in data["race_modifiers"]:
        modifiers: dict[str, float] = data["race_modifiers"][race]
        for magic_type, multiplier in modifiers.items():
            if magic_type in base_weights:
                base_weights[magic_type] *= multiplier

    if magic_count <= 0 or not base_weights:
        return {
            "base": None,
            "subtype": None,
            "available_types": []
        }

    picks: list[dict[str, Any]] = []
    weights_pool = base_weights.copy()

    for _ in range(min(magic_count, len(weights_pool))):
        base_choice: str = weighted_choice(weights_pool)
        chosen_type_data: dict[str, Any] = next(t for t in data["types"] if t["name"] == base_choice)

        # Handle subtypes
        subtype: str | None = None
        available: list[str] = []
        if chosen_type_data["subtypes"]:
            subtype_weights: dict[str, float] = {"no_subtype": chosen_type_data["no_subtype_weight"]}
            for st in chosen_type_data["subtypes"]:
                subtype_weights[st["name"]] = st["weight"]
            subtype_choice: str = weighted_choice(subtype_weights)
            if subtype_choice != "no_subtype":
                subtype = subtype_choice
                chosen_subtype_data: dict[str, Any] = next(s for s in chosen_type_data["subtypes"] if s["name"] == subtype_choice)
                replaces_parent: bool = chosen_subtype_data["replaces_parent"]
                available = [subtype_choice] if replaces_parent else [base_choice, subtype_choice]
            else:
                available = [base_choice]
        else:
            available = [base_choice]

        picks.append({
            "base": base_choice,
            "subtype": subtype,
            "available_types": available
        })

        weights_pool.pop(base_choice, None)

    if not picks:
        return {
            "base": None,
            "subtype": None,
            "available_types": []
        }

    primary = picks[0]
    combined_available = []
    for p in picks:
        combined_available.extend(p["available_types"])

    return {
        "base": primary["base"],
        "subtype": primary["subtype"],
        "available_types": combined_available
    }

def _normalize_magic_entry(magic: Any) -> dict[str, Any]:
    """
    Normalize magic data to the common dict format with keys:
    base, subtype, available_types.
    Accepts either the existing dict shape or a list of magic names.
    """
    if isinstance(magic, dict):
        return {
            "base": magic.get("base"),
            "subtype": magic.get("subtype"),
            "available_types": magic.get("available_types", []),
        }
    if isinstance(magic, list):
        base = magic[0] if magic else None
        return {
            "base": base,
            "subtype": None,
            "available_types": magic,
        }
    return {"base": None, "subtype": None, "available_types": []}


def generate_entity(race: str | None = None) -> dict[str, Any]:
    chosen_race = race or get_random_race()
    name = get_random_name(chosen_race)
    traits = get_starting_traits(chosen_race)
    magic = get_random_magic(chosen_race)
    return {
        "id": None,
        "name": name,
        "race": chosen_race,
        "traits": traits,
        "magic": _normalize_magic_entry(magic),
        "house": None,
        "role": None,
        "gender": None,
        "age": None,
        "notes": None,
    }


def generate_entity_from_template(template: dict[str, Any]) -> dict[str, Any]:
    race = template.get("race", "Human")
    magic_raw = template.get("magic", [])
    magic = _normalize_magic_entry(magic_raw)
    return {
        "id": template.get("id"),
        "name": template.get("name"),
        "race": race,
        "traits": template.get("traits", []),
        "magic": magic,
        "house": template.get("house"),
        "role": template.get("role"),
        "gender": template.get("gender"),
        "age": template.get("age"),
        "notes": template.get("notes"),
    }