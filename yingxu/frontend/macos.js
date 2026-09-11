/* The macOS host implements only close coordination; file actions use the HTTP API. */
(() => {
  'use strict';
  if (new URLSearchParams(location.search).get('desktop') !== 'macos') return;
  window.yingxuMac = true;
  const listeners = [], pending = [];
  const send = data => {
    if (data?.action === 'choose-external-files') {
      window.yingxuMacOpenExternal().catch(report); return;
    }
    if (!['desktop-ready','exit-response'].includes(data?.action)) return;
    if (!window.pywebview?.api?.post_message) { pending.push(data); return; }
    window.pywebview.api.post_message(data, state.bootstrap?.token || '').catch(console.error);
  };
  window.chrome ||= {};
  window.chrome.webview = {postMessage:send, addEventListener:(type,handler) => {
    if (type === 'message') listeners.push(handler);
  }};
  window.yingxuMacReceive = data => listeners.forEach(handler => handler({data}));
  window.addEventListener('pywebviewready', () => pending.splice(0).forEach(send));
  const style = document.createElement('style');
  style.textContent = '[data-action="capture-screen"],[data-drag-file]{display:none!important}';
  document.head.appendChild(style);

  window.yingxuMacOpenExternal = async () => {
    if (!state.bootstrap || state.modalBusy || $('#appDialog').open) return;
    state.modalBusy = true;
    let entries = [];
    try {
      const result = await api('/api/pick',{method:'POST',body:{kind:'files'}});
      if (result.paths?.length) entries = (await api('/api/external-open',{method:'POST',body:{paths:result.paths}})).entries;
    } finally { state.modalBusy = false; }
    if (entries.length) await queueExternalFiles(entries);
  };

  window.yingxuMacSettings = () => {
    if (!state.bootstrap) return;
    if ($('#appDialog').open || groupsIsOpen() || globalSearchIsOpen()) { toast('请先完成或关闭当前对话框。','info'); return; }
    const settings = state.bootstrap.settings || defaultSettings;
    const toggle = (key,label) => `<label class="setting-row"><span><strong>${label}</strong></span><input type="checkbox" name="${key}" ${settings[key] ? 'checked' : ''}></label>`;
    showDialog({title:'设置',subtitle:'macOS 试用版 · 关闭窗口会退出映序并检查未保存文稿。',submit:'保存设置',
      body:`<div class="settings-section"><h3>删除与恢复</h3>${toggle('confirm_delete','移入映序回收站前确认')}${toggle('confirm_trash_delete','移入 macOS 废纸篓前确认')}</div>
      <div class="settings-section"><h3>工作台</h3>${toggle('autoplay_media','打开音视频时自动播放')}
      <div class="field"><label>启动视图</label><select name="default_view">${optionHtml([{key:'grid',label:'画廊'},{key:'list',label:'列表'},{key:'board',label:'分镜看板'}],settings.default_view)}</select></div>
      <div class="field"><label>默认排序</label><select name="default_sort">${optionHtml([{key:'updated',label:'最近更新'},{key:'name',label:'名称'},{key:'order',label:'分镜顺序'}],settings.default_sort)}</select></div>
      <p class="field-hint">⌘S 保存 · ⌘F 当前搜索 · ⌘K 全局搜索。截图、菜单栏常驻与原生拖出暂未提供。</p></div>`,
      onSubmit:async form => {
        const values = new FormData(form), patch = {};
        for (const key of ['confirm_delete','confirm_trash_delete','autoplay_media']) patch[key] = values.has(key);
        patch.default_view = values.get('default_view'); patch.default_sort = values.get('default_sort');
        state.bootstrap.settings = await api('/api/settings',{method:'PATCH',body:patch});
        configureSection(); if (state.section === 'assets') await loadItems(); toast('设置已保存。');
      }});
  };
})();
