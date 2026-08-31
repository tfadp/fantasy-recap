#!/usr/bin/env python3
"""
The Tuesday morning run.

    1. pull both leagues
    2. confirm the week's games are final
    3. analyze everything
    4. write one recap per league using that league's prompt and history
    5. hand off the finished text

Usage:
    python3 run.py                      # current week, every league in leagues.json
    python3 run.py --week 5
    python3 run.py --only sleeper
    python3 run.py --no-write           # facts only, skip the model
    python3 run.py --force              # write even if a game is not final
"""

import argparse
import json
import os
import re
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import analyze  # noqa: E402
import env  # noqa: E402
import nfl_status  # noqa: E402
import power_rankings  # noqa: E402
import qc  # noqa: E402
import schema  # noqa: E402
import standings  # noqa: E402
from adapters import sleeper  # noqa: E402

OUT = os.path.join(HERE, "out")
HIST = os.path.join(HERE, "history")


def load_config():
    with open(os.path.join(HERE, "leagues.json")) as f:
        return json.load(f)


def brief(a):
    """Readable version of the facts. Goes into the prompt beside the JSON."""
    f, L = a["facts"], []
    L.append(f"{a['league']} — {a['season']} Week {a['week']}")
    L.append("")
    L.append("SCOREBOARD")
    for g in a["games"]:
        L.append(f"  {g['winner']} {g['winner_points']} def. {g['loser']} {g['loser_points']}"
                 f"  (by {g['margin']})")
    L.append("")
    L.append("THE WEEK IN ONE GLANCE")
    if "highest_score" in f:
        L.append(f"  high: {f['highest_score']['team']} {f['highest_score']['points']}")
        L.append(f"  low:  {f['lowest_score']['team']} {f['lowest_score']['points']}")
        L.append(f"  league average: {f['average_score']}")
    if "closest_game" in f:
        c = f["closest_game"]
        L.append(f"  closest: {c['winner']} over {c['loser']} by {c['margin']}")
        b = f["biggest_blowout"]
        L.append(f"  blowout: {b['winner']} over {b['loser']} by {b['margin']}")
    if "biggest_upset" in f:
        u = f["biggest_upset"]
        L.append(f"  upset: {u['winner']} ({u['winner_season_avg']} avg) beat "
                 f"{u['loser']} ({u['loser_season_avg']} avg), {u['score']}")
    if "unluckiest_loss" in f:
        u = f["unluckiest_loss"]
        L.append(f"  unlucky: {u['team']} scored {u['points']} and still lost to "
                 f"{u['opponent']} ({u['opponent_points']}); that score would have beaten "
                 f"{u['would_have_beaten']} of the other {u['of_other_teams']} teams")
    if "luckiest_win" in f:
        w = f["luckiest_win"]
        L.append(f"  lucky:   {w['team']} won with just {w['points']} "
                 f"against {w['opponent']}'s {w['opponent_points']}")
    L.append("")
    L.append("PLAYERS")
    for p in f.get("top_5_players", []):
        L.append(f"  {p['points']:>6}  {p['player']} ({p['pos']}, {p['team']})")
    if "worst_starter_league_wide" in f:
        w = f["worst_starter_league_wide"]
        L.append(f"  worst start: {w['player']} ({w['pos']}) {w['points']} for {w['team']}")
    L.append("")
    L.append("BENCH LEGENDS (losing teams, single legal swap only)")
    if not f.get("bench_legends"):
        L.append("  none")
    for b in f.get("bench_legends", []):
        flip = "  WOULD HAVE FLIPPED THE GAME" if b["flipped_the_game"] else ""
        L.append(f"  {b['benched']} ({b['benched_points']}, {b['manager']}) "
                 f"- would have replaced {b['started']} ({b['started_points']}) "
                 f"at {b['started_slot']}, +{b['swing']}{flip}")
    for c in f.get("optimal_lineup_only_note", []):
        L.append(f"  NOT a flip: {c['team']} only clears {c['opponent_points']} with a "
                 f"full optimal lineup ({c['optimal']}), which is several swaps. "
                 f"Do not write this as could-have-won.")

    if f.get("empty_starting_slots"):
        L.append("")
        L.append("STARTED NOBODY")
        for x in f["empty_starting_slots"]:
            L.append(f"  {x['team']} left {x['slot']} empty and took a 0 there "
                     f"({x['result']} by {x['margin']})")

    sf = f.get("studs_who_failed") or {}
    if sf.get("busts"):
        L.append("")
        L.append("STUDS WHO FAILED (played, under 50% of this week's positional median)")
        for b in sf["busts"]:
            inj = f", {b['injury']}" if b.get("injury") else ""
            L.append(f"  {b['player']} ({b['pos']}, {b['team']}) {b['points']} vs "
                     f"{b['pos']} median {b['position_median']} "
                     f"= {b['pct_of_median']}%{inj}")
    if sf.get("started_but_never_played"):
        L.append("")
        L.append("STARTED A ZERO (bye, inactive or scratched; not a bust, a lineup problem)")
        for z in sf["started_but_never_played"]:
            inj = f" [{z['injury']}]" if z.get("injury") else ""
            L.append(f"  {z['team']} started {z['player']} ({z['pos']}){inj} for 0.0")

    if f.get("call_the_doctor"):
        L.append("")
        L.append("CALL THE DOCTOR (bottom scorers)")
        for d in f["call_the_doctor"]:
            rec = f"{d['record']}, " if d.get("record") else ""
            L.append(f"  {d['team']} ({rec}{d['points']}) - rank {d['rank']}/{d['of']} "
                     f"this week; here for: {', '.join(d['reasons'])}")

    if f.get("toilet_bowl"):
        t = f["toilet_bowl"]
        L.append("")
        L.append(f"TOILET BOWL: {t['team']} {t['points']}")

    if f.get("waiver_wire_genius"):
        L.append("")
        L.append("WAIVER WIRE GENIUS (started, 10+, top-3 or swung the game)")
        for g in f["waiver_wire_genius"]:
            why = []
            if g["top_3_on_roster"]:
                why.append("top-3 on roster")
            if g["swung_the_game"]:
                why.append(f"bigger than the {g['team_margin']} margin")
            L.append(f"  {g['manager']} -> {g['player']} {g['points']} "
                     f"({', '.join(why)})")
    L.append("")
    L.append("STANDINGS")
    changes = {c["team"]: c["change"] for c in f.get("record_changes", [])}
    for t in f["standings"]:
        mv = changes.get(t["name"])
        arrow = "" if not mv else f"  ({'up' if mv > 0 else 'down'} {abs(mv)})"
        rec = f"{t['wins']}-{t['losses']}" + (f"-{t['ties']}" if t.get("ties") else "")
        L.append(f"  {t['rank']:>2}. {t['name']}  {rec}"
                 f"  PF {t['points_for']}  PA {t['points_against']}{arrow}")
    L.append("")
    L.append("STREAKS")
    for s in f.get("streaks", []):
        if s["length"] >= 2:
            L.append(f"  {s['team']}: {s['length']} straight {'wins' if s['kind']=='W' else 'losses'}"
                     f"  ({s['results']})")
    h = f.get("historical", {})
    if h.get("weeks_of_history"):
        L.append("")
        L.append(f"HISTORY ({h['weeks_of_history']} prior weeks on record)")
        t = h.get("top_score_context") or {}
        if t.get("is_league_record"):
            L.append(f"  {t['team']}'s {t['points']} is the highest score in league history")
        elif t.get("last_time_higher"):
            p = t["last_time_higher"]
            L.append(f"  {t['team']}'s {t['points']} is the best since {p['team']} put up "
                     f"{p['points']} in {p['season']} week {p['week']}")
        lo = h.get("low_score_context") or {}
        if lo.get("is_league_low"):
            L.append(f"  {lo['team']}'s {lo['points']} is the lowest score in league history")
        for pb in h.get("season_or_career_highs", []):
            L.append(f"  {pb['team']} set a new high: {pb['points']} (old best {pb['previous_best']})")
    wp = f.get("waiver_pickups") or {}
    if wp.get("pickups"):
        L.append("")
        L.append("WAIVER PICKUPS, BY POINTS SCORED THIS WEEK")
        for i, p in enumerate(wp["pickups"], 1):
            pts = "n/a" if p["points"] is None else f"{p['points']}"
            where = (f"started at {p['slot']}" if p["status"] == "started"
                     else p["status"])
            bid = f", ${p['faab_bid']}" if p.get("faab_bid") else ""
            L.append(f"  {i}. {p['player']} ({p['manager']}, {p['date']}{bid}) — "
                     f"{pts} points ({where})")
        if wp.get("best_add"):
            b = wp["best_add"]
            L.append(f"  best add: {b['player']} — {b['points']} for {b['manager']}")
            w = wp["worst_add"]
            L.append(f"  worst add: {w['player']} — started at {w['slot']}, "
                     f"{w['points']} for {w['manager']}")

    pr = a.get("power_rankings") or []
    if pr:
        L.append("")
        L.append("POWER RANKINGS (through this week)")
        L.append(power_rankings.render(pr))

    L.append("")
    L.append("MOVES")
    if not f.get("transactions"):
        L.append("  none")
    for t in f.get("transactions", []):
        bid = f" ${t['faab_bid']}" if t.get("faab_bid") else ""
        adds = ", ".join(f"{a['player']} to {a['team']}" for a in t.get("adds", []))
        drops = ", ".join(f"{d['player']} off {d['team']}" for d in t.get("drops", []))
        # a drop with no add is a cut, and used to render as "free_agent: ;"
        parts = [x for x in (adds, f"dropped {drops}" if drops else "") if x]
        L.append(f"  {t['type']}{bid}: {'; '.join(parts) or '(no players)'}")
    return "\n".join(L)


SYSTEM_TAIL = """

Every number below is already computed and verified. Use them exactly as given.
Do not add up scores, compare values, or infer any statistic that is not stated.
If a fact you want is not present, leave it out.

The format and voice rules above are exact. Follow the section order, the bullet
shapes, the word counts and the punctuation as written. This is pasted into an
iMessage thread, so it must be plain text: no markdown headings, no tables, no
emoji."""


def _text_of(msg):
    """
    The last text block, not content[0].

    With thinking on, content[0] is a thinking block, and the old
    `msg.content[0].text` would have returned reasoning or raised. Worth being
    explicit about because the failure only shows up once thinking is enabled.
    """
    parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    if not parts:
        raise RuntimeError(f"model returned no text (stop_reason={msg.stop_reason})")
    return parts[-1].strip()


# W-L records the style guide wants as en dashes. The model gets them right in
# the match summaries and drifts to hyphens in Call the Doctor and the Power
# Rankings notes, so the mechanical part is done mechanically. The lookbehind
# protects team names that legitimately contain a hyphen after a colon, which
# is the whole reason "Proverbs 3:5-6" survives this untouched.
_RECORD = re.compile(r"(?<![\d:])(\d{1,2})-(\d{1,2})(?![\d-])")


def polish(text):
    return _RECORD.sub("\\1\u2013\\2", text)


def write_recap(a, cfg, note=None):
    """Call Claude with the league's prompt. Skipped if no API key is set."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    import anthropic

    with open(os.path.join(HERE, cfg["prompt_file"])) as fh:
        base_prompt = fh.read()

    def read_optional(field):
        path = os.path.join(HERE, cfg.get(field, ""))
        if cfg.get(field) and os.path.exists(path):
            with open(path) as fh:
                return fh.read()
        return ""

    lore = read_optional("lore_file")
    chat = read_optional("chat_file")

    # Filter to write-ups *first*, then take the last three. Sorting the whole
    # directory and slicing before filtering only ever yielded one recap, since
    # each week also writes a -brief.txt and a -facts.json that sort alongside.
    past = []
    pdir = os.path.join(OUT, cfg["name"])
    if os.path.isdir(pdir):
        for fn in sorted(fn for fn in os.listdir(pdir) if fn.endswith(".md"))[-3:]:
            with open(os.path.join(pdir, fn)) as fh:
                past.append(f"--- {fn} ---\n{fh.read()}")

    client = anthropic.Anthropic(api_key=key)
    msg = client.beta.messages.create(
        model=os.environ.get("RECAP_MODEL", "claude-opus-5"),
        max_tokens=16000,
        thinking={"type": "adaptive"},
        # If the roast trips a safety classifier at 9am on a Tuesday, the run
        # should still produce a recap rather than an empty inbox.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=base_prompt + SYSTEM_TAIL,
        messages=[{"role": "user", "content": "\n\n".join(filter(None, [
            ("HOW THIS LEAGUE ACTUALLY TALKS. Real messages from the group chat. "
             "Match this energy and reuse these bits where they land; do not quote "
             "anyone verbatim as if they said it this week:\n" + chat) if chat else "",
            f"LEAGUE LORE, RIVALRIES AND RUNNING JOKES:\n{lore}" if lore else "",
            "PREVIOUS WRITE-UPS, for continuity of voice and running bits:\n"
            + "\n\n".join(past) if past else "",
            f"THIS WEEK, PLAIN:\n{brief(a)}",
            f"POWER RANKINGS AUDIT:\n{a.get('power_rankings_audit', '')}",
            f"QC AUDIT, context only. Do NOT reproduce any of this in the recap:\n"
            f"{a.get('qc_audit', '')}",
            f"THIS WEEK, COMPLETE DATA:\n{json.dumps(a, indent=2)}",
            (f"NOTE FROM DAN ON THIS REWRITE, follow it over any default:\n{note}"
             if note else ""),
            "Write this week's recap.",
        ]))}],
    )
    if msg.stop_reason == "refusal":
        raise RuntimeError(
            "The model declined to write this one and the fallback did too. "
            "Usually a roast that read wrong out of context. Re-run with "
            "--note to steer it.")
    return polish(_text_of(msg))


class NothingYet(Exception):
    """No week has been played yet. Not a failure, just early."""


def _latest_played_week(cfg):
    """
    The week to write up is the most recent one that actually has scores.

    Sleeper advances state/nfl into the new week during Tuesday, which is
    exactly when this runs. Trusting `display_week` would ask for a week whose
    games have not been played and fail every Tuesday at 9am - including the
    first real one of the season. So start where the API points and step back
    until a week has points on the board.
    """
    state = sleeper.current_state()
    start = int(state.get("display_week") or state["week"])
    for wk in range(start, max(start - 3, 0), -1):
        try:
            lw = sleeper.fetch(cfg["league_id"], wk)
        except Exception:
            continue
        if any(side["points"] > 0 for m in lw["matchups"] for side in m["teams"]):
            return wk, lw
    raise NothingYet(
        f"{cfg.get('display_name', cfg['name'])}: no week has been played yet "
        f"(the API is on week {start}, season starts "
        f"{state.get('season_start_date')}). Nothing to write.")


def do_league(cfg, week, force, do_write, note=None):
    if cfg["platform"] == "sleeper":
        if week:
            wk = int(week)
            lw = sleeper.fetch(cfg["league_id"], wk)
        else:
            wk, lw = _latest_played_week(cfg)
        history = sleeper.season_history(cfg["league_id"], wk,
                                         seasons_back=cfg.get("seasons_back", 2))
    elif cfg["platform"] == "yahoo":
        from adapters import yahoo
        wk = week or _yahoo_current_week(cfg)
        lw = yahoo.fetch(cfg["league_id"], wk)
        history = _load_history(cfg["name"])
    elif cfg["platform"] == "payload":
        from adapters import payload
        lw = payload.fetch(cfg["league_id"], week)
        wk = int(lw["week"])
        history = _load_history(cfg["name"])
    else:
        raise ValueError(f"unknown platform {cfg['platform']}")

    schema.validate(lw)
    # the season to check is the one the data is from, not whatever season the
    # calendar happens to be in. Getting this backwards makes the gate check
    # games that have not been scheduled yet and refuse a finished week.
    nfl_status.assert_final(lw["season"], wk, allow_incomplete=force)

    # Records, PF and PA as they stood after *this* week, computed from the
    # season's own results. Must run before analyze and power_rankings, both of
    # which read lw["teams"]. See standings.py for why the API's own numbers
    # are not trustworthy outside the live Tuesday run.
    stand = standings.apply(lw, history)

    a = analyze.analyze(lw, history)
    a["standings_source"] = stand

    # power rankings, plus last week's so the arrows have something to move from
    pr = power_rankings.compute(
        lw, history,
        pf_mode=cfg.get("pr_pf_mode", "value"),
        consistency_mode=cfg.get("pr_consistency_mode", "spec"),
        display_scale=cfg.get("pr_display_scale", "score"))
    power_rankings.add_movement(pr, _load_previous_power(cfg["name"], lw))
    a["power_rankings"] = pr
    a["power_rankings_audit"] = power_rankings.audit_block(
        pr, pf_mode=cfg.get("pr_pf_mode", "value"),
        consistency_mode=cfg.get("pr_consistency_mode", "spec"))

    # QC runs before the model is called. A failure here writes nothing.
    a["qc_audit"] = qc.run(a, lw, pr, standings_source=stand)

    _save_history(cfg["name"], lw)
    _save_power(cfg["name"], lw, pr)

    d = os.path.join(OUT, cfg["name"])
    os.makedirs(d, exist_ok=True)
    stem = f"{lw['season']}-wk{wk:02d}"
    with open(os.path.join(d, stem + "-facts.json"), "w") as f:
        json.dump(a, f, indent=2)
    with open(os.path.join(d, stem + "-brief.txt"), "w") as f:
        f.write(brief(a))

    text = write_recap(a, cfg, note=note) if do_write else None
    if text:
        with open(os.path.join(d, stem + ".md"), "w") as f:
            f.write(text)
    return a, text


def _yahoo_current_week(cfg):
    from adapters import yahoo
    d = yahoo._flatten(yahoo._get(f"/league/{cfg['league_id']}"))
    return int(yahoo._find_first(d, "current_week"))


def _load_previous_power(name, lw):
    """Last week's ranking, so movement is computed rather than eyeballed."""
    path = os.path.join(HIST, name, f"power-{lw['season']}-wk{lw['week'] - 1:02d}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _save_power(name, lw, pr):
    d = os.path.join(HIST, name)
    os.makedirs(d, exist_ok=True)
    slim = [{"team_id": r["team_id"], "team": r["team"], "rank": r["rank"],
             "power_score": r["power_score"]} for r in pr]
    with open(os.path.join(d, f"power-{lw['season']}-wk{lw['week']:02d}.json"), "w") as f:
        json.dump(slim, f, indent=2)


def _save_history(name, lw):
    d = os.path.join(HIST, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{lw['season']}-wk{lw['week']:02d}.json"), "w") as f:
        json.dump(lw, f)


def _load_history(name):
    d = os.path.join(HIST, name)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            with open(os.path.join(d, fn)) as f:
                out.append(json.load(f))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int)
    ap.add_argument("--only", help="league name from leagues.json")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore unfinished games")
    ap.add_argument("--note", help="steer a rewrite, e.g. --note 'lead with the Kittle zero'")
    a = ap.parse_args()

    env.load()

    active = [c for c in load_config()["leagues"] if c.get("enabled", True)]
    if a.only:
        active = [c for c in active if c["name"] == a.only]
        if not active:
            sys.exit(f"no enabled league named {a.only!r} in leagues.json")
    failures, early = [], []
    for cfg in active:
        try:
            _, text = do_league(cfg, a.week, a.force, not a.no_write, note=a.note)
            print(f"\n=== {cfg['name']} ===")
            print(text or "(facts written; no model call)")
        except NothingYet as e:
            # Pre-season Tuesdays are not failures. Saying so quietly beats
            # sending a red X and a "recap failed" email every week until
            # kickoff, which trains you to ignore the one that matters.
            early.append(cfg["name"])
            print(f"\n=== {cfg['name']}: not yet ===\n{e}")
        except Exception as e:
            failures.append((cfg["name"], str(e)))
            print(f"\n=== {cfg['name']} FAILED ===\n{e}", file=sys.stderr)

    # one league failing must not stop the other from being delivered
    if failures and len(failures) == len(active):
        sys.exit(1)
    if early and not failures:
        sys.exit(0)


if __name__ == "__main__":
    main()
