"""Region-scoped tournament event simulation."""
from __future__ import annotations

from typing import Any

from ..state import PendingEvent, RegionState, TickContext

TERMINAL_TOURNAMENT_STATUSES = {"completed", "cancelled"}
ACTIVE_PARTICIPANT_STATUSES = {"registered", "active"}


def tournament_system(state: RegionState, ctx: TickContext) -> list[PendingEvent]:
    """Advance tournament registration and bracket rounds for this region."""
    events: list[PendingEvent] = []
    for tournament in state.tournaments:
        if tournament.get("status") in TERMINAL_TOURNAMENT_STATUSES:
            continue
        events.extend(_advance_tournament(state, tournament, ctx))
    return events


def _advance_tournament(
    state: RegionState,
    tournament: dict[str, Any],
    ctx: TickContext,
) -> list[PendingEvent]:
    events: list[PendingEvent] = []
    status = str(tournament.get("status", "scheduled"))
    current_tick = ctx.absolute_game_tick

    if status == "scheduled" and _registration_open_due(tournament, current_tick):
        tournament["status"] = "registration_open"
        state.mark_tournament_dirty(int(tournament["id"]))
        events.append(_event("tournament.registration_opened", tournament, ctx))
        status = "registration_open"

    if status == "registration_open" and _registration_close_due(tournament, current_tick):
        tournament["status"] = "registration_closed"
        state.mark_tournament_dirty(int(tournament["id"]))
        events.append(_event("tournament.registration_closed", tournament, ctx))
        status = "registration_closed"

    if status in {"scheduled", "registration_open", "registration_closed"}:
        if int(tournament["starts_at_game_tick"]) <= current_tick:
            participants = _eligible_participants(state, tournament)
            min_participants = int((tournament.get("payload") or {}).get("min_participants", 2))
            if len(participants) < min_participants:
                tournament["status"] = "cancelled"
                tournament["completed_at_game_tick"] = current_tick
                state.mark_tournament_dirty(int(tournament["id"]))
                events.append(
                    _event(
                        "tournament.cancelled",
                        tournament,
                        ctx,
                        reason="not_enough_participants",
                    )
                )
                return events
            _start_tournament(state, tournament, participants, ctx, events)

    if tournament.get("status") == "running":
        events.extend(_run_rounds(state, tournament, ctx))

    return events


def _registration_open_due(tournament: dict[str, Any], current_tick: int) -> bool:
    opens_at = tournament.get("registration_opens_at_game_tick")
    return opens_at is None or int(opens_at) <= current_tick


def _registration_close_due(tournament: dict[str, Any], current_tick: int) -> bool:
    closes_at = tournament.get("registration_closes_at_game_tick")
    return closes_at is not None and int(closes_at) <= current_tick


def _eligible_participants(
    state: RegionState,
    tournament: dict[str, Any],
) -> list[dict[str, Any]]:
    participants = state.tournament_participants_by_tournament_id.get(
        int(tournament["id"]), []
    )
    eligible = [
        participant
        for participant in participants
        if participant.get("status") in ACTIVE_PARTICIPANT_STATUSES
    ]
    return sorted(eligible, key=lambda p: (_participant_seed(p), int(p["entity_id"])))


def _start_tournament(
    state: RegionState,
    tournament: dict[str, Any],
    participants: list[dict[str, Any]],
    ctx: TickContext,
    events: list[PendingEvent],
) -> None:
    tournament["status"] = "running"
    tournament["current_round"] = max(0, int(tournament.get("current_round", 0)))
    payload = dict(tournament.get("payload") or {})
    payload.setdefault("format", "single_elimination")
    payload["remaining_entity_ids"] = [int(p["entity_id"]) for p in participants]
    payload.setdefault("rounds", [])
    tournament["payload"] = payload
    state.mark_tournament_dirty(int(tournament["id"]))

    for participant in participants:
        participant["status"] = "active"
        state.mark_tournament_participant_dirty(
            int(tournament["id"]), int(participant["entity_id"])
        )

    events.append(
        _event(
            "tournament.started",
            tournament,
            ctx,
            participant_count=len(participants),
        )
    )


def _run_rounds(
    state: RegionState,
    tournament: dict[str, Any],
    ctx: TickContext,
) -> list[PendingEvent]:
    events: list[PendingEvent] = []
    rounds_to_run = max(1, int(tournament.get("max_rounds_per_tick", 1)))
    for _ in range(rounds_to_run):
        if tournament.get("status") != "running":
            break
        payload = tournament.get("payload") or {}
        remaining = [int(entity_id) for entity_id in payload.get("remaining_entity_ids", [])]
        if len(remaining) <= 1:
            _complete_tournament(state, tournament, ctx, events, remaining[0] if remaining else None)
            break
        _run_one_round(state, tournament, remaining, ctx, events)
    return events


def _run_one_round(
    state: RegionState,
    tournament: dict[str, Any],
    remaining: list[int],
    ctx: TickContext,
    events: list[PendingEvent],
) -> None:
    tournament_id = int(tournament["id"])
    participant_by_entity = {
        int(p["entity_id"]): p
        for p in state.tournament_participants_by_tournament_id.get(tournament_id, [])
    }
    round_number = int(tournament.get("current_round", 0)) + 1
    next_remaining: list[int] = []
    match_events: list[dict[str, Any]] = []

    for index in range(0, len(remaining), 2):
        first_id = remaining[index]
        second_id = remaining[index + 1] if index + 1 < len(remaining) else None
        if second_id is None:
            next_remaining.append(first_id)
            match_events.append(
                {
                    "match": (index // 2) + 1,
                    "winner_entity_id": first_id,
                    "loser_entity_id": None,
                    "bye": True,
                }
            )
            continue

        winner_id, loser_id, scores = _resolve_match(
            participant_by_entity[first_id],
            participant_by_entity[second_id],
            ctx,
        )
        loser = participant_by_entity[loser_id]
        loser["status"] = "eliminated"
        loser["eliminated_round"] = round_number
        state.mark_tournament_participant_dirty(tournament_id, loser_id)
        next_remaining.append(winner_id)
        match_event = {
            "match": (index // 2) + 1,
            "winner_entity_id": winner_id,
            "loser_entity_id": loser_id,
            "scores": scores,
            "bye": False,
        }
        match_events.append(match_event)
        events.append(
            _event(
                "tournament.match_completed",
                tournament,
                ctx,
                round=round_number,
                **match_event,
            )
        )

    payload = dict(tournament.get("payload") or {})
    rounds = list(payload.get("rounds", []))
    rounds.append({"round": round_number, "matches": match_events})
    payload["rounds"] = rounds
    payload["remaining_entity_ids"] = next_remaining
    tournament["payload"] = payload
    tournament["current_round"] = round_number
    state.mark_tournament_dirty(tournament_id)
    events.append(
        _event(
            "tournament.round_completed",
            tournament,
            ctx,
            round=round_number,
            remaining_entity_ids=next_remaining,
        )
    )

    if len(next_remaining) == 1:
        _complete_tournament(state, tournament, ctx, events, next_remaining[0])


def _resolve_match(
    first: dict[str, Any],
    second: dict[str, Any],
    ctx: TickContext,
) -> tuple[int, int, dict[str, float]]:
    first_id = int(first["entity_id"])
    second_id = int(second["entity_id"])
    first_score = _participant_base_score(first) + ctx.rng.random()
    second_score = _participant_base_score(second) + ctx.rng.random()
    if first_score >= second_score:
        return first_id, second_id, {str(first_id): first_score, str(second_id): second_score}
    return second_id, first_id, {str(first_id): first_score, str(second_id): second_score}


def _participant_base_score(participant: dict[str, Any]) -> float:
    payload = participant.get("payload") or {}
    if payload.get("power") is not None:
        return float(payload["power"])
    seed = participant.get("seed")
    return 100.0 - float(seed) if seed is not None else 50.0


def _participant_seed(participant: dict[str, Any]) -> int:
    seed = participant.get("seed")
    return int(seed) if seed is not None else 1_000_000


def _complete_tournament(
    state: RegionState,
    tournament: dict[str, Any],
    ctx: TickContext,
    events: list[PendingEvent],
    winner_entity_id: int | None,
) -> None:
    tournament_id = int(tournament["id"])
    tournament["status"] = "completed"
    tournament["winner_entity_id"] = winner_entity_id
    tournament["completed_at_game_tick"] = ctx.absolute_game_tick
    state.mark_tournament_dirty(tournament_id)

    for participant in state.tournament_participants_by_tournament_id.get(tournament_id, []):
        entity_id = int(participant["entity_id"])
        if winner_entity_id is not None and entity_id == int(winner_entity_id):
            participant["status"] = "winner"
            state.mark_tournament_participant_dirty(tournament_id, entity_id)
        elif participant.get("status") == "active":
            participant["status"] = "eliminated"
            participant["eliminated_round"] = int(tournament.get("current_round", 0))
            state.mark_tournament_participant_dirty(tournament_id, entity_id)

    events.append(
        _event(
            "tournament.completed",
            tournament,
            ctx,
            winner_entity_id=winner_entity_id,
        )
    )
    if winner_entity_id is not None:
        events.append(
            _event(
                "tournament.winner_declared",
                tournament,
                ctx,
                winner_entity_id=winner_entity_id,
            )
        )


def _event(
    kind: str,
    tournament: dict[str, Any],
    ctx: TickContext,
    **extra: Any,
) -> PendingEvent:
    return PendingEvent(
        kind=kind,
        significance=3,
        payload={
            "tournament_id": int(tournament["id"]),
            "tournament_name": tournament.get("name"),
            "game_tick": ctx.absolute_game_tick,
            **extra,
        },
    )
