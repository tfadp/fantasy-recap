"""
Power Rankings, exactly as specified, computed from the API rather than typed in.

    Power Score = 0.40 x Season PF Score
                + 0.25 x Last 2 Weeks Score
                + 0.25 x Win% Score
                + 0.10 x Consistency Score

Every sub-score is on 0-100 before weighting. Every input and sub-score is
returned alongside the result so the audit block can print them and anyone in
the league can re-derive the number by hand.

TWO FORMULAS WERE SUPPLIED AND THEY DISAGREE. The earlier one weighted
0.50/0.25/0.15/0.10 and built the PF component from *rank* (best PF = 100,
worst = 0). The later, fuller one weights 0.40/0.25/0.25/0.10 and builds it
from the *values* normalized against the league. This module defaults to the
later one and keeps the earlier available via WEIGHTS_V1 / pf_mode="rank",
because the choice changes the order: rank mode spaces teams evenly and
ignores how far apart they actually scored, value mode lets a runaway team
pull away. Set it once and leave it, so movement stays meaningful.
"""

import statistics

WEIGHTS = {"pf": 0.40, "last2": 0.25, "record": 0.25, "consistency": 0.10}
WEIGHTS_V1 = {"pf": 0.50, "last2": 0.25, "record": 0.15, "consistency": 0.10}


def _normalize(values):
    """Min-max onto 0-100. All-equal inputs land on 50 rather than dividing by zero."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [50.0 for _ in values]
    return [round((v - lo) / (hi - lo) * 100, 2) for v in values]


def _rank_scores(values):
    """Best value = 100, worst = 0, evenly spaced. The v1 reading."""
    order = sorted(range(len(values)), key=lambda i: -values[i])
    n = len(values)
    out = [0.0] * n
    for place, i in enumerate(order):
        out[i] = round(100 * (n - 1 - place) / (n - 1), 2) if n > 1 else 50.0
    return out


def weekly_scores_by_team(history, current, season):
    """
    {team_id: [week1, week2, ...]} for this season, in week order, including
    the week being written about.
    """
    weeks = [h for h in history if h["season"] == season and h["week"] < current["week"]]
    weeks.sort(key=lambda h: h["week"])
    seq = {}
    for h in weeks + [current]:
        for m in h["matchups"]:
            for side in m["teams"]:
                seq.setdefault(side["team_id"], []).append(side["points"])
    return seq


def compute(current, history, weights=None, pf_mode="value",
            consistency_mode="spec", display_scale="score"):
    """
    Returns a list ordered best to worst, each entry carrying its inputs and
    sub-scores. Feed `previous` into add_movement() to get the arrows.
    """
    weights = weights or WEIGHTS
    season = current["season"]
    teams = current["teams"]
    seq = weekly_scores_by_team(history, current, season)

    ids = [t["team_id"] for t in teams if seq.get(t["team_id"])]
    if not ids:
        return []
    by_id = {t["team_id"]: t for t in teams}

    season_pf = [by_id[i]["points_for"] for i in ids]
    last2 = []
    for i in ids:
        s = seq[i]
        last2.append(round(sum(s[-2:]) / len(s[-2:]), 2))

    winpct = []
    for i in ids:
        t = by_id[i]
        games = t["wins"] + t["losses"] + t["ties"]
        winpct.append(round(((t["wins"] + 0.5 * t["ties"]) / games * 100) if games else 50.0, 2))

    stdevs = []
    for i in ids:
        s = seq[i]
        stdevs.append(round(statistics.pstdev(s), 2) if len(s) > 1 else 0.0)

    pf_scores = _rank_scores(season_pf) if pf_mode == "rank" else _normalize(season_pf)
    last2_scores = _normalize(last2)
    record_scores = winpct[:]          # already 0-100, per the spec

    league_stdev = sum(stdevs) / len(stdevs) if stdevs else 0
    if consistency_mode == "spec":
        # 100 - (stdev / league avg stdev x 100), floored at 0, as written.
        # Note this puts an average-volatility team at 0, not 50, so the whole
        # component sits low. It is only 10% of the score, but it is the reason
        # consistency rarely moves anyone. Set consistency_mode="normalized"
        # to spread it across 0-100 instead.
        cons_scores = [max(0.0, round(100 - (sd / league_stdev * 100), 2)) if league_stdev else 50.0
                       for sd in stdevs]
    else:
        cons_scores = _normalize([-sd for sd in stdevs])

    rows = []
    for k, i in enumerate(ids):
        t = by_id[i]
        score = (weights["pf"] * pf_scores[k]
                 + weights["last2"] * last2_scores[k]
                 + weights["record"] * record_scores[k]
                 + weights["consistency"] * cons_scores[k])
        rows.append({
            "team_id": i,
            "team": t["name"],
            "manager": t.get("manager"),
            # ties only appear if there actually are any; this league writes W-L
            "record": f"{t['wins']}-{t['losses']}" + (f"-{t['ties']}" if t.get("ties") else ""),
            "power_score": round(score, 2),
            "inputs": {
                "season_pf": season_pf[k],
                "last2_avg": last2[k],
                "win_pct": winpct[k],
                "stdev": stdevs[k],
                "league_avg_stdev": round(league_stdev, 2),
                "weeks_counted": len(seq[i]),
            },
            "subscores": {
                "pf": pf_scores[k],
                "last2": last2_scores[k],
                "record": record_scores[k],
                "consistency": cons_scores[k],
            },
        })

    rows.sort(key=lambda r: -r["power_score"])
    for n, r in enumerate(rows, 1):
        r["rank"] = n

    # The sample recap prints Power Rankings on a points-looking scale
    # (135.8 down to 95.4), not the 0-100 the stated formula produces. The
    # ordering is identical either way; only the printed number differs.
    # display_scale="points" maps the 0-100 score onto the league's own
    # weekly scoring range so it reads the way the old recaps did.
    if display_scale == "points" and rows:
        wk = [p for s_ in seq.values() for p in s_]
        lo_p, hi_p = min(wk), max(wk)
        scores = [r["power_score"] for r in rows]
        s_lo, s_hi = min(scores), max(scores)
        for r in rows:
            frac = (r["power_score"] - s_lo) / (s_hi - s_lo) if s_hi > s_lo else 0.5
            r["display_score"] = round(lo_p + frac * (hi_p - lo_p), 1)
    else:
        for r in rows:
            r["display_score"] = r["power_score"]
    return rows


def add_movement(rows, previous):
    """
    previous: [{team_id, rank}] from last week, or None.
    Movement is last week's rank minus this week's, so positive means climbed.
    The sum across all teams is always zero, which is the check the QC pass runs.
    """
    if not previous:
        for r in rows:
            r["movement"] = None
            r["previous_rank"] = None
        return rows
    prev = {p["team_id"]: p["rank"] for p in previous}
    for r in rows:
        p = prev.get(r["team_id"])
        r["previous_rank"] = p
        r["movement"] = (p - r["rank"]) if p is not None else None
    return rows


def render(rows):
    """Plain lines, no table, ready to paste."""
    out = []
    for r in rows:
        mv = r.get("movement")
        arrow = ""
        if mv:
            arrow = f" ({'up' if mv > 0 else 'down'} {abs(mv)})"
        elif mv == 0:
            arrow = " (--)"
        out.append(f"{r['rank']}. {r['team']} - {r.get('display_score', r['power_score'])}"
                   f" - {r['record']}{arrow}")
    return "\n".join(out)


def audit_block(rows, weights=None, pf_mode="value", consistency_mode="spec"):
    weights = weights or WEIGHTS
    lines = [f"PR inputs (weights pf {weights['pf']}, last2 {weights['last2']}, "
             f"record {weights['record']}, consistency {weights['consistency']}; "
             f"pf_mode {pf_mode}, consistency_mode {consistency_mode})"]
    for r in rows:
        i, s = r["inputs"], r["subscores"]
        lines.append(
            f"  {r['team']}: PF {i['season_pf']} -> {s['pf']} | "
            f"L2 {i['last2_avg']} -> {s['last2']} | "
            f"win% {i['win_pct']} | stdev {i['stdev']} -> {s['consistency']} | "
            f"= {r['power_score']}")
    return "\n".join(lines)
