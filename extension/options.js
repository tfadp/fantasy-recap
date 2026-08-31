const $ = (id) => document.getElementById(id);

chrome.storage.sync.get(["repo", "token"]).then((c) => {
  $("repo").value = c.repo || "";
  $("token").value = c.token || "";
});

$("save").onclick = async () => {
  await chrome.storage.sync.set({
    repo: $("repo").value.trim(),
    token: $("token").value.trim(),
  });
  $("saved").textContent = "Saved.";
  setTimeout(() => ($("saved").textContent = ""), 2000);
};
