"""
Tests for the waiver-wire helper's free-agent computation.

Same style as test_pipeline.py: plain asserts, stdlib only, run with
    python3 test_waivers.py

A "free agent" is simply a player who is not on ANY team's roster in the
league. We compute it by subtracting every rostered player_id from the full
Sleeper player database, then keep only players worth picking up (a real NFL
team, a fantasy position).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import waivers  # noqa: E402  (import after sys.path setup, like test_pipeline.py)


# A tiny stand-in for Sleeper's /players/nfl response. Real one has ~5000
# entries; four is enough to prove the subtraction logic.
PLAYERS_DB = {
    "1": {"full_name": "Rostered RB", "position": "RB", "team": "BUF", "injury_status": None},
    "2": {"full_name": "Free RB", "position": "RB", "team": "MIA", "injury_status": None},
    "3": {"full_name": "Free WR", "position": "WR", "team": "NYJ", "injury_status": "Questionable"},
    "4": {"full_name": "Free K", "position": "K", "team": "DAL", "injury_status": None},
    "99": {"full_name": "Retired Nobody", "position": "RB", "team": None, "injury_status": None},
}
# Two teams. Player "1" is owned; everyone else in the db is available.
ROSTERS = [{"players": ["1"]}, {"players": ["some-other-team-guy"]}]


def test_free_agents_excludes_rostered_players():
    fas = waivers.compute_free_agents(ROSTERS, PLAYERS_DB)
    ids = {p["player_id"] for p in fas}
    assert "1" not in ids, "player on a roster must NOT appear as a free agent"
    assert {"2", "3", "4"} <= ids, "un-rostered players must appear as free agents"


def test_free_agents_excludes_players_with_no_nfl_team():
    # No NFL team => retired / not on an active roster => not a real pickup.
    fas = waivers.compute_free_agents(ROSTERS, PLAYERS_DB)
    ids = {p["player_id"] for p in fas}
    assert "99" not in ids, "a player with no NFL team is not a pickup candidate"


def test_free_agents_can_filter_by_position():
    fas = waivers.compute_free_agents(ROSTERS, PLAYERS_DB, positions={"RB"})
    positions = {p["pos"] for p in fas}
    assert positions == {"RB"}, f"expected only RBs, got {positions}"


def run():
    test_free_agents_excludes_rostered_players()
    test_free_agents_excludes_players_with_no_nfl_team()
    test_free_agents_can_filter_by_position()
    print("waiver tests passed")


if __name__ == "__main__":
    run()
