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
            counts = range(4, 25) if system in server.STATIC_SYSTEMS else range(4, 25, 4)
            for n in counts:
                with self.subTest(system=system, n=n):
                    response = self.start(system, n)
                    self.assertEqual(response.status_code, 200)
                    if system in server.STATIC_SYSTEMS:
                        self.assertIn("<table>", response.text)
                        self.assertEqual("Bye(s)" in response.text, bool(n % 4))
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
        for path, field in (("/submitRR2", "setup_token"), ("/next-round", "state_token")):
            self.assertEqual(self.client.post(path).status_code, 400)
            self.assertEqual(self.client.post(path, data={field: "not-a-token"}).status_code, 400)
        setup = Inputs(self.start("full", 8, binnames="names_y")).values["setup_token"]
        self.assertEqual(self.client.post("/next-round", data={"state_token": setup}).status_code, 400)

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
        response = self.start("pool1", 4)
        payload = server.signer().loads(Inputs(response).values["state_token"])
        payload["state"]["round"] = server.MAX_ROUNDS
        response = self.client.post("/next-round", data={
            "state_token": server.signer().dumps(payload), "winner_0": "0"
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("Session complete.", response.text)
        self.assertIn("Won:", response.text)


if __name__ == "__main__":
    unittest.main()
