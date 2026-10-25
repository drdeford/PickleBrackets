from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / "localflasktest"
sys.path.insert(0, str(ROOT / "src"))
from picklebrackets.schedules import load_round_robin


class ScheduleTests(unittest.TestCase):
    def test_every_original_count_has_complete_unique_rosters(self):
        for n in range(4, 25):
            for round_ in load_round_robin(n, ROOT / "static"):
                with self.subTest(n=n, round=round_.number):
                    played = [p for game in round_.matches for team in (game.team_a, game.team_b) for p in team]
                    self.assertEqual(len(round_.matches), n // 4)
                    self.assertEqual(len(round_.byes), n % 4)
                    self.assertEqual(sorted(played + list(round_.byes)), list(range(n)))

    def test_twenty_one_restores_complete_whist_exposures(self):
        partners, opponents, byes = Counter(), Counter(), Counter()
        for round_ in load_round_robin(21, ROOT / "static"):
            byes.update(round_.byes)
            for game in round_.matches:
                partners.update([tuple(sorted(game.team_a)), tuple(sorted(game.team_b))])
                opponents.update(tuple(sorted((a, b))) for a in game.team_a for b in game.team_b)
        for pair in combinations(range(21), 2):
            self.assertEqual(partners[pair], 1)
            self.assertEqual(opponents[pair], 2)
        self.assertEqual(set(byes.values()), {1})

    def test_repairs_do_not_change_original_json(self):
        for n in (19, 21):
            path = ROOT / "static" / f"pb{n}.json"
            original = path.read_bytes()
            load_round_robin(n, path.parent)
            self.assertEqual(path.read_bytes(), original)
        original = json.loads((ROOT / "static" / "pb19.json").read_text())
        self.assertEqual(original["19"][1][0][0], [6, 6])


if __name__ == "__main__":
    unittest.main()
