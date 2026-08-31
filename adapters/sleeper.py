"""
Sleeper adapter. No authentication, no key, no application. Just the league id.

The league id is the long number in the URL when you open the league on the web:
    https://sleeper.com/leagues/123456789012345678/team
"""

import json
import os
import time
import urllib.request

API = "https://api.sleeper.app/v1"
LEAGUE_TZ = os.environ.get("LEAGUE_TZ", "America/New_York")
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
PLAYER_CACHE = os.path.join(CACHE_DIR, "sleeper_players.json")
PLAYER_CACHE_MAX_AGE = 60 * 60 * 24 * 3


def _get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as r:
        return json.loads(r.read().decode())


def current_state():
    return _get("/state/nfl")


def _players():
    os.makedirs(CACHE_DIR, exist_ok=True)
    fresh = (os.path.exists(PLAYER_CACHE)
             and time.time() - os.path.getmtime(PLAYER_CACHE) < PLAYER_CACHE_MAX_AGE)
    if fresh:
        with open(PLAYER_CACHE) as f:
            return json.load(f)
    data = _get("/players/nfl")
    with open(PLAYER_CACHE, "w") as f:
        json.dump(data, f)
    return data


def list_leagues(username, season=None):
    """Helper for setup: find your league ids from your Sleeper username."""
    u = _get(f"/user/{username}")
    season = season or current_state()["season"]
    out = []
    for lg in _get(f"/user/{u['user_id']}/leagues/nfl/{season}"):
        out.append({"league_id": lg["league_id"], "name": lg["name"],
                    "teams": lg["total_rosters"], "status": lg["status"]})
    return out


def _mkplayer(pmap, pid, points, slot=None):
    # Sleeper writes "0" into a starting slot the manager left empty. That is
    # not a missing player, it is a manager who started nobody, and it is worth
    # saying out loud rather than rendering as a player named "0".
    if str(pid) in ("0", "", "None"):
        return {"player_id": "0", "name": "(empty slot)", "pos": slot or "?",
                "nfl_team": "-", "slot": slot, "points": 0.0,
                "injury": None, "empty": True}
    p = pmap.get(str(pid)) or {}
    name = p.get("full_name") or " ".join(
        x for x in (p.get("first_name"), p.get("last_name")) if x) or str(pid)
    return {
        "player_id": str(pid),
        "name": name,
        "pos": p.get("position") or ("DEF" if str(pid).isalpha() else "?"),
        "nfl_team": p.get("team") or "FA",
        "slot": slot,
        "points": round(float(points or 0), 2),
        "injury": p.get("injury_status"),
    }


def fetch(league_id, week):
    """Return one league_week dict. See schema.py."""
    week = int(week)
    league = _get(f"/league/{league_id}")
    users = _get(f"/league/{league_id}/users")
    rosters = _get(f"/league/{league_id}/rosters")
    matchups = _get(f"/league/{league_id}/matchups/{week}")
    try:
        txns = _get(f"/league/{league_id}/transactions/{week}")
    except Exception:
        txns = []
    pmap = _players()

    user_by_id = {u["user_id"]: u for u in users}

    def label(r):
        u = user_by_id.get(r.get("owner_id")) or {}
        meta = u.get("metadata") or {}
        return (meta.get("team_name") or u.get("display_name")
                or f"Roster {r['roster_id']}"), (u.get("display_name") or "unknown")

    teams = []
    name_by_rid = {}
    for r in rosters:
        s = r.get("settings") or {}
        tname, manager = label(r)
        rid = str(r["roster_id"])
        name_by_rid[rid] = tname
        teams.append({
            "team_id": rid,
            "name": tname,
            "manager": manager,
            "wins": s.get("wins", 0),
            "losses": s.get("losses", 0),
            "ties": s.get("ties", 0),
            "points_for": round(float(s.get("fpts", 0)) + float(s.get("fpts_decimal", 0)) / 100, 2),
            "points_against": round(
                float(s.get("fpts_against", 0)) + float(s.get("fpts_against_decimal", 0)) / 100, 2),
        })

    slots = [s for s in (league.get("roster_positions") or []) if s not in ("BN", "IR", "TAXI")]

    grouped = {}
    for m in matchups:
        grouped.setdefault(m.get("matchup_id"), []).append(m)

    out_matchups = []
    for mid, side in sorted(grouped.items(), key=lambda kv: (kv[0] is None, kv[0])):
        entry = {"matchup_id": str(mid), "teams": []}
        for m in side:
            rid = str(m["roster_id"])
            starters = m.get("starters") or []
            spts = m.get("starters_points") or []
            ppts = m.get("players_points") or {}
            start_players = []
            for i, pid in enumerate(starters):
                slot = slots[i] if i < len(slots) else "FLEX"
                start_players.append(_mkplayer(pmap, pid, spts[i] if i < len(spts) else 0, slot))
            bench_ids = [p for p in (m.get("players") or []) if p not in starters]
            bench = [_mkplayer(pmap, pid, ppts.get(pid, 0)) for pid in bench_ids]
            entry["teams"].append({
                "team_id": rid,
                "points": round(float(m.get("points") or 0), 2),
                "projected": None,
                "starters": start_players,
                "bench": bench,
            })
        out_matchups.append(entry)

    out_txns = []
    for t in txns:
        if t.get("status") != "complete":
            continue
        ts = t.get("status_updated")
        when = None
        if ts:
            import datetime
            from zoneinfo import ZoneInfo
            # league-local dates, so "11/20" matches what the league saw
            when = datetime.datetime.fromtimestamp(
                ts / 1000, ZoneInfo(LEAGUE_TZ)).strftime("%m/%d")
        out_txns.append({
            "type": {"waiver": "waiver", "free_agent": "free_agent",
                     "trade": "trade"}.get(t.get("type"), t.get("type")),
            "date": when,
            "team_ids": [str(r) for r in (t.get("roster_ids") or [])],
            "adds": [{"player_id": str(pid), "player": _mkplayer(pmap, pid, 0)["name"],
                      "pos": _mkplayer(pmap, pid, 0)["pos"], "team_id": str(rid)}
                     for pid, rid in (t.get("adds") or {}).items()],
            "drops": [{"player_id": str(pid), "player": _mkplayer(pmap, pid, 0)["name"],
                       "pos": _mkplayer(pmap, pid, 0)["pos"], "team_id": str(rid)}
                      for pid, rid in (t.get("drops") or {}).items()],
            "faab_bid": (t.get("settings") or {}).get("waiver_bid"),
        })

    return {
        "source": "sleeper",
        "league_id": str(league_id),
        "league_name": league.get("name"),
        "season": str(league.get("season")),
        "week": week,
        "roster_slots": slots,
        "flex_eligible": {},
        "teams": teams,
        "matchups": out_matchups,
        "transactions": out_txns,
        "_previous_league_id": league.get("previous_league_id"),
    }


def season_history(league_id, through_week, seasons_back=2):
    """Every completed week of this league and its prior seasons, for record comparisons."""
    weeks = []
    lid = str(league_id)
    depth = 0
    while lid and depth <= seasons_back:
        try:
            league = _get(f"/league/{lid}")
        except Exception:
            break
        is_current = str(lid) == str(league_id)
        last = through_week - 1 if is_current else int(
            (league.get("settings") or {}).get("playoff_week_start", 15)) - 1
        for w in range(1, max(last, 0) + 1):
            try:
                lw = fetch(lid, w)
                if any(s["points"] > 0 for m in lw["matchups"] for s in m["teams"]):
                    weeks.append(lw)
            except Exception:
                continue
        lid = league.get("previous_league_id")
        depth += 1
    return weeks
