/* Pull one completed week out of Yahoo into the league_week shape.
 *
 * Run it in the console on any page of your league:
 *   https://football.fantasysports.yahoo.com/f1/<league>/...
 *
 * Everything the recap needs is on the matchup page. It carries two roster
 * tables with identical headers — starters, then bench — and the bench rows
 * are marked with the same span.pos-label[data-pos="BN"] hook as the rest.
 * YAHOO-MARKUP.md said for a while that the matchup page had no bench; that
 * was established against an undrafted league where the second table was
 * empty, and it is wrong. Team pages are fetched only for their titles, which
 * is where the team names live.
 *
 * Column positions are resolved from each table's own header row, never
 * hardcoded, so a relayout cannot silently swap projections for real points.
 *
 * Handoff is the green box: select it and press Cmd+C. Blob downloads fire
 * without error on Yahoo's pages and silently write nothing, and copy() is a
 * DevTools API that is usually out of scope inside an async function.
 */
(async () => {
  // The completed week to pull. Override by running it on a page whose URL
  // already carries ?week=N, otherwise bump this line each Tuesday.
  const WEEK = Number(new URLSearchParams(location.search).get("week")) || 2;
  const MAX_TEAM_ID = 16;

  console.clear();
  const LG = (location.pathname.match(/\/f1\/(\d+)/) || [])[1];
  if (!LG) { alert("Open a page inside your Yahoo league first (…/f1/<league>/…)"); return; }

  const dbg = { league: LG, week: WEEK, fetches: {}, notes: [], unparsed: [] };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const txt = (e) => (e ? e.textContent || "" : "").replace(/\s+/g, " ").trim();
  const num = (s) => { const m = String(s).match(/-?\d+(?:\.\d+)?/); return m ? parseFloat(m[0]) : null; };
  const squash = (s, n) => String(s || "").replace(/\s+/g, " ").slice(0, n);

  const get = async (p) => {
    try {
      const r = await fetch(new URL(p, location.origin), { credentials: "include" });
      const html = await r.text();
      dbg.fetches[p] = r.status;
      return { status: r.status, doc: new DOMParser().parseFromString(html, "text/html") };
    } catch (e) {
      dbg.fetches[p] = "threw: " + e.message;
      return { status: 0, doc: new DOMParser().parseFromString("", "text/html") };
    }
  };

  const columns = (table) => {
    let head = [], hi = -1;
    for (let i = 0; i < Math.min(3, table.rows.length); i++) {
      const cells = [...table.rows[i].cells].map((c) => txt(c));
      if (cells.some((h) => /fan\s*pts/i.test(h))) { head = cells; hi = i; break; }
    }
    const find = (re) => head.map((h, i) => (re.test(h) ? i : -1)).filter((i) => i >= 0);
    return { head, headerRow: hi, pts: find(/fan\s*pts/i), player: find(/player/i) };
  };

  const POS = /\b([A-Za-z]{2,3})\s*[-–]\s*(QB|RB|WR|TE|K|DEF)\b/gi;

  const player = (cell, slot) => {
    if (!cell || cell.querySelector(".emptyplayer")) return null;
    const holder = cell.querySelector(".ysf-player-name") || cell;
    const a = holder.querySelector('a[href*="/players/"]') || holder.querySelector("a");
    const name = txt(a);
    if (!name) return null;

    // "Tyler Shough Video Forecast Player Note NO - QB" — take the LAST
    // team-position pair, so nothing inside the note text can be mistaken
    // for one. Yahoo writes these title case ("Chi - RB"), not all caps.
    const full = txt(holder);
    let team = null, pos = null, m;
    POS.lastIndex = 0;
    while ((m = POS.exec(full)) !== null) { team = m[1]; pos = m[2]; }

    if (!pos && /^(DEF|K)$/i.test(slot || "")) pos = slot.toUpperCase();
    const inj = cell.querySelector('.F-injury, [class*="ysf-player-status"], abbr[title]');
    const pid = ((a && a.getAttribute("href")) || "").match(/\/players\/(\d+)/);

    return {
      player_id: pid ? pid[1] : name,
      name,
      pos: (pos || "?").toUpperCase(),
      nfl_team: (team || "FA").toUpperCase(),
      slot: null,
      points: 0,
      injury: inj ? txt(inj).toUpperCase().slice(0, 4) || null : null,
      _rawcell: squash(full, 90),
    };
  };

  /* Read both mirrored sides out of every roster table on a matchup page.
     Starters and bench are separate tables with the same header shape, so
     one pass over all of them picks up everything. */
  const readMatchup = (doc) => {
    const out = [];
    for (const t of [...doc.querySelectorAll("table")]) {
      if (!t.querySelector('a[href*="/players/"]')) continue;
      const c = columns(t);
      if (c.pts.length < 2 || c.player.length < 2) {
        if (c.pts.length || c.player.length) {
          dbg.unparsed.push({ cls: squash(t.className, 50), head: c.head });
        }
        continue;
      }
      const sides = [
        { player: c.player[0], pts: c.pts[0], side: 0 },
        { player: c.player[c.player.length - 1], pts: c.pts[c.pts.length - 1], side: 1 },
      ];
      for (const r of [...t.rows].slice(c.headerRow + 1)) {
        const el = r.querySelector("span.pos-label[data-pos]");
        const slot = el ? el.getAttribute("data-pos") : "";
        if (!slot) continue;
        for (const s of sides) {
          const p = player(r.cells[s.player], slot);
          if (!p) continue;
          p.points = num(txt(r.cells[s.pts])) ?? 0;
          out.push({ ...p, _slot: slot, _side: s.side });
        }
      }
    }
    return out;
  };

  /* ---- team ids and names ------------------------------------------------ */
  const names = {};
  for (let id = 1; id <= MAX_TEAM_ID; id++) {
    const { status, doc } = await get(`/f1/${LG}/${id}`);
    if (status !== 200) continue;
    const title = txt(doc.querySelector("title"));
    const nm = (title.split("|")[0] || "").split(" - ").slice(1).join(" - ").trim();
    if (nm) names[id] = nm;
    await sleep(150);
  }
  const ids = Object.keys(names);
  dbg.teamIds = ids;

  /* ---- the week's pairings ----------------------------------------------- */
  const pairs = new Map();
  const harvest = (doc) => {
    doc.querySelectorAll('a[href*="mid1="]').forEach((a) => {
      const h = a.getAttribute("href") || "";
      if (String((h.match(/week=(\d+)/) || [])[1]) !== String(WEEK)) return;
      const m1 = (h.match(/mid1=(\d+)/) || [])[1], m2 = (h.match(/mid2=(\d+)/) || [])[1];
      if (m1 && m2 && m1 !== m2) pairs.set([m1, m2].sort((x, y) => x - y).join("-"), [m1, m2]);
    });
  };
  for (const p of [`/f1/${LG}?week=${WEEK}`, `/f1/${LG}/scoreboard?week=${WEEK}`,
                   `/f1/${LG}/matchup?week=${WEEK}`]) {
    const { status, doc } = await get(p);
    if (status === 200) harvest(doc);
  }
  for (const id of ids) {
    if (pairs.size * 2 >= ids.length) break;
    const { status, doc } = await get(`/f1/${LG}/${id}?week=${WEEK}`);
    if (status === 200) harvest(doc);
    await sleep(150);
  }
  dbg.pairs = [...pairs.values()];
  if (pairs.size * 2 !== ids.length) {
    dbg.notes.push(`${pairs.size} pairings for ${ids.length} teams — expected ${ids.length / 2}`);
  }

  /* ---- matchup pages: totals, starters, bench, managers ------------------ */
  const totals = {}, starters = {}, bench = {}, managers = {};
  const BN = /^(BN|IR|IR\+)$/i;
  for (const [, [m1, m2]] of pairs) {
    const path = `/f1/${LG}/matchup?week=${WEEK}&mid1=${m1}&mid2=${m2}`;
    const { status, doc } = await get(path);
    if (status !== 200) { dbg.notes.push(`matchup ${m1} v ${m2} returned ${status}`); continue; }

    const rows = readMatchup(doc);
    [[m1, 0], [m2, 1]].forEach(([id, side]) => {
      const mine = rows.filter((p) => p._side === side);
      starters[id] = mine.filter((p) => !BN.test(p._slot))
        .map(({ _slot, _side, _rawcell, ...p }) => ({ ...p, slot: _slot }));
      bench[id] = mine.filter((p) => BN.test(p._slot))
        .map(({ _slot, _side, _rawcell, ...p }) => p);
    });

    const totalRow = [...doc.querySelectorAll("table")].flatMap((t) => [...t.rows])
      .find((r) => [...r.cells].some((c) => /^TOTAL$/i.test(txt(c))));
    if (totalRow) {
      const c = columns(totalRow.closest("table"));
      if (c.pts.length >= 2) {
        totals[m1] = num(txt(totalRow.cells[c.pts[0]]));
        totals[m2] = num(txt(totalRow.cells[c.pts[c.pts.length - 1]]));
      }
    }
    // the "Compare Managers" strip carries the two scores and the two managers
    const cmp = [...doc.querySelectorAll("table")].find((t) => /Tst-table/.test(t.className || ""));
    if (cmp && cmp.rows[0]) {
      const cells = [...cmp.rows[0].cells].map((x) => txt(x).replace(/\s*View Profile\s*$/i, "").trim())
        .filter(Boolean);
      // Yahoo's compare strip sometimes yields a UI label ("Category") instead
      // of a name. A scraped artifact must never reach the write-up looking
      // like a person, so anything that is not plausibly a name is dropped and
      // the team name stands in downstream.
      const JUNK = /^(category|view profile|manager|team|—|-)?$/i;
      const ok = (x) => x && !JUNK.test(x.trim());
      if (cells.length >= 2) {
        if (ok(cells[0])) managers[m1] = cells[0];
        if (ok(cells[cells.length - 1])) managers[m2] = cells[cells.length - 1];
      }
    }
    if (totals[m1] == null) {
      const strip = [...doc.querySelectorAll("table")].find((t) => /M-a/.test(t.className || ""));
      const nums = strip ? [...strip.querySelectorAll("td")].map((c) => txt(c))
        .filter((x) => /^\d+\.\d{2}$/.test(x)) : [];
      if (nums.length >= 2) { totals[m1] = num(nums[0]); totals[m2] = num(nums[1]); }
    }
    await sleep(200);
  }

  /* ---- assemble ---------------------------------------------------------- */
  const order = ["QB", "RB", "WR", "TE", "W/R/T", "K", "DEF"];
  const first = ids.find((id) => (starters[id] || []).length);
  const rosterSlots = first ? starters[first].map((p) => p.slot) : [];

  const teams = ids.map((id) => ({
    team_id: String(id), name: names[id], manager: managers[id] || "unknown",
    wins: 0, losses: 0, ties: 0, points_for: 0, points_against: 0,
  }));
  const matchups = [...pairs.values()].map(([m1, m2], i) => ({
    matchup_id: String(i),
    teams: [m1, m2].map((id) => ({
      team_id: String(id),
      points: totals[id] ?? +((starters[id] || []).reduce((a, b) => a + b.points, 0)).toFixed(2),
      projected: null,
      starters: starters[id] || [],
      bench: bench[id] || [],
    })),
  }));

  const lw = {
    source: "yahoo", league_id: LG,
    league_name: (document.title.split("|")[0] || "").split(" - ")[0].trim() || `Yahoo ${LG}`,
    season: String(new Date().getFullYear()), week: WEEK,
    roster_slots: rosterSlots,
    flex_eligible: { "W/R/T": ["RB", "WR", "TE"] },
    teams, matchups, transactions: [],
    _method: "matchup-pages", _debug: dbg,
  };
  lw._check = matchups.flatMap((m) => m.teams.map((t) => ({
    team: (teams.find((x) => x.team_id === t.team_id) || {}).name,
    total: t.points,
    sumStarters: +t.starters.reduce((a, b) => a + b.points, 0).toFixed(2),
    starters: t.starters.length, bench: t.bench.length,
    unknownPos: t.starters.concat(t.bench).filter((p) => p.pos === "?").length,
  })));

  const s = JSON.stringify(lw);
  window.__yahooWeek = s;
  try { copy(s); } catch (e) {}

  document.querySelectorAll("[data-yahoo-week-box]").forEach((n) => n.remove());
  const box = document.createElement("textarea");
  box.setAttribute("data-yahoo-week-box", "1");
  box.value = s;
  box.setAttribute("style",
    "position:fixed;z-index:2147483647;top:20px;left:20px;right:20px;height:55vh;" +
    "font:12px/1.4 monospace;padding:12px;border:4px solid #0a0;background:#fff;color:#000");
  document.body.appendChild(box); box.focus(); box.select();

  const benchTotal = Object.values(bench).reduce((a, b) => a + b.length, 0);
  const unknown = lw._check.reduce((a, b) => a + b.unknownPos, 0);
  console.log("%cteams " + teams.length + " · matchups " + matchups.length +
              " · bench players " + benchTotal + " · unknown pos " + unknown +
              "\\nGreen box is selected — press Cmd+C.",
              "font-size:15px;color:#0a0;font-weight:bold");
  console.table(lw._check);
})();
