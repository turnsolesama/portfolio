function classify(url, type = "") {
  let path;
  try { path = new URL(url).pathname.toLowerCase(); } catch { return null; }
  const mime = type.toLowerCase().split(";")[0].trim();
  if (/\.m3u8$/.test(path) || ["application/vnd.apple.mpegurl", "application/x-mpegurl", "audio/mpegurl", "audio/x-mpegurl"].includes(mime)) return "hls";
  if (/\.mpd$/.test(path) || mime === "application/dash+xml") return "dash";
  if (/\.(ts|m4s|cmfv|cmfa|m4a|aac)$/.test(path) || ["video/mp2t", "audio/mp4"].includes(mime)) return null;
  if (/\.(mp4|webm|mov|mkv|flv|avi|m4v)$/.test(path) || mime.startsWith("video/")) return "file";
  return null;
}
if (typeof module !== "undefined") module.exports = { classify };
