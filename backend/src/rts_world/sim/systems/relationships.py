"""Relationship term decay and cached opinion recalculation."""
from __future__ import annotations

from collections import defaultdict

from ..state import PendingEvent, RegionState, TickContext

MIN_OPINION = -100
MAX_OPINION = 100


def clamp_opinion(value: int) -> int:
    return max(MIN_OPINION, min(MAX_OPINION, value))


def decay_toward_zero(value: int, amount: int) -> int:
    if amount <= 0 or value == 0:
        return value
    if value > 0:
        return max(0, value - amount)
    return min(0, value + amount)


def relationship_dynamics(state: RegionState, ctx: TickContext) -> list[PendingEvent]:
    """Apply temporary term decay and refresh cached relationship opinions."""
    terms_by_pair: dict[tuple[int, int], list[dict[str, object]]] = defaultdict(list)
    current_tick = ctx.absolute_game_tick

    for term in state.relationship_terms:
        subject_id = int(term["subject_entity_id"])
        target_id = int(term["target_entity_id"])
        key = (subject_id, target_id)

        old_value = int(term["value"])
        new_value = old_value

        expires_at = term.get("expires_at_game_tick")
        if expires_at is not None and int(expires_at) <= current_tick:
            new_value = 0
        else:
            new_value = decay_toward_zero(old_value, int(term.get("decay_per_tick", 0)))

        if new_value != old_value:
            term["value"] = new_value
            state.mark_relationship_term_dirty(int(term["id"]))

        terms_by_pair[key].append(term)

    relationships_by_key = {
        (int(r["subject_entity_id"]), int(r["target_entity_id"])): r
        for r in state.relationships
    }

    for key, terms in terms_by_pair.items():
        opinion = clamp_opinion(sum(int(term["value"]) for term in terms))
        relationship = relationships_by_key.get(key)
        if relationship is None:
            relationship = {
                "subject_entity_id": key[0],
                "target_entity_id": key[1],
                "opinion": opinion,
                "last_updated": ctx.now,
            }
            state.relationships.append(relationship)
            relationships_by_key[key] = relationship
            state.mark_relationship_dirty(key[0], key[1])
            continue

        if int(relationship["opinion"]) != opinion:
            relationship["opinion"] = opinion
            state.mark_relationship_dirty(key[0], key[1])

    return []
