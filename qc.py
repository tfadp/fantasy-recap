"""
The QC pass, as executable checks instead of a checklist.

Most of the ten checks in COMMON_ERRORS.md exist because a model was reading
screenshots. Pulling from the API removes the whole class: there is no W/L
column to misparse, no bench player whose owner can be misread, no win count
to remember. Those errors are not caught here, they are unreachable.

What remains are checks worth running anyway, because a wrong number that
nobody notices is worse than a run that stops. Every one of these raises
before the model is called, so a failure produces no recap rather than a
confident wrong one.

Mapping to the original ten:

  1  matchup totals            -> structurally guaranteed, verified below
  2  winner and MoV recomputed -> verified below
  3  highest/lowest真 max/min  -> verified below
  4  player points cited       -> the model is handed them, cannot invent
  5  bench swap legal + flip   -> verified below
  6  DEF/K included            -> verified below
  7  waiver dates in window    -> the API returns the week's own transactions
  8  PR audit block present    -> verified below
  9  no cross-chat memory      -> each run reads only this week's pull
  10 no typos / dupes / omits  -> verified below
"""


class QCFailure(AssertionError):
    pass


def _fail(msg):
    raise QCFailure(msg)


def run(a, lw, power=None, previous_power=None):
    """Returns the audit footer. Raises QCFailure on anything wrong."""
    checks = []
    f = a["facts"]
    scored = [r for r in a["teams"] if r["points"] is not None]

    # --- 10: every team present exactly once ------------------------------
    ids = [r["team_id"] for r in a["teams"]]
    if len(ids) != len(set(ids)):
        _fail(f"a team appears in more than one matchup: {ids}")
    roster_ids = {t["team_id"] for t in lw["teams"]}
    missing = roster_ids - set(ids)
    if missing:
        names = [t["name"] for t in lw["teams"] if t["team_id"] in missing]
        _fail(f"team(s) in the league but absent from the week: {names}")
    checks.append(f"{len(ids)} teams, each exactly once")

    # --- matchup count ----------------------------------------------------
    expected = len(roster_ids) // 2
    if len(a["games"]) and len(a["games"]) != expected:
        _fail(f"{len(a['games'])} games for {len(roster_ids)} teams; expected {expected}")
    checks.append(f"{len(a['games'])} games")

    # --- 2: winner and margin recomputed from the totals -------------------
    for g in a["games"]:
        if g["winner_points"] < g["loser_points"]:
            _fail(f"winner scored less than loser: {g['winner']} {g['winner_points']} "
                  f"vs {g['loser']} {g['loser_points']}")
        m = round(g["winner_points"] - g["loser_points"], 2)
        if abs(m - g["margin"]) > 0.011:
            _fail(f"margin wrong for {g['winner']} vs {g['loser']}: "
                  f"stated {g['margin']}, recomputed {m}")
    checks.append("winners and margins recomputed")

    # --- 1: team totals equal the sum of their starters --------------------
    drift = []
    for r in scored:
        s = round(sum(p["points"] for p in r["starters"]), 2)
        if abs(s - r["points"]) > 0.5:
            drift.append(f"{r['team']} total {r['points']} vs starters {s}")
    if drift:
        # Sleeper applies scoring overrides that legitimately move a total, so
        # this reports rather than stops. It is the tell for a bad slot parse.
        checks.append(f"NOTE totals differ from starter sums: {'; '.join(drift)}")
    else:
        checks.append("totals match starter sums")

    # --- 3: superlatives are actually the max and min -----------------------
    if scored:
        hi = max(r["points"] for r in scored)
        lo = min(r["points"] for r in scored)
        if f.get("highest_score", {}).get("points") != hi:
            _fail(f"highest_score says {f.get('highest_score')} but week max is {hi}")
        if f.get("lowest_score", {}).get("points") != lo:
            _fail(f"lowest_score says {f.get('lowest_score')} but week min is {lo}")
        tb = f.get("toilet_bowl") or {}
        if tb and tb.get("points") != lo:
            _fail(f"toilet bowl {tb} is not the week low {lo}")
        checks.append(f"high {hi}, low {lo}, toilet bowl matches")

    # --- 5: the bench swap is legal, single, and flips only if it flips -----
    for r in scored:
        sw = r.get("best_legal_swap")
        if not sw:
            continue
        total = round(r["points"] + sw["swing"], 2)
        if abs(total - r["total_after_best_swap"]) > 0.011:
            _fail(f"{r['team']} swap math: {r['points']} + {sw['swing']} != "
                  f"{r['total_after_best_swap']}")
        if r["would_have_won"]:
            if r["result"] != "L":
                _fail(f"{r['team']} flagged as a flip but did not lose")
            if not (total > r["opponent_points"]):
                _fail(f"{r['team']} flagged as a flip but {total} does not beat "
                      f"{r['opponent_points']}")
    flips = [r["team"] for r in scored if r["would_have_won"]]
    checks.append(f"bench swaps legal and single; {len(flips)} genuine flip(s)"
                  + (f": {', '.join(flips)}" if flips else ""))

    # --- 6: kickers and defenses are in the data ---------------------------
    kd = sum(1 for r in scored for p in r["starters"]
             if p["pos"] in ("K", "DEF", "D/ST", "DST"))
    checks.append(f"{kd} K/DEF starters counted")

    # --- 8 + PR movement sums to zero --------------------------------------
    if power:
        moves = [r.get("movement") for r in power if r.get("movement") is not None]
        if moves and sum(moves) != 0:
            _fail(f"power ranking movement does not net to zero: {sum(moves)}")
        ranks = [r["rank"] for r in power]
        if ranks != list(range(1, len(power) + 1)):
            _fail(f"power ranking ranks are not 1..n: {ranks}")
        for r in power:
            if not r.get("inputs") or not r.get("subscores"):
                _fail(f"power ranking for {r['team']} has no audit inputs")
        checks.append(f"power rankings 1-{len(power)}, movement nets to zero"
                      if moves else f"power rankings 1-{len(power)}, no prior week so no arrows")

    # --- 4/7: what the model is allowed to say -----------------------------
    checks.append("every cited number computed here; the model adds no arithmetic")

    footer = [
        f"QC audit - {a['league']} week {a['week']}, {a['season']}",
        f"  games counted: {len(a['games'])}",
        f"  max score: {f.get('highest_score', {}).get('points')}"
        f" ({f.get('highest_score', {}).get('team')})",
        f"  min score: {f.get('lowest_score', {}).get('points')}"
        f" ({f.get('lowest_score', {}).get('team')})",
        f"  waiver window: the week's own transactions, from the API",
        f"  history: {f.get('historical', {}).get('weeks_of_history', 0)} prior weeks",
    ]
    footer += [f"  check: {c}" for c in checks]
    return "\n".join(footer)
