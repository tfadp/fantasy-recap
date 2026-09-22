/*
 * One click: read the week, read the waivers, hand both to the Action.
 *
 * The button injects extract.js into the league page you have open, then
 * opens the transactions page in a background tab, reads its rendered DOM,
 * closes it again, and fires a GitHub repository_dispatch carrying the whole
 * week. That starts the same workflow the Tuesday cron runs, so a handed-in
 * week and a scheduled one go through identical analysis.
 *
 * The token is a fine-grained PAT scoped to the one repository, stored in this
 * browser's extension storage and nowhere else.
 */

const YAHOO = "https://football.fantasysports.yahoo.com";

chrome.runtime.onMessage.addListener((msg, _sender, respond) => {
  if (msg.type !== "run") return;
  run(msg).then(respond).catch((e) => respond({ ok: false, error: e.message }));
  return true; // async
});

async function run({ week, dispatch }) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/football\.fantasysports\.yahoo\.com\/f1\//.test(tab.url || "")) {
    throw new Error("Open your Yahoo league page first, then click this.");
  }
  const league = (tab.url.match(/\/f1\/(\d+)/) || [])[1];

  if (week) {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id }, world: "MAIN",
      func: (w) => { window.__RECAP_WEEK = w; }, args: [Number(week)],
    });
  }

  const [res] = await chrome.scripting.executeScript({
    target: { tabId: tab.id }, world: "MAIN", files: ["extract.js"],
  });
  const lw = res && res.result;
  if (!lw) throw new Error("Could not read the league page.");
  if (lw.error) throw new Error(lw.error);

  // waivers, from a throwaway tab on the transactions page
  try {
    lw.transactions = await waivers(league, lw);
  } catch (e) {
    lw.transactions = [];
    (lw._debug = lw._debug || {}).waiverError = e.message;
  }

  const summary = {
    week: lw.week,
    teams: lw.teams.length,
    matchups: lw.matchups.length,
    transactions: lw.transactions.length,
    reconciles: lw._check.every((c) => Math.abs(c.total - c.sumStarters) < 0.011),
    bench: lw._check.reduce((a, c) => a + c.bench, 0),
  };
  if (!dispatch) return { ok: true, summary, payload: lw };
  await send(lw);
  return { ok: true, summary, sent: true };
}

async function waivers(league, lw) {
  const tab = await chrome.tabs.create({
    url: `${YAHOO}/f1/${league}/transactions`, active: false,
  });
  try {
    await new Promise((resolve) => {
      const done = (id, info) => {
        if (id === tab.id && info.status === "complete") {
          chrome.tabs.onUpdated.removeListener(done);
          resolve();
        }
      };
      chrome.tabs.onUpdated.addListener(done);
      setTimeout(() => { chrome.tabs.onUpdated.removeListener(done); resolve(); }, 20000);
    });
    await new Promise((r) => setTimeout(r, 1500)); // let the client render settle
    const [out] = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, world: "MAIN", files: ["transactions.js"],
    });
    return parseTransactions((out && out.result && out.result.bodyText) || "", lw);
  } finally {
    try { await chrome.tabs.remove(tab.id); } catch (e) { /* already gone */ }
  }
}

/*
 * Turn the transaction log's text into the schema's transactions.
 *
 * Each record reads as a run of "<player> <Team> - <POS> <marker>" pairs, then
 * the team, then a timestamp. "Free Agent" and "$N Waiver" mark an add; the
 * "To ..." markers mark a drop, and must be tested first so "To Free Agent"
 * is not read as "Free Agent".
 */
function parseTransactions(body, lw) {
  if (!body) return [];
  let seg = body;
  const start = seg.indexOf("FAB Offers");
  if (start >= 0) seg = seg.slice(start + "FAB Offers".length);
  const end = seg.indexOf("Yahoo Sports - NBC");
  if (end >= 0) seg = seg.slice(0, end);

  const teams = {};
  lw.teams.forEach((t) => { teams[t.name] = t.team_id; });
  const pid = {};
  lw.matchups.forEach((m) => m.teams.forEach((s) =>
    [...s.starters, ...s.bench].forEach((p) => { pid[p.name] = p.player_id; })));

  const DATE = /([A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2} [ap]m)/g;
  const PLAYER = new RegExp(
    "([A-Z][A-Za-z'’.\\-]*(?:[ ][A-Z][A-Za-z'’.\\-]*)*?)\\s+" +
    "([A-Z][A-Za-z]{1,2})\\s*-\\s*(QB|RB|WR|TE|K|DEF)" +
    "((?:\\s+(?:IR-R|IR|Q|D|O|SUSP|PUP|NA))?)\\s*" +
    "(To Free Agent|To Waivers|Free Agent|\\$\\d+ Waiver)", "g");
  const MONTH = { Jan: 0, Feb: 1, Mar: 2, Apr: 3, May: 4, Jun: 5,
                  Jul: 6, Aug: 7, Sep: 8, Oct: 9, Nov: 10, Dec: 11 };

  const chunks = seg.split(DATE);
  const names = Object.keys(teams).sort((a, b) => b.length - a.length);
  const out = [];
  for (let i = 1; i < chunks.length; i += 2) {
    const text = chunks[i - 1], stamp = chunks[i];
    const team = names.find((n) => text.includes(n));
    if (!team) continue;
    const tid = teams[team];

    const d = stamp.match(/([A-Z][a-z]{2}) (\d{1,2}), (\d{1,2}):(\d{2}) ([ap])m/);
    let ts = 0;
    if (d) {
      let h = parseInt(d[3], 10);
      if (d[5] === "p" && h !== 12) h += 12;
      if (d[5] === "a" && h === 12) h = 0;
      ts = Math.floor(new Date(Number(lw.season), MONTH[d[1]], +d[2], h, +d[4]).getTime() / 1000);
    }

    const adds = [], drops = [];
    let bid = null, m;
    PLAYER.lastIndex = 0;
    while ((m = PLAYER.exec(text)) !== null) {
      const ent = { player: m[1].trim(), player_id: pid[m[1].trim()] || null,
                    pos: m[3], team_id: tid };
      if (m[5].startsWith("To ")) drops.push(ent);
      else {
        adds.push(ent);
        const b = m[5].match(/^\$(\d+)/);
        if (b) bid = parseInt(b[1], 10);
      }
    }
    if (!adds.length && !drops.length) continue;
    out.push({
      type: bid ? "waiver" : "free_agent",
      team_ids: [tid], adds, drops, faab_bid: bid,
      date: d ? `${String(MONTH[d[1]] + 1).padStart(2, "0")}/${String(d[2]).padStart(2, "0")}` : null,
      ts,
    });
  }
  out.sort((a, b) => a.ts - b.ts);
  return out;
}

async function send(payload) {
  const cfg = await chrome.storage.sync.get(["repo", "token"]);
  if (!cfg.repo || !cfg.token) {
    throw new Error("Set your repository and token in Settings first.");
  }
  const slim = { ...payload };
  delete slim._debug;
  delete slim._check;

  const body = JSON.stringify({
    event_type: "yahoo-week",
    client_payload: { league_week: slim },
  });
  if (body.length > 60000) {
    throw new Error(`Payload is ${Math.round(body.length / 1024)}KB, over GitHub's 64KB limit.`);
  }
  const r = await fetch(`https://api.github.com/repos/${cfg.repo}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${cfg.token}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
    },
    body,
  });
  if (r.status !== 204) {
    throw new Error(`GitHub returned ${r.status}: ${(await r.text()).slice(0, 200)}`);
  }
}
