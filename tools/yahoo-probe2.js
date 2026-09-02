/* Run on your Yahoo LEAGUE page.

   Puts the result on your clipboard AND drops it in a box on the page with the
   text already selected, so if the clipboard gets clobbered you can just press
   Cmd+C. Reload the page to clear the box.

   Read-only: it requests the same matchup pages your browser would if you
   clicked them, and changes nothing. */
(async () => {
  console.clear();
  const out = { url: location.href, league: document.title.split("|")[0].trim() };
  try {
    const links = [...new Set([...document.querySelectorAll('a[href*="matchup?week="]')]
      .map(a => a.getAttribute("href")))];
    out.matchupLinks = links;
    out.matchupCount = links.length;
    out.weekLinks = [...new Set([...document.querySelectorAll('a[href*="week="]')]
      .map(a => (a.getAttribute("href").match(/week=(\d+)/) || [])[1]))]
      .filter(Boolean).sort((a, b) => a - b);

    const probe = async (href) => {
      const r = await fetch(new URL(href, location.origin), { credentials: "include" });
      const html = await r.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const tables = [...doc.querySelectorAll("table")];
      return {
        href, status: r.status, bytes: html.length,
        title: (doc.querySelector("title") || {}).textContent,
        loginWall: /Sign in to Yahoo/i.test(html),
        tables: tables.length,
        playerLinks: doc.querySelectorAll('a[href*="/nfl/players/"]').length,
        playerNameNodes: doc.querySelectorAll('.ysf-player-name, [class*="player"]').length,
        tableShapes: tables.slice(0, 8).map(t => ({
          rows: t.rows.length,
          cls: (t.className || "").slice(0, 50),
          headers: [...t.querySelectorAll("th")].slice(0, 12)
            .map(h => h.textContent.trim()).filter(Boolean)
        })),
        pointsish: (html.match(/>\s*\d{1,3}\.\d{2}\s*</g) || []).length
      };
    };

    if (links.length) {
      out.sample = await probe(links[0]);
      if (links[1]) out.sampleTwo = await probe(links[1]);
    } else {
      out.error = "no matchup links found on this page";
    }
  } catch (e) {
    out.threw = String((e && e.stack) || e);
  }

  const s = JSON.stringify(out, null, 1);
  try { copy(s); } catch (e) { /* console-only helper, fine if absent */ }

  const box = document.createElement("textarea");
  box.value = s;
  box.setAttribute("style",
    "position:fixed;z-index:2147483647;top:20px;left:20px;right:20px;height:60vh;" +
    "font:12px/1.4 monospace;padding:12px;border:3px solid #0a0;background:#fff;color:#000");
  document.body.appendChild(box);
  box.focus();
  box.select();
  console.log("%cDone. It is on your clipboard, and in the green box on the page " +
              "(already selected - press Cmd+C). Reload to clear.",
              "font-size:15px;color:green;font-weight:bold");
})();
