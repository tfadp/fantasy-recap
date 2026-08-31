"""Synthetic league, three weeks, to prove the analysis math before real data lands."""
import json
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze
import schema
from run import brief

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"]
TEAMS = ["Bandit Bunch", "Gridiron Gary", "Team Melanie", "Fourth Down Fools"]
POSNAMES = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "DEF": "DEF"}


def mkplayer(pid, pos, pts, slot=None):
    return {"player_id": pid, "name": f"{pos}{pid}", "pos": pos, "nfl_team": "BUF",
            "slot": slot, "points": round(pts, 2), "injury": None}


def make_week(week, rng, records):
    teams = []
    for i, n in enumerate(TEAMS):
        w, l, pf, pa = records[n]
        teams.append({"team_id": str(i), "name": n, "manager": n.split()[0],
                      "wins": w, "losses": l, "ties": 0,
                      "points_for": round(pf, 2), "points_against": round(pa, 2)})

    matchups = []
    pairs = [(0, 1), (2, 3)] if week % 2 else [(0, 2), (1, 3)]
    for mi, (a, b) in enumerate(pairs):
        sides = []
        for t in (a, b):
            starters, total = [], 0.0
            for si, slot in enumerate(SLOTS):
                pos = "RB" if slot == "FLEX" else slot
                pts = max(0.0, rng.gauss(13, 7))
                starters.append(mkplayer(f"{t}-{week}-{si}", pos, pts, slot))
                total += pts
            bench = [mkplayer(f"{t}-{week}-b{j}", rng.choice(["RB", "WR", "TE"]),
                              max(0.0, rng.gauss(11, 9))) for j in range(5)]
            sides.append({"team_id": str(t), "points": round(total, 2), "projected": None,
                          "starters": starters, "bench": bench})
        matchups.append({"matchup_id": str(mi), "teams": sides})

    return {"source": "sleeper", "league_id": "TEST", "league_name": "The Test League",
            "season": "2026", "week": week, "roster_slots": SLOTS, "flex_eligible": {},
            "teams": teams, "matchups": matchups,
            "transactions": [{"type": "waiver", "team_ids": ["0"],
                              "adds": [{"player": "Waiver Hero", "team_id": "0"}],
                              "drops": [{"player": "Cut Guy", "team_id": "0"}],
                              "faab_bid": 23}] if week == 3 else []}


def run():
    rng = random.Random(7)
    records = {n: [0, 0, 0.0, 0.0] for n in TEAMS}
    history = []
    for week in (1, 2, 3):
        lw = make_week(week, rng, records)
        schema.validate(lw)
        for m in lw["matchups"]:
            a, b = m["teams"]
            na = TEAMS[int(a["team_id"])]
            nb = TEAMS[int(b["team_id"])]
            records[na][2] += a["points"]; records[na][3] += b["points"]
            records[nb][2] += b["points"]; records[nb][3] += a["points"]
            if a["points"] > b["points"]:
                records[na][0] += 1; records[nb][1] += 1
            else:
                records[nb][0] += 1; records[na][1] += 1
        if week < 3:
            history.append(lw)
        else:
            final = lw
    # refresh records onto the final week's team rows
    for t in final["teams"]:
        w, l, pf, pa = records[t["name"]]
        t.update(wins=w, losses=l, points_for=round(pf, 2), points_against=round(pa, 2))

    a = analyze.analyze(final, history)
    print(brief(a))
    print("\n--- sanity checks ---")
    f = a["facts"]
    scores = sorted((s["points"] for m in final["matchups"] for s in m["teams"]), reverse=True)
    assert f["highest_score"]["points"] == scores[0], "high score wrong"
    assert f["lowest_score"]["points"] == scores[-1], "low score wrong"
    assert f["closest_game"]["margin"] <= f["biggest_blowout"]["margin"]
    for r in a["teams"]:
        assert r["optimal_points"] >= r["points"] - 0.01, "optimal below actual"
        assert len(r["starters"]) == len(SLOTS)
    tot = sum(t["wins"] + t["losses"] for t in f["standings"])
    assert tot == len(TEAMS) * 3, f"records don't total 3 weeks: {tot}"
    print(f"checks passed: {len(a['teams'])} teams, {len(a['games'])} games, "
          f"{f['historical']['weeks_of_history']} weeks of history")


if __name__ == "__main__":
    run()
