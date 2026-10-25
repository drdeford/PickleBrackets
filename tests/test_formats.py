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
from picklebrackets import (SYSTEMS, advance_session, create_session,
                            current_round, random_schedule)


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
                for outcome in outcomes:
                    match = current_round(state).matches[0]
                    for team in (match.team_a, match.team_b):
                        partners[tuple(sorted(team))] += 1
                    for a in match.team_a:
                        for b in match.team_b:
                            opponents[tuple(sorted((a, b)))] += 1
                    wins.update((match.team_a, match.team_b)[outcome])
                    state = advance_session(state, [outcome])
                self.assertEqual(set(partners), set(combinations(range(4), 2)))
                self.assertEqual(set(partners.values()), {1})
                self.assertEqual(set(opponents.values()), {2})
                self.assertIn(sorted(wins.values()), ([0, 2, 2, 2], [1, 1, 1, 3]))
                self.assertEqual(state["wins"], [wins[p] for p in range(4)])
                self.assertEqual(state["pool_wins"], [0] * 4)
                self.assertEqual(current_round(state).number, 4)

    def test_pool_promotes_only_after_three_games(self):
        for system in ("pool1", "pool2"):
            state = create_session(system, 16, 190)
            initial = [players(m) for m in current_round(state).matches]
            for _ in range(2):
                state = advance_session(state, [0] * 4)
                self.assertEqual(initial, [players(m) for m in current_round(state).matches])
            state = advance_session(state, [0] * 4)
            following = [players(m) for m in current_round(state).matches]
            count = 1 if system == "pool1" else 2
            for court in range(3):
                self.assertEqual(len(initial[court] & following[court + 1]), count)
                self.assertEqual(len(initial[court + 1] & following[court]), count)
            self.assertEqual(len(initial[0] & following[0]), 4 - count)
            self.assertEqual(len(initial[-1] & following[-1]), 4 - count)

    def test_pool_promotes_by_block_wins_not_lifetime_wins(self):
        for system in ("pool1", "pool2"):
            state = create_session(system, 12, 778)
            original_groups = deepcopy(state["groups"])
            # These unique synthetic standings make boundary selection exact.
            state["round"] = 3
            expected = []
            for group in original_groups:
                for rank, p in enumerate(group):
                    state["pool_wins"][p] = 100 - rank * 10
                    state["wins"][p] = rank * 100
                expected.append(list(group))
            count = 1 if system == "pool1" else 2
            for upper in range(2):
                for p in original_groups[upper][-count:]:
                    expected[upper].remove(p)
                    expected[upper + 1].append(p)
                for p in original_groups[upper + 1][:count]:
                    expected[upper + 1].remove(p)
                    expected[upper].append(p)
            following = current_round(advance_session(state, [0] * 3))
            self.assertEqual([players(m) for m in following.matches], [set(g) for g in expected])

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
