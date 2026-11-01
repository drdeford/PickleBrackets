"""Exercise the real Flask routes, templates, and signed session workflow."""
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

APP_ROOT = Path(__file__).resolve().parents[1] / "localflasktest"
sys.path.insert(0, str(APP_ROOT))
import server


class Inputs(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.values = {}
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and values.get("type") == "hidden":
            self.values[values["name"]] = values.get("value", "")


class WebTests(unittest.TestCase):
    def setUp(self):
        server.app.config.update(TESTING=True, SECRET_KEY="test-key-only")
        self.client = server.app.test_client()

    def start(self, system="full", n=8, **extra):
        return self.client.post("/submitRR", data={"system": system, "numplay": n, **extra})

    def advance(self, response, courts=2):
        return self.client.post("/next-round", data={
            **Inputs(response).values, **{f"winner_{i}": i % 2 for i in range(courts)}
        })

    def pool_scores(self, response):
        data = Inputs(response).values
        payload = server.signer().loads(data["state_token"])
        for c, court in enumerate(server.current_pool(payload["state"])):
            for g, game in enumerate(court.games):
                data[f"score_{c}_{g}_a"] = str(court.target)
                data[f"score_{c}_{g}_b"] = str(g)
        return data

    def test_home_and_assets(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="system"', response.text)
        self.assertIn('name="numplay"', response.text)
        self.assertIn('name="binnames"', response.text)
        with self.client.get("/static/style.css") as stylesheet:
            self.assertEqual(stylesheet.status_code, 200)

    def test_every_supported_system_and_count_renders(self):
        for system in server.SYSTEMS:
            if system in server.POOL_SYSTEMS:
                counts = [4, 5, 8, 9, 10, *range(12, 25)]
            else:
                counts = range(4, 25) if system in server.STATIC_SYSTEMS else range(4, 25, 4)
            for n in counts:
                with self.subTest(system=system, n=n):
                    response = self.start(system, n)
                    self.assertEqual(response.status_code, 200)
                    if system in server.STATIC_SYSTEMS:
                        self.assertIn("<table>", response.text)
                        self.assertEqual("Bye(s)" in response.text, bool(n % 4))
                    elif system in server.POOL_SYSTEMS:
                        for _ in range(3):
                            response = self.client.post("/next-pool", data=self.pool_scores(response))
                            self.assertEqual(response.status_code, 200)
                        self.assertIn("Pool 4", response.text)
                    else:
                        for _ in range(6):
                            response = self.advance(response, n // 4)
                            self.assertEqual(response.status_code, 200)
                        self.assertIn("Round 7", response.text)

    def test_original_post_without_system_still_works(self):
        response = self.client.post("/submitRR", data={"numplay": "4"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("1 / 2 vs. 3 / 4", response.text)
        self.assertIn("3 rounds", response.text)

    def test_bad_counts_and_systems_are_rejected(self):
        for data in ({}, {"numplay": "abc"}, {"numplay": "3"}, {"numplay": "25"},
                     {"numplay": "7", "system": "full"},
                     {"numplay": "8", "system": "unknown"}):
            self.assertEqual(self.client.post("/submitRR", data=data).status_code, 400)
        for path in ("/submitRR", "/submitRR2"):
            self.assertEqual(self.client.get(path).status_code, 302)
        for system in server.POOL_SYSTEMS:
            for n in (6, 7, 11):
                self.assertEqual(self.start(system, n).status_code, 400)

    def test_names_are_escaped_and_blank_names_use_player_number(self):
        for system in server.SYSTEMS:
            response = self.start(system, 4, binnames="names_y")
            response = self.client.post("/submitRR2", data={
                **Inputs(response).values, "p1": "<script>alert(1)</script>", "p2": "  ",
                "p3": "Ada", "p4": "Lin"
            })
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("<script>alert(1)</script>", response.text)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", response.text)
            self.assertIn("Ada", response.text)
            self.assertIn("Lin", response.text)

    def test_separate_named_brackets_do_not_overwrite_each_other(self):
        first = Inputs(self.start("full", 8, binnames="names_y")).values
        second = Inputs(self.start("round_robin", 5, binnames="names_y")).values
        response = self.client.post("/submitRR2", data={**first, "p1": "First"})
        self.assertIn("8 players", response.text)
        self.assertIn("First", response.text)
        response = self.client.post("/submitRR2", data={**second, "p1": "Second"})
        self.assertIn("5 players", response.text)
        self.assertIn("Second", response.text)

    def test_missing_or_tampered_tokens_fail_cleanly(self):
        for path, field in (("/submitRR2", "setup_token"), ("/next-round", "state_token"),
                            ("/next-pool", "state_token")):
            self.assertEqual(self.client.post(path).status_code, 400)
            self.assertEqual(self.client.post(path, data={field: "not-a-token"}).status_code, 400)
        setup = Inputs(self.start("full", 8, binnames="names_y")).values["setup_token"]
        self.assertEqual(self.client.post("/next-round", data={"state_token": setup}).status_code, 400)
        live = Inputs(self.start("full", 8)).values
        pool = Inputs(self.start("pool1", 9)).values
        self.assertEqual(self.client.post("/next-pool", data=live).status_code, 400)
        self.assertEqual(self.client.post("/next-round", data=pool).status_code, 400)

    def test_missing_or_invalid_winner_preserves_round(self):
        response = self.start()
        fields = Inputs(response).values
        for winners in ({}, {"winner_0": "0"}, {"winner_0": "2", "winner_1": "0"},
                        {"winner_0": "x", "winner_1": "0"}):
            rejected = self.client.post("/next-round", data={**fields, **winners})
            self.assertEqual(rejected.status_code, 400)
            self.assertIn("Round 1", rejected.text)
            self.assertEqual(Inputs(rejected).values, fields)

    def test_reposting_a_round_does_not_double_count(self):
        first = self.start()
        second = self.advance(first)
        repeated = self.advance(first)
        self.assertEqual(second.data, repeated.data)
        self.assertIn("Round 2", second.text)
        self.assertIn("Completed rounds (1)", second.text)

    def test_session_finishes_and_keeps_results(self):
        response = self.start("full", 4)
        payload = server.signer().loads(Inputs(response).values["state_token"])
        payload["state"]["round"] = server.MAX_ROUNDS
        response = self.client.post("/next-round", data={
            "state_token": server.signer().dumps(payload), "winner_0": "0"
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("Session complete.", response.text)
        self.assertIn("Won:", response.text)

    def test_mixed_pool_has_complete_schedules_scores_byes_and_totals(self):
        response = self.start("pool1", 9)
        self.assertIn("4 players · 3 games to 15", response.text)
        self.assertIn("5 players · 5 games to 11", response.text)
        self.assertEqual(response.text.count('aria-label="Court '), 16)
        self.assertEqual(response.text.count("Bye: "), 5)
        self.assertNotIn("Select winner", response.text)
        data = self.pool_scores(response)
        saved = self.client.post("/next-pool", data=data)
        self.assertEqual(saved.status_code, 200)
        self.assertIn("Pool 2", saved.text)
        self.assertIn("Completed pools (1)", saved.text)
        payload = server.signer().loads(Inputs(saved).values["state_token"])
        courts = payload["completed"][0]["courts"]
        self.assertEqual([len(c["games"]) for c in courts], [3, 5])
        self.assertEqual([c["target"] for c in courts], [15, 11])
        self.assertEqual([sum(p["total"] for p in c["points"]) for c in courts], [96, 130])
        replayed = self.client.post("/next-pool", data=data)
        self.assertEqual(saved.data, replayed.data)

    def test_bad_pool_scores_preserve_all_assignments_and_entered_values(self):
        response = self.start("pool2", 9)
        data = self.pool_scores(response)
        for value in ("", "abc", "-1", "11", "12", "15"):
            with self.subTest(value=value):
                rejected = self.client.post("/next-pool", data={**data, "score_1_4_b": value})
                self.assertEqual(rejected.status_code, 400)
                self.assertIn("Pool 1", rejected.text)
                self.assertEqual(Inputs(rejected).values, Inputs(response).values)
                self.assertIn('<option value="15" selected>15</option>', rejected.text)
        bad_four = self.client.post("/next-pool", data={**data, "score_0_0_a": "11"})
        self.assertEqual(bad_four.status_code, 400)
        valid = self.client.post("/next-pool", data=data)
        self.assertEqual(valid.status_code, 200)

    def test_named_five_player_pool_and_finished_session(self):
        response = self.start("pool2", 5, binnames="names_y")
        response = self.client.post("/submitRR2", data={
            **Inputs(response).values, "p1": "Ada", "p2": "<Lin>",
            "p3": "Jo", "p4": "Sam", "p5": "Avery"
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("&lt;Lin&gt;", response.text)
        self.assertIn("Bye: Avery", response.text)
        data = self.pool_scores(response)
        payload = server.signer().loads(data["state_token"])
        payload["state"]["pool"] = server.MAX_POOLS
        payload["state"]["round"] = server.MAX_POOLS
        data["state_token"] = server.signer().dumps(payload)
        response = self.client.post("/next-pool", data=data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Session complete.", response.text)
        self.assertIn("Points:", response.text)
        self.assertNotIn('action="/next-pool"', response.text)


if __name__ == "__main__":
    unittest.main()
