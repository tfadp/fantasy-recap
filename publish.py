#!/usr/bin/env python3
"""
Builds the web page you paste into the iMessage thread.

Writes docs/, which GitHub Pages serves. Each week gets a permanent URL and
index.html always points at the newest one, so the link you send is short and
the archive builds itself.

    https://<you>.github.io/fantasy-recap/            newest
    https://<you>.github.io/fantasy-recap/2026-wk05.html

    python3 publish.py --artifact 2025-wk12 > page.html
        emits one week as a fragment, for hosting somewhere that supplies its
        own document shell.

The write-up is the page. It is the thing people actually read, so it gets the
whole screen and none of the furniture. The numbers live under one fold at the
bottom labeled "the receipts", for whoever wants to argue about them.
"""

import argparse
import glob
import html
import json
import os
import re
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
DOCS = os.path.join(HERE, "docs")

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Barlow+Condensed:wght@500;600;700&'
         'family=Barlow:wght@400;500;600&'
         'family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400'
         '&display=swap">')

CSS = """
:root{
  --paper:#eef1f3; --card:#fff; --ink:#0f1519; --dim:#5b6774; --rule:#d7dde2;
  --accent:#a82f1a; --good:#186b3f; --bad:#a3211a; --agate:#f6f8f9;
  --display:"Barlow Condensed","Haettenschweiler","Arial Narrow",sans-serif;
  --body:"Source Serif 4",Georgia,"Times New Roman",serif;
  --data:"Barlow","Helvetica Neue",Arial,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#0e1216; --card:#161b21; --ink:#e7ecf0; --dim:#98a3b0;
    --rule:#28303a; --accent:#ff7d5e; --good:#5cc98d; --bad:#ff8f81;
    --agate:#12171d;
  }
}
:root[data-theme="dark"]{
  --paper:#0e1216; --card:#161b21; --ink:#e7ecf0; --dim:#98a3b0;
  --rule:#28303a; --accent:#ff7d5e; --good:#5cc98d; --bad:#ff8f81;
  --agate:#12171d;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);
  font-size:17px;line-height:1.62;-webkit-text-size-adjust:100%}
.wrap{max-width:640px;margin:0 auto;padding:26px 18px 64px}

.masthead{margin-bottom:26px}
.masthead .eyebrow{font-family:var(--data);font-size:11px;font-weight:600;
  letter-spacing:.18em;text-transform:uppercase;color:var(--accent)}
.masthead h1{font-family:var(--display);font-weight:700;font-size:clamp(36px,10vw,58px);
  line-height:.94;margin:8px 0 0;letter-spacing:-.01em;text-wrap:balance;
  text-transform:uppercase}
.masthead .dateline{font-family:var(--data);font-size:12px;color:var(--dim);
  letter-spacing:.04em;margin-top:12px}

section{margin-top:34px}
.label{font-family:var(--data);font-size:11px;font-weight:600;letter-spacing:.15em;
  text-transform:uppercase;color:var(--dim);border-bottom:1px solid var(--ink);
  padding-bottom:5px;margin-bottom:0}

/* box score, only ever inside the receipts */
.game{display:grid;grid-template-columns:1fr auto;gap:6px 14px;
  align-items:baseline;padding:11px 0;border-bottom:1px solid var(--rule);
  font-family:var(--data)}
.game .teams{font-size:16px;line-height:1.35}
.game .w{font-weight:600}
.game .l{color:var(--dim)}
.game .sep{color:var(--dim);font-size:13px;padding:0 2px}
.game .score{font-family:var(--display);font-size:22px;font-weight:600;
  font-variant-numeric:tabular-nums;white-space:nowrap;letter-spacing:.01em}
.game .score .lp{color:var(--dim)}

/* the write-up, which is the whole point of the page */
.column{font-family:var(--body);font-size:18px;line-height:1.6}

/* the receipts: folded away, for people who want to argue */
.receipts{margin-top:44px;border-top:3px solid var(--ink);padding-top:0}
.receipts summary{font-family:var(--data);font-size:12px;font-weight:600;
  letter-spacing:.14em;text-transform:uppercase;color:var(--dim);
  padding:15px 0;cursor:pointer;list-style:none;display:flex;
  justify-content:space-between;align-items:center;gap:12px}
.receipts summary::-webkit-details-marker{display:none}
.receipts summary::after{content:"Show";font-size:11px;color:var(--accent)}
.receipts[open] summary::after{content:"Hide"}
.receipts summary:hover{color:var(--ink)}
.receipts section:first-of-type{margin-top:6px}
.column p{margin:0 0 15px}
.column p:last-child{margin-bottom:0}
/* power rankings: the number is content, not list furniture, so it is kept
   literal. An <ol> would renumber from 1 every time a description line
   interrupts it, which is exactly what this format does twelve times. */
.column p.ranked{margin:0 0 3px;font-family:var(--data);font-weight:600;
  font-size:16px;font-variant-numeric:tabular-nums}
.column p.ranked + p{margin:0 0 16px;color:var(--dim);font-size:16px}
.column p.ranked .num{color:var(--accent);display:inline-block;min-width:1.6em}
.column p strong:only-child{font-family:var(--data);font-size:12px;font-weight:600;
  letter-spacing:.14em;text-transform:uppercase;color:var(--accent);
  display:block;margin-top:26px}
.column hr{border:0;border-top:1px solid var(--rule);margin:30px 0}
.column h3{font-family:var(--display);text-transform:uppercase;letter-spacing:.01em;
  font-size:26px;font-weight:600;margin:34px 0 11px;line-height:1.05;
  text-wrap:balance}
.column ul,.column ol{margin:0 0 19px;padding-left:22px}
.column li{margin-bottom:8px}
.column em{font-style:italic;color:var(--dim)}
.column strong{font-weight:600}
.column blockquote{margin:0 0 19px;padding-left:16px;
  border-left:3px solid var(--accent);color:var(--dim);font-style:italic}

/* agate */
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-family:var(--data);font-size:14px;
  font-variant-numeric:tabular-nums;margin-top:2px}
th{text-align:left;font-size:10px;letter-spacing:.11em;text-transform:uppercase;
  color:var(--dim);font-weight:600;padding:9px 8px 6px 0;border-bottom:1px solid var(--rule)}
td{padding:7px 8px 7px 0;border-bottom:1px solid var(--rule)}
tr:last-child td{border-bottom:0}
td:last-child,th:last-child{padding-right:0}
.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.rank{color:var(--dim);width:1.6em;font-size:13px}
.pts{font-weight:600}
.up{color:var(--good);font-size:12px}
.down{color:var(--bad);font-size:12px}
.muted{color:var(--dim)}
.slot{font-size:12px;color:var(--dim);letter-spacing:.03em;text-transform:uppercase}

nav{margin-top:40px;padding-top:16px;border-top:3px solid var(--ink);
  font-family:var(--data);font-size:13px;display:flex;flex-wrap:wrap;gap:8px 16px}
nav a{color:var(--accent);text-decoration:none}
nav a:hover,nav a:focus-visible{text-decoration:underline}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
footer{margin-top:22px;font-family:var(--data);font-size:11px;color:var(--dim);
  letter-spacing:.03em}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


def md_to_html(md):
    out, in_list = [], None
    for raw in md.split("\n"):
        line = raw.rstrip()
        h = re.match(r"^(#{1,4})\s+(.*)", line)
        b = re.match(r"^\s*[-*]\s+(.*)", line)
        n = re.match(r"^\s*(\d+)[.)]\s+(.*)", line)
        if h:
            if in_list: out.append(f"</{in_list}>"); in_list = None
            out.append(f"<h3>{inline(h.group(2))}</h3>")
        elif n:
            if in_list: out.append(f"</{in_list}>"); in_list = None
            out.append(f'<p class="ranked"><span class="num">{n.group(1)}.</span> '
                       f'{inline(n.group(2))}</p>')
        elif b:
            if in_list != "ul":
                if in_list: out.append(f"</{in_list}>")
                out.append("<ul>"); in_list = "ul"
            out.append(f"<li>{inline(b.group(1))}</li>")
        elif line.strip() in ("---", "***", "___", "\u2e3b"):
            if in_list: out.append(f"</{in_list}>"); in_list = None
            out.append("<hr>")
        elif not line.strip():
            if in_list: out.append(f"</{in_list}>"); in_list = None
        else:
            if in_list: out.append(f"</{in_list}>"); in_list = None
            out.append(f"<p>{inline(line)}</p>")
    if in_list: out.append(f"</{in_list}>")
    return "\n".join(out)


def split_headline(md):
    """
    Let the write-up name itself. If it opens with a heading, that becomes the
    page headline instead of a generic "Week 12", because the joke in the
    headline is doing more work than the week number ever will.
    """
    lines = md.lstrip().split("\n")
    if lines and re.match(r"^#{1,3}\s+\S", lines[0]):
        return re.sub(r"^#{1,3}\s+", "", lines[0]).strip(), "\n".join(lines[1:]).lstrip()
    return None, md


def inline(t):
    t = html.escape(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", t)
    return t


def e(x):
    return html.escape(str(x if x is not None else ""))


def league_block(name, recap_md, data, multi):
    """The write-up, then everything else folded into one collapsed block."""
    f = (data or {}).get("facts") or {}
    head = []
    if multi:
        head.append(f'<section><p class="label">{e(name)}</p></section>')

    headline, body_md = split_headline(recap_md or "")
    if body_md.strip():
        head.append(f'<div class="column">{md_to_html(body_md)}</div>')

    R = []

    games = (data or {}).get("games") or []
    if games:
        rows = "".join(
            '<div class="game">'
            f'<div class="teams"><span class="w">{e(g["winner"])}</span>'
            f'<span class="sep"> def. </span>'
            f'<span class="l">{e(g["loser"])}</span></div>'
            f'<div class="score">{g["winner_points"]}'
            f'<span class="lp">&thinsp;&ndash;&thinsp;{g["loser_points"]}</span></div>'
            '</div>' for g in games)
        R.append(f'<section><p class="label">Box score</p>{rows}</section>')

    st = f.get("standings") or []
    if st:
        changes = {c["team"]: c["change"] for c in f.get("record_changes", [])}
        rows = []
        for t in st:
            mv = changes.get(t["name"])
            arrow = ""
            if mv:
                cls, ch = ("up", "&#9650;") if mv > 0 else ("down", "&#9660;")
                arrow = f' <span class="{cls}">{ch}{abs(mv)}</span>'
            rows.append(
                f'<tr><td class="rank">{t["rank"]}</td>'
                f'<td>{e(t["name"])}{arrow}</td>'
                f'<td class="n">{t["wins"]}&#8211;{t["losses"]}</td>'
                f'<td class="n pts">{t["points_for"]}</td></tr>')
        R.append('<section><p class="label">Standings</p><div class="scroll"><table>'
                 '<thead><tr><th></th><th>Team</th><th class="n">Rec</th>'
                 f'<th class="n">PF</th></tr></thead><tbody>{"".join(rows)}'
                 '</tbody></table></div></section>')

    tp = f.get("top_5_players") or []
    if tp:
        rows = "".join(
            f'<tr><td>{e(p["player"])} <span class="slot">{e(p["pos"])}</span></td>'
            f'<td class="muted">{e(p["team"])}</td>'
            f'<td class="n pts">{p["points"]}</td></tr>' for p in tp)
        R.append('<section><p class="label">Top performers</p><div class="scroll"><table>'
                 '<thead><tr><th>Player</th><th>Team</th><th class="n">Pts</th></tr></thead>'
                 f'<tbody>{rows}</tbody></table></div></section>')

    wp = f.get("waiver_pickups") or {}
    if wp.get("pickups"):
        rows = "".join(
            f'<tr><td>{e(p["player"])} <span class="slot">{e(p["pos"])}</span></td>'
            f'<td class="muted">{e(p["manager"])}</td>'
            f'<td class="slot">{e("started " + (p["slot"] or "") if p["status"] == "started" else p["status"])}</td>'
            f'<td class="n pts">{p["points"]}</td></tr>' for p in wp["pickups"])
        R.append('<section><p class="label">Waiver wire</p><div class="scroll"><table>'
                 '<thead><tr><th>Pickup</th><th>By</th><th>Used</th>'
                 '<th class="n">Pts</th></tr></thead>'
                 f'<tbody>{rows}</tbody></table></div></section>')

    coulda = f.get("would_have_won_with_optimal_lineup") or []
    if coulda:
        rows = "".join(
            f'<tr><td>{e(c["team"])}</td><td class="n">{c["scored"]}</td>'
            f'<td class="n muted">{c["optimal"]}</td>'
            f'<td class="n">{e(c["opponent_points"])}</td></tr>' for c in coulda)
        R.append('<section><p class="label">Should have won</p><div class="scroll"><table>'
                 '<thead><tr><th>Team</th><th class="n">Scored</th>'
                 '<th class="n">Best</th><th class="n">Needed</th></tr></thead>'
                 f'<tbody>{rows}</tbody></table></div></section>')

    receipts = ""
    if R:
        label = "The receipts" if not multi else f"The receipts &middot; {e(name)}"
        receipts = (f'<details class="receipts"><summary>{label}</summary>'
                    f'{"".join(R)}</details>')
    return headline, "\n".join(head) + receipts


def week_body(stem, entries):
    blocks, league, wk, season, headline = [], None, None, None, None
    multi = len(entries) > 1
    for cfg, fpath in sorted(entries, key=lambda x: x[0]["name"]):
        with open(fpath) as fh:
            data = json.load(fh)
        league, wk, season = data["league"], data["week"], data["season"]
        md_path = fpath.replace("-facts.json", ".md")
        md = open(md_path).read() if os.path.exists(md_path) else None
        h, block = league_block(cfg.get("display_name", cfg["name"]), md, data, multi)
        headline = headline or h
        blocks.append(block)
    return league, wk, season, headline, "\n".join(blocks)


def render(stem, entries, order, standalone=True):
    league, wk, season, headline, body = week_body(stem, entries)
    display = headline or f"{league} Week {wk}"
    title = f"{league} Week {wk}"
    nav = "".join(f'<a href="{s}.html">Week {s.split("-wk")[1].lstrip("0")}</a>'
                  for s in order[:14] if s != stem)
    page = f"""<header class="masthead">
<div class="eyebrow">{e(league)} &middot; Week {wk}, {e(season)}</div>
<h1>{e(display)}</h1>
<div class="dateline">{datetime.date.today().strftime("%A, %B %-d")}</div>
</header>
{body}
<nav>{nav}</nav>
<footer>Every number pulled straight from the league. Take it up with the API.</footer>"""

    if not standalone:
        return (f"<title>{e(title)}</title>{FONTS}<style>{CSS}</style>"
                f'<div class="wrap">{page}</div>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(display)}">
<meta property="og:title" content="{e(display)}">
<meta property="og:description" content="{e(league)} week {wk} recap.">
{FONTS}<style>{CSS}</style></head>
<body><div class="wrap">{page}</div></body></html>"""


def collect():
    cfgs = json.load(open(os.path.join(HERE, "leagues.json")))["leagues"]
    weeks = {}
    for cfg in cfgs:
        for f in glob.glob(os.path.join(OUT, cfg["name"], "*-facts.json")):
            stem = os.path.basename(f).replace("-facts.json", "")
            weeks.setdefault(stem, []).append((cfg, f))
    return weeks


def build():
    weeks = collect()
    if not weeks:
        print("Nothing in out/ to publish.")
        return []
    os.makedirs(DOCS, exist_ok=True)
    order = sorted(weeks, reverse=True)
    for stem in order:
        with open(os.path.join(DOCS, f"{stem}.html"), "w") as fh:
            fh.write(render(stem, weeks[stem], order))
    with open(os.path.join(DOCS, "index.html"), "w") as fh:
        fh.write(open(os.path.join(DOCS, f"{order[0]}.html")).read())
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print(f"Published {len(order)} week(s) to docs/, newest is {order[0]}")
    return order


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", metavar="STEM",
                    help="print one week as a fragment instead of building docs/")
    a = ap.parse_args()
    if a.artifact:
        w = collect()
        if a.artifact not in w:
            raise SystemExit(f"no such week: {a.artifact}. have: {', '.join(sorted(w))}")
        print(render(a.artifact, w[a.artifact], sorted(w, reverse=True), standalone=False))
    else:
        build()
