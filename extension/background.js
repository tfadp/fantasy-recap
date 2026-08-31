/*
 * Fires a GitHub repository_dispatch carrying the week you just read.
 * That starts the same Action that runs on Tuesdays, so Yahoo and Sleeper
 * go through identical analysis and come out as one pair of write-ups.
 *
 * The token is stored in Chrome's extension storage on your machine only.
 * Use a fine-grained personal access token scoped to this one repository
 * with Contents: read and write. Nothing else needs access.
 */

chrome.runtime.onMessage.addListener((msg, _sender, respond) => {
  if (msg.type !== "send") return;
  send(msg.payload).then(respond).catch((e) => respond({ ok: false, error: e.message }));
  return true; // async
});

async function send(payload) {
  const cfg = await chrome.storage.sync.get(["repo", "token"]);
  if (!cfg.repo || !cfg.token) {
    return { ok: false, error: "Set your repository and token in Settings first." };
  }

  // repository_dispatch caps client_payload at 64KB, so the roster detail is
  // trimmed to what the analysis actually consumes before sending.
  const slim = {
    ...payload,
    matchups: (payload.matchups || []).map((m) => ({
      ...m,
      teams: m.teams.map((t) => ({
        ...t,
        starters: (t.starters || []).map(trim),
        bench: (t.bench || []).map(trim),
      })),
    })),
  };
  delete slim._diagnostic;

  const body = JSON.stringify({
    event_type: "yahoo-week",
    client_payload: { league_week: slim },
  });
  if (body.length > 60000) {
    return { ok: false, error: `Payload is ${Math.round(body.length / 1024)}KB, ` +
                              `over GitHub's 64KB limit. Use Download JSON instead.` };
  }

  const r = await fetch(`https://api.github.com/repos/${cfg.repo}/dispatches`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${cfg.token}`,
      "Accept": "application/vnd.github+json",
      "Content-Type": "application/json",
    },
    body,
  });
  if (r.status === 204) return { ok: true };
  const text = await r.text();
  return { ok: false, error: `GitHub returned ${r.status}: ${text.slice(0, 200)}` };
}

function trim(p) {
  return {
    player_id: p.player_id, name: p.name, pos: p.pos,
    nfl_team: p.nfl_team, slot: p.slot, points: p.points, injury: p.injury,
  };
}
