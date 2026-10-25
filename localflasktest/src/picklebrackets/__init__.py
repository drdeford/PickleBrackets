"""Small, deterministic rec-play schedules with no web or simulator dependency.

Court zero is the top court. Player IDs are zero-based. Session dictionaries
contain JSON values only; callers should authenticate them before accepting
them from a browser. Each advance returns new state and leaves its input alone.
"""

from copy import deepcopy
from dataclasses import dataclass
from random import Random
from typing import Any, Sequence


SYSTEMS = ("random", "full", "steve", "joe", "pool1", "pool2", "swiss")
KING_SYSTEMS = ("full", "steve", "joe")


@dataclass(frozen=True)
class Match:
    team_a: tuple[int, int]
    team_b: tuple[int, int]


@dataclass(frozen=True)
class Round:
    matches: tuple[Match, ...]
    byes: tuple[int, ...]
    number: int


def _validate_config(system: str, n: int, seed: int) -> None:
    if system not in SYSTEMS:
        raise ValueError("Choose a supported play system.")
    if type(n) is not int or not 4 <= n <= 24:
        raise ValueError("Choose between 4 and 24 players.")
    if system != "random" and n % 4:
        raise ValueError("This system needs a multiple of four players.")
    if type(seed) is not int:
        raise ValueError("The schedule seed must be an integer.")


def _rng(state: dict[str, Any], phase: str) -> Random:
    return Random(f"{state['seed']}:{state['round']}:{phase}")


def _partitions(group: Sequence[int]) -> tuple[Match, Match, Match]:
    a, b, c, d = group
    return (
        Match((a, b), (c, d)),
        Match((a, c), (b, d)),
        Match((a, d), (b, c)),
    )


def _pair_key(team: Sequence[int]) -> str:
    a, b = sorted(team)
    return f"{a}:{b}"


def _choose_pairing(
    group: Sequence[int], partners: dict[str, int], rng: Random
) -> Match:
    choices = _partitions(group)
    costs = [sum(partners.get(_pair_key(t), 0) for t in (m.team_a, m.team_b))
             for m in choices]
    best = min(costs)
    return rng.choice([m for m, cost in zip(choices, costs) if cost == best])


def create_session(system: str, n: int, seed: int) -> dict[str, Any]:
    """Create a randomly initialized session; no games have been played yet."""
    _validate_config(system, n, seed)
    state: dict[str, Any] = {
        "system": system,
        "n": n,
        "seed": seed,
        "round": 1,
        "wins": [0] * n,
        "pool_wins": [0] * n,
        "partners": {},
    }
    order = list(range(n))
    _rng(state, "initial").shuffle(order)
    state["groups"] = [order[i:i + 4] for i in range(0, n - n % 4, 4)]
    state["bye_order"] = order
    return state


def current_round(state: dict[str, Any]) -> Round:
    """Return the assignments for the next unplayed round, without mutation."""
    system = state["system"]
    _validate_config(system, state["n"], state["seed"])
    number = state["round"]
    if type(number) is not int or number < 1:
        raise ValueError("The round number must be positive.")
    if system == "random":
        count = state["n"] % 4
        order = state["bye_order"]
        start = ((number - 1) * count) % state["n"]
        byes = tuple(order[(start + j) % state["n"]] for j in range(count))
        active = [p for p in order if p not in byes]
        _rng(state, "random-courts").shuffle(active)
        matches = tuple(Match(tuple(active[i:i + 2]), tuple(active[i + 2:i + 4]))
                        for i in range(0, len(active), 4))
        return Round(matches, byes, number)

    matches = []
    for court, group in enumerate(state["groups"]):
        rng = _rng(state, f"pairing:{court}")
        if system.startswith("pool"):
            match = _partitions(group)[(number - 1) % 3]
        elif system == "swiss":
            match = _choose_pairing(group, state["partners"], rng)
        else:
            # Later groups contain two arriving pairs. Both pairs must split.
            options = _partitions(group)
            match = rng.choice(options if number == 1 else options[1:])
        matches.append(match)
    return Round(tuple(matches), (), number)


def _king_groups(system: str, won: list[list[int]], lost: list[list[int]]) -> list[list[int]]:
    courts = len(won)
    if courts == 1:
        return [won[0] + lost[0]]
    if system == "steve":
        return [won[c] + lost[(c - 1) % courts] for c in range(courts)]
    if system == "joe":
        return ([won[0] + won[1]]
                + [lost[c] + won[c + 1] for c in range(1, courts - 1)]
                + [lost[0] + lost[-1]])
    return ([won[0] + won[1]]
            + [lost[c - 1] + won[c + 1] for c in range(1, courts - 1)]
            + [lost[-2] + lost[-1]])


def _pool_groups(state: dict[str, Any]) -> list[list[int]]:
    ranked = []
    for court, group in enumerate(state["groups"]):
        order = list(group)
        _rng(state, f"pool-ties:{court}").shuffle(order)
        order.sort(key=lambda p: state["pool_wins"][p], reverse=True)
        ranked.append(order)
    courts = len(ranked)
    if courts == 1:
        return ranked
    count = 1 if state["system"] == "pool1" else 2
    groups = [list(group) for group in ranked]
    # Each boundary exchanges the bottom k above for the top k below.
    for upper in range(courts - 1):
        down = ranked[upper][-count:]
        up = ranked[upper + 1][:count]
        for player in down:
            groups[upper].remove(player)
            groups[upper + 1].append(player)
        for player in up:
            groups[upper + 1].remove(player)
            groups[upper].append(player)
    return groups


def advance_session(state: dict[str, Any], winners: Sequence[int]) -> dict[str, Any]:
    """Record one 0/1 result per court and produce the following round's state."""
    round_plan = current_round(state)
    if len(winners) != len(round_plan.matches) or any(type(w) is not int or w not in (0, 1) for w in winners):
        raise ValueError("Choose a winning team on every court.")
    next_state = deepcopy(state)
    won, lost = [], []
    for match, result in zip(round_plan.matches, winners):
        teams = (match.team_a, match.team_b)
        won.append(list(teams[result]))
        lost.append(list(teams[1 - result]))
        for player in teams[result]:
            next_state["wins"][player] += 1
            next_state["pool_wins"][player] += 1
        for team in teams:
            key = _pair_key(team)
            next_state["partners"][key] = next_state["partners"].get(key, 0) + 1

    system = state["system"]
    if system in KING_SYSTEMS:
        next_state["groups"] = _king_groups(system, won, lost)
    elif system.startswith("pool") and state["round"] % 3 == 0:
        next_state["groups"] = _pool_groups(next_state)
        next_state["pool_wins"] = [0] * state["n"]
    elif system == "swiss":
        order = list(range(state["n"]))
        _rng(state, "swiss-ties").shuffle(order)
        order.sort(key=lambda p: next_state["wins"][p], reverse=True)
        next_state["groups"] = [order[i:i + 4] for i in range(0, len(order), 4)]
    next_state["round"] += 1
    return next_state


def random_schedule(n: int, seed: int, rounds: int = 8) -> tuple[Round, ...]:
    """Random doubles with a shuffled cyclic bye order and balanced rest counts."""
    if type(rounds) is not int or not 1 <= rounds <= 1000:
        raise ValueError("Choose between 1 and 1000 rounds.")
    state = create_session("random", n, seed)
    result = []
    for number in range(1, rounds + 1):
        state["round"] = number
        result.append(current_round(state))
    return tuple(result)


__all__ = ["Match", "Round", "SYSTEMS", "create_session", "current_round",
           "advance_session", "random_schedule"]
