"""Small, stateless Flask interface for printable brackets and live rec play."""
import os
from pathlib import Path
import secrets
import sys

from flask import Flask, redirect, render_template, request, url_for
from itsdangerous import BadData, URLSafeSerializer

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from picklebrackets import advance_session, create_session, current_round, random_schedule
from picklebrackets.schedules import load_round_robin

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024

SYSTEMS = {
    "round_robin": "Mixed Round Robin",
    "random": "Random Rotating Doubles",
    "full": "King's Court — Full",
    "steve": "King's Court — Steve",
    "joe": "King's Court — Joe",
    "pool1": "Pool Play — Move 1",
    "pool2": "Pool Play — Move 2",
    "swiss": "Mixed-Partner Swiss",
}
NOTES = {
    "round_robin": "Rotating partners, with byes when needed.",
    "random": "Eight rounds with shuffled partners and rotating byes.",
    "full": "Winners move up; losers move down. Partners split. Court 1 is the top.",
    "steve": "Winners stay; losers move down and wrap to Court 1. Partners split.",
    "joe": "Winners move up; losers stay, except Court 1 losers wrap to the bottom. Partners split.",
    "pool1": "Three games per pool, then swap the top/bottom player across adjacent courts. Ties drawn at random.",
    "pool2": "Three games per pool, then swap the top/bottom two across adjacent courts. Ties drawn at random.",
    "swiss": "Group by total wins; avoid repeat partners within each court. Ties drawn at random.",
}
STATIC_SYSTEMS = {"round_robin", "random"}
MAX_ROUNDS = 100


def signer():
    return URLSafeSerializer(app.secret_key, salt="picklebrackets-rec-play-v1")


def setup_page(error=None, system="round_robin", n=8, named=False):
    return render_template("index.html", systems=SYSTEMS, notes=NOTES,
                           selected=system, n=n, named=named, error=error)


def read_token(field, kind):
    token = request.form.get(field, "")
    if len(token) > 200000:
        raise ValueError("This bracket is too large. Please start a new one.")
    try:
        payload = signer().loads(token)
    except BadData as exc:
        raise ValueError("This bracket is no longer available. Please start a new one.") from exc
    if not isinstance(payload, dict) or payload.get("kind") != kind:
        raise ValueError("Please start a new bracket.")
    return payload


def match_label(match, names):
    return " / ".join(names[p] for p in match.team_a) + " vs. " + " / ".join(names[p] for p in match.team_b)


def display_round(round_, names, winners=None):
    return {
        "number": round_.number,
        "matches": [match_label(match, names) for match in round_.matches],
        "byes": ", ".join(names[p] for p in round_.byes),
        "winners": [] if winners is None else [
            " / ".join(names[p] for p in (match.team_a if winner == 0 else match.team_b))
            for match, winner in zip(round_.matches, winners)
        ],
    }


def start_bracket(system, names):
    n = len(names)
    if system in STATIC_SYSTEMS:
        if system == "round_robin":
            rows = [display_round(round_, names) for round_ in
                    load_round_robin(n, Path(app.static_folder))]
        else:
            rows = [display_round(round_, names) for round_ in random_schedule(n, secrets.randbits(64))]
        return render_template("RR.html", title=SYSTEMS[system], rows=rows,
                               courts=n // 4, has_byes=bool(n % 4), n=n,
                               note=NOTES[system], system=system)
    payload = {"kind": "play", "system": system, "names": names,
               "state": create_session(system, n, secrets.randbits(64)), "completed": []}
    return play_page(payload)


def play_page(payload, error=None):
    round_ = current_round(payload["state"])
    names = payload["names"]
    games = [{"a": " / ".join(names[p] for p in match.team_a),
              "b": " / ".join(names[p] for p in match.team_b)} for match in round_.matches]
    return render_template("play.html", title=SYSTEMS[payload["system"]],
                           note=NOTES[payload["system"]], system=payload["system"],
                           games=games, round_number=round_.number, n=len(names),
                           completed=payload["completed"], token=signer().dumps(payload),
                           error=error, max_rounds=MAX_ROUNDS)


@app.get("/")
def index():
    return setup_page()


@app.route("/submitRR", methods=["GET", "POST"])
def submitRR():
    if request.method == "GET":
        return redirect(url_for("index"))
    system = request.form.get("system", "round_robin")
    named = "binnames" in request.form
    try:
        n = int(request.form.get("numplay", ""))
    except ValueError:
        return setup_page("Choose a player count from 4 to 24.", named=named), 400
    if system not in SYSTEMS:
        return setup_page("Choose a play system.", n=n, named=named), 400
    if not 4 <= n <= 24:
        return setup_page("Choose a player count from 4 to 24.", system, named=named), 400
    if system not in STATIC_SYSTEMS and n % 4:
        return setup_page("This system needs 4, 8, 12, 16, 20, or 24 players.", system, n, named), 400
    if named:
        token = signer().dumps({"kind": "setup", "system": system, "n": n})
        return render_template("gather_names.html", n=n, title=SYSTEMS[system], token=token)
    return start_bracket(system, [str(i + 1) for i in range(n)])


@app.route("/submitRR2", methods=["GET", "POST"])
def submitRR2():
    if request.method == "GET":
        return redirect(url_for("index"))
    try:
        payload = read_token("setup_token", "setup")
    except ValueError as exc:
        return setup_page(str(exc)), 400
    names = [request.form.get(f"p{i + 1}", "").strip()[:40] or str(i + 1)
             for i in range(payload["n"])]
    return start_bracket(payload["system"], names)


@app.post("/next-round")
def next_round():
    try:
        payload = read_token("state_token", "play")
    except ValueError as exc:
        return setup_page(str(exc)), 400
    round_ = current_round(payload["state"])
    try:
        winners = [int(request.form.get(f"winner_{i}", "")) for i in range(len(round_.matches))]
        if any(winner not in (0, 1) for winner in winners):
            raise ValueError
    except ValueError:
        return play_page(payload, "Select a winner on every court."), 400
    payload["completed"].append(display_round(round_, payload["names"], winners))
    if round_.number >= MAX_ROUNDS:
        return render_template("RR.html", title=SYSTEMS[payload["system"]],
                               rows=payload["completed"], courts=len(round_.matches),
                               has_byes=False, n=len(payload["names"]),
                               note="Session complete.", system=payload["system"])
    payload["state"] = advance_session(payload["state"], winners)
    return play_page(payload)


if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=8080)
