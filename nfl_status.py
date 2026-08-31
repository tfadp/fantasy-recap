"""
Step 2 of the Tuesday run: confirm the week's games are actually final.

Without this the pipeline will happily write a recap in the middle of Sunday
afternoon and declare someone the winner while their running back is still
on the field. Uses ESPN's public scoreboard, which needs no key.
"""

import json
import urllib.request

ESPN = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        "?week={week}&seasontype={st}&dates={season}")


def week_status(season, week, season_type=2):
    """season_type: 1 preseason, 2 regular season, 3 postseason."""
    url = ESPN.format(week=int(week), st=season_type, season=season)
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read().decode())
    events = data.get("events", [])
    games = []
    for e in events:
        t = (e.get("status") or {}).get("type") or {}
        games.append({
            "game": e.get("shortName"),
            "state": t.get("name"),
            "completed": bool(t.get("completed")),
        })
    unfinished = [g for g in games if not g["completed"]]
    return {
        "season": str(season),
        "week": int(week),
        "total_games": len(games),
        "final": len(games) > 0 and not unfinished,
        "unfinished": unfinished,
    }


def assert_final(season, week, season_type=2, allow_incomplete=False):
    s = week_status(season, week, season_type)
    if s["total_games"] == 0:
        raise RuntimeError(f"ESPN has no games for {season} week {week}. Wrong week or season?")
    if not s["final"] and not allow_incomplete:
        names = ", ".join(g["game"] for g in s["unfinished"])
        raise RuntimeError(
            f"{len(s['unfinished'])} game(s) not final for week {week}: {names}. "
            f"Re-run later, or pass --force to write anyway.")
    return s
