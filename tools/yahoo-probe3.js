/* Run on your Yahoo LEAGUE page. Dumps the real markup of one matchup page's
   roster table, so the parser can be written against what is actually there
   instead of guessed at.

   Read-only. Result goes to your clipboard and to a green box on the page. */
(async () => {
  console.clear();
  const out = { url: location.href };
  const squash = (s, n) => s.replace(/\s+/g, " ").slice(0, n);
  try {
    const href = [...document.querySelectorAll('a[href*="matchup?week="]')]
      .map(a => a.getAttribute("href"))[0];
    out.href = href;
    const html = await (await fetch(new URL(href, location.origin),
                                    { credentials: "include" })).text();
    const doc = new DOMParser().parseFromString(html, "text/html");

    // the mirrored two-team roster table, by its header signature
    const tables = [...doc.querySelectorAll("table")];
    const roster = tables.filter(t =>
      /Fan Pts/.test(t.textContent) && /Player/.test(t.textContent));
    out.rosterTableCount = roster.length;

    out.tables = roster.slice(0, 2).map(t => ({
      cls: t.className,
      rows: t.rows.length,
      // the header row, cell by cell, with classes
      headCells: [...(t.rows[0] ? t.rows[0].cells : [])].map(c => ({
        txt: squash(c.textContent, 24), cls: squash(c.className, 40),
        span: c.colSpan
      })),
      // two body rows in full, which is where the player, slot and points live
      bodyRows: [...t.rows].slice(1, 3).map(r => ({
        cls: squash(r.className, 40),
        cells: [...r.cells].map(c => ({
          txt: squash(c.textContent, 40),
          cls: squash(c.className, 50),
          links: [...c.querySelectorAll("a")].slice(0, 2)
            .map(a => squash(a.getAttribute("href") || "", 60)),
          data: Object.keys(c.dataset || {}).slice(0, 5)
        }))
      })),
      rawFirstBodyRow: squash((t.rows[1] || {}).outerHTML || "", 2500)
    }));

    // where do team names and totals live
    out.teamNameGuesses = [...doc.querySelectorAll(
      '[class*="team-name" i], [class*="teamName" i], .Fz-lg, .Navtarget')]
      .slice(0, 8).map(e => squash(e.textContent, 40));
    out.totalsGuesses = [...doc.querySelectorAll('[class*="total" i], [class*="score" i]')]
      .slice(0, 10).map(e => ({ cls: squash(e.className, 40), txt: squash(e.textContent, 24) }));
  } catch (e) {
    out.threw = String((e && e.stack) || e);
  }

  const s = JSON.stringify(out, null, 1);
  try { copy(s); } catch (e) {}
  const box = document.createElement("textarea");
  box.value = s;
  box.setAttribute("style",
    "position:fixed;z-index:2147483647;top:20px;left:20px;right:20px;height:60vh;" +
    "font:12px/1.4 monospace;padding:12px;border:3px solid #0a0;background:#fff;color:#000");
  document.body.appendChild(box);
  box.focus(); box.select();
  console.log("%cDone - clipboard + green box. Reload to clear.",
              "font-size:15px;color:green;font-weight:bold");
})();
