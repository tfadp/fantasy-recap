"""
Adapter for a league_week handed in from outside, rather than fetched.

That is what the browser extension sends: you open your Yahoo league, click
once, and the week arrives here already in the common shape. From this point
on it is indistinguishable from an API pull, so it gets the same analysis and
the same write-up quality.

Source order, best first:
  1. LEAGUE_WEEK_JSON environment variable (what the GitHub Action sets)
  2. inbox/*.json, newest first (what you get if you download the file)
"""

import glob
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(HERE, "inbox")

# the extension's fallback path can return matchups with scores but no rosters
NEEDS_ROSTERS = ("top performer", "bench regret", "optimal lineup", "waiver pickups")


def fetch(league_id, week):
    lw = _load()
    if lw is None:
        raise RuntimeError(
            "No week was handed in. Either the extension did not fire, or "
            "there is nothing in inbox/. Nothing was written.")
    if week and lw.get("week") and int(lw["week"]) != int(week):
        raise RuntimeError(
            f"Asked for week {week} but the handed-in data is week {lw['week']}. "
            f"Refusing to mislabel it.")
    lw.setdefault("transactions", [])
    lw.setdefault("roster_slots", [])
    lw.setdefault("flex_eligible", {})
    lw.setdefault("teams", [])
    _warn_if_thin(lw)
    return lw


def _load():
    raw = os.environ.get("LEAGUE_WEEK_JSON")
    if raw:
        return json.loads(raw)
    files = sorted(glob.glob(os.path.join(INBOX, "*.json")),
                   key=os.path.getmtime, reverse=True)
    if files:
        with open(files[0]) as f:
            return json.load(f)
    return None


def _warn_if_thin(lw):
    """
    Say plainly what is missing rather than letting the write-up quietly skip
    half its material. A scores-only week still produces a real recap; it just
    cannot talk about benches.
    """
    have_rosters = any(t.get("starters") for m in lw.get("matchups", [])
                       for t in m.get("teams", []))
    notes = []
    if not have_rosters:
        notes.append("no player rosters, so " + ", ".join(NEEDS_ROSTERS) +
                     " will be absent from this week's recap")
    if not lw.get("teams"):
        notes.append("no standings")
    if not lw.get("transactions"):
        notes.append("no transactions (Yahoo's matchup page does not show them; "
                     "the extension would need the transactions page too)")
    if notes:
        lw["_thin"] = notes
        print("  note: " + "; ".join(notes))
    return lw
