"""Independent structural and small-case checks for operational play formats."""

from collections import Counter
from copy import deepcopy
from dataclasses import FrozenInstanceError
from itertools import combinations, product
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "localflasktest" / "src"))
from picklebrackets import (POOL_SYSTEMS, SYSTEMS, advance_pool, advance_session,
                            create_session, current_pool, current_round,
                            pool_sizes, random_schedule)


def players(match):
    return set(match.team_a + match.team_b)


class FormatTests(unittest.TestCase):
    def assert_round_valid(self, plan, n):
        roster = list(plan.byes)
        self.assertEqual(len(plan.matches), n // 4)
        self.assertEqual(len(plan.byes), n % 4)
        for match in plan.matches:
            self.assertEqual(len(match.team_a), 2)
            self.assertEqual(len(match.team_b), 2)
            self.assertEqual(len(players(match)), 4)
            roster.extend(match.team_a + match.team_b)
        self.assertEqual(sorted(roster), list(range(n)))

    def test_all_formats_counts_and_rounds(self):
        for system in SYSTEMS:
            if system in POOL_SYSTEMS:
                continue
            counts = range(4, 25) if system == "random" else range(4, 25, 4)
            for n in counts:
                with self.subTest(system=system, n=n):
                    state = create_session(system, n, 7821)
                    for r in range(1, 25):
                        plan = current_round(state)
                        self.assertEqual(plan.number, r)
                        self.assert_round_valid(plan, n)
                        state = advance_session(state, [(r + c) % 2 for c in range(n // 4)])
                    self.assertEqual(sum(state["wins"]), 24 * (n // 4) * 2)

    def test_replay_and_json_round_trip(self):
        for system in SYSTEMS:
            if system in POOL_SYSTEMS:
                continue
            state = create_session(system, 16, 165)
            same = create_session(system, 16, 165)
            for r in range(12):
                before = deepcopy(state)
                plan = current_round(state)
                self.assertEqual(state, before)
                self.assertEqual(plan, current_round(same))
                self.assertEqual(plan, current_round(json.loads(json.dumps(state))))
                results = [int((r + c) % 3 == 0) for c in range(4)]
                advanced = advance_session(state, results)
                self.assertEqual(state, before)
                state = advanced
                same = advance_session(same, results)
                self.assertEqual(state, same)

    def test_round_records_are_immutable(self):
        plan = current_round(create_session("full", 4, 1))
        with self.assertRaises(FrozenInstanceError):
            plan.number = 2
        with self.assertRaises(FrozenInstanceError):
            plan.matches[0].team_a = (2, 3)

    def test_random_byes_balanced_at_every_prefix(self):
        for n in range(4, 25):
            for seed in (0, 31, 104):
                rests = Counter({p: 0 for p in range(n)})
                schedules = random_schedule(n, seed, n * 2)
                self.assertEqual(schedules, random_schedule(n, seed, n * 2))
                for plan in schedules:
                    self.assert_round_valid(plan, n)
                    rests.update(plan.byes)
                    self.assertLessEqual(max(rests.values()) - min(rests.values()), 1)
                self.assertEqual(set(rests.values()), {2 * (n % 4)})

    def test_random_rounds_ignore_match_results(self):
        for n in (4, 7, 16, 23):
            state = create_session("random", n, 193)
            for plan in random_schedule(n, 193):
                self.assertEqual(plan, current_round(state))
                state = advance_session(state, [1] * (n // 4))

    def test_kings_routing_exact_three_and_four_courts(self):
        # Expected source cohorts are an independent restatement of the rules.
        expected_sources = {
            3: {
                "full": (("W0", "W1"), ("L0", "W2"), ("L1", "L2")),
                "steve": (("W0", "L2"), ("W1", "L0"), ("W2", "L1")),
                "joe": (("W0", "W1"), ("L1", "W2"), ("L0", "L2")),
            },
            4: {
                "full": (("W0", "W1"), ("L0", "W2"), ("L1", "W3"), ("L2", "L3")),
                "steve": (("W0", "L3"), ("W1", "L0"), ("W2", "L1"), ("W3", "L2")),
                "joe": (("W0", "W1"), ("L1", "W2"), ("L2", "W3"), ("L0", "L3")),
            },
        }
        for courts, systems in expected_sources.items():
            for system, expected in systems.items():
                for outcomes in product((0, 1), repeat=courts):
                    state = create_session(system, courts * 4, 150)
                    original = current_round(state)
                    cohorts = {}
                    for c, (match, winner) in enumerate(zip(original.matches, outcomes)):
                        teams = (set(match.team_a), set(match.team_b))
                        cohorts[f"W{c}"] = teams[winner]
                        cohorts[f"L{c}"] = teams[1 - winner]
                    following = current_round(advance_session(state, outcomes))
                    for match, (first, second) in zip(following.matches, expected):
                        self.assertEqual(players(match), cohorts[first] | cohorts[second])
                        for team in (set(match.team_a), set(match.team_b)):
                            self.assertEqual(len(team & cohorts[first]), 1)
                            self.assertEqual(len(team & cohorts[second]), 1)

    def test_one_court_kings_split_both_teams(self):
        for system in ("full", "steve", "joe"):
            state = create_session(system, 4, 31)
            for _ in range(20):
                original = current_round(state).matches[0]
                state = advance_session(state, [0])
                following = current_round(state).matches[0]
                self.assertEqual(len(set(original.team_a) & set(following.team_a)), 1)
                self.assertEqual(len(set(original.team_b) & set(following.team_a)), 1)

    def test_full_and_joe_two_court_equivalence(self):
        full = create_session("full", 8, 891)
        joe = create_session("joe", 8, 891)
        for r in range(20):
            self.assertEqual(current_round(full), current_round(joe))
            winners = [r % 2, (r // 2) % 2]
            full = advance_session(full, winners)
            joe = advance_session(joe, winners)

    def test_four_player_pool_exhaustive_outcomes(self):
        for system in ("pool1", "pool2"):
            for outcomes in product((0, 1), repeat=3):
                state = create_session(system, 4, 71)
                partners, opponents = Counter(), Counter()
                wins = Counter({p: 0 for p in range(4)})
                plan = current_pool(state)
                for game, outcome in zip(plan[0].games, outcomes):
                    match = game.match
                    for team in (match.team_a, match.team_b):
                        partners[tuple(sorted(team))] += 1
                    for a in match.team_a:
                        for b in match.team_b:
                            opponents[tuple(sorted((a, b)))] += 1
                    wins.update((match.team_a, match.team_b)[outcome])
                scores = [[(15, 0) if outcome == 0 else (0, 15) for outcome in outcomes]]
                state = advance_pool(state, scores)
                self.assertEqual(set(partners), set(combinations(range(4), 2)))
                self.assertEqual(set(partners.values()), {1})
                self.assertEqual(set(opponents.values()), {2})
                self.assertIn(sorted(wins.values()), ([0, 2, 2, 2], [1, 1, 1, 3]))
                self.assertEqual(state["wins"], [wins[p] for p in range(4)])
                self.assertEqual(state["last_pool_points"], [15 * wins[p] for p in range(4)])
                self.assertEqual(state["pool"], 2)

    def test_five_player_pool_exhaustive_outcomes(self):
        for outcomes in product((0, 1), repeat=5):
            state = create_session("pool1", 5, 71)
            court, = current_pool(state)
            partners, opponents, byes, games_played = Counter(), Counter(), Counter(), Counter()
            points = Counter({p: 0 for p in range(5)})
            self.assertEqual(court.target, 11)
            for game, outcome in zip(court.games, outcomes):
                match = game.match
                self.assertEqual(players(match) | {game.bye}, set(range(5)))
                self.assertNotIn(game.bye, players(match))
                byes[game.bye] += 1
                games_played.update(players(match))
                for team in (match.team_a, match.team_b):
                    partners[tuple(sorted(team))] += 1
                for a in match.team_a:
                    for b in match.team_b:
                        opponents[tuple(sorted((a, b)))] += 1
                for player in (match.team_a, match.team_b)[outcome]:
                    points[player] += 11
            self.assertEqual(byes, Counter({p: 1 for p in range(5)}))
            self.assertEqual(games_played, Counter({p: 4 for p in range(5)}))
            self.assertEqual(set(partners), set(combinations(range(5), 2)))
            self.assertEqual(set(partners.values()), {1})
            self.assertEqual(set(opponents), set(combinations(range(5), 2)))
            self.assertEqual(set(opponents.values()), {2})
            scores = [[(11, 0) if outcome == 0 else (0, 11) for outcome in outcomes]]
            after = advance_pool(state, scores)
            self.assertEqual(after["last_pool_points"], [points[p] for p in range(5)])

    def test_pool_mixed_sizes_move_by_current_points_not_wins(self):
        # Independently tabulated 4-player totals: 45,18,17,16.
        # Five-player totals: 31,43,33,21,22; wins: 1,3,3,1,2.
        # Thus the one-win player scoring 31 ranks above a two-win player.
        expected = {
            "pool1": ({0, 1, 2, 5}, {3, 4, 6, 8, 10}, {7, 9, 11, 12, 13}),
            "pool2": ({0, 1, 5, 6}, {2, 3, 4, 10, 11}, {7, 8, 9, 12, 13}),
        }
        for system in ("pool1", "pool2"):
            state = create_session(system, 14, 778)
            state["groups"] = [list(range(4)), list(range(4, 9)), list(range(9, 14))]
            state["wins"] = [100 * p for p in range(14)]
            state["last_pool_points"] = [1000 * p for p in range(14)]
            scores5 = [(11, 0), (11, 0), (11, 0), (11, 10), (10, 11)]
            following = advance_pool(state, [[(15, 0), (15, 1), (15, 2)], scores5, scores5])
            self.assertEqual(tuple(map(set, following["groups"])), expected[system])
            self.assertEqual(following["last_pool_points"], [45, 18, 17, 16] + [31, 43, 33, 21, 22] * 2)

    def test_pool_sizes_use_four_and_five_player_courts(self):
        expected = {
            4: (4,), 5: (5,), 8: (4, 4), 9: (4, 5), 10: (5, 5),
            12: (4, 4, 4), 13: (4, 4, 5), 14: (4, 5, 5), 15: (5, 5, 5),
            16: (4, 4, 4, 4), 17: (4, 4, 4, 5), 18: (4, 4, 5, 5),
            19: (4, 5, 5, 5), 20: (4, 4, 4, 4, 4),
            21: (4, 4, 4, 4, 5), 22: (4, 4, 4, 5, 5),
            23: (4, 4, 5, 5, 5), 24: (4, 4, 4, 4, 4, 4),
        }
        for n, sizes in expected.items():
            self.assertEqual(pool_sizes(n), sizes)
            for system in POOL_SYSTEMS:
                self.assertEqual(tuple(map(len, create_session(system, n, 77)["groups"])), sizes)
        for n in (3, 6, 7, 11, 25, 4.0, True, "5"):
            with self.subTest(n=n), self.assertRaises(ValueError):
                pool_sizes(n)
            for system in POOL_SYSTEMS:
                with self.subTest(system=system, n=n), self.assertRaises(ValueError):
                    create_session(system, n, 1)

    def test_all_pool_counts_repeated_invariants_and_replay(self):
        for system in POOL_SYSTEMS:
            for n in (4, 5, 8, 9, 10, *range(12, 25)):
                for seed in (1, 941):
                    state = create_session(system, n, seed)
                    for block in range(1, 9):
                        with self.subTest(system=system, n=n, seed=seed, block=block):
                            before = deepcopy(state)
                            courts = current_pool(state)
                            self.assertEqual(state, before)
                            self.assertEqual(courts, current_pool(json.loads(json.dumps(state))))
                            self.assertEqual(state["pool"], block)
                            self.assertEqual([c.number for c in courts], list(range(1, len(courts) + 1)))
                            self.assertEqual(tuple(len(c.players) for c in courts), pool_sizes(n))
                            self.assertEqual(sorted(p for c in courts for p in c.players), list(range(n)))
                            for court in courts:
                                partners, byes, played = Counter(), Counter(), Counter()
                                self.assertEqual((len(court.games), court.target), (3, 15) if len(court.players) == 4 else (5, 11))
                                for game in court.games:
                                    active = players(game.match)
                                    self.assertEqual(len(active), 4)
                                    self.assertEqual(active | (set() if game.bye is None else {game.bye}), set(court.players))
                                    played.update(active)
                                    if game.bye is not None:
                                        byes[game.bye] += 1
                                    for team in (game.match.team_a, game.match.team_b):
                                        partners[tuple(sorted(team))] += 1
                                self.assertEqual(set(partners), set(combinations(sorted(court.players), 2)))
                                self.assertEqual(set(partners.values()), {1})
                                self.assertEqual(set(played.values()), {len(court.players) - 1})
                                self.assertEqual(byes, Counter() if len(court.players) == 4 else Counter({p: 1 for p in court.players}))
                            scores = [[(c.target, (block + g) % c.target) if (block + g + c.number) % 2 else ((block + g) % c.target, c.target)
                                       for g in range(len(c.games))] for c in courts]
                            following = advance_pool(state, scores)
                            self.assertEqual(state, before)
                            self.assertEqual(following, advance_pool(json.loads(json.dumps(state)), scores))
                            count = 1 if system == "pool1" else 2
                            for upper in range(len(courts) - 1):
                                self.assertEqual(len(set(state["groups"][upper]) & set(following["groups"][upper + 1])), count)
                                self.assertEqual(len(set(state["groups"][upper + 1]) & set(following["groups"][upper])), count)
                            self.assertEqual(sum(following["wins"]) - sum(state["wins"]), 2 * sum(len(c.games) for c in courts))
                            state = following

    def test_pool_records_are_immutable(self):
        court, = current_pool(create_session("pool1", 5, 10))
        with self.assertRaises(FrozenInstanceError):
            court.target = 15
        with self.assertRaises(FrozenInstanceError):
            court.games[0].bye = 3
        with self.assertRaises(FrozenInstanceError):
            court.games[0].match.team_a = (1, 3)

    def test_pool_invalid_scores_are_atomic(self):
        state = create_session("pool2", 9, 190)
        valid = [[(15, 10)] * 3, [(11, 7)] * 5]
        bad_batches = (None, [], valid[:1], valid + [valid[0]], [valid[0], valid[1][:-1]])
        for scores in bad_batches:
            before = deepcopy(state)
            with self.subTest(scores=scores), self.assertRaises(ValueError):
                advance_pool(state, scores)
            self.assertEqual(state, before)
        for bad_pair in (None, [], [11], [11, 7, 0], [11, 11], [12, 10], [10, 9],
                         [11, -1], [True, 11], [11.0, 7], ["11", 7]):
            scores = deepcopy(valid)
            scores[-1][-1] = bad_pair
            before = deepcopy(state)
            with self.subTest(pair=bad_pair), self.assertRaises(ValueError):
                advance_pool(state, scores)
            self.assertEqual(state, before)
        for target, loser in ((15, 14), (11, 10)):
            n = 4 if target == 15 else 5
            state = create_session("pool1", n, 1)
            advance_pool(state, [[(target, loser)] * (3 if n == 4 else 5)])

    def test_pool_requires_whole_pool_score_api(self):
        for system in POOL_SYSTEMS:
            state = create_session(system, 4, 1)
            with self.assertRaises(ValueError):
                current_round(state)
            with self.assertRaises(ValueError):
                advance_session(state, [0])
        state = create_session("full", 4, 1)
        with self.assertRaises(ValueError):
            current_pool(state)
        with self.assertRaises(ValueError):
            advance_pool(state, [[(15, 0)] * 3])

    def test_swiss_groups_by_wins_and_avoids_available_repeat(self):
        state = create_session("swiss", 16, 92)
        first = current_round(state)
        winners = set(p for m in first.matches for p in m.team_a)
        state = advance_session(state, [0] * 4)
        second = current_round(state)
        self.assertEqual(set.union(*(players(m) for m in second.matches[:2])), winners)
        for match in second.matches:
            group = sorted(players(match))
            a, b, c, d = group
            candidates = (((a, b), (c, d)), ((a, c), (b, d)), ((a, d), (b, c)))
            def cost(teams):
                return sum(state["partners"].get(":".join(map(str, sorted(t))), 0) for t in teams)
            self.assertEqual(cost((match.team_a, match.team_b)), min(map(cost, candidates)))

    def test_invalid_inputs(self):
        for args in (("bogus", 8, 1), ("full", 5, 1), ("pool1", 7, 1),
                     ("random", 3, 1), ("swiss", 28, 1), ("random", 5.0, 1),
                     ("full", 4, "seed"), ("random", True, 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                create_session(*args)
        state = create_session("full", 8, 21)
        for winners in ([], [0], [0, 0, 0], [0, 2], [True, 0], ["0", 1]):
            with self.subTest(winners=winners), self.assertRaises(ValueError):
                advance_session(state, winners)
        for rounds in (0, -1, 1001, "8", True):
            with self.assertRaises(ValueError):
                random_schedule(8, 1, rounds)


if __name__ == "__main__":
    unittest.main()
