"""
Waiver-wire helper. Reads a league's rosters and works out who is available to
pick up (the free-agent pool), so the Tuesday recommendation has a real,
computed list of candidates rather than a guess.

Design rule, same as the recap: code computes, the model writes. This module
only produces facts (who is rostered, who is free); it makes no add/drop call.

Stdlib only, like the rest of the Sleeper path.
"""
from adapters import sleeper

# The positions a fantasy manager can actually roster. Anything else in the
# player database (offensive linemen, etc.) is noise for waivers.
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


def compute_free_agents(
    rosters: list[dict],
    players_db: dict,
    positions: set[str] | None = None,
) -> list[dict]:
    """Players in the database who are on nobody's roster.

    rosters:    Sleeper roster dicts, each with a "players" list of player_ids.
    players_db: the Sleeper /players/nfl map, player_id -> player info.
    positions:  which positions to keep (defaults to all fantasy positions).

    A free agent is defined by subtraction: every player, minus everyone who is
    rostered. We then drop players with no NFL team, because a player who is not
    on an active roster (retired, practice squad) is not a real pickup.
    """
    keep = positions or FANTASY_POSITIONS
    rostered = {str(pid) for r in rosters for pid in (r.get("players") or [])}

    free: list[dict] = []
    for pid, p in players_db.items():
        if str(pid) in rostered:
            continue
        pos = p.get("position")
        if pos not in keep:
            continue
        if not p.get("team"):  # no NFL team => not a pickup candidate
            continue
        name = p.get("full_name") or " ".join(
            x for x in (p.get("first_name"), p.get("last_name")) if x) or str(pid)
        free.append({
            "player_id": str(pid),
            "name": name,
            "pos": pos,
            "nfl_team": p.get("team"),
            "injury": p.get("injury_status"),
        })
    return free


def fetch_free_agents(league_id: str, positions: set[str] | None = None) -> list[dict]:
    """Live free-agent pool for a Sleeper league.

    Reuses the Sleeper adapter's cached player database and its HTTP helper so
    we neither re-download the 5MB player file nor duplicate request logic.
    """
    rosters = sleeper._get(f"/league/{league_id}/rosters")
    players_db = sleeper._players()
    return compute_free_agents(rosters, players_db, positions)
