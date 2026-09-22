/*
 * Pull a completed week out of Yahoo, in the shape run.py expects.
 *
 * Injected into the league page you already have open, in the MAIN world, by
 * the extension's button. It runs only on click, only on that tab, and only
 * reads what your own session can already see.
 *
 * Everything the recap needs is on the matchup pages: the pairings, both
 * totals, the starters and the bench. Team pages are fetched only for their
 * <title>, which is where team names live. Column positions are resolved from
 * each table's own header row rather than hardcoded, so a Yahoo relayout
 * cannot silently swap projections for real points.
 *
 * Returns a promise; chrome.scripting awaits it.
 */
(() => {
  const txt = (e) => (e ? e.textContent || "" : "").replace(/\s+/g, " ").trim();
  const num = (s) => { const m = String(s).match(/-?\d+(?:\.\d+)?/); return m ? parseFloat(m[0]) : null; };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const LG = (location.pathname.match(/\/f1\/(\d+)/) || [])[1];
  if (!LG) return Promise.resolve({ error: "Not on a Yahoo fantasy football league page." });

  const dbg = { fetches: {}, notes: [] };
  const get = async (p) => {
    try {
      const r = await fetch(new URL(p, location.origin), { credentials: "include" });
      const html = await r.text();
      dbg.fetches[p] = r.status;
      return { status: r.status, doc: new DOMParser().parseFromString(html, "text/html") };
    } catch (e) {
      dbg.fetches[p] = "threw";
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
    const full = txt(holder);
    let team = null, pos = null, m;
    POS.lastIndex = 0;
    while ((m = POS.exec(full)) !== null) { team = m[1]; pos = m[2]; }
    if (!pos && /^(DEF|K)$/i.test(slot || "")) pos = slot.toUpperCase();
    const inj = cell.querySelector('.F-injury, [class*="ysf-player-status"]');
    const pid = ((a && a.getAttribute("href")) || "").match(/\/players\/(\d+)/);
    return {
      player_id: pid ? pid[1] : name, name,
      pos: (pos || "?").toUpperCase(), nfl_team: (team || "FA").toUpperCase(),
      slot: null, points: 0,
      injury: inj ? txt(inj).toUpperCase().slice(0, 4) || null : null,
    };
  };

  const readMatchup = (doc) => {
    const out = [];
    for (const t of [...doc.querySelectorAll("table")]) {
      if (!t.querySelector('a[href*="/players/"]')) continue;
      const c = columns(t);
      if (c.pts.length < 2 || c.player.length < 2) continue;
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

  /* Which week to write up. The league page renders the *current* week's
     matchup links, so the completed one is the week before. Verified rather
     than assumed: a week with no points on the board is not finished, so step
     back until one is. That also makes the button safe to press on a Sunday. */
  const weekOnPage = () => {
    const counts = {};
    document.querySelectorAll('a[href*="matchup?week="]').forEach((a) => {
      const w = (a.getAttribute("href").match(/week=(\d+)/) || [])[1];
      if (w) counts[w] = (counts[w] || 0) + 1;
    });
    const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    return best ? parseInt(best[0], 10) : null;
  };

  const hasScores = async (wk) => {
    const { status, doc } = await get(`/f1/${LG}/matchup?week=${wk}`);
    if (status !== 200) return false;
    return readMatchup(doc).some((p) => p.points !== 0);
  };

  const pickWeek = async (override) => {
    if (override) return override;
    const cur = weekOnPage();
    let wk = cur ? cur - 1 : null;
    if (!wk) return null;
    for (let i = 0; i < 3 && wk > 0; i++, wk--) {
      if (await hasScores(wk)) return wk;
      dbg.notes.push(`week ${wk} has no scores yet, stepping back`);
    }
    return null;
  };

  return (async () => {
    const WEEK = await pickWeek(window.__RECAP_WEEK);
    if (!WEEK) return { error: "Could not work out which week is finished. Open the league page, or set the week by hand." };

    // team ids and names, from each team page's <title>
    const names = {};
    for (let id = 1; id <= 16; id++) {
      const { status, doc } = await get(`/f1/${LG}/${id}`);
      if (status !== 200) continue;
      const title = txt(doc.querySelector("title"));
      const nm = (title.split("|")[0] || "").split(" - ").slice(1).join(" - ").trim();
      if (nm) names[id] = nm;
      await sleep(120);
    }
    const ids = Object.keys(names);
    if (!ids.length) return { error: "No team pages resolved. Are you signed in to this league?" };

    // the week's pairings
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
      await sleep(120);
    }

    const totals = {}, starters = {}, bench = {}, managers = {};
    const BN = /^(BN|IR|IR\+)$/i;
    // Yahoo's compare strip sometimes yields a UI label where a name goes. A
    // scraped artifact must never reach the write-up looking like a person.
    const JUNK = /^(category|view profile|manager|team|—|-)?$/i;
    for (const [, [m1, m2]] of pairs) {
      const { status, doc } = await get(`/f1/${LG}/matchup?week=${WEEK}&mid1=${m1}&mid2=${m2}`);
      if (status !== 200) { dbg.notes.push(`matchup ${m1} v ${m2} returned ${status}`); continue; }
      const rows = readMatchup(doc);
      [[m1, 0], [m2, 1]].forEach(([id, side]) => {
        const mine = rows.filter((p) => p._side === side);
        starters[id] = mine.filter((p) => !BN.test(p._slot))
          .map(({ _slot, _side, ...p }) => ({ ...p, slot: _slot }));
        bench[id] = mine.filter((p) => BN.test(p._slot))
          .map(({ _slot, _side, ...p }) => p);
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
      const cmp = [...doc.querySelectorAll("table")].find((t) => /Tst-table/.test(t.className || ""));
      if (cmp && cmp.rows[0]) {
        const cells = [...cmp.rows[0].cells].map((x) => txt(x).replace(/\s*View Profile\s*$/i, "").trim())
          .filter(Boolean);
        const ok = (x) => x && !JUNK.test(x.trim());
        if (cells.length >= 2) {
          if (ok(cells[0])) managers[m1] = cells[0];
          if (ok(cells[cells.length - 1])) managers[m2] = cells[cells.length - 1];
        }
      }
      await sleep(150);
    }

    const first = ids.find((id) => (starters[id] || []).length);
    const teams = ids.map((id) => ({
      team_id: String(id), name: names[id],
      manager: managers[id] || names[id],   // never a UI label, never blank
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

    return {
      source: "yahoo", league_id: LG,
      league_name: (document.title.split("|")[0] || "").split(" - ")[0].trim() || `Yahoo ${LG}`,
      season: String(new Date().getFullYear()), week: WEEK,
      roster_slots: first ? starters[first].map((p) => p.slot) : [],
      flex_eligible: { "W/R/T": ["RB", "WR", "TE"] },
      teams, matchups, transactions: [],
      _method: "extension/matchup-pages",
      _check: matchups.flatMap((m) => m.teams.map((t) => ({
        team: (teams.find((x) => x.team_id === t.team_id) || {}).name,
        total: t.points,
        sumStarters: +t.starters.reduce((a, b) => a + b.points, 0).toFixed(2),
        starters: t.starters.length, bench: t.bench.length,
      }))),
      _debug: dbg,
    };
  })();
})();
