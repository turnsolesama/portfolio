/* Event-driven screenshot integration; no timers or clipboard monitoring. */
(() => {
  'use strict';
  const validId = value => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
  function imageURL(noteId,url) {
    if (!validId(noteId) || typeof url !== 'string' || !url || url.length > 4096) return null;
    let decoded;
    try { decoded = decodeURIComponent(url); } catch { return null; }
    if (/^[\/\\]|[:\\\x00-\x1f]/.test(decoded)) return null;
    if (!/\.(png|jpe?g|webp|gif|bmp)$/i.test(decoded)) return null;
    return `/api/markdown-assets/image?note=${noteId}&path=${encodeURIComponent(url)}`;
  }
  function install({api,getTarget,insert,refresh,toast,send}) {
    const pending = new Map();
    let processing = 0;
    async function handle(data) {
      if (data?.action === 'capture-context-request') {
        if (typeof data.requestId !== 'string' || !data.requestId || data.requestId.length > 100) return true;
        const target = getTarget() || {};
        pending.clear(); pending.set(data.requestId,target);
        const projectId = validId(target.projectId) ? target.projectId : '';
        send('capture-context',{requestId:data.requestId,projectId,itemId:projectId && validId(target.itemId) ? target.itemId : ''});
        return true;
      }
      if (data?.action !== 'capture-result') return false;
      const target = pending.get(data.requestId); pending.delete(data.requestId);
      if (data.cancelled) return true;
      processing++;
      try {
        const item = data.item;
        let inserted = false;
        if (item && validId(item.id)) {
          if (target?.itemId && String(item.project_id) === String(target.projectId)) {
            try {
              const link = await api(`/api/markdown-assets/link?note=${encodeURIComponent(target.itemId)}&image=${encodeURIComponent(item.id)}`);
              if (typeof link.markdown === 'string' && link.markdown.length <= 8192) inserted = !!await insert(target,link.markdown);
            } catch(error) { toast(`截图已保存到项目，未插入笔记：${error.message}`,'info'); }
          }
          await refresh(item.project_id);
        }
        const parts = [];
        if (item && validId(item.id)) parts.push(inserted ? '截图已保存到项目并插入笔记草稿' : '截图已保存到项目的参考资料');
        if (data.clipboardCopied) parts.push('图片已复制到剪贴板');
        if (parts.length) toast(parts.join('；')+'。', 'success');
        if (data.saveError || data.clipboardError || data.error) toast([data.saveError,data.clipboardError,data.error].filter(Boolean).join('；'),'error');
        if (!parts.length && !data.saveError && !data.clipboardError && !data.error) toast('截图未完成，请重试。','info');
        return true;
      } finally { processing--; }
    }
    return {handle,isBusy:() => pending.size > 0 || processing > 0};
  }
  window.YingXuCapture = {install,imageURL};
})();
