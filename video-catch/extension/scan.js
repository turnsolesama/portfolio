// Executed in the selected page only. Returns a narrow, noncredential media snapshot.
function scanPage() {
  const result = { url: location.href, hasVideo: !!document.querySelector("video"), formats: [] };
  if (!["www.bilibili.com", "bilibili.com", "m.bilibili.com"].includes(location.hostname)) return result;
  const state = window.__INITIAL_STATE__ || {};
  const video = state.videoData || {};
  const bvid = location.pathname.match(/\/video\/(BV[^/]+)/)?.[1];
  if (bvid && video.bvid && video.bvid !== bvid) return result;
  const part = Number(new URL(location.href).searchParams.get("p") || 1);
  if (video.pages?.[part - 1]?.cid && state.cid && video.pages[part - 1].cid !== state.cid) return result;
  const observed = window.__videoCatchPlayback;
  const expectedCid = video.pages?.[part - 1]?.cid || state.cid;
  const pageKey = href => {
    const u = new URL(href);
    return u.pathname.replace(/\/$/, "") + "?p=" + (u.searchParams.get("p") || "1");
  };
  const observedMatches = observed && pageKey(observed.page) === pageKey(location.href) &&
    (!observed.cid || !expectedCid || String(observed.cid) === String(expectedCid)) &&
    (!observed.bvid || !bvid || observed.bvid === bvid);
  const play = observedMatches ? observed.play : window.__playinfo__?.data;
  if (!play || play.is_drm || play.drm_tech_type || play.dash?.is_drm) return result;
  const add = (track, role) => {
    if (!track || track.drm || track.has_drm) return;
    const url = track.baseUrl || track.base_url || track.url;
    if (typeof url !== "string" || !/^https?:\/\//.test(url)) return;
    result.formats.push({url, role, codec: track.codecs, width: track.width,
      height: track.height, bandwidth: track.bandwidth});
  };
  for (const track of play.dash?.video || []) add(track, "video");
  for (const track of play.dash?.audio || []) add(track, "audio");
  // Single-file progressive playback; multiple durl pieces still use the site extractor.
  if (!result.formats.length && play.durl?.length === 1) add(play.durl[0], "combined");
  result.formats = result.formats.slice(0, 100);
  return result;
}
if (typeof module !== "undefined") module.exports = { scanPage };
