#!/usr/bin/env python3
"""
The Tuesday waiver recommendation, for Dan's own team.

    1. read this week's footballguys advice (history/footballguys/, pulled from
       Gmail and parsed by footballguys.py)
    2. pull the league from Sleeper: Dan's roster, the free-agent pool, the
       FAAB budget
    3. keep only the advice that applies here: recommended players who are
       actually unowned, Dan's players footballguys says to cut or keep
    4. hand the model those facts and let it write the short recommendation

Design rule, same as the recap: code computes, the model writes. Every player
here is matched by Sleeper id, every bid is a dollar figure derived from the
league's real budget, and the model is told to use them exactly.

Usage:
    python3 waiver_rec.py                 # current Sleeper week, the mop league
    python3 waiver_rec.py --week 4
    python3 waiver_rec.py --no-write      # facts only, skip the model

Output: out/<league>/<season>-wk<NN>-waivers-facts.json and, with an API key,
out/<league>/<season>-wk<NN>-waivers.md
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import env  # noqa: E402
import footballguys  # noqa: E402
import waivers  # noqa: E402
from adapters import sleeper  # noqa: E402
from run import _text_of  # noqa: E402

OUT = os.path.join(HERE, "out")
PROMPT_FILE = os.path.join(HERE, "prompts", "waivers.md")

# Dan's Sleeper display name. Overridable so the same script serves another
# manager without an edit.
MY_USERNAME = os.environ.get("SLEEPER_USERNAME", "tfadp")

# Suffixes that footballguys and Sleeper disagree on ("Ollie Gordon II" vs
# "Ollie Gordon", "Cheap Flier Jr." vs "Cheap Flier"). Dropped before matching.
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_PCT_RANGE_RE = re.compile(r"(?P<lo>\d+)\s*-\s*(?P<hi>\d+)\s*%")


def normalize_name(name: str) -> str:
    """Lowercase, no punctuation, no generational suffix, single spaces."""
    cleaned = re.sub(r"[^a-z0-9 ]", "", name.lower())
    words = [w for w in cleaned.split() if w not in _SUFFIXES]
    return " ".join(words)


def _key(player: dict) -> tuple[str, str]:
    # Name plus position. Two players sharing a full name is rare; two sharing
    # a name AND a position is rare enough to ignore.
    return normalize_name(player["name"]), player["pos"]


def bid_dollars(text: str | None, budget: int, remaining: int | None = None) -> tuple[int, int] | None:
    """Turn "10-20% of Annual FAAB Budget" into ($10, $20) of a $budget league.

    Capped at what Dan has left, because a recommendation he cannot afford is
    not a recommendation. Returns None when the text carries no percent range.
    """
    if not text:
        return None
    match = _PCT_RANGE_RE.search(text)
    if not match:
        return None
    lo = round(int(match.group("lo")) * budget / 100)
    hi = round(int(match.group("hi")) * budget / 100)
    if remaining is not None:
        lo, hi = min(lo, remaining), min(hi, remaining)
    return lo, hi


def match_advice(picks: list[dict], priority: list[dict],
                 free_agents: list[dict], my_roster: list[dict]) -> dict:
    """Sort footballguys' advice into what applies to this league and this team.

    available: recommended players nobody owns here (the real candidates)
    gone:      recommended players someone else already owns
    droppable: Dan's players footballguys marked "DROP FOR X OR HIGHER"
    hold:      Dan's players footballguys listed as upgrades (do not cut these)

    A featured pick (the inlined article) carries reasoning and a bid; a
    priority-list row carries only a bid. When both mention the same player the
    featured pick wins, because it says why.
    """
    free_by_key = {_key(p): p for p in free_agents}
    mine_by_key = {_key(p): p for p in my_roster}

    # Merge the two sources per player, featured pick first.
    advice: dict[tuple[str, str], dict] = {}
    for pick in picks:
        advice[_key(pick)] = {
            "name": pick["name"], "pos": pick["pos"], "nfl_team": pick["nfl_team"],
            "bid_pct": _pct_only(pick.get("bid_recommendation")),
            "reasoning": pick.get("reasoning") or "",
            "source": "featured",
        }
    for row in priority:
        key = _key(row)
        if row["direction"] == "upgrade" and key not in advice:
            advice[key] = {
                "name": row["name"], "pos": row["pos"], "nfl_team": row["nfl_team"],
                "bid_pct": row.get("bid"), "reasoning": "", "source": "priority_list",
            }

    available, gone, hold = [], [], []
    for key, entry in advice.items():
        if key in mine_by_key:
            hold.append({**entry, "player_id": mine_by_key[key]["player_id"]})
        elif key in free_by_key:
            fa = free_by_key[key]
            # Sleeper's name spelling and injury flag are the truth on the wire.
            available.append({**entry, "name": fa["name"], "player_id": fa["player_id"],
                              "injury": fa.get("injury")})
        elif entry["bid_pct"]:
            # Only a bid-worthy player counts as "gone"; an unbid upgrade owned
            # elsewhere is just a player having a good week.
            gone.append(entry)

    droppable = []
    for row in priority:
        if row["direction"] == "downgrade" and row.get("drop_for"):
            key = _key(row)
            if key in mine_by_key:
                droppable.append({"name": mine_by_key[key]["name"], "pos": row["pos"],
                                  "nfl_team": row["nfl_team"], "drop_for": row["drop_for"],
                                  "player_id": mine_by_key[key]["player_id"]})

    return {"available": available, "gone": gone, "droppable": droppable, "hold": hold}


def _pct_only(bid_text: str | None) -> str | None:
    """'25-50% of Annual FAAB Budget' -> '25-50%'."""
    if not bid_text:
        return None
    match = _PCT_RANGE_RE.search(bid_text)
    return f"{match.group('lo')}-{match.group('hi')}%" if match else None


def _my_roster(league_id: str, players_db: dict) -> tuple[dict, list[dict], list[dict]]:
    """Dan's Sleeper roster: the raw roster dict, his players, and all rosters."""
    users = sleeper._get(f"/league/{league_id}/users")
    rosters = sleeper._get(f"/league/{league_id}/rosters")
    me = [u for u in users if (u.get("display_name") or "").lower() == MY_USERNAME.lower()]
    if not me:
        sys.exit(f"no Sleeper user named {MY_USERNAME!r} in league {league_id}")
    mine = [r for r in rosters if r["owner_id"] == me[0]["user_id"]][0]
    starters = set(mine.get("starters") or [])
    players = [
        {**sleeper._mkplayer(players_db, pid, 0), "starter": pid in starters}
        for pid in (mine.get("players") or [])
    ]
    return mine, players, rosters


def build_facts(cfg: dict, season: str, week: int) -> dict:
    """Everything the model is allowed to know, all of it computed."""
    league_id = cfg["league_id"]
    league = sleeper._get(f"/league/{league_id}")
    players_db = sleeper._players()
    mine, my_players, rosters = _my_roster(league_id, players_db)
    free_agents = waivers.compute_free_agents(rosters, players_db)

    budget = int(league["settings"].get("waiver_budget") or 100)
    remaining = budget - int(mine["settings"].get("waiver_budget_used") or 0)

    days = footballguys.load_week(season, week)
    picks = [p for d in days for p in d.get("picks", [])]
    priority = [r for d in days for r in d.get("priority", [])]

    matched = match_advice(picks, priority, free_agents, my_players)
    for entry in matched["available"]:
        entry["bid_dollars"] = bid_dollars(entry["bid_pct"], budget, remaining)

    return {
        "league": cfg.get("display_name", cfg["name"]),
        "season": season,
        "week": week,
        "team": MY_USERNAME,
        "record": f"{mine['settings'].get('wins', 0)}-{mine['settings'].get('losses', 0)}",
        "faab": {"budget": budget, "remaining": remaining},
        "roster_slots": league["roster_positions"],
        "my_roster": sorted(my_players, key=lambda p: (not p["starter"], p["pos"], p["name"])),
        "advice_days": len(days),
        "free_agent_pool_size": len(free_agents),
        **matched,
    }


def brief(facts: dict) -> str:
    """The facts as the model should read them, plain and in order."""
    lines = [
        f"{facts['league']}, {facts['season']} week {facts['week']} waivers for {facts['team']} "
        f"({facts['record']}). FAAB ${facts['faab']['remaining']} of ${facts['faab']['budget']} left.",
        f"Roster slots: {', '.join(facts['roster_slots'])}",
        "",
        "MY ROSTER (starters first):",
    ]
    for p in facts["my_roster"]:
        flag = " (starter)" if p["starter"] else ""
        inj = f" [{p['injury']}]" if p.get("injury") else ""
        lines.append(f"  {p['pos']} {p['name']} {p['nfl_team']}{flag}{inj}")

    lines += ["", "AVAILABLE AND RECOMMENDED (unowned in this league):"]
    for a in facts["available"]:
        dollars = a.get("bid_dollars")
        bid = f"bid ${dollars[0]}-${dollars[1]}" if dollars else "no bid figure"
        inj = f" [{a['injury']}]" if a.get("injury") else ""
        lines.append(f"  {a['pos']} {a['name']} {a['nfl_team']}{inj}: {bid} ({a['bid_pct'] or 'n/a'} of budget)")
        if a["reasoning"]:
            lines.append(f"      {a['reasoning']}")
    if not facts["available"]:
        lines.append("  (none of this week's recommended players is unowned here)")

    lines += ["", "ALREADY OWNED BY SOMEONE ELSE:"]
    lines += [f"  {g['pos']} {g['name']} {g['nfl_team']}" for g in facts["gone"]] or ["  (none)"]

    lines += ["", "MY PLAYERS FOOTBALLGUYS SAYS ARE CUTTABLE:"]
    lines += [f"  {d['pos']} {d['name']} {d['nfl_team']} (drop for {d['drop_for']} or higher)"
              for d in facts["droppable"]] or ["  (none)"]

    lines += ["", "MY PLAYERS FOOTBALLGUYS LIKES (hold):"]
    lines += [f"  {h['pos']} {h['name']} {h['nfl_team']}" for h in facts["hold"]] or ["  (none)"]
    return "\n".join(lines)


def write_recommendation(facts: dict) -> str | None:
    """Call Claude with the waivers prompt. Skipped if no API key is set."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    import anthropic

    with open(PROMPT_FILE) as fh:
        system = fh.read()

    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=os.environ.get("RECAP_MODEL", "claude-opus-5"),
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": "\n\n".join([
            f"THIS WEEK, PLAIN:\n{brief(facts)}",
            f"THIS WEEK, COMPLETE DATA:\n{json.dumps(facts, indent=2)}",
            "Write this week's waiver recommendation.",
        ])}],
    )
    return _text_of(msg)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, help="NFL week the waivers are FOR (default: Sleeper's current week)")
    ap.add_argument("--league", default="mop", help="league name from leagues.json")
    ap.add_argument("--no-write", action="store_true", help="facts only, skip the model")
    args = ap.parse_args()

    env.load()
    with open(os.path.join(HERE, "leagues.json")) as fh:
        cfgs = [c for c in json.load(fh)["leagues"] if c["name"] == args.league]
    if not cfgs or cfgs[0]["platform"] != "sleeper":
        sys.exit(f"{args.league!r} is not a Sleeper league in leagues.json; only Sleeper is supported")
    cfg = cfgs[0]

    state = sleeper.current_state()
    season = str(state["season"])
    week = args.week or int(state["week"])

    facts = build_facts(cfg, season, week)
    if facts["advice_days"] == 0:
        sys.exit(f"no footballguys advice stored for {season} week {week}. "
                 f"Pull the emails into history/footballguys/{season}-wk{week:02d}.json first.")

    out_dir = os.path.join(OUT, cfg["name"])
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, f"{season}-wk{week:02d}-waivers")
    with open(f"{stem}-facts.json", "w") as fh:
        json.dump(facts, fh, indent=2)
    print(brief(facts))

    text = None if args.no_write else write_recommendation(facts)
    if text:
        with open(f"{stem}.md", "w") as fh:
            fh.write(text + "\n")
        print(f"\n=== recommendation ===\n{text}")
    else:
        print("\n(facts written; no model call)")


if __name__ == "__main__":
    main()
