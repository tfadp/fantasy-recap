"""
The common format both adapters must produce: league_week.

Everything downstream (analysis, the write-up prompt) reads only this.
Adding a third platform later means writing one more adapter and nothing else.

league_week = {
  "source":        "sleeper" | "yahoo",
  "league_id":     str,
  "league_name":   str,
  "season":        str,            # "2026"
  "week":          int,
  "roster_slots":  [str],          # ["QB","RB","RB","WR","WR","TE","FLEX","K","DEF"]
  "flex_eligible": {slot: [pos]},  # {"FLEX": ["RB","WR","TE"]}
  "teams": [ {
      "team_id":        str,
      "name":           str,        # team name as shown in the league
      "manager":        str,        # human's display name
      "wins":           int,
      "losses":         int,
      "ties":           int,
      "points_for":     float,      # season to date, through this week
      "points_against": float,
  } ],
  "matchups": [ {
      "matchup_id": str,
      "teams": [ {                  # 1 entry if a bye, otherwise 2
          "team_id":  str,
          "points":   float,
          "projected": float | None,
          "starters": [ player ],
          "bench":    [ player ],
      } ],
  } ],
  "transactions": [ {
      "type":      "waiver" | "free_agent" | "trade",
      "team_ids":  [str],
      "adds":      [ {"player": str, "team_id": str} ],
      "drops":     [ {"player": str, "team_id": str} ],
      "faab_bid":  int | None,
  } ],
}

player = {
  "player_id": str,
  "name":      str,       # "Josh Allen"
  "pos":       str,       # "QB"
  "nfl_team":  str,       # "BUF"
  "slot":      str|None,  # lineup slot for starters, None for bench
  "points":    float,
  "injury":    str|None,
}
"""

REQUIRED_TOP = ("source", "league_id", "league_name", "season", "week",
                "roster_slots", "teams", "matchups", "transactions")

DEFAULT_FLEX = {
    "FLEX": ["RB", "WR", "TE"],
    "W/R/T": ["RB", "WR", "TE"],
    "WRT": ["RB", "WR", "TE"],
    "REC_FLEX": ["WR", "TE"],
    "W/T": ["WR", "TE"],
    "SUPER_FLEX": ["QB", "RB", "WR", "TE"],
    "SUPERFLEX": ["QB", "RB", "WR", "TE"],
    "Q/W/R/T": ["QB", "RB", "WR", "TE"],
    "IDP_FLEX": ["DL", "LB", "DB"],
}

# slots that never hold a real scoring starter
NON_STARTING_SLOTS = {"BN", "IR", "TAXI", "BE"}


def validate(lw):
    """Raise if an adapter produced something the analyzer can't read."""
    missing = [k for k in REQUIRED_TOP if k not in lw]
    if missing:
        raise ValueError(f"league_week missing keys: {missing}")
    if not lw["matchups"]:
        raise ValueError(
            f"{lw.get('league_name')} week {lw['week']} came back with no matchups. "
            f"Usually this means the week has not been played yet, or the league id "
            f"points at a season that has not started. Nothing was written.")
    ids = {t["team_id"] for t in lw["teams"]}
    for m in lw["matchups"]:
        for side in m["teams"]:
            if side["team_id"] not in ids:
                raise ValueError(f"matchup references unknown team {side['team_id']}")
            for p in side["starters"] + side["bench"]:
                for k in ("player_id", "name", "pos", "points"):
                    if k not in p:
                        raise ValueError(f"player missing '{k}': {p}")
    return True
