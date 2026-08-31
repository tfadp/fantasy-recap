# MOP LEAGUE WRITE-UP STYLE GUIDE

Dan's source document. `prompts/mop.md` is the operative version handed to the
model each week; this is the reasoning behind it. If the two ever disagree,
this one is the intent and `mop.md` is the bug.

Decisions locked from Part 5:

- **Power rankings weights:** Version B (0.40 season PF / 0.25 last two weeks /
  0.25 win% / 0.10 consistency). Already the default in `power_rankings.py`.
- **PR display scale:** points-like, matching the Week 4 sample's 95-136 range,
  set as `pr_display_scale: "points"` in `leagues.json`. Ordering is identical
  either way; this only changes how the number reads.
- **Section heading:** "Biggest Losers", plural.
- **QC audit footer:** kept for verification, stripped from the group chat
  version. The model is told not to write it; `deliver.py` appends it to your
  email instead.

Part 6's drafting sequence is implemented as code rather than instructions.
Steps 1-6 are `analyze.py`, `standings.py` and `power_rankings.py`; step 8 is
`qc.py`, which runs before the model is called and refuses to write anything
if a check fails.

---


# MOP LEAGUE WRITE-UP STYLE GUIDE
### The house style, section by section, with voice rules and worked examples
Derived from: the Week 4 sample write-up, the rules doc, the QC process, and COMMON_ERRORS.md.

## PART 0: WHAT THIS DOC IS

The rules doc tells you *what data to collect*. COMMON_ERRORS.md tells you *what not to get wrong*.
This doc tells you *how it should read*. Format, sentence shape, voice, and the specific move that makes each section land.

Rule of thumb for the whole thing: **numbers first, joke second.** Every adjective is earned by a stat that appears in the same sentence.

## PART 1: THE SKELETON (fixed order, never rearranged)

```
Week X Recap – MOP League

Match Summaries
[6 matchups]

⸻

Biggest Losers (Bench Legends)
Studs Who Failed
Call the Doctor
Waiver Wire Genius
Toilet Bowl Performance

⸻

Power Rankings (with Movement)
[1-12]
```

Two divider lines total. One after Match Summaries, one before Power Rankings. The four middle sections run together with no dividers between them.

Header format is `Week X Recap – MOP League`, not "MOP League — Week X Recap."

## PART 2: SECTION-BY-SECTION SPEC

### 2.1 Match Summaries

**Structure per matchup: a score line, then 1 to 3 short sentences. Never more than three.**

The three-beat structure:

1. **Verdict fragment.** Two to four words, no verb needed. "Absolute bloodbath." "Game of the week." "Not pretty, but enough."
2. **Evidence.** Named starters with points in parentheses. Winner's guys first, then the loser's best guy with a "but" turn.
3. **Closer.** The record line, or the twist. "Dan sneaks to 3–1." "Oakland stuck at 0–4."

Score line rules: two decimals exactly as the box score shows; `def.` is the verb, never "beat" or "over"; ties are `Team A (n.nn) tied Team B (n.nn)`.

Ordering the matchups: keep whatever order the box scores arrive in so the reader can follow along with their app.

### 2.2 Biggest Losers (Bench Legends)

`• Player (##.#, manager) – One-line consequence.` 2 to 4 entries.

The consequence line is the whole point. Three flavors: flipped it (only if the math actually flips it), cost the margin, missed upside.

### 2.3 Studs Who Failed

`• Player (#.#, team) – Short brutal line.` Five to eight words. Bench Legends lines explain, Studs Who Failed lines only sting.

### 2.4 Call the Doctor

`• Team (record, weekly score) – Diagnosis.` Record leads, because the point is that the problem is chronic.

### 2.5 Waiver Wire Genius

`• Manager → Player (##.#) — Why it mattered.` Points in parens only if he played. Can be gently ironic.

### 2.6 Toilet Bowl Performance

`• Team (###.##) — Context on the gap.` The context clause is what makes it land. Never just restate the number.

### 2.7 Power Rankings (with Movement)

`N. Team — ###.# (↑N)` then one factual sentence. Arrows `(↑3)`, `(↓4)`, `(–)`, never `(0)`. Record in the note, not the top line. Arrows across all 12 must sum to zero.

## PART 3: VOICE

1. **Numbers first, joke second.**
2. **Fragments are the default.**
3. **Short. Then shorter.**
4. **Punch the roster, not the person.**
5. **Sympathy for the high-score loser.** "Cruelest fate in fantasy."

Verbs for winning: carried, fueled, powered, rode, led the charge, sneaks to, jumps to.
Verbs for losing: flatlined, lagged, disappeared, couldn't keep pace, stuck at, fell back to earth.

Does not fit: sportscaster inflation ("statement win", "sent a message", "must-win"); hedging ("arguably", "one of the better"); any sentence writable without the box score; predictions; second person.

Mechanics: no emojis; no tables; en dash for records (3–1); em dash for asides; points in parens right after the name; negative defenses keep the minus sign.

## PART 4: LENGTH TARGETS

| Section | Entries | Words per entry |
|---|---|---|
| Match Summaries | 6 | 30 to 45 |
| Bench Legends | 2 to 4 | 12 to 18 |
| Studs Who Failed | 2 to 4 | 8 to 14 |
| Call the Doctor | 2 | 10 to 15 |
| Waiver Wire Genius | 2 to 4 | 10 to 16 |
| Toilet Bowl | 1 | 10 to 15 |
| Power Rankings | 12 | 8 to 12 in the note |

Whole write-up lands around 700 to 850 words. If a draft runs past 900, the matchup blocks have grown a fourth sentence. Cut it.

## PART 6: THE DRAFTING SEQUENCE

Implemented as code in this repo rather than followed by hand. The one rule that prevents most of the damage: never write a number you have not just looked at.

---

## Amendments after the first live runs

Dan's changes, which override Parts 1-3 above where they conflict:

1. **A cold open.** Three to five sentences before the first score line: the
   "oh fuck, that happened" paragraph. Leads with the single most surprising
   thing, carries at least one shoutout and one embarrassment, every sentence
   with a number and a name. No throat-clearing, and nothing that would survive
   being pasted into a different week.
2. **Player names bold**, everywhere, every section. Players, defenses and
   kickers only, never teams and never manager handles. This is the sole piece
   of markdown in the write-up. The web page renders it; `deliver.py` strips it
   from the copy-for-iMessage block, because iMessage would show the asterisks.
3. **Cutting, not gentle.** Part 3's "punch the roster, not the person" is
   loosened: be genuinely mean about the football. The manager is fair game for
   what he did on Sunday, never for who he is.

Length target moves to 780-950 words to make room for the opener.
