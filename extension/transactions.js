/*
 * Read the league's transaction log out of the live page.
 *
 * This one has to run on the transactions page itself. A background fetch
 * only ever sees server-rendered HTML and this page renders client side - the
 * same reason the standings page comes back with zero tables. The tab has
 * already run its JavaScript, so reading `document` gets what a fetch cannot.
 *
 * It returns the page's text rather than a parsed structure. The structure
 * lives in background.js, which also holds the week's rosters and so can
 * resolve a player name to the id the analysis keys on. Parsing here would
 * mean guessing at both halves.
 */
(() => {
  const txt = (e) => (e ? e.textContent || "" : "").replace(/\s+/g, " ").trim();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  return (async () => {
    // Lazy lists render only what has been scrolled past; some paginate.
    const size = () => document.querySelectorAll('a[href*="/players/"]').length;
    let before = -1;
    for (let i = 0; i < 15 && size() !== before; i++) {
      before = size();
      window.scrollTo(0, document.body.scrollHeight);
      const more = [...document.querySelectorAll("a, button")]
        .find((b) => /show more|load more|older/i.test(txt(b)) && b.offsetParent);
      if (more) more.click();
      await sleep(600);
    }
    window.scrollTo(0, 0);
    return {
      league_id: (location.pathname.match(/\/f1\/(\d+)/) || [])[1] || null,
      playerLinks: size(),
      bodyText: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 60000),
    };
  })();
})();
