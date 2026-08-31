"""
Yahoo adapter.

Two one-time setup steps, then it runs itself:

  1. Get API access approved at https://sports.yahoo.com/developer/access/
     Read-only is the default and is all this needs.
  2. Create the app, then run `python3 setup_yahoo.py` once. It opens a Yahoo
     login, you click Approve, and it writes oauth2.json. After that the
     library refreshes the token on its own.

Your league key looks like `449.l.123456`. The number after `l.` is the league id
in your league URL. The prefix is Yahoo's game key for that NFL season, which
this file looks up for you.

NOTE ON YAHOO'S JSON: it is deeply nested and uses numeric string keys for
lists. `_flatten` below turns those into ordinary lists so the rest of the
pipeline never has to know.
"""

import json
import os

BASE = "https://fantasysports.yahooapis.com/fantasy/v2"
TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "oauth2.json")


def _session():
    from yahoo_oauth import OAuth2
    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError(
            f"{TOKEN_FILE} not found. Run setup_yahoo.py once to authorize.")
    oauth = OAuth2(None, None, from_file=TOKEN_FILE)
    if not oauth.token_is_valid():
        oauth.refresh_access_token()
    return oauth.session


def _get(path):
    sep = "&" if "?" in path else "?"
    r = _session().get(f"{BASE}{path}{sep}format=json")
    r.raise_for_status()
    return r.json()


def _flatten(node):
    """Yahoo wraps lists as {"0": {...}, "1": {...}, "count": n}. Undo that."""
    if isinstance(node, dict):
        keys = [k for k in node if k.isdigit()]
        if keys and "count" in node:
            return [_flatten(node[k]) for k in sorted(keys, key=int)]
        return {k: _flatten(v) for k, v in node.items() if k != "count"}
    if isinstance(node, list):
        merged = {}
        others = []
        for item in node:
            if isinstance(item, dict):
                merged.update(item)
            elif item not in (None, [], {}):
                others.append(_flatten(item))
        if merged and not others:
            return {k: _flatten(v) for k, v in merged.items()}
        return [_flatten(i) for i in node]
    return node


def game_key(season):
    """Yahoo's game key for an NFL season, e.g. 2026 -> '4xx'."""
    d = _flatten(_get(f"/game/nfl"))
    g = d["fantasy_content"]["game"]
    if isinstance(g, list):
        g = g[0]
    if str(g.get("season")) == str(season):
        return str(g["game_key"])
    d = _flatten(_get(f"/games;game_codes=nfl;seasons={season}"))
    games = d["fantasy_content"]["users"] if "users" in d["fantasy_content"] else d
    return str(_find_first(games, "game_key"))


def _find_first(node, key):
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for v in node.values():
            r = _find_first(v, key)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = _find_first(v, key)
            if r is not None:
                return r
    return None


def list_leagues(season):
    """Helper for setup: your Yahoo NFL leagues for a season."""
    gk = game_key(season)
    d = _flatten(_get(f"/users;use_login=1/games;game_keys={gk}/leagues"))
    out = []

    def walk(n):
        if isinstance(n, dict):
            if "league_key" in n and "name" in n:
                out.append({"league_key": n["league_key"], "name": n["name"]})
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(d)
    return out


def _player_entries(node):
    """Pull every player object out of a roster payload."""
    found = []

    def walk(n):
        if isinstance(n, dict):
            if "player_key" in n and ("name" in n or "player_id" in n):
                found.append(n)
                return
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return found


def _mkplayer(p):
    name = p.get("name")
    if isinstance(name, dict):
        name = name.get("full")
    sel = p.get("selected_position")
    if isinstance(sel, list):
        sel = next((x.get("position") for x in sel if isinstance(x, dict) and "position" in x), None)
    elif isinstance(sel, dict):
        sel = sel.get("position")
    pts = p.get("player_points")
    if isinstance(pts, dict):
        pts = pts.get("total")
    pos = p.get("display_position") or p.get("primary_position") or "?"
    if isinstance(pos, str) and "," in pos:
        pos = pos.split(",")[0]
    return {
        "player_id": str(p.get("player_key") or p.get("player_id")),
        "name": name or "unknown",
        "pos": pos,
        "nfl_team": p.get("editorial_team_abbr") or "FA",
        "slot": sel,
        "points": round(float(pts or 0), 2),
        "injury": p.get("status_full") or p.get("status"),
    }


def fetch(league_key, week):
    """Return one league_week dict. See schema.py."""
    week = int(week)
    settings = _flatten(_get(f"/league/{league_key}/settings"))
    league = settings["fantasy_content"]["league"]
    if isinstance(league, list):
        league = {k: v for d in league if isinstance(d, dict) for k, v in d.items()}

    slots = []
    rp = _find_first(league, "roster_positions") or []
    for entry in rp if isinstance(rp, list) else []:
        e = entry.get("roster_position", entry) if isinstance(entry, dict) else {}
        pos = e.get("position")
        if pos and pos not in ("BN", "IR", "IR+"):
            slots += [pos] * int(e.get("count", 1))

    standings = _flatten(_get(f"/league/{league_key}/standings"))
    teams = []
    name_by_key = {}
    for t in _collect_teams(standings):
        tk = t["team_id"]
        name_by_key[tk] = t["name"]
        teams.append(t)

    board = _flatten(_get(f"/league/{league_key}/scoreboard;week={week}"))
    out_matchups = []
    for i, mu in enumerate(_collect_matchups(board)):
        entry = {"matchup_id": str(i), "teams": []}
        for tk, pts in mu:
            roster = _flatten(
                _get(f"/team/{tk}/roster;week={week}/players/stats;type=week;week={week}"))
            players = [_mkplayer(p) for p in _player_entries(roster)]
            starters = [p for p in players if p["slot"] not in (None, "BN", "IR", "IR+")]
            bench = [p for p in players if p["slot"] in ("BN", "IR", "IR+")]
            entry["teams"].append({
                "team_id": tk,
                "points": round(float(pts or 0), 2),
                "projected": None,
                "starters": starters,
                "bench": bench,
            })
        out_matchups.append(entry)

    try:
        txns = _parse_transactions(_flatten(_get(f"/league/{league_key}/transactions")), week)
    except Exception:
        txns = []

    return {
        "source": "yahoo",
        "league_id": str(league_key),
        "league_name": league.get("name", "Yahoo League"),
        "season": str(league.get("season")),
        "week": week,
        "roster_slots": slots,
        "flex_eligible": {},
        "teams": teams,
        "matchups": out_matchups,
        "transactions": txns,
    }


def _collect_teams(node):
    out, seen = [], set()

    def walk(n):
        if isinstance(n, dict):
            if "team_key" in n and "name" in n:
                tk = n["team_key"]
                if tk in seen:
                    return
                seen.add(tk)
                st = n.get("team_standings") or {}
                rec = st.get("outcome_totals") or {}
                mgr = _find_first(n.get("managers", {}), "nickname") or "unknown"
                out.append({
                    "team_id": tk,
                    "name": n["name"],
                    "manager": mgr,
                    "wins": int(rec.get("wins", 0) or 0),
                    "losses": int(rec.get("losses", 0) or 0),
                    "ties": int(rec.get("ties", 0) or 0),
                    "points_for": round(float(st.get("points_for", 0) or 0), 2),
                    "points_against": round(float(st.get("points_against", 0) or 0), 2),
                })
                return
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return out


def _collect_matchups(board):
    """-> [ [(team_key, points), (team_key, points)], ... ]"""
    results = []

    def walk(n):
        if isinstance(n, dict):
            if "matchup" in n:
                m = n["matchup"]
                pair = []
                for t in _collect_matchup_teams(m):
                    pair.append(t)
                if pair:
                    results.append(pair)
                return
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(board)
    return results


def _collect_matchup_teams(m):
    out, seen = [], set()

    def walk(n):
        if isinstance(n, dict):
            if "team_key" in n:
                tk = n["team_key"]
                if tk not in seen:
                    seen.add(tk)
                    pts = n.get("team_points")
                    if isinstance(pts, dict):
                        pts = pts.get("total")
                    out.append((tk, pts))
                return
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(m)
    return out


def _parse_transactions(node, week):
    out = []

    def walk(n):
        if isinstance(n, dict):
            if "transaction_key" in n:
                ttype = n.get("type")
                if ttype in ("add", "drop", "add/drop", "trade"):
                    adds, drops, tids = [], [], set()
                    for p in _player_entries(n):
                        td = p.get("transaction_data")
                        if isinstance(td, list):
                            td = td[0] if td else {}
                        td = td or {}
                        nm = p.get("name")
                        nm = nm.get("full") if isinstance(nm, dict) else nm
                        dest = td.get("destination_team_key")
                        src = td.get("source_team_key")
                        if td.get("type") == "add" and dest:
                            adds.append({"player": nm, "team_id": dest})
                            tids.add(dest)
                        elif td.get("type") == "drop" and src:
                            drops.append({"player": nm, "team_id": src})
                            tids.add(src)
                    out.append({
                        "type": "trade" if ttype == "trade" else (
                            "waiver" if n.get("faab_bid") else "free_agent"),
                        "team_ids": sorted(tids),
                        "adds": adds,
                        "drops": drops,
                        "faab_bid": int(n["faab_bid"]) if n.get("faab_bid") else None,
                    })
                return
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return out
