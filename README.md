# PickleBrackets

Simple Flask brackets for mixed round robin, random rotating doubles,
Full/Steve/Joe King's Court, Pool-1/Pool-2, and mixed-partner Swiss.

Choose the system and player count; player names are optional. Round robin and
random doubles produce printable schedules for 4–24 players. Pool play supports
4, 5, 8, 9, 10, and every count from 12–24: enter the scores for each court's
complete pool, then advance. King's Court and Swiss use full courts (4, 8, 12,
16, 20, or 24 players): select each game's winner, then advance. Live sessions
support up to 100 rounds or 100 pools; browser Back allows previous results to
be corrected. Completed results remain below the current assignments.

## Run

Python 3.10 or later. From this directory:

```sh
python -m pip install -r localflasktest/requirements.txt
python localflasktest/server.py
```

The existing Waitress entry point listens on port 8080. For local development:

```sh
python -m flask --app localflasktest/server.py run --port 8081
```

Set a persistent, random `SECRET_KEY` environment variable in the AWS service,
shared by every worker, to preserve signed forms across restarts and workers.
Without it, local single-process runs generate a temporary key at startup.
There is no database or account setup; each form carries its signed session.
Keep `templates/`, `static/`, and `src/` alongside `server.py` when deploying.

## Rules and checks

- Court 1 is the top court for King's Court and pool promotion. King's Court
  partners split after every game; the boundaries follow the project's
  Full/Steve/Joe rules.
- Pool courts have four or five players. Four-player courts play three games
  capped at 15; five-player courts play five games capped at 11, with one bye
  per player. Each player partners every courtmate once and opposes them twice.
  Winning every game earns 45 or 44 points respectively. The winner must reach
  the cap and the loser must be below it (win by one; no extended scores).
- Pool ranks use total points scored within that court in the current pool,
  with seeded random tie breaks. All courts finish before the top/bottom one
  or two swap across each adjacent boundary. Court sizes stay fixed. Setup
  uses the most courts possible, placing five-player courts at the bottom
  (for example, 13 players form courts of 4, 4, and 5).
- Swiss groups by cumulative wins, breaks ties at random, and minimizes previous
  partnership counts among the three pairings on each court.
- Random doubles has eight rounds. A shuffled cyclic bye order keeps each
  player's bye count within one of every other player's at every round.
- Scheduling is deterministic for a saved seed/state. Reposting the same results
  returns the same next round or pool. The engine uses only the Python standard library.
- Original JSON schedules are preserved. The loader repairs duplicated players
  in nine 19-player rounds and the mistyped bye in round 13 for 21 players, then
  checks every roster. The legacy 19-player schedule still has uneven partner
  and bye exposure; it is not a fully balanced Whist design.

Run the app's tests from this directory:

```sh
python -m unittest discover -s tests -v
```

The research simulator and its dependencies are not needed to run the site.
