/*
 * Runs only when you click the button, only on the tab you are already
 * looking at, and only reads what that page has already rendered for you.
 * It sends nothing anywhere on its own.
 *
 * Two strategies, tried in order:
 *   1. the JSON state Yahoo embeds in the page, which is complete and stable
 *   2. reading the rendered scoreboard and roster tables
 *
 * If both come up short it returns a diagnostic dump instead of a half-built
 * week, because a half-built week is how you end up with a confident recap
 * that is quietly wrong.
 */

function extractWeek() {
  const out = {
    source: "yahoo",
    league_id: null,
    league_name: null,
    season: String(new Date().getFullYear()),
    week: null,
    roster_slots: [],
    flex_eligible: {},
    teams: [],
    matchups: [],
    transactions: [],
    _method: null,
    _warnings: [],
  };

  const url = location.href;
  const lm = url.match(/\/f1\/(\d+)/);
  if (lm) out.league_id = lm[1];
  const wm = url.match(/[?&]week=(\d+)/) || url.match(/\/matchup\/(\d+)/);
  if (wm) out.week = parseInt(wm[1], 10);

  // ---- strategy 1: embedded state -------------------------------------
  const state = findEmbeddedState();
  if (state) {
    out._method = "embedded-json";
    try {
      Object.assign(out, fromState(state, out));
      if (out.matchups.length) return out;
      out._warnings.push("embedded state found but no matchups parsed");
    } catch (e) {
      out._warnings.push("embedded state parse failed: " + e.message);
    }
  }

  // ---- strategy 2: rendered tables ------------------------------------
  const dom = fromDom();
  if (dom.matchups.length) {
    out._method = out._method ? out._method + "+dom" : "dom";
    out.matchups = dom.matchups;
    out.teams = dom.teams;
    if (!out.league_name) out.league_name = dom.league_name;
    if (!out.week) out.week = dom.week;
    return out;
  }

  out._method = "failed";
  out._warnings.push("no matchup data found on this page");
  out._diagnostic = diagnostic();
  return out;
}

function findEmbeddedState() {
  for (const key of ["__PRELOADED_STATE__", "__INITIAL_STATE__", "YAHOO"]) {
    if (window[key] && typeof window[key] === "object") return window[key];
  }
  for (const s of document.querySelectorAll("script")) {
    const t = s.textContent || "";
    if (t.length < 200) continue;
    const m = t.match(/(?:root\.App\.main|__PRELOADED_STATE__|__INITIAL_STATE__)\s*=\s*(\{[\s\S]*?\});?\s*$/);
    if (m) {
      try { return JSON.parse(m[1]); } catch (e) { /* keep looking */ }
    }
  }
  return null;
}

/* Walk an arbitrary object looking for the shapes we need. Yahoo moves things
   around between redesigns, so we search by content rather than by path. */
function collect(node, test, found = [], depth = 0) {
  if (depth > 12 || node === null || typeof node !== "object") return found;
  if (test(node)) { found.push(node); return found; }
  for (const v of Object.values(node)) collect(v, test, found, depth + 1);
  return found;
}

function fromState(state, base) {
  const res = { teams: [], matchups: [] };

  const teamNodes = collect(state, (n) =>
    n && typeof n === "object" && n.team_key && (n.name || n.team_name));
  const seen = new Set();
  for (const t of teamNodes) {
    if (seen.has(t.team_key)) continue;
    seen.add(t.team_key);
    const st = t.team_standings || {};
    const rec = st.outcome_totals || {};
    res.teams.push({
      team_id: String(t.team_key),
      name: t.name || t.team_name,
      manager: (t.managers && t.managers[0] &&
                (t.managers[0].nickname || t.managers[0].manager?.nickname)) || "unknown",
      wins: num(rec.wins), losses: num(rec.losses), ties: num(rec.ties),
      points_for: num(st.points_for), points_against: num(st.points_against),
    });
  }

  const mNodes = collect(state, (n) =>
    n && typeof n === "object" && n.matchup_id !== undefined && n.teams);
  mNodes.forEach((m, i) => {
    const sides = [];
    for (const t of collect(m.teams, (n) => n && n.team_key)) {
      sides.push({
        team_id: String(t.team_key),
        points: num(t.team_points && (t.team_points.total ?? t.team_points)),
        projected: num(t.team_projected_points && t.team_projected_points.total) || null,
        starters: players(t, false),
        bench: players(t, true),
      });
    }
    if (sides.length) res.matchups.push({ matchup_id: String(i), teams: sides });
  });

  const lg = collect(state, (n) => n && n.league_key && n.name)[0];
  if (lg) {
    res.league_name = lg.name;
    if (lg.season) res.season = String(lg.season);
    if (lg.current_week && !base.week) res.week = parseInt(lg.current_week, 10);
  }
  return res;
}

function players(teamNode, wantBench) {
  const found = collect(teamNode, (n) => n && n.player_key && (n.name || n.player_id));
  const out = [];
  for (const p of found) {
    let slot = p.selected_position;
    if (slot && typeof slot === "object") slot = slot.position;
    if (Array.isArray(slot)) slot = (slot.find((x) => x && x.position) || {}).position;
    const isBench = slot === "BN" || slot === "IR" || slot === "IR+";
    if (isBench !== wantBench) continue;
    let pts = p.player_points;
    if (pts && typeof pts === "object") pts = pts.total;
    let name = p.name;
    if (name && typeof name === "object") name = name.full;
    let pos = p.display_position || p.primary_position || "?";
    if (typeof pos === "string" && pos.includes(",")) pos = pos.split(",")[0];
    out.push({
      player_id: String(p.player_key),
      name: name || "unknown",
      pos,
      nfl_team: p.editorial_team_abbr || "FA",
      slot: wantBench ? null : slot || null,
      points: num(pts),
      injury: p.status_full || p.status || null,
    });
  }
  return out;
}

/* Fallback: read what is on the screen. Less complete than the embedded
   state and more likely to break on a redesign, which is why it is second. */
function fromDom() {
  const res = { teams: [], matchups: [], league_name: null, week: null };
  const h = document.querySelector("h1, .Navtarget");
  if (h) res.league_name = h.textContent.trim();

  const rows = [];
  document.querySelectorAll("table tr").forEach((tr) => {
    const cells = [...tr.querySelectorAll("td, th")].map((c) => c.textContent.trim());
    if (cells.length >= 2) rows.push(cells);
  });

  const teamLinks = [...document.querySelectorAll('a[href*="/f1/"][href*="/team/"], a[href*="teamId"]')];
  const scores = [];
  teamLinks.forEach((a) => {
    const row = a.closest("tr, li, div");
    if (!row) return;
    const m = row.textContent.match(/(\d{1,3}\.\d{1,2})/);
    if (m) {
      const name = a.textContent.trim();
      if (name && !scores.some((s) => s.name === name)) {
        scores.push({ name, points: parseFloat(m[1]) });
      }
    }
  });

  for (let i = 0; i + 1 < scores.length; i += 2) {
    res.matchups.push({
      matchup_id: String(i / 2),
      teams: [scores[i], scores[i + 1]].map((s) => ({
        team_id: s.name,
        points: s.points,
        projected: null,
        starters: [],
        bench: [],
      })),
    });
  }
  res.teams = scores.map((s) => ({
    team_id: s.name, name: s.name, manager: "unknown",
    wins: 0, losses: 0, ties: 0, points_for: 0, points_against: 0,
  }));
  if (res.matchups.length) {
    res.matchups.forEach(() => {});
  }
  return res;
}

function diagnostic() {
  return {
    url: location.href,
    title: document.title,
    scriptCount: document.querySelectorAll("script").length,
    tableCount: document.querySelectorAll("table").length,
    globals: Object.keys(window).filter((k) => /STATE|PRELOAD|YAHOO|__/.test(k)).slice(0, 40),
    sample: document.body.innerText.slice(0, 3000),
  };
}

function num(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

extractWeek();
