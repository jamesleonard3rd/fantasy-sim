import json
import random
from pathlib import Path
from re import T

PROJECT_DIR = Path(__file__).parent.parent.parent.parent
GAME_DATA_DIR = PROJECT_DIR / "game_data"
RARITY_DIR = GAME_DATA_DIR / "rarity"

def load_rarity(category: str) -> dict:
    return json.loads((RARITY_DIR / f"{category}.json").read_text())

def get_magic_types_available(magic_result: dict) -> list[str]:
    """Extract the list of magic types an entity can actually use."""
    return magic_result["available_types"]


def weighted_choice(weights: dict) -> str:
    items = list(weights.keys())
    probs = list(weights.values())
    return random.choices(items, weights=probs, k=1)[0]

def generate_entity() -> dict:
    pass

def get_random_magic(race: str) -> dict:
    """
    Get random magic for a race using the new hierarchical JSON structure.

    New JSON format:
    {
        "no_magic_weight": 50,
        "types": [
            {
                "name": "Fire",
                "weight": 20,
                "no_subtype_weight": 30,
                "subtypes": [
                    {"name": "Lava", "weight": 2, "replaces_parent": true}
                ]
            }
        ],
        "race_modifiers": {"Elf": {"Arcane": 2.0}}
    }
    """
    data = load_rarity("magic")

    # Build base weights including "no magic" option
    base_weights = {"no_magic": data["no_magic_weight"]}

    # Add all magic types with their base weights
    for magic_type in data["types"]:
        base_weights[magic_type["name"]] = magic_type["weight"]

    if race in data["race_modifiers"]:
        modifiers = data["race_modifiers"][race]
        for magic_type, multiplier in modifiers.items():
            base_weights[magic_type] *= multiplier
    
    base_choice = weighted_choice(base_weights)

    # Handle no magic case
    if base_choice == "no_magic":
        return {
            "base": None,
            "subtype": None,
            "available_types": []
        }

    # Find the chosen magic type data
    chosen_type_data = next(t for t in data["types"] if t["name"] == base_choice)

    # Handle subtypes
    if chosen_type_data["subtypes"]:
        # Build subtype weights
        subtype_weights = {"no_subtype": chosen_type_data["no_subtype_weight"]}

        for subtype in chosen_type_data["subtypes"]:
            subtype_weights[subtype["name"]] = subtype["weight"]

        subtype_choice = weighted_choice(subtype_weights)

        if subtype_choice == "no_subtype":
            return {
                "base": base_choice,
                "subtype": None,
                "available_types": [base_choice]
            }
        else:
            # Find the chosen subtype data
            chosen_subtype_data = next(s for s in chosen_type_data["subtypes"] if s["name"] == subtype_choice)
            replaces_parent = chosen_subtype_data["replaces_parent"]

            return {
                "base": base_choice,
                "subtype": subtype_choice,
                "available_types": [subtype_choice] if replaces_parent else [base_choice, subtype_choice]
            }

    # No subtypes available
    return {
        "base": base_choice,
        "subtype": None,
        "available_types": [base_choice]
    }