/* Run on your Yahoo LEAGUE page. Checks whether the TEAM page carries bench
   players and per-week points, which decides the whole extractor design.
   Read-only. Clipboard + green box. */
(async () => {
  console.clear();
  const out = { url: location.href };
  const squash = (s, n) => (s || "").replace(/\s+/g, " ").slice(0, n);
  const get = async (p) => {
    const r = await fetch(new URL(p, location.origin), { credentials: "include" });
    const h = await r.text();
    return { status: r.status, html: h,
             doc: new DOMParser().parseFromString(h, "text/html") };
  };
  try {
    // team ids come out of the matchup links
    const ids = [...new Set([...document.querySelectorAll('a[href*="matchup?week="]')]
      .flatMap(a => [...a.getAttribute("href").matchAll(/mid\d=(\d+)/g)].map(m => m[1])))];
    out.teamIds = ids;

    for (const path of [`/f1/78540/${ids[0]}`, `/f1/78540/${ids[0]}?week=1`]) {
      const { status, doc } = await get(path);
      const tables = [...doc.querySelectorAll("table")];
      out[path] = {
        status,
        title: squash((doc.querySelector("title") || {}).textContent, 60),
        tables: tables.length,
        // does any table mention a bench slot
        benchWords: ["BN", "Bench", "IR"].filter(w => new RegExp(`>\\s*${w}\\s*<`).test(doc.body.innerHTML)),
        posLabels: [...new Set([...doc.querySelectorAll("span.pos-label[data-pos]")]
          .map(s => s.getAttribute("data-pos")))],
        tableShapes: tables.slice(0, 8).map(t => ({
          rows: t.rows.length, cls: squash(t.className, 45),
          headers: [...t.querySelectorAll("th")].slice(0, 12).map(h => squash(h.textContent, 14)).filter(Boolean)
        })),
        teamNameCandidates: [...doc.querySelectorAll("h1, .Navtarget, [class*='teamName' i]")]
          .slice(0, 6).map(e => squash(e.textContent, 40))
      };
    }

    const { status, doc } = await get("/f1/78540/standings");
    out.standings = { status,
      tables: [...doc.querySelectorAll("table")].slice(0, 4).map(t => ({
        rows: t.rows.length, cls: squash(t.className, 45),
        headers: [...t.querySelectorAll("th")].slice(0, 12).map(h => squash(h.textContent, 14)).filter(Boolean),
        firstRow: [...(t.rows[1] ? t.rows[1].cells : [])].map(c => squash(c.textContent, 22))
      })) };
  } catch (e) { out.threw = String((e && e.stack) || e); }

  const s = JSON.stringify(out, null, 1);
  try { copy(s); } catch (e) {}
  const box = document.createElement("textarea");
  box.value = s;
  box.setAttribute("style", "position:fixed;z-index:2147483647;top:20px;left:20px;right:20px;" +
    "height:60vh;font:12px/1.4 monospace;padding:12px;border:3px solid #0a0;background:#fff;color:#000");
  document.body.appendChild(box); box.focus(); box.select();
  console.log("%cDone - clipboard + green box.", "font-size:15px;color:green;font-weight:bold");
})();
