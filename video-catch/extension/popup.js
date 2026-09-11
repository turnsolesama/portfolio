const token = document.getElementById("token");
const name = document.getElementById("name");
const status = document.getElementById("status");
const button = document.getElementById("connect");
chrome.storage.local.get(["token", "name"]).then(v => { token.value = v.token || ""; name.value = v.name || ""; });
button.addEventListener("click", async () => {
  if (!token.value.trim()) { status.textContent = "请填写配对码"; return; }
  button.disabled = true;
  status.textContent = "正在连接本机程序…";
  try {
    await chrome.storage.local.set({ token: token.value.trim(), name: name.value.trim() });
    const result = await chrome.runtime.sendMessage({ type: "sync" });
    status.textContent = result.ok ? `已连接，发现 ${result.count} 个标签页。请在桌面勾选。` : result.error;
  } catch { status.textContent = "连接失败，请确认桌面程序正在运行"; }
  finally { button.disabled = false; }
});
