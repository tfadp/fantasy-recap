/* Probe 2. Run on your Yahoo LEAGUE page (the same one as before).

   This one tests the actual plan: find every matchup link for the week, then
   fetch those pages in the background using your existing session, and report
   what came back. Read-only - it requests the same pages your browser would
   if you clicked them, and changes nothing. */
(async () => {
  const out = { url: location.href, league: document.title.split("|")[0].trim() };

  // 1. every matchup link on this page, deduped
  const links = [...new Set([...document.querySelectorAll('a[href*="matchup?week="]')]
    .map(a => a.getAttribute("href")))];
  out.matchupLinks = links;
  out.matchupCount = links.length;

  // what weeks are selectable, so we know how to ask for a finished one later
  out.weekLinks = [...new Set([...document.querySelectorAll('a[href*="week="]')]
    .map(a => (a.getAttribute("href").match(/week=(\d+)/) || [])[1]))]
    .filter(Boolean).sort((a, b) => a - b);

  if (!links.length) { out.error = "no matchup links on this page"; console.log(JSON.stringify(out,null,1)); return; }

  // 2. fetch ONE matchup page with the session and dissect it
  const probe = async (href) => {
    const r = await fetch(new URL(href, location.origin), { credentials: "include" });
    const html = await r.text();
    const doc = new DOMParser().parseFromString(html, "text/html");
    const tables = [...doc.querySelectorAll("table")];
    return {
      href, status: r.status, bytes: html.length,
      title: (doc.querySelector("title") || {}).textContent,
      tables: tables.length,
      // the real question: are player rows in there, and how are they marked
      playerLinks: doc.querySelectorAll('a[href*="/nfl/players/"]').length,
      playerNameNodes: doc.querySelectorAll('.ysf-player-name, [class*="player"]').length,
      tableShapes: tables.slice(0, 6).map(t => ({
        rows: t.rows.length,
        cls: (t.className || "").slice(0, 40),
        headers: [...t.querySelectorAll("th")].slice(0, 10).map(h => h.textContent.trim()).filter(Boolean)
      })),
      // any numbers that look like fantasy points
      pointsish: (html.match(/>\s*\d{1,3}\.\d{2}\s*</g) || []).length
    };
  };

  out.sample = await probe(links[0]);
  out.sampleTwo = links[1] ? await probe(links[1]) : null;

  const s = JSON.stringify(out, null, 1);
  console.log(s);
  copy && copy(s);
  return "Copied. Paste back to Claude.";
})();
