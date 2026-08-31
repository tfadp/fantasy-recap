let cached = null;

const el = (id) => document.getElementById(id);
const say = (msg, cls) => {
  const s = el("status");
  s.className = cls;
  s.textContent = msg;
};

async function grab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/fantasysports\.yahoo\.com/.test(tab.url || "")) {
    throw new Error("Open your Yahoo league matchup page first, then click this.");
  }
  const [out] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    world: "MAIN",
    files: ["extract.js"],
  });
  const data = out && out.result;
  if (!data) throw new Error("Could not read the page.");
  return data;
}

function summarize(d) {
  const games = (d.matchups || []).length;
  const withPlayers = (d.matchups || []).filter(
    (m) => m.teams.some((t) => (t.starters || []).length)).length;
  return `week ${d.week ?? "?"}, ${games} matchup(s), ` +
         `${withPlayers} with full rosters (${d._method})`;
}

el("send").onclick = async () => {
  try {
    say("Reading the page…", "warn");
    cached = await grab();
    if (cached._method === "failed") {
      say("Could not find matchup data on this page. Use Download JSON and " +
          "send me the file; the diagnostic in it says what the page looks " +
          "like so the selectors can be fixed.", "err");
      return;
    }
    say("Read " + summarize(cached) + "\nSending…", "warn");
    const r = await chrome.runtime.sendMessage({ type: "send", payload: cached });
    if (r && r.ok) {
      say("Sent. " + summarize(cached) +
          "\nThe recap will land in your email shortly.", "ok");
    } else {
      say("Read the page fine, but sending failed:\n" +
          (r && r.error ? r.error : "unknown") +
          "\nUse Copy JSON as a fallback.", "err");
    }
  } catch (e) {
    say(e.message, "err");
  }
};

el("copy").onclick = async () => {
  try {
    cached = cached || await grab();
    await navigator.clipboard.writeText(JSON.stringify(cached, null, 2));
    say("Copied. " + summarize(cached), "ok");
  } catch (e) { say(e.message, "err"); }
};

el("download").onclick = async () => {
  try {
    cached = cached || await grab();
    const blob = new Blob([JSON.stringify(cached, null, 2)],
                          { type: "application/json" });
    await chrome.downloads.download({
      url: URL.createObjectURL(blob),
      filename: `yahoo-week-${cached.week || "unknown"}.json`,
    }).catch(async () => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `yahoo-week-${cached.week || "unknown"}.json`;
      a.click();
    });
    say("Downloaded. " + summarize(cached), "ok");
  } catch (e) { say(e.message, "err"); }
};

el("opts").onclick = (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
};
