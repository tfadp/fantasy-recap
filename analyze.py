"""
Turns a league_week into facts.

This is the layer that exists so the model never does arithmetic. Everything
the write-up might want to claim is computed here, checked here, and handed
over as a finished number. The model's only job downstream is voice.
"""

from schema import DEFAULT_FLEX


# --------------------------------------------------------------------------
# lineup math
# --------------------------------------------------------------------------

def _eligible(slot, pos):
    if slot == pos:
        return True
    if slot in ("DEF", "D/ST", "DST") and pos in ("DEF", "D/ST", "DST"):
        return True
    return pos in DEFAULT_FLEX.get(slot, [])


def optimal_lineup(players, slots):
    """
    Best legal lineup from everyone rostered. Greedy from the highest scorer
    down, each player taking the most restrictive slot he is eligible for,
    which is the standard approach and matches a true optimum in practice.
    """
    pool = sorted(players, key=lambda p: -p["points"])
    openings = list(slots)
    breadth = {i: sum(1 for p in pool if _eligible(s, p["pos"]))
               for i, s in enumerate(openings)}
    taken, used = [], set()
    for p in pool:
        cand = [i for i, s in enumerate(openings)
                if i not in used and _eligible(s, p["pos"])]
        if not cand:
            continue
        pick = min(cand, key=lambda i: breadth[i])
        used.add(pick)
        taken.append(dict(p, slot=openings[pick]))
        if len(used) == len(openings):
            break
    return taken, round(sum(p["points"] for p in taken), 2)


def best_legal_swap(side):
    """
    The single best legal bench-for-starter swap, and only that.

    The house rule is explicit: never stack two bench players, never combine
    two players who cannot legally be in the lineup together. So this returns
    exactly one swap, the one with the largest positive swing, where "legal"
    means the bench player is eligible for the slot the starter occupied.
    """
    best = None
    for st in side["starters"]:
        slot = st.get("slot") or st["pos"]
        for b in side["bench"]:
            if not _eligible(slot, b["pos"]):
                continue
            swing = round(b["points"] - st["points"], 2)
            if swing <= 0:
                continue
            if best is None or swing > best["swing"]:
                best = {
                    "benched": b["name"], "benched_pos": b["pos"],
                    "benched_points": b["points"],
                    "started": st["name"], "started_slot": slot,
                    "started_points": st["points"],
                    "swing": swing,
                }
    return best


def _all_legal_swaps(row):
    """
    Every legal single swap for one team, best first, one entry per bench
    player so the same manager can appear twice without anything being added
    together. Each line stands alone.
    """
    out = []
    for b in row["bench"]:
        best = None
        for st in row["starters"]:
            slot = st.get("slot") or st["pos"]
            if not _eligible(slot, b["pos"]):
                continue
            swing = round(b["points"] - st["points"], 2)
            if swing <= 0:
                continue
            if best is None or swing > best["swing"]:
                best = {"benched": b["name"], "benched_pos": b["pos"],
                        "benched_points": b["points"], "started": st["name"],
                        "started_slot": slot, "started_points": st["points"],
                        "swing": swing}
        if best:
            out.append(best)
    out.sort(key=lambda x: -x["swing"])
    return out


def bench_mistakes(side, slots):
    """Every case where a benched player would have replaced a starter."""
    starters, bench = side["starters"], side["bench"]
    out = []
    for b in bench:
        swaps = [s for s in starters if _eligible(s.get("slot") or s["pos"], b["pos"])]
        if not swaps:
            swaps = [s for s in starters if s["pos"] == b["pos"]]
        if not swaps:
            continue
        worst = min(swaps, key=lambda s: s["points"])
        if b["points"] > worst["points"]:
            out.append({
                "benched": b["name"],
                "benched_points": b["points"],
                "started": worst["name"],
                "started_points": worst["points"],
                "cost": round(b["points"] - worst["points"], 2),
            })
    out.sort(key=lambda x: -x["cost"])
    return out


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def analyze(lw, history=None):
    history = history or []
    slots = lw["roster_slots"]
    team_by_id = {t["team_id"]: t for t in lw["teams"]}

    def tname(tid):
        return (team_by_id.get(tid) or {}).get("name", tid)

    # ---- per team ---------------------------------------------------------
    rows = []
    for m in lw["matchups"]:
        sides = m["teams"]
        opp = {}
        if len(sides) == 2:
            opp[sides[0]["team_id"]] = sides[1]
            opp[sides[1]["team_id"]] = sides[0]
        for side in sides:
            tid = side["team_id"]
            allp = side["starters"] + side["bench"]
            opt_lineup, opt_pts = optimal_lineup(allp, slots)
            o = opp.get(tid)
            mistakes = bench_mistakes(side, slots)
            swap = best_legal_swap(side)
            # "would have won" is judged on the ONE legal swap, never on the
            # full optimal lineup. Optimal is several swaps at once, which is
            # exactly the claim the house rules forbid.
            swap_total = round(side["points"] + swap["swing"], 2) if swap else side["points"]
            flips = bool(o and side["points"] < o["points"] and swap_total > o["points"])
            rows.append({
                "team_id": tid,
                "team": tname(tid),
                "manager": (team_by_id.get(tid) or {}).get("manager"),
                "matchup_id": m["matchup_id"],
                "points": side["points"],
                "opponent": tname(o["team_id"]) if o else None,
                "opponent_id": o["team_id"] if o else None,
                "opponent_points": o["points"] if o else None,
                "result": (None if not o else
                           "W" if side["points"] > o["points"] else
                           "L" if side["points"] < o["points"] else "T"),
                "margin": round(abs(side["points"] - o["points"]), 2) if o else None,
                "top_starter": max(side["starters"], key=lambda p: p["points"], default=None),
                "worst_starter": min(
                    [p for p in side["starters"] if p["pos"] not in ("K", "DEF", "D/ST")],
                    key=lambda p: p["points"], default=None),
                "optimal_points": opt_pts,
                "points_left_on_bench": round(opt_pts - side["points"], 2),
                "lineup_efficiency": round(side["points"] / opt_pts, 4) if opt_pts else None,
                "bench_mistakes": mistakes[:5],
                "best_legal_swap": swap,
                "total_after_best_swap": swap_total,
                "would_have_won": flips,
                "would_have_won_optimal_lineup_only": bool(
                    o and side["points"] < o["points"] and opt_pts > o["points"]
                    and not flips),
                "starters": side["starters"],
                "bench": side["bench"],
            })

    scored = [r for r in rows if r["points"] is not None]

    # ---- all-play: how you'd have done against every other team this week --
    pts = sorted((r["points"] for r in scored), reverse=True)
    for r in scored:
        better = sum(1 for p in pts if p < r["points"])
        worse = sum(1 for p in pts if p > r["points"])
        r["all_play_record"] = f"{better}-{worse}"
        r["week_rank"] = worse + 1

    # ---- superlatives -----------------------------------------------------
    facts = {}
    if scored:
        hi = max(scored, key=lambda r: r["points"])
        lo = min(scored, key=lambda r: r["points"])
        facts["highest_score"] = {"team": hi["team"], "points": hi["points"]}
        facts["lowest_score"] = {"team": lo["team"], "points": lo["points"]}
        facts["average_score"] = round(sum(r["points"] for r in scored) / len(scored), 2)

    games = []
    seen = set()
    for r in scored:
        if r["opponent_id"] is None or r["matchup_id"] in seen:
            continue
        seen.add(r["matchup_id"])
        w = r if r["result"] == "W" else next(
            x for x in scored if x["team_id"] == r["opponent_id"])
        l = r if w is not r else next(
            x for x in scored if x["team_id"] == r["opponent_id"])
        games.append({
            "matchup_id": r["matchup_id"],
            "winner": w["team"], "winner_points": w["points"],
            "loser": l["team"], "loser_points": l["points"],
            "margin": round(w["points"] - l["points"], 2),
            "winner_id": w["team_id"], "loser_id": l["team_id"],
        })

    if games:
        facts["closest_game"] = min(games, key=lambda g: g["margin"])
        facts["biggest_blowout"] = max(games, key=lambda g: g["margin"])

    # unlucky / lucky. Only claimed when the score actually justifies it:
    # a high-scoring loss must be above average, a lucky win below it.
    avg = facts.get("average_score")
    losers = [r for r in scored if r["result"] == "L"]
    winners = [r for r in scored if r["result"] == "W"]
    if losers:
        u = max(losers, key=lambda r: r["points"])
        beat = sum(1 for r in scored
                   if r["points"] < u["points"] and r["team_id"] != u["team_id"])
        if avg is None or u["points"] > avg:
            facts["unluckiest_loss"] = {
                "team": u["team"], "points": u["points"],
                "opponent": u["opponent"], "opponent_points": u["opponent_points"],
                "would_have_beaten": beat, "of_other_teams": len(scored) - 1}
    if winners:
        lw_ = min(winners, key=lambda r: r["points"])
        if avg is None or lw_["points"] < avg:
            facts["luckiest_win"] = {"team": lw_["team"], "points": lw_["points"],
                                     "opponent": lw_["opponent"],
                                     "opponent_points": lw_["opponent_points"]}

    # ---- upset ------------------------------------------------------------
    # expectation from season-to-date scoring average, excluding this week
    prior_avg = _season_averages(history, lw)
    for g in games:
        wa, la = prior_avg.get(g["winner_id"]), prior_avg.get(g["loser_id"])
        g["expected_margin"] = round(wa - la, 2) if (wa is not None and la is not None) else None
        g["upset_size"] = round(-g["expected_margin"], 2) if g["expected_margin"] is not None else None
    upsets = [g for g in games if g.get("upset_size") is not None and g["upset_size"] > 0]
    if upsets:
        big = max(upsets, key=lambda g: g["upset_size"])
        facts["biggest_upset"] = {
            "winner": big["winner"], "loser": big["loser"],
            "score": f"{big['winner_points']} to {big['loser_points']}",
            "actual_margin": big["margin"],
            "winner_season_avg": prior_avg.get(big["winner_id"]),
            "loser_season_avg": prior_avg.get(big["loser_id"]),
            "expected_margin_for_loser": big["upset_size"]}

    # ---- players ----------------------------------------------------------
    all_starters = [dict(p, team=r["team"]) for r in scored for p in r["starters"]]
    if all_starters:
        best = max(all_starters, key=lambda p: p["points"])
        facts["highest_scoring_player"] = {
            "player": best["name"], "pos": best["pos"], "team": best["team"],
            "points": best["points"]}
        skill = [p for p in all_starters if p["pos"] not in ("K", "DEF", "D/ST")]
        if skill:
            worst = min(skill, key=lambda p: p["points"])
            facts["worst_starter_league_wide"] = {
                "player": worst["name"], "pos": worst["pos"],
                "team": worst["team"], "points": worst["points"]}
        facts["top_5_players"] = [
            {"player": p["name"], "pos": p["pos"], "team": p["team"], "points": p["points"]}
            for p in sorted(all_starters, key=lambda p: -p["points"])[:5]]

    # ---- bench regret -----------------------------------------------------
    with_mistakes = [r for r in scored if r["bench_mistakes"]]
    if with_mistakes:
        worst = max(with_mistakes, key=lambda r: r["bench_mistakes"][0]["cost"])
        m = worst["bench_mistakes"][0]
        facts["biggest_bench_mistake"] = {
            "team": worst["team"], "benched": m["benched"],
            "benched_points": m["benched_points"], "started": m["started"],
            "started_points": m["started_points"], "cost": m["cost"]}
    coulda = [r for r in scored if r["would_have_won"]]
    facts["would_have_won_with_one_legal_swap"] = [
        {"team": r["team"], "scored": r["points"],
         "after_swap": r["total_after_best_swap"],
         "opponent": r["opponent"], "opponent_points": r["opponent_points"],
         "swap": r["best_legal_swap"]}
        for r in coulda]
    # kept separate and clearly labeled so it can never be written up as a flip
    facts["optimal_lineup_only_note"] = [
        {"team": r["team"], "scored": r["points"], "optimal": r["optimal_points"],
         "opponent_points": r["opponent_points"]}
        for r in scored if r.get("would_have_won_optimal_lineup_only")]
    # Losing teams only. A winner does not need to second-guess his lineup.
    #
    # Several entries per manager is fine and the sample recap does it: two of
    # Zazach's benched players each get their own line. What the house rule
    # forbids is COMBINING them into a single could-have-won, which is why the
    # flip flag below only ever comes from `best_legal_swap`, one swap.
    legends = []
    for r in scored:
        if r["result"] != "L":
            continue
        best = r.get("best_legal_swap")
        for m in _all_legal_swaps(r)[:2]:
            legends.append({
                "team": r["team"], "manager": r["manager"], **m,
                "is_best_swap_for_team": bool(best and m["benched"] == best["benched"]),
                "flipped_the_game": bool(
                    best and m["benched"] == best["benched"] and r["would_have_won"]),
            })
    facts["bench_legends"] = sorted(legends, key=lambda x: -x["swing"])[:8]
    if scored:
        facts["least_efficient_lineup"] = min(
            (r for r in scored if r["lineup_efficiency"] is not None),
            key=lambda r: r["lineup_efficiency"], default=None) and {
            "team": min((r for r in scored if r["lineup_efficiency"] is not None),
                        key=lambda r: r["lineup_efficiency"])["team"],
            "efficiency": min((r for r in scored if r["lineup_efficiency"] is not None),
                              key=lambda r: r["lineup_efficiency"])["lineup_efficiency"]}

    # ---- standings and streaks -------------------------------------------
    standings = sorted(lw["teams"], key=lambda t: (-t["wins"], -t["points_for"]))
    for i, t in enumerate(standings, 1):
        t = dict(t)
        standings[i - 1] = t
        t["rank"] = i
    facts["standings"] = standings
    facts["streaks"] = _streaks(history, lw)
    facts["record_changes"] = _record_changes(history, lw, standings)

    # ---- history ----------------------------------------------------------
    facts["historical"] = _historical(history, lw, scored)

    # ---- transactions -----------------------------------------------------
    facts["transactions"] = [
        {**t,
         "teams": [tname(x) for x in t.get("team_ids", [])],
         "adds": [{**a, "team": tname(a["team_id"])} for a in t.get("adds", [])],
         "drops": [{**d, "team": tname(d["team_id"])} for d in t.get("drops", [])]}
        for t in lw.get("transactions", [])]
    facts["trades"] = [t for t in facts["transactions"] if t["type"] == "trade"]
    facts["waiver_pickups"] = _pickup_performance(lw, rows, team_by_id)

    # ---- the template's own sections -------------------------------------
    facts["match_summaries"] = [
        {"winner": g["winner"], "winner_points": g["winner_points"],
         "loser": g["loser"], "loser_points": g["loser_points"],
         "margin": g["margin"], "tie": g["margin"] == 0,
         "winner_top_scorer": next(
             (r["top_starter"] for r in scored if r["team_id"] == g["winner_id"]), None),
         "loser_top_scorer": next(
             (r["top_starter"] for r in scored if r["team_id"] == g["loser_id"]), None),
         "winner_def": next(
             (p for r in scored if r["team_id"] == g["winner_id"]
              for p in r["starters"] if p["pos"] in ("DEF", "D/ST")), None),
         } for g in games]
    facts["studs_who_failed"] = _studs_who_failed(scored)
    facts["call_the_doctor"] = _call_the_doctor(scored, facts.get("standings"))
    facts["toilet_bowl"] = (
        {"team": min(scored, key=lambda r: r["points"])["team"],
         "manager": min(scored, key=lambda r: r["points"])["manager"],
         "points": min(scored, key=lambda r: r["points"])["points"]}
        if scored else None)
    facts["waiver_wire_genius"] = _waiver_genius(facts["waiver_pickups"], scored)
    facts["empty_starting_slots"] = [
        {"team": r["team"], "manager": r["manager"], "slot": p["slot"],
         "result": r["result"], "margin": r["margin"]}
        for r in scored for p in r["starters"] if p.get("empty")]

    return {
        "league": lw["league_name"],
        "source": lw["source"],
        "season": lw["season"],
        "week": lw["week"],
        "games": games,
        "teams": rows,
        "facts": facts,
    }


def _studs_who_failed(scored):
    """
    In-week baselines only, no outside projections. Median points among every
    started player at that position across the league this week; anyone under
    half of it is eligible. Using the league's own week means a position-wide
    bad Sunday does not turn ten players into busts.
    """
    import statistics
    by_pos = {}
    for r in scored:
        for p in r["starters"]:
            if p.get("empty"):
                continue          # an unfilled slot would drag every median down
            by_pos.setdefault(p["pos"], []).append(p["points"])
    medians = {pos: round(statistics.median(v), 2) for pos, v in by_pos.items() if v}

    out, zeros = [], []
    for r in scored:
        for p in r["starters"]:
            if p.get("empty"):
                continue
            med = medians.get(p["pos"])
            if not med or med <= 0:
                continue
            if p["points"] >= med * 0.5:
                continue
            rec = {
                "player": p["name"], "pos": p["pos"], "nfl_team": p["nfl_team"],
                "points": p["points"], "team": r["team"], "manager": r["manager"],
                "position_median": med,
                "pct_of_median": round(p["points"] / med * 100, 1),
                "injury": p.get("injury"),
            }
            # A flat zero is almost always a player who never took the field:
            # bye week, inactive, or a late scratch. That is a lineup-management
            # story, not a star who underperformed, and writing it as "failed"
            # is the kind of claim that gets corrected in the group chat.
            (zeros if p["points"] <= 0 else out).append(rec)
    out.sort(key=lambda x: x["pct_of_median"])
    zeros.sort(key=lambda x: x["team"])
    return {"position_medians": medians, "busts": out[:8],
            "started_but_never_played": zeros}


def _call_the_doctor(scored, standings=None, n=3):
    """
    Teams in trouble. The sample recap puts a 0-4 team here on a 106-point
    week, so this is not purely the week's low scores: it is the worst weekly
    scores plus the worst records, deduplicated. Each entry says which one put
    it there so the write-up can cite the right reason.
    """
    total = len(scored)
    ranked = sorted(scored, key=lambda r: r["points"])
    rank_by_team = {r["team"]: total - i for i, r in enumerate(ranked)}

    picked, seen = [], set()

    def add(r, why):
        if r["team"] in seen:
            for p in picked:
                if p["team"] == r["team"] and why not in p["reasons"]:
                    p["reasons"].append(why)
            return
        seen.add(r["team"])
        st = next((t for t in (standings or []) if t["name"] == r["team"]), {})
        picked.append({
            "team": r["team"], "manager": r["manager"], "points": r["points"],
            "rank": rank_by_team[r["team"]], "of": total, "result": r["result"],
            "opponent": r["opponent"], "opponent_points": r["opponent_points"],
            "record": (f"{st.get('wins', 0)}-{st.get('losses', 0)}" if st else None),
            "reasons": [why],
        })

    for r in ranked[:n]:
        add(r, "one of the week's lowest scores")
    if standings:
        worst = sorted(standings, key=lambda t: (t["wins"], t["points_for"]))[:2]
        for t in worst:
            r = next((x for x in scored if x["team"] == t["name"]), None)
            if r:
                add(r, f"record ({t['wins']}-{t['losses']})")
    return picked


def _waiver_genius(pickups, scored):
    """
    Genius, by the stated bar: started, double digits, and either top-3 on the
    roster that week or big enough to have swung a close game.
    """
    by_team = {r["team"]: r for r in scored}
    out = []
    for p in (pickups or {}).get("pickups", []):
        if p["status"] != "started" or (p["points"] or 0) < 10:
            continue
        r = by_team.get(p["team"])
        if not r:
            continue
        ranked = sorted((x["points"] for x in r["starters"]), reverse=True)
        top3 = p["points"] >= ranked[2] if len(ranked) >= 3 else True
        swung = bool(r["result"] == "W" and r["margin"] is not None
                     and p["points"] > r["margin"])
        if top3 or swung:
            out.append({**p,
                        "top_3_on_roster": top3,
                        "swung_the_game": swung,
                        "team_result": r["result"],
                        "team_margin": r["margin"]})
    out.sort(key=lambda x: -(x["points"] or 0))
    return out


def _pickup_performance(lw, rows, team_by_id):
    """
    Every player added this week, what he then scored, and whether the manager
    who added him actually had the nerve to start him. Ranked by points.
    """
    where = {}
    for r in rows:
        for p in r["starters"]:
            where[(r["team_id"], p["player_id"])] = ("started", p.get("slot"), p["points"])
        for p in r["bench"]:
            where[(r["team_id"], p["player_id"])] = ("benched", None, p["points"])

    out, off_roster = [], []
    for t in lw.get("transactions", []):
        if t["type"] == "trade":
            continue
        for a in t.get("adds", []):
            tid = a["team_id"]
            team = team_by_id.get(tid) or {}
            rec = {
                "player": a["player"],
                "pos": a.get("pos"),
                "manager": team.get("manager"),
                "team": team.get("name"),
                "date": t.get("date"),
                "faab_bid": t.get("faab_bid"),
            }
            hit = where.get((tid, a.get("player_id")))
            if hit is None:
                # added after this week's games, or added and cut before kickoff.
                # Either way he never counted for this week, so he stays out of
                # the ranking rather than showing up with a fake zero.
                off_roster.append({**rec, "status": "not on the roster at kickoff",
                                   "slot": None, "points": None})
                continue
            status, slot, pts = hit
            out.append({**rec, "status": status, "slot": slot, "points": pts})
    out.sort(key=lambda x: -(x["points"] or 0))

    started = [p for p in out if p["status"] == "started" and p["points"] is not None]
    result = {"pickups": out, "added_but_did_not_count": off_roster}
    if started:
        result["best_add"] = max(started, key=lambda p: p["points"])
        result["worst_add"] = min(started, key=lambda p: p["points"])
    benched_gems = [p for p in out
                    if p["status"] == "benched" and (p["points"] or 0) >= 10]
    if benched_gems:
        result["added_and_benched"] = benched_gems
    return result


# --------------------------------------------------------------------------
# history helpers
# --------------------------------------------------------------------------

def _team_week_scores(history):
    """[(season, week, team_id, team_name, points)] across every prior week."""
    out = []
    for h in history:
        names = {t["team_id"]: t["name"] for t in h["teams"]}
        for m in h["matchups"]:
            for s in m["teams"]:
                out.append((h["season"], h["week"], s["team_id"],
                            names.get(s["team_id"], s["team_id"]), s["points"]))
    return out


def _season_averages(history, lw):
    """Scoring average per team this season before this week."""
    tot, n = {}, {}
    for season, week, tid, _, pts in _team_week_scores(history):
        if season != lw["season"] or week >= lw["week"]:
            continue
        tot[tid] = tot.get(tid, 0) + pts
        n[tid] = n.get(tid, 0) + 1
    return {tid: round(tot[tid] / n[tid], 2) for tid in tot if n[tid]}


def _results_by_week(h):
    res = {}
    for m in h["matchups"]:
        if len(m["teams"]) != 2:
            continue
        a, b = m["teams"]
        res[a["team_id"]] = "W" if a["points"] > b["points"] else "L" if a["points"] < b["points"] else "T"
        res[b["team_id"]] = "W" if b["points"] > a["points"] else "L" if b["points"] < a["points"] else "T"
    return res


def _streaks(history, lw):
    """Current W/L streak per team, this season, including this week."""
    season = [h for h in history if h["season"] == lw["season"] and h["week"] < lw["week"]]
    season.sort(key=lambda h: h["week"])
    seq = {}
    for h in season + [lw]:
        for tid, r in _results_by_week(h).items():
            seq.setdefault(tid, []).append(r)
    names = {t["team_id"]: t["name"] for t in lw["teams"]}
    out = []
    for tid, rs in seq.items():
        last = rs[-1]
        n = 0
        for r in reversed(rs):
            if r != last:
                break
            n += 1
        out.append({"team": names.get(tid, tid), "streak": f"{last}{n}",
                    "kind": last, "length": n, "results": "".join(rs)})
    out.sort(key=lambda x: (x["kind"] != "W", -x["length"]))
    return out


def _record_changes(history, lw, standings):
    """Rank movement versus last week."""
    prev = [h for h in history if h["season"] == lw["season"] and h["week"] == lw["week"] - 1]
    if not prev:
        return []
    old = sorted(prev[0]["teams"], key=lambda t: (-t["wins"], -t["points_for"]))
    old_rank = {t["team_id"]: i + 1 for i, t in enumerate(old)}
    out = []
    for t in standings:
        o = old_rank.get(t["team_id"])
        if o is None:
            continue
        out.append({"team": t["name"], "rank": t["rank"], "previous_rank": o,
                    "change": o - t["rank"]})
    return [c for c in out if c["change"] != 0]


def _historical(history, lw, scored):
    """Where this week's scores sit against everything that came before."""
    prior = [x for x in _team_week_scores(history)
             if not (x[0] == lw["season"] and x[1] >= lw["week"])]
    out = {"weeks_of_history": len({(s, w) for s, w, _, _, _ in prior})}
    if not prior or not scored:
        return out

    hi = max(scored, key=lambda r: r["points"])
    beaten = [x for x in prior if x[4] >= hi["points"]]
    out["top_score_context"] = {
        "team": hi["team"], "points": hi["points"],
        "all_time_rank": len(beaten) + 1,
        "is_league_record": not beaten,
    }
    if beaten:
        last = max(beaten, key=lambda x: (x[0], x[1]))
        out["top_score_context"]["last_time_higher"] = {
            "season": last[0], "week": last[1], "team": last[3], "points": last[4]}

    lo = min(scored, key=lambda r: r["points"])
    lower = [x for x in prior if x[4] <= lo["points"]]
    out["low_score_context"] = {
        "team": lo["team"], "points": lo["points"],
        "is_league_low": not lower,
        "worse_performances_on_record": len(lower),
    }

    pts = [x[4] for x in prior]
    out["league_history_average"] = round(sum(pts) / len(pts), 2)

    # personal bests
    pbs = []
    for r in scored:
        mine = [x[4] for x in prior if x[2] == r["team_id"]]
        if mine and r["points"] > max(mine):
            pbs.append({"team": r["team"], "points": r["points"],
                        "previous_best": max(mine)})
    if pbs:
        out["season_or_career_highs"] = pbs
    return out
