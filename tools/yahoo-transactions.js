/* The waiver half of the week.
 *
 * Run it ON the transactions page, with the page open in front of you:
 *   https://football.fantasysports.yahoo.com/f1/<league>/transactions
 *
 * A background fetch only sees server-rendered HTML, and this page renders
 * client side — the same reason probe 4 found the standings page empty. In
 * the tab you are looking at it has already rendered, so reading `document`
 * directly gets what a fetch cannot.
 *
 * It assumes nothing about the markup. v1 looked for <table> rows and found
 * zero, because there are none. This walks out from the player links instead,
 * which have to exist whatever the page is built out of, and carries the raw
 * text of the whole log so the rows can be parsed on the other end even if
 * the structure defeats it here.
 *
 * Read-only. Handoff is the green box: click it and press Cmd+C.
 */
(async () => {
  console.clear();
  const LG = (location.pathname.match(/\/f1\/(\d+)/) || [])[1];
  if (!LG) { alert("Open a page inside your Yahoo league first."); return; }
  if (!/transaction/i.test(location.pathname)) {
    alert("Go to the Transactions page first:\n\n" +
          location.origin + "/f1/" + LG + "/transactions");
    return;
  }

  const txt = (e) => (e ? e.textContent || "" : "").replace(/\s+/g, " ").trim();
  const squash = (s, n) => String(s || "").replace(/\s+/g, " ").slice(0, n);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* Lazy lists only render what has been scrolled past, and some of these
     pages paginate with a "Show more" control instead. Do both, and stop as
     soon as the page stops growing. */
  const size = () => document.querySelectorAll('a[href*="/players/"]').length;
  let before = -1;
  for (let i = 0; i < 15 && size() !== before; i++) {
    before = size();
    window.scrollTo(0, document.body.scrollHeight);
    const more = [...document.querySelectorAll('a, button')]
      .find((b) => /show more|load more|next|older/i.test(txt(b)) && b.offsetParent);
    if (more) more.click();
    await sleep(700);
  }
  window.scrollTo(0, 0);

  const KEY = /\b(added|add|claimed|dropped|drop|released|waived|traded|trade)\b/i;

  /* Climb from each player link until the ancestor carries a transaction verb,
     then treat that ancestor as the row. Cap the climb so a match does not
     escalate to <body> and swallow the page. */
  const rows = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href*="/players/"]')) {
    let node = a, hit = null;
    for (let up = 0; up < 7 && node && node !== document.body; up++) {
      node = node.parentElement;
      if (!node) break;
      const t = txt(node);
      if (t.length > 1200) break;
      if (KEY.test(t)) { hit = node; break; }
    }
    if (!hit || seen.has(hit)) continue;
    seen.add(hit);

    const whole = txt(hit);
    const players = [...hit.querySelectorAll('a[href*="/players/"]')].map((p) => ({
      name: txt(p),
      player_id: ((p.getAttribute("href") || "").match(/\/players\/(\d+)/) || [])[1] || null,
    }));
    const teams = [...hit.querySelectorAll(`a[href*="/f1/${LG}/"]`)]
      .map((t) => ({ name: txt(t), href: t.getAttribute("href") }))
      .filter((t) => /\/f1\/\d+\/\d+(\?|#|$)/.test(t.href))
      .map((t) => ({ name: t.name, team_id: (t.href.match(/\/f1\/\d+\/(\d+)/) || [])[1] }));
    const faab = whole.match(/\$\s*(\d+)/);
    const date = whole.match(/\b([A-Z][a-z]{2}\s+\d{1,2}(?:,\s*\d{2,4})?)\b/)
              || whole.match(/\b(\d{1,2}\/\d{1,2}(?:\/\d{2,4})?)\b/);

    rows.push({
      date: date ? date[1] : null,
      faab_bid: faab ? parseInt(faab[1], 10) : null,
      players, teams,
      raw: squash(whole, 500),
    });
  }

  const out = {
    source: "yahoo-transactions",
    league_id: LG,
    url: location.href,
    pulled_at: new Date().toISOString(),
    row_count: rows.length,
    transactions: rows,
    /* Always included, not only on failure. The structured rows above are a
       best guess at a page I have never seen; this is the ground truth the
       parse can be rebuilt from without making you run it again. */
    diagnostic: {
      playerLinks: document.querySelectorAll('a[href*="/players/"]').length,
      tables: document.querySelectorAll("table").length,
      listItems: document.querySelectorAll("li").length,
      bodyText: squash(document.body.innerText, 60000),
    },
  };

  const s = JSON.stringify(out);
  window.__yahooTx = s;
  try { copy(s); } catch (e) {}

  document.querySelectorAll("[data-yahoo-tx-box]").forEach((n) => n.remove());
  const box = document.createElement("textarea");
  box.setAttribute("data-yahoo-tx-box", "1");
  box.value = s;
  box.setAttribute("style",
    "position:fixed;z-index:2147483647;top:20px;left:20px;right:20px;height:55vh;" +
    "font:12px/1.4 monospace;padding:12px;border:4px solid #0a0;background:#fff;color:#000");
  document.body.appendChild(box); box.focus(); box.select();

  console.log("%crows " + rows.length + " · player links " + out.diagnostic.playerLinks +
              " · text " + Math.round(out.diagnostic.bodyText.length / 1024) + "KB" +
              "\\nGreen box is selected — press Cmd+C. (or type: copy(__yahooTx) )",
              "font-size:15px;color:#0a0;font-weight:bold");
})();
