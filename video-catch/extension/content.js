// A playing/blob video can have no recognizable media-file request at all.
let last = 0;
function notifyVideo() {
  if (!document.querySelector("video") || Date.now() - last < 3000) return;
  last = Date.now();
  chrome.runtime.sendMessage({ type: "video-present" }).catch(() => {});
}
document.addEventListener("play", notifyVideo, true);
document.addEventListener("loadedmetadata", notifyVideo, true);
setInterval(notifyVideo, 5000);
notifyVideo();
