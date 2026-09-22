const el = (id) => document.getElementById(id);
const say = (msg, cls) => { el("status").className = cls || ""; el("status").textContent = msg; };

async function go(dispatch) {
  el("go").disabled = true;
  el("test").disabled = true;
  say("Reading the league…\nThis takes about a minute: every matchup page, then the waiver log.", "warn");
  try {
    const r = await chrome.runtime.sendMessage({
      type: "run",
      week: el("week").value || null,
      dispatch,
    });
    if (!r || !r.ok) throw new Error((r && r.error) || "unknown error");
    const s = r.summary;
    const lines = [
      `Week ${s.week}: ${s.teams} teams, ${s.matchups} matchups`,
      `${s.bench} bench players, ${s.transactions} transactions`,
      s.reconciles
        ? "Every total matches the sum of its starters."
        : "WARNING: a total does not match its starters. Not sent as trustworthy.",
    ];
    if (r.sendError) lines.push("Read fine, but sending failed:\n" + r.sendError);
    else lines.push(r.sent
      ? "Sent. The recap will be in your email shortly."
      : "Read only - nothing was sent.");
    say(lines.join("\n"), r.sendError || !s.reconciles ? "err" : "ok");
  } catch (e) {
    say(e.message, "err");
  } finally {
    el("go").disabled = false;
    el("test").disabled = false;
  }
}

el("go").onclick = () => go(true);
el("test").onclick = () => go(false);

el("opts").onclick = (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); };
