"""Load the supplied brackets with narrow, source-preserving roster repairs."""
import json
from pathlib import Path

from . import Match, Round


def load_round_robin(n: int, directory: Path) -> tuple[Round, ...]:
    if type(n) is not int or not 4 <= n <= 24:
        raise ValueError("Choose between 4 and 24 players.")
    with (directory / f"pb{n}.json").open(encoding="utf-8") as source:
        rows = json.load(source)[str(n)]

    # The original 19-player even rounds repeat a player inside Court 1's
    # first team. Restore the missing player in the +12 mod 19 rotation.
    # This repairs participation only; this legacy schedule is not pair-balanced.
    if n == 19:
        replacements = (8, 1, 13, 6, 18, 11, 4, 16, 9)
        for index, player in zip(range(1, 19, 2), replacements):
            team = rows[index][0][0]
            if team[0] == team[1] == (player - 2) % 19:
                team[1] = player
    # All twenty active IDs in this round are correct; the bye was mistyped.
    if n == 21 and rows[12][5] == [1]:
        rows[12][5] = [11]

    result = []
    for number, row in enumerate(rows, 1):
        if len(row) != n // 4 + bool(n % 4):
            raise ValueError(f"Invalid court count in round {number}.")
        matches = tuple(Match(tuple(game[0]), tuple(game[1])) for game in row[:n // 4])
        byes = tuple(row[-1]) if n % 4 else ()
        players = [p for match in matches for team in (match.team_a, match.team_b) for p in team]
        if (any(len(team) != 2 for match in matches for team in (match.team_a, match.team_b))
                or len(byes) != n % 4 or sorted(players + list(byes)) != list(range(n))):
            raise ValueError(f"Invalid player assignments in round {number}.")
        result.append(Round(matches, byes, number))
    return tuple(result)
