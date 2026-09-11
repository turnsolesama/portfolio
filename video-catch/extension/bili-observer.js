// Observe the player's own playurl replies. Do not issue API requests or read credentials.
(() => {
  if (window.__videoCatchObserverInstalled) return;
  window.__videoCatchObserverInstalled = true;
  function context(value) {
    try {
      const url = new URL(typeof value === "string" ? value : value.url, location.href);
      if (url.hostname !== "api.bilibili.com" || !/^\/(x\/player\/(wbi\/)?playurl|pgc\/player\/web\/playurl)$/.test(url.pathname)) return null;
      return { page: location.href, cid: url.searchParams.get("cid"), bvid: url.searchParams.get("bvid") };
    } catch { return null; }
  }
  function keep(ctx, response) {
    if (!ctx || !response || response.code !== 0) return;
    const data = response.data || response.result?.video_info || response.result;
    if (!data || data.is_drm || data.drm_tech_type) return;
    // Keep only media fields, never the complete API response or request headers.
    const track = t => ({baseUrl: t.baseUrl || t.base_url || t.url, codecs: t.codecs,
      width: t.width, height: t.height, bandwidth: t.bandwidth, drm: t.drm, has_drm: t.has_drm});
    const tracks = values => Array.isArray(values) ? values.filter(t => t && typeof t === "object").slice(0, 80).map(track) : [];
    window.__videoCatchPlayback = { ...ctx, play: { dash: {
      video: tracks(data.dash?.video), audio: tracks(data.dash?.audio), is_drm: data.dash?.is_drm
    }, durl: tracks(data.durl) } };
  }
  // The current player clears __playinfo__ after consuming the server-rendered data.
  const descriptor = Object.getOwnPropertyDescriptor(window, "__playinfo__");
  if (!descriptor || (descriptor.configurable && descriptor.writable && !descriptor.get && !descriptor.set)) {
    let value = descriptor?.value;
    const embedded = data => { try { keep({page: location.href, bvid: location.pathname.match(/\/video\/(BV[^/]+)/)?.[1]}, data); } catch {} };
    embedded(value);
    Object.defineProperty(window, "__playinfo__", { configurable: true, enumerable: true,
      get() { return value; }, set(next) { value = next; embedded(next); } });
  }
  const originalFetch = window.fetch;
  window.fetch = function (...args) {
    const ctx = context(args[0]);
    const promise = originalFetch.apply(this, args);
    if (ctx) promise.then(response => {
      if (Number(response.headers.get("content-length") || 0) < 1000000) response.clone().json().then(data => keep(ctx, data)).catch(() => {});
    }).catch(() => {});
    return promise;
  };
  const open = XMLHttpRequest.prototype.open;
  const listeners = new WeakMap();
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    const previous = listeners.get(this);
    if (previous) this.removeEventListener("load", previous);
    listeners.delete(this);
    const ctx = context(url);
    if (ctx) {
      const listener = () => {
      try {
        const value = this.responseType === "json" ? this.response :
          ((!this.responseType || this.responseType === "text") && this.responseText.length < 1000000 ? JSON.parse(this.responseText) : null);
        keep(ctx, value);
      } catch { /* Player errors remain the player's responsibility. */ }
      };
      listeners.set(this, listener);
      this.addEventListener("load", listener, { once: true });
    }
    return open.call(this, method, url, ...rest);
  };
})();
