# What a Yahoo matchup page actually looks like

Established by probing league 78540 (14 teams) while undrafted, so the shapes
are real and the values are all empty. Values get verified after week 1.

## Page inventory

A matchup page (`/f1/<league>/matchup?week=N&mid1=A&mid2=B`) has four tables:

| class | rows | what |
|---|---|---|
| `M-a` | 4 | "Compare Managers" header strip |
| `... Datatable ...` | 11 | **starters, both teams mirrored** |
| `... Datatable ...` | 2 | **the TOTAL row, both teams** |
| `Tst-table Table F-reset` | 10 | manager comparison, carries real manager names |

## The mirrored roster table

One table holds both lineups, left team and right team either side of the
position column. Eleven cells per row:

| # | column | notes |
|---|---|---|
| 0 | Stats | spacer, empty |
| 1 | **Player (left)** | `.ysf-player-name`; `.emptyplayer` when the slot is unfilled |
| 2 | Proj (left) | projection, not the score |
| 3 | **Fan Pts (left)** | the actual points. `–` (en dash) when no game has been played |
| 4 | Pos | hidden duplicate, carries `span.pos-label[data-pos]` |
| 5 | **Pos** | the visible slot label: QB, RB, W/R/T, DEF … |
| 6 | Pos | hidden duplicate |
| 7 | **Fan Pts (right)** | |
| 8 | Proj (right) | |
| 9 | **Player (right)** | |
| 10 | Stats | spacer |

The clean hook for the lineup slot is `span.pos-label[data-pos="QB"]` — an
attribute rather than display text, so it survives a relayout.

Team totals come from the second Datatable, same cell indices 3 and 7, on the
row whose position cell reads `TOTAL`.

## The problem: no bench

`rosterTableCount: 2` — starters and totals. **The matchup page does not carry
bench players.** That removes, for Yahoo:

- Biggest Losers (Bench Legends)
- optimal lineup, points left on the bench, lineup efficiency
- whether a waiver pickup was started or benched

Those are a large share of what makes the MOP recap land, so the matchup page
alone is not enough. The team page (`/f1/<league>/<teamId>`) is the candidate
source, since it shows a full roster including bench. If it also carries
per-week points, the better architecture is:

- league page -> matchup links give the pairings, from `mid1`/`mid2`
- fetch the 14 **team** pages -> full rosters with bench
- standings page -> records
- transactions page -> waivers

That is 14 fetches instead of 7 and gets everything, rather than 7 fetches that
get half a recap.

## Probe 4: confirmed, plus two things that change the plan

**The team page has the bench.** `/f1/<league>/<teamId>` reports
`benchWords: ["BN","Bench","IR"]`, and carries a slot summary table whose header
row is the league's own lineup shape:

    QB | RB | WR | TE | W-R-T | K | DEF | BN | IR

**Team names come from the page title**, cleanly:

    "Bring It On Season 19 - Philly Special | Fantasy Football | ..."
                             ^^^^^^^^^^^^^^

so team 10 is "Philly Special". No selector to break.

**`span.pos-label[data-pos]` exists only on the matchup page.** `posLabels` is
empty on the team page, so the two pages need different row parsers. The
matchup page keeps the clean attribute hook; the team page will need indices.

**The standings page is useless to us: 200 with zero tables.** It renders client
side, and `fetch` only ever sees server-rendered HTML. That is a real constraint
on this whole approach, not just this page.

It costs nothing here, though, because `standings.py` already computes records,
points for and points against from the weekly results themselves - it was
written for exactly this reason on the Sleeper side. Yahoo standings come free
from the same code, and week 1 is trivially 1-0 or 0-1.

Transactions are still unmapped and may well be client-rendered too, in which
case Yahoo recaps lose the waiver section until the API comes through.
