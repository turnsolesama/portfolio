/* Local, cross-project search. Result navigation remains owned by the app. */
(() => {
  'use strict';
  function install({api,openResult,escapeHtml,toast,canOpen = () => true,categoryLabel = value => value}) {
    const esc = value => escapeHtml(String(value ?? ''));
    const dialog = document.createElement('dialog');
    dialog.id = 'globalSearchDialog';
    dialog.className = 'global-search-dialog';
    dialog.setAttribute('aria-labelledby','globalSearchTitle');
    dialog.innerHTML = `<div class="global-search-header"><div><h2 id="globalSearchTitle">全局搜索</h2><p id="globalSearchScope">搜索所有项目、已索引的文稿内容与已登记 SKILL；未保存修改不参与，外部文件修改后需同步项目。</p></div><button type="button" class="global-search-close" data-search-close aria-label="关闭全局搜索">关闭 <kbd>Esc</kbd></button></div><div class="global-search-input-wrap"><label class="global-search-label" for="globalSearchInput">搜索关键词</label><input id="globalSearchInput" type="search" placeholder="输入名称、标签或正文关键词…" autocomplete="off" spellcheck="false" maxlength="200" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="globalSearchResults" aria-describedby="globalSearchScope"></div><p id="globalSearchStatus" class="global-search-status" role="status" aria-live="polite"></p><p class="global-search-notice" data-search-notice hidden></p><div id="globalSearchResults" class="global-search-results" role="listbox" aria-label="搜索结果"></div><div class="global-search-footer"><span class="global-search-help">↑ ↓ 选择 · Enter 打开</span><nav class="global-search-pages" aria-label="搜索结果分页"><button type="button" data-search-prev>上一页</button><span data-search-page></span><button type="button" data-search-next>下一页</button></nav></div>`;
    document.body.appendChild(dialog);
    const input = dialog.querySelector('#globalSearchInput');
    const results = dialog.querySelector('#globalSearchResults');
    const status = dialog.querySelector('#globalSearchStatus');
    const notice = dialog.querySelector('[data-search-notice]');
    const previous = dialog.querySelector('[data-search-prev]');
    const next = dialog.querySelector('[data-search-next]');
    const page = dialog.querySelector('[data-search-page]');
    const types = {item:'资源',project:'项目',skill:'SKILL'};
    let entries = [], selected = -1, offset = 0, total = 0, more = false;
    let timer = null, controller = null, revision = 0, pending = false, composing = false;
    let previousFocus = null, restoreFocus = true, closing = false, navigating = false;

    function invalidate() {
      clearTimeout(timer); timer = null; revision++;
      controller?.abort(); controller = null; pending = false;
      return revision;
    }
    function empty(message) {
      entries = []; selected = -1; more = false; total = 0;
      results.innerHTML = ''; status.textContent = message;
      notice.hidden = true; notice.textContent = '';
      input.setAttribute('aria-expanded','false'); input.removeAttribute('aria-activedescendant');
      previous.disabled = true; next.disabled = true; page.textContent = '';
      results.setAttribute('aria-busy',String(pending));
    }
    function select(index,scroll = false) {
      selected = Math.max(0,Math.min(entries.length-1,index));
      if (!entries.length) { selected = -1; input.removeAttribute('aria-activedescendant'); return; }
      results.querySelectorAll('[data-search-result]').forEach((row,i) => {
        row.classList.toggle('selected',i === selected);
        row.setAttribute('aria-selected',String(i === selected));
        if (scroll && i === selected) row.scrollIntoView?.({block:'nearest'});
      });
      input.setAttribute('aria-activedescendant',`globalSearchResult${selected}`);
    }
    function render(response) {
      entries = response.results.slice(0,20).filter(entry => entry && Object.hasOwn(types,entry.type) && typeof entry.id === 'string' && entry.id);
      total = Number.isFinite(response.total) ? Math.max(0,Math.floor(response.total)) : entries.length;
      more = typeof response.has_more === 'boolean' ? response.has_more : offset+entries.length < total;
      results.innerHTML = entries.map((entry,index) => {
        const origin = entry.project_name || (entry.type === 'skill' ? 'SKILL 库' : entry.type === 'project' ? '项目库' : '未分类项目');
        const category = entry.category ? ` · ${categoryLabel(entry.category)}` : '';
        return `<button id="globalSearchResult${index}" class="global-search-result" type="button" role="option" tabindex="-1" aria-selected="false" data-search-result="${index}"><span class="global-search-result-heading"><span class="global-search-result-name">${esc(String(entry.name || '未命名').slice(0,300))}</span><span class="global-search-result-type">${types[entry.type]}</span></span><span class="global-search-result-origin">${esc(String(origin+category).slice(0,600))}</span>${entry.snippet ? `<span class="global-search-result-snippet">${esc(String(entry.snippet).slice(0,2000))}</span>` : ''}</button>`;
      }).join('');
      const partial = response.partial || response.truncated || response.total_exact === false;
      status.textContent = entries.length ? `${partial ? '已找到' : '找到'} ${total.toLocaleString()} 条${partial ? ' · 部分结果' : '结果'}` : '没有找到匹配结果，请换一个关键词。';
      const warnings = Array.isArray(response.warnings) ? response.warnings.map(String) : [];
      if (response.notice) warnings.push(String(response.notice));
      if (partial) warnings.unshift('部分内容暂未纳入检索，当前显示已找到的结果。');
      notice.textContent = warnings.join('\n');
      notice.hidden = !notice.textContent;
      previous.disabled = offset === 0; next.disabled = !more;
      page.textContent = entries.length ? `${offset+1}–${offset+entries.length}` : offset ? `第 ${Math.floor(offset/20)+1} 页` : '';
      results.setAttribute('aria-busy','false');
      input.setAttribute('aria-expanded',String(entries.length > 0));
      select(0);
      results.scrollTop = 0;
    }
    async function search(start = 0) {
      if (!dialog.open || closing || composing) return;
      const query = input.value.trim();
      const current = invalidate(); offset = start;
      if (!query) { empty('输入关键词，在所有项目和 SKILL 中查找。'); return; }
      controller = new AbortController(); const signal = controller.signal;
      pending = true; empty('正在搜索…');
      try {
        const response = await api(`/api/search?q=${encodeURIComponent(query)}&limit=20&offset=${start}`,{signal});
        if (current !== revision || !dialog.open || closing) return;
        if (!response || !Array.isArray(response.results)) throw new Error('搜索结果格式无效，请重试。');
        pending = false; controller = null; render(response);
      } catch(error) {
        if (current !== revision || !dialog.open || closing) return;
        pending = false; controller = null;
        empty(`搜索未完成：${error?.message || '请稍后重试。'}`);
        // Keep the input and current page usable after a transient failure.
        previous.disabled = offset === 0;
      }
    }
    function schedule() {
      invalidate(); offset = 0;
      empty(input.value.trim() ? '输入完成后搜索…' : '输入关键词，在所有项目和 SKILL 中查找。');
      if (!composing && input.value.trim()) timer = setTimeout(() => { timer = null; search(); },250);
    }
    function close(restore = true) {
      if (!dialog.open || closing) return Promise.resolve();
      restoreFocus = restore; closing = true; invalidate();
      return new Promise(resolve => { dialog.addEventListener('close',resolve,{once:true}); dialog.close(); });
    }
    async function activate(index) {
      if (pending || navigating || composing || !dialog.open || closing || !entries[index] || !canOpen()) return;
      const entry = entries[index]; navigating = true;
      try {
        await close(false);
        await openResult(entry);
      } catch(error) { toast(error?.message || '结果未能打开，请稍后重试。','error'); }
      finally { navigating = false; }
    }
    input.addEventListener('input',schedule);
    input.addEventListener('compositionstart',() => { composing = true; invalidate(); empty('正在输入…'); });
    input.addEventListener('compositionend',() => { composing = false; schedule(); });
    dialog.addEventListener('close',() => {
      invalidate(); closing = false; composing = false;
      if (restoreFocus && previousFocus?.isConnected && typeof previousFocus.focus === 'function') previousFocus.focus({preventScroll:true});
      previousFocus = null;
    });
    dialog.addEventListener('cancel',event => { event.preventDefault(); if (!composing) close(true); });
    dialog.addEventListener('keydown',event => {
      if (composing || event.isComposing || event.keyCode === 229) return;
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); return; }
      if (event.target !== input && !results.contains(event.target)) return;
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault(); event.stopPropagation();
        if (entries.length) select(selected+(event.key === 'ArrowDown' ? 1 : -1),true);
      } else if (event.key === 'Enter') {
        event.preventDefault(); event.stopPropagation();
        if (entries.length) activate(selected);
        else if (!pending && input.value.trim()) search();
      }
    });
    dialog.addEventListener('click',event => {
      const button = event.target.closest('button'); if (!button || !dialog.contains(button)) return;
      if (button.hasAttribute('data-search-close')) { close(true); return; }
      if (button.hasAttribute('data-search-result')) { activate(Number(button.dataset.searchResult)); return; }
      if (button === previous && !previous.disabled) search(Math.max(0,offset-20));
      if (button === next && !next.disabled) search(offset+20);
    });
    return {
      open() {
        if (closing || navigating || !canOpen()) return false;
        if (dialog.open) { input.focus(); input.select(); return true; }
        invalidate(); previousFocus = document.activeElement; restoreFocus = true;
        input.value = ''; offset = 0; composing = false;
        empty('输入关键词，在所有项目和 SKILL 中查找。');
        dialog.showModal(); input.focus(); return true;
      },
      isOpen:() => dialog.open || closing
    };
  }
  window.YingXuGlobalSearch = {install};
})();
