/* Paste into the Chrome console on your Yahoo league page, press Enter,
   then copy the whole output back.

   Read-only: it inspects what the page already loaded. It sends nothing,
   changes nothing, and clicks nothing. */
(() => {
  const out = { url: location.href, title: document.title };

  // 1. which embedded-state globals exist
  out.globals = Object.keys(window).filter(k =>
    /^(root|__|YAHOO|App|PREFETCH|Fantasy)/.test(k) ||
    /STATE|PRELOAD|INITIAL|CONTEXT/i.test(k)).slice(0, 40);

  // 2. Yahoo historically hangs everything off root.App.main
  const main = window.root && window.root.App && window.root.App.main;
  out.rootAppMain = main ? Object.keys(main).slice(0, 30) : null;
  if (main && main.context && main.context.dispatcher) {
    const st = main.context.dispatcher.stores || {};
    out.stores = Object.keys(st).slice(0, 40);
    // the store names are the real prize: they tell us where matchups live
    for (const k of Object.keys(st)) {
      if (/matchup|scoreboard|team|player|standing|league/i.test(k)) {
        const v = st[k];
        out["store:" + k] = v && typeof v === "object"
          ? Object.keys(v).slice(0, 12) : typeof v;
      }
    }
  }

  // 3. big JSON blobs in <script> tags, which is the fallback source
  out.jsonScripts = [];
  document.querySelectorAll("script").forEach((s, i) => {
    const t = s.textContent || "";
    if (t.length > 2000 && /matchup|teamPoints|"points"|roster/i.test(t)) {
      out.jsonScripts.push({
        i, bytes: t.length, type: s.type || "text/javascript",
        head: t.slice(0, 120).replace(/\s+/g, " ")
      });
    }
  });
  document.querySelectorAll('script[type="application/json"]').forEach((s, i) => {
    out.jsonScripts.push({ appJson: i, id: s.id || null, bytes: (s.textContent||"").length });
  });

  // 4. what the rendered page offers, as a floor
  out.dom = {
    tables: document.querySelectorAll("table").length,
    teamLinks: document.querySelectorAll('a[href*="/team/"], a[href*="teamId"]').length,
    weekSelector: !!document.querySelector('[name="week"], select[id*="week" i], a[href*="week="]'),
    matchupLinks: [...document.querySelectorAll('a[href*="matchup"]')]
      .slice(0, 8).map(a => a.getAttribute("href"))
  };

  const s = JSON.stringify(out, null, 1);
  console.log(s);
  copy && copy(s);            // puts it on your clipboard in Chrome
  return "Copied to clipboard. Paste it back to Claude.";
})();
