importScripts("media.js", "scan.js");
const API = "http://127.0.0.1:18796";
const requestHeaders = new Map();
const recent = new Map();
let syncing = null;
const lastScan = new Map();

async function scanTab(tabId) {
  if (Date.now() - (lastScan.get(tabId) || 0) < 2000) return;
  lastScan.set(tabId, Date.now());
  try {
    const tab = await chrome.tabs.get(tabId);
    if (tab.incognito) return;
    const bili = /^https?:\/\/(www\.|m\.)?bilibili\.com\/(video|bangumi\/play)\//.test(tab.url || "");
    const results = await chrome.scripting.executeScript({ target: {tabId}, world: bili ? "MAIN" : "ISOLATED", func: scanPage });
    const snapshot = results[0]?.result;
    if (snapshot && (snapshot.hasVideo || bili)) {
      await post("/page", { tabId, url: snapshot.url, formats: bili ? snapshot.formats : [], headers: {"User-Agent": navigator.userAgent} });
    }
  } catch { /* A navigated/closed/restricted tab is retried on the next scan. */ }
}

async function settings() {
  const value = await chrome.storage.local.get(["token", "client", "name"]);
  if (!value.client) {
    value.client = crypto.randomUUID();
    await chrome.storage.local.set({ client: value.client });
  }
  return value;
}
async function post(path, body) {
  const config = await settings();
  if (!config.token) throw new Error("请先粘贴桌面程序中的配对码");
  const result = await fetch(API + path, {
    method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${config.token}` },
    body: JSON.stringify({ ...body, client: config.client }), signal: AbortSignal.timeout(3500)
  });
  if (result.status === 401) throw new Error("配对码已失效，请从桌面程序重新复制");
  if (!result.ok) throw new Error(`本机程序返回 ${result.status}`);
  return result.json();
}
async function sync() {
  if (syncing) return syncing;
  syncing = (async () => {
    const config = await settings();
    const tabs = (await chrome.tabs.query({})).filter(t => /^https?:\/\//.test(t.url || "") && !t.incognito)
      .map(t => ({ id: t.id, title: t.title, url: t.url }));
    const result = await post("/sync", { name: config.name || (/Edg\//.test(navigator.userAgent) ? "Edge" : "Chrome / Chromium"), tabs });
    if (result.protocol !== 3) throw new Error("桌面程序版本不匹配，请打开 0.3.0 新版拾影再连接");
    await Promise.allSettled((result.watching || []).map(scanTab));
    await chrome.action.setBadgeText({ text: "ON" });
    await chrome.action.setBadgeBackgroundColor({ color: "#168b76" });
    return { ok: true, count: tabs.length };
  })().catch(async error => {
    await chrome.action.setBadgeText({ text: "!" });
    throw error;
  }).finally(() => { syncing = null; });
  return syncing;
}
function quietSync() { sync().catch(() => {}); }
chrome.runtime.onInstalled.addListener(() => { chrome.alarms.create("sync", { periodInMinutes: .5 }); quietSync(); });
chrome.runtime.onStartup.addListener(() => { chrome.alarms.create("sync", { periodInMinutes: .5 }); quietSync(); });
chrome.alarms.onAlarm.addListener(quietSync);
chrome.tabs.onCreated.addListener(quietSync);
chrome.tabs.onRemoved.addListener(id => { lastScan.delete(id); quietSync(); });
chrome.tabs.onUpdated.addListener((_id, change) => { if (change.url || change.status === "complete") quietSync(); });
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message.type === "video-present" && sender.tab && !sender.tab.incognito) {
    quietSync();
    return;
  }
  if (message.type === "sync") {
    recent.clear();
    lastScan.clear();
    sync().then(reply, error => reply({ ok: false, error: error.message === "Failed to fetch" ? "未连接：请先打开桌面程序" : error.message }));
    return true;
  }
});
const filter = { urls: ["http://*/*", "https://*/*"] };
chrome.webRequest.onBeforeSendHeaders.addListener(d => {
  if (d.tabId < 0 || d.incognito || d.url.startsWith(API + "/")) return;
  const headers = {};
  for (const h of d.requestHeaders || []) {
    if (["referer", "user-agent", "origin"].includes(h.name.toLowerCase())) headers[h.name] = h.value;
  }
  requestHeaders.set(d.requestId, headers);
  if (requestHeaders.size > 2000) requestHeaders.delete(requestHeaders.keys().next().value);
}, filter, ["requestHeaders", "extraHeaders"]);
chrome.webRequest.onHeadersReceived.addListener(d => {
  if (d.tabId < 0 || d.incognito || d.statusCode < 200 || d.statusCode >= 300) return;
  const headers = Object.fromEntries((d.responseHeaders || []).map(h => [h.name.toLowerCase(), h.value || ""]));
  if (/\.(m4s|cmfv|cmfa)(\?|$)/i.test(d.url) || (headers["content-type"] || "").startsWith("audio/mp4")) {
    quietSync();  // Discover the parent page and its paired tracks, not an orphan fragment.
    return;
  }
  if (!classify(d.url, headers["content-type"])) return;
  const key = `${d.tabId}:${d.url}`;
  if (Date.now() - (recent.get(key) || 0) < 2500) return;
  recent.set(key, Date.now());
  if (recent.size > 1000) recent.delete(recent.keys().next().value);
  const captured = requestHeaders.get(d.requestId) || {};
  // Capture ordinary context headers only; cookies and authorization are not collected.
  sync().then(() => post("/media", { tabId: d.tabId, url: d.url, contentType: headers["content-type"] || "",
    size: headers["content-range"]?.split("/")[1] || headers["content-length"] || "", headers: captured }))
    .catch(() => {});
}, filter, ["responseHeaders"]);
for (const event of [chrome.webRequest.onCompleted, chrome.webRequest.onErrorOccurred]) {
  event.addListener(d => requestHeaders.delete(d.requestId), filter);
}
