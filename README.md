# fantasy-recap

Pulls both leagues, computes every fact, hands a clean dataset to the model,
posts the write-up. No screenshots.

```
Sleeper API ─────────┐
                     ├─→ league_week ─→ analyze.py ─→ facts ─┐
Yahoo Chrome button ─┘                                       │
                                                             ├─→ recap ─┬─→ email
              your prompt + league lore + group chat ────────┘          └─→ web page
```

The design rule the whole thing is built around: **code computes, the model
writes.** Every number the recap can cite is calculated, checked and labeled
before the model sees it. The model is told, in its system prompt, that it may
not add, compare, or infer any figure. It cannot decide 143.7 beats 147.2
because it is never asked to.

## Status

| Piece | State |
|---|---|
| Sleeper adapter | Working, tested against MOP league 2025 week 12 |
| Analysis layer | Working, 25 weeks of real history pulled and validated |
| Yahoo Chrome button | Written, **untested** until run on a live league page |
| Yahoo API adapter | Parked. Written, unused, no approval pursued |
| Web page + archive | Working, see `docs/` |
| Game-final gate | Working, ESPN public scoreboard |
| Email + link delivery | Written, needs an email key |
| Schedule | GitHub Actions, Tuesday 9am Eastern |
| Recap sections | All seven, computed. Validated on Weeks 12, 13 and 14 |
| Power Rankings | Working, cross-checked against the Week 4 hand ranking |

Validation run: the pipeline reproduced the waiver-wire section of Dan's
hand-written Week 12 recap exactly, including pickup dates and started/benched
status, and caught two pickups the manual version missed.

## Yahoo

The Chrome button, not the API. Open your league page, click once, done. No
application, no approval queue, works today.

The honest read on Yahoo's terms: this is not a crawler. It runs only on click,
only on the tab you already have open, only on your own league, and it sends
nothing on its own. That is meaningfully different from a scheduled scraper,
but Yahoo's general terms are broad enough that it is not clearly *permitted*
either. Defensible, not sanctioned.

The API adapter stays in the repo, disabled, in case that ever changes.

## Setup

```bash
pip install -r requirements.txt
python3 run.py --only mop --week 12 --no-write     # Sleeper works immediately
```

Sleeper needs nothing but the league id, already in `leagues.json`.

For Yahoo: open `chrome://extensions`, turn on Developer mode, Load unpacked,
pick the `extension/` folder. In its Settings put your repository
(`you/fantasy-recap`) and a fine-grained token scoped to that one repo with
Contents read and write. Then open your Yahoo league matchup page and click
the button.

Then set `ANTHROPIC_API_KEY` to have it write the recap, and either
`RESEND_API_KEY` + `RECAP_EMAIL_TO` for email or `GROUPME_BOT_ID` to post.

## Delivery

The league is on iMessage, which cannot be posted to programmatically, so the
run produces two things you can hand over instead:

- an **email** with the finished write-up, ready to copy into the thread
- a **web page** on GitHub Pages, so you can paste one link instead

Turn on Pages in repository settings, source `docs/`. Every week gets a
permanent URL and `index.html` follows the newest one, so the archive builds
itself and the link you send is always short.

## The QC process, as code

The COMMON_ERRORS post-mortem catalogs six error categories from Weeks 4-8.
Five of them cannot happen any more, because they were all the same error:
a model reading a screenshot.

| Original error | Status now |
|---|---|
| Winner/loser reversal | Unreachable. There is no W/L column to misparse; the winner is whoever has more points, computed. |
| Bench player ownership | Unreachable. Bench players arrive attached to a roster id. |
| Win count accuracy | Unreachable. Records come from standings, never counted by hand. |
| "Both now 6-2" | Unreachable. Each record is a separate field. |
| Season stats and superlatives | Checked. `qc.py` asserts the stated high and low are the actual week max and min. |
| Waiver attribution | Unreachable for the window and the manager, both of which come from the API. |

What is left runs in `qc.py` as assertions, before the model is called. A
failure writes nothing rather than producing a confident wrong recap:

- every team appears exactly once, none missing, none duplicated
- game count matches the league size
- every winner scored more than every loser, every margin recomputed
- team totals reconcile against the sum of their starters
- the stated high, low and Toilet Bowl are the actual max and min
- every bench swap is a single legal swap, and a flip is only a flip if the
  new total actually clears the opponent
- Power Rankings are 1..n and the movement arrows net to zero

This is the point the post-mortem was reaching for: the system catches errors
during execution instead of asking a person to catch them afterwards.

## Power Rankings

Implemented as specified, weights 0.40 season PF, 0.25 last two weeks, 0.25
win percentage, 0.10 consistency, every sub-score normalized to 0-100 first.
`power_rankings.py` returns the inputs and sub-scores alongside every result,
so the audit block prints them and anyone in the league can re-derive a number
by hand.

**Validated against the Week 4 sample.** Running the formula on Week 4 from
the API and comparing to the hand-made Power Rankings in that recap: ten of
twelve teams land within two spots, average displacement 1.7. One team
disagrees hard. "Chase da $ chase da" was ranked 1st by hand and 8th by the
formula, because that team was 9th of 12 in season Points For at the time
(451.85, including a 67.17 in Week 2) and had just posted a single 154.40.
The hand ranking was recency; the formula's 40% season PF weight is exactly
the correction it was written to apply. Working as designed, and worth knowing
before the first week the arrows surprise someone.

Two more notes from running it on real data:

**The two supplied formulas disagree.** The earlier one weighted
0.50/0.25/0.15/0.10 and built the PF component from rank. The later one uses
0.40/0.25/0.25/0.10 and values. The later one is the default; the earlier is
available via `pr_pf_mode: "rank"` and `WEIGHTS_V1`. Pick one and leave it,
because switching mid-season makes the movement arrows meaningless.

**The sample prints a different scale.** The Week 4 recap shows Power Ranking
scores from 135.8 down to 95.4, which is not the 0-100 the stated formula
produces. Ordering is unaffected either way. `pr_display_scale: "points"` maps
the score onto the league's own weekly scoring range so it reads like the old
recaps; the default prints the 0-100 the formula actually computes.

**The consistency component floors out.** Written as
`100 - (stdev / league avg stdev x 100)`, a team of exactly average volatility
scores 0, not 50. On MOP Week 14 that put four of twelve teams at 0.0 and the
component averaged 25.1 across a 0-62 range. At 10% weight it did not change
the ordering, so this is a note rather than a problem. `pr_consistency_mode:
"normalized"` spreads it over the full 0-100 instead if you want it to bite.

## Making it funny

The stats layer makes the recap accurate. It does nothing at all to make it
good. Three files carry the voice, and they matter more than any statistic in
this repo:

- `prompts/<league>.md` is your write-up prompt, verbatim.
- `prompts/<league>-lore.md` is nicknames, rivalries, who mocks who.
- `prompts/<league>-chat.md` is **real messages pasted from the group chat.**

That last one is the highest-leverage file here. Without it the model writes a
competent recap in nobody's voice, which is the same failure as a stat sheet
with adjectives. Paste actual chat in, and the running bits come back on their
own. Past write-ups in `out/` are fed forward automatically for the same
reason, so continuity builds week over week.

The page reflects this too. The write-up is the whole page. Every table is
folded into one collapsed block at the bottom called "the receipts", for
whoever wants to argue.

## The data contract

Both adapters emit the same `league_week` shape, documented in full at the top
of `schema.py`. Anything downstream reads only that, so adding ESPN or NFL.com
later is one file and no other changes.

```
league_week = {
  source, league_id, league_name, season, week,
  roster_slots: ["QB","RB","RB","WR","WR","TE","FLEX","FLEX","DEF"],
  teams:    [{team_id, name, manager, wins, losses, ties, points_for, points_against}],
  matchups: [{matchup_id, teams: [{team_id, points, starters[], bench[]}]}],
  transactions: [{type, date, team_ids, adds[], drops[], faab_bid}],
}
player = {player_id, name, pos, nfl_team, slot, points, injury}
```

`schema.validate()` runs on every pull and raises before the model is ever
called, so a malformed week fails loudly instead of producing a confident
recap built on nothing.

## What gets calculated

Per matchup: final score, margin, winner.

Per team: points, opponent, result, top starter, worst starter (skill
positions only, so a kicker never wins the award), optimal lineup, points left
on the bench, lineup efficiency as a percentage, every individual bench
mistake ranked by cost, whether the optimal lineup would have won the game,
all-play record against the whole league that week, and week rank.

League-wide: highest and lowest team score, league average, closest game,
biggest blowout, biggest upset measured against each team's season scoring
average rather than record, unluckiest loss (only claimed when the losing
score is above average), luckiest win (only when below), highest-scoring
player, worst started skill player, top five players, biggest bench mistake,
every "would have won with the right lineup" case, least efficient lineup.

Standings: full table, rank movement versus last week, and current streaks
with the whole W/L sequence.

Waivers: every player added that week ranked by what he then scored, with the
date, the FAAB bid, and whether the manager started him or left him on the
bench. Players added after the games, or cut before kickoff, are separated out
instead of appearing as a misleading zero.

History: how this week's high score ranks against every recorded week, when a
score was last beaten, league records, league-wide historical average, and any
team setting a new personal best. Sleeper history walks `previous_league_id`
backwards, so prior seasons come along automatically.

## Failure modes

**A league failing does not stop the other.** The runner treats each
independently, so a broken Yahoo pull still delivers the Sleeper write-up.

**The Chrome button is unverified against a live page.** Yahoo's markup is not
public and changes between redesigns. It tries the embedded page state first
and falls back to reading the rendered tables, and if both come up short it
refuses rather than sending a half-built week, with a diagnostic dump you can
send over so the selectors get fixed. Expect one round of that on first use.

**A scores-only week still works.** If the button gets matchup scores but not
rosters, the run says so and produces a recap without the bench and waiver
material rather than inventing it.

**GitHub's repository_dispatch caps the payload at 64KB.** Rosters are trimmed
to the fields the analysis uses before sending, and if it is still too big the
button says so and points you at Download JSON.

**Yahoo's JSON is hostile.** Deeply nested, numeric string keys standing in for
lists, shapes that vary by endpoint. `_flatten` in the adapter normalizes it,
but this is the part most likely to need a fix on first contact with real
credentials, which is why it is marked untested.

**Yahoo authorization can be revoked** by a password change or an app removal.
It fails loudly; rerun `setup_yahoo.py`.

**Stat corrections land Tuesday and Wednesday.** A Tuesday 9am recap can cite a
number that shifts by Thursday. Running Wednesday instead trades freshness for
accuracy.

**The final-games gate depends on ESPN's public endpoint**, which is
undocumented and unversioned. If it disappears the run stops rather than
writing a recap mid-game. `--force` overrides it.

**GitHub Actions cron is UTC and ignores daylight saving.** Two schedules are
registered and a guard step exits on the wrong one, so the run lands at 9am
Eastern year round.

**GitHub Actions cron is best-effort** and can be delayed under load. It is
also skipped on repos with no activity for 60 days, which the weekly commit
of results prevents.

**GroupMe caps messages at 1000 characters.** Long recaps are split on
paragraph breaks and sent in order.

## Files

```
leagues.json              which leagues, which prompt, how far back
schema.py                 the contract + validation
adapters/sleeper.py       no auth, league id only
adapters/yahoo.py         OAuth2, needs approval first
adapters/payload.py       a week handed in from the browser button
extension/                the one-click Yahoo button
nfl_status.py             are the games actually final
analyze.py                every statistic, computed once
run.py                    orchestration + the plain-text brief
publish.py                builds the web page and the archive
deliver.py                email / GroupMe, with chunking
prompts/<league>.md       your existing write-up prompt, verbatim
prompts/<league>-lore.md  nicknames, rivalries, running jokes
prompts/<league>-chat.md  real group chat messages, the voice reference
out/<league>/             facts json, brief, finished recap per week
docs/                     the published pages, served by GitHub Pages
history/<league>/         every past week, feeding the comparisons
inbox/                    where a downloaded week gets dropped
test_pipeline.py          synthetic league, asserts the math
```

Past write-ups in `out/` are fed back into the next week's prompt, so running
jokes and voice carry forward on their own.
