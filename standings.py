"""
As-of-week standings, computed from results instead of read off the API.

Sleeper's /rosters endpoint reports wins, losses and points_for as they stand
*right now*, not as they stood after the week being written up. On the live
Tuesday run those are the same thing, so nothing looks wrong. Every other day
they are different, and the difference is silent: ask for week 1 in December
and every team comes back carrying its final record, which the model then
prints without hesitation, because technically every number it was handed had
been computed.

That is the exact failure the rest of this repo is built to make impossible,
arriving through the one door nobody was watching. So the table gets computed
here, by walking the season's own results, the same way the scoreboard is.

Same answer on Tuesday. Correct answer every other day. And rank movement
starts working, which it never did before: the old code compared this week's
standings against a "last week" that had been re-fetched live, so the two were
always identical and `record_changes` was always empty.
"""


def _results(lw):
    """(team_id, points, opponent_points) per team. opponent None on a bye."""
    out = []
    for m in lw.get("matchups", []):
        sides = m.get("teams") or []
        if len(sides) == 2:
            a, b = sides
            out.append((a["team_id"], float(a["points"]), float(b["points"])))
            out.append((b["team_id"], float(b["points"]), float(a["points"])))
        else:
            # a bye, or a league scoring against the median. No head to head
            # result, but the points still count toward PF.
            for s in sides:
                out.append((s["team_id"], float(s["points"]), None))
    return out


def table_through(weeks):
    """Cumulative record keyed by team_id over `weeks`, which must be in order."""
    acc = {}
    for lw in weeks:
        for tid, pts, opp in _results(lw):
            r = acc.setdefault(tid, {"wins": 0, "losses": 0, "ties": 0,
                                     "points_for": 0.0, "points_against": 0.0,
                                     "games": 0})
            r["points_for"] += pts
            if opp is None:
                continue
            r["games"] += 1
            r["points_against"] += opp
            if pts > opp:
                r["wins"] += 1
            elif pts < opp:
                r["losses"] += 1
            else:
                r["ties"] += 1
    for r in acc.values():
        r["points_for"] = round(r["points_for"], 2)
        r["points_against"] = round(r["points_against"], 2)
    return acc


def _stamp(lw, tbl):
    for t in lw["teams"]:
        r = tbl.get(t["team_id"])
        if r:
            t.update({k: v for k, v in r.items() if k != "games"})
            t["games_played"] = r["games"]


def apply(lw, history):
    """
    Rewrite `lw` (and each current-season week in `history`) so every record is
    the record as it stood at the end of that week.

    Returns a dict describing what was used, for the QC footer.
    """
    season = lw["season"]
    prior = sorted((h for h in history
                    if h["season"] == season and h["week"] < lw["week"]),
                   key=lambda h: h["week"])

    # each history week gets the table as of itself, so rank movement compares
    # two tables that were each true at the time
    for i, h in enumerate(prior):
        _stamp(h, table_through(prior[:i + 1]))

    before = {t["team_id"]: (t.get("wins"), t.get("losses"), t.get("points_for"))
              for t in lw["teams"]}
    final = table_through(prior + [lw])
    _stamp(lw, final)
    after = {t["team_id"]: (t.get("wins"), t.get("losses"), t.get("points_for"))
             for t in lw["teams"]}

    weeks_used = sorted(h["week"] for h in prior) + [lw["week"]]
    return {
        "weeks_counted": weeks_used,
        "expected_games": len(weeks_used),
        # The API's own totals are a free second opinion. They agree on a live
        # run and disagree when you re-run an old week, which is worth saying
        # out loud rather than hiding.
        "agrees_with_api": before == after,
    }
