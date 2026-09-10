/* Logical material stacks. No file operation is issued from this module. */
(() => {
  'use strict';
  const categories = {scripts:'剧本与文档',shots:'分镜',characters:'角色',scenes:'场景',props:'道具',previs:'白模预演',generated:'生成素材',delivery:'成片交付',references:'参考资料'};
  const kinds = {markdown:'文',text:'文',docx:'文',image:'图',video:'影',audio:'音',pdf:'PDF',model:'3D',file:'件'};
  const validId = value => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
  const uniqueIds = values => Array.isArray(values) && values.length <= 200 ? [...new Set(values.filter(validId))] : [];
  function visibleGroups(groups, context) {
    if (context.section !== 'assets' || !['grid','board'].includes(context.view) || context.q || context.status || context.kind) return [];
    const page = new Set((context.items || []).map(item => item.id));
    return groups.filter(group => group.project_id === context.projectId && group.member_ids.some(id => page.has(id)));
  }
  function dropTarget(target, ids, root) {
    if (!ids.length || !root?.contains(target) || target.closest('[data-drag-file]')) return null;
    const group = target.closest('[data-resource-group]');
    if (group) return {node:group,groupId:group.dataset.resourceGroup,key:`group:${group.dataset.resourceGroup}`};
    const item = target.closest('.resource-card[data-item]');
    if (!item || ids.includes(item.dataset.item)) return null;
    return {node:item,itemId:item.dataset.item,key:`item:${item.dataset.item}`};
  }
  async function transferMember(api,source,itemId,target) {
    if (!validId(itemId) || !validId(source.id) || !Number.isInteger(source.revision) || source.revision < 1) throw new Error('素材组信息已变化，请刷新后重试。');
    if (target && (target.id === source.id || target.project_id !== source.project_id || !validId(target.id) || !Number.isInteger(target.revision) || target.revision < 1)) throw new Error('请选择同项目内的另一个素材组。');
    const body = {ids:[itemId],revision:source.revision,target_group_id:target?.id || null};
    if (target) body.target_revision = target.revision;
    return api(`/api/resource-groups/${source.id}/transfer`,{method:'POST',body});
  }
  function installMemberDrag({node,group,targets,getProject,canDrag,onDrop,onError = () => {}}) {
    const doc = node.ownerDocument || document, win = doc.defaultView || window;
    let gesture = null, panel = null, inFlight = false, suppressClick = false, highlightedZone = null, hintKey = null;
    const subscriptions = [];
    const on = (target,type,fn,options) => { target.addEventListener?.(type,fn,options); subscriptions.push(() => target.removeEventListener?.(type,fn,options)); };
    const available = targets.filter(value => value.id !== group.id && value.project_id === group.project_id && validId(value.id));
    const targetsById = new Map(available.map(value => [value.id,value]));
    const valid = () => node.open && getProject() === group.project_id && canDrag() && !inFlight;
    function clear() {
      const previous = gesture; gesture = null;
      panel?.remove(); panel = null; node.classList.remove('yx-member-dragging','yx-member-outside');
      highlightedZone = null; hintKey = null;
      previous?.row.classList.remove('yx-member-drag-source');
      if (previous && node.hasPointerCapture?.(previous.id)) node.releasePointerCapture(previous.id);
      if (previous?.started) suppressClick = true;
    }
    function destination(x,y) {
      if (!(x >= 0 && y >= 0 && x < win.innerWidth && y < win.innerHeight)) return null;
      const hit = doc.elementFromPoint(x,y),zone = hit?.closest('[data-member-drop]');
      if (zone && panel?.contains(zone)) {
        const target = targetsById.get(zone.dataset.memberDrop);
        return zone.dataset.memberDrop === 'remove' ? {target:null,zone} : target ? {target,zone} : null;
      }
      // Buttons, inputs and empty space inside the group remain cancellation
      // targets. Only the actual outside of the dialog means removing a member.
      const rect = node.getBoundingClientRect();
      return x < rect.left || x > rect.right || y < rect.top || y > rect.bottom ? {target:null,zone:null} : null;
    }
    function indicate(x,y) {
      const result = destination(x,y);
      const zone = result?.zone || null,key = result ? result.target?.id || 'remove' : 'cancel';
      if (zone !== highlightedZone) { highlightedZone?.classList.remove('yx-member-drop-active'); zone?.classList.add('yx-member-drop-active'); highlightedZone = zone; }
      if (key !== hintKey) {
        node.classList.toggle('yx-member-outside',!!result && !result.target);
        panel.querySelector('[data-member-drag-status]').textContent = result ? result.target ? `松开移到「${result.target.name}」` : '松开移出当前组，原文件保持不变' : '拖到下方目标组，或拖出弹窗移出组；Esc 取消';
        hintKey = key;
      }
      return result;
    }
    function showPanel() {
      panel = doc.createElement('div'); panel.className = 'yx-member-drop-panel';
      const status = doc.createElement('p'); status.setAttribute('data-member-drag-status',''); status.setAttribute('role','status'); panel.append(status);
      const choices = doc.createElement('div'); choices.className = 'yx-member-drop-choices';
      for (const target of [...available,null]) {
        const zone = doc.createElement('div'); zone.dataset.memberDrop = target?.id || 'remove'; zone.className = 'yx-member-drop-zone';
        zone.textContent = target ? `移到 ${target.name} · ${target.count} 项` : '移出当前组（保留文件）'; choices.append(zone);
      }
      panel.append(choices); node.append(panel); node.classList.add('yx-member-dragging');
    }
    on(node,'pointerdown',event => {
      suppressClick = false;
      if (gesture || !valid() || event.button !== 0 || (event.pointerType && event.pointerType !== 'mouse') || event.target.closest('button,input,select,textarea,a,[contenteditable]')) return;
      const row = event.target.closest('[data-member-drag]'),itemId = row?.dataset.memberDrag;
      if (!row || !node.contains(row) || !group.members.some(item => item.id === itemId)) return;
      gesture = {id:event.pointerId,itemId,row,x:event.clientX,y:event.clientY,started:false};
      event.preventDefault(); event.stopPropagation(); node.setPointerCapture(event.pointerId);
    });
    on(node,'pointermove',event => {
      const g = gesture; if (!g || event.pointerId !== g.id) return;
      if (!valid()) { clear(); return; }
      if (!g.started && Math.hypot(event.clientX-g.x,event.clientY-g.y) >= 6) { g.started = true; g.row.classList.add('yx-member-drag-source'); showPanel(); }
      if (g.started) { event.preventDefault(); event.stopPropagation(); indicate(event.clientX,event.clientY); }
    });
    on(node,'pointerup',event => {
      const g = gesture; if (!g || event.pointerId !== g.id) return;
      const result = g.started && valid() ? destination(event.clientX,event.clientY) : null;
      if (g.started) { event.preventDefault(); event.stopPropagation(); }
      clear();
      if (result) {
        inFlight = true;
        Promise.resolve().then(() => onDrop(g.itemId,result.target)).catch(onError).finally(() => { inFlight = false; });
      }
    });
    on(node,'pointercancel',event => { if (gesture?.id === event.pointerId) clear(); });
    on(node,'lostpointercapture',event => { if (gesture?.id === event.pointerId) clear(); });
    on(node,'keydown',event => { if (gesture && event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); clear(); } },true);
    on(node,'cancel',event => { if (gesture || inFlight) { event.preventDefault(); clear(); } });
    on(node,'click',event => { if (suppressClick) { suppressClick = false; event.preventDefault(); event.stopImmediatePropagation(); } },true);
    on(node,'dragstart',event => { if (gesture) event.preventDefault(); });
    on(win,'blur',clear); on(win,'resize',clear);
    return {cancel:clear,isBusy:() => !!gesture || inFlight,destroy:() => { clear(); subscriptions.forEach(off => off()); }};
  }
  function install({api,toast,escapeHtml:esc,openItem,refresh:refreshItems,getContext,guard = async () => true}) {
    let groups = [], projectId = null, sequence = 0, openSequence = 0, root = null, dialog = null, disposed = false, lastRender = null;
    let drag = null, hover = null, timer = null, pending = false, opening = 0, openingMember = false, memberPending = 0;
    const subscriptions = [];
    const error = e => toast(e.message || '素材组操作未完成。','error');
    const context = () => getContext() || {};
    const on = (node, type, callback, options) => { node.addEventListener(type,callback,options); subscriptions.push(() => node.removeEventListener(type,callback,options)); };
    const json = (method, body) => ({method,body});
    const caption = item => categories[item.category] || item.category || '素材';
    const tiny = item => `<span class="yx-group-mini" title="${esc(item.name)}"><span>${esc(kinds[item.kind] || '件')}</span>${item.thumbnail_url && ['image','video'].includes(item.kind) ? `<img src="/api/thumbnail/${esc(item.id)}" loading="lazy" draggable="false" alt="">` : ''}</span>`;
    const thumbnail = group => `<span class="yx-group-preview" aria-hidden="true">${group.preview.map(tiny).join('')}${Array.from({length:Math.max(0,4-group.preview.length)},() => '<span class="yx-group-mini yx-group-mini-empty"></span>').join('')}</span>`;

    async function refresh() {
      const current = {...context()}, ticket = ++sequence;
      if (!current.projectId || current.section !== 'assets') { groups = []; projectId = null; render(); return; }
      const result = await api(`/api/resource-groups?project=${encodeURIComponent(current.projectId)}`);
      if (disposed || ticket !== sequence || context().projectId !== current.projectId) return;
      groups = result.groups || []; projectId = current.projectId; render();
    }
    function render(parent) {
      if (parent) root = parent;
      if (!root || disposed) return;
      const current = context();
      const inputs = () => [root,root.firstChild,root.lastChild,groups,projectId,current.projectId,current.section,current.items,current.view,current.q,current.status,current.kind];
      const before = inputs();
      if (lastRender?.every((value,index) => value === before[index])) return;
      for (const node of root.querySelectorAll('[data-yx-group-hidden]')) { node.hidden = false; node.removeAttribute('data-yx-group-hidden'); }
      root.querySelectorAll('.yx-group-card,.yx-groups-bar,.yx-group-board-strip').forEach(node => node.remove());
      if (projectId !== current.projectId || current.section !== 'assets') return;
      if (groups.length) {
        const bar = document.createElement('div'); bar.className = 'yx-groups-bar';
        bar.innerHTML = `<button type="button" class="button button-ghost button-small">管理素材组 · ${groups.length}</button><span>分组保留文件原位置</span>`;
        bar.querySelector('button').addEventListener('click',() => open().catch(error)); root.prepend(bar);
      }
      const visible = visibleGroups(groups,current);
      let strip = null;
      if (current.view === 'board' && visible.length) {
        strip = document.createElement('div'); strip.className = 'yx-group-board-strip';
        strip.setAttribute('aria-label','素材组，组内素材保留原制作状态');
        const bar = root.querySelector('.yx-groups-bar');
        if (bar) bar.after(strip); else root.prepend(strip);
      }
      for (const group of visible) {
        const ids = new Set(group.member_ids), nodes = [...root.querySelectorAll('.resource-card[data-item]')].filter(node => ids.has(node.dataset.item));
        if (!nodes.length) continue;
        const card = document.createElement('button'); card.type = 'button'; card.className = 'yx-group-card'; card.dataset.resourceGroup = group.id;
        card.setAttribute('aria-label',`打开素材组 ${group.name}，${group.count} 个素材`);
        card.innerHTML = `${thumbnail(group)}<span class="yx-group-card-copy"><strong>${esc(group.name)}</strong><small>${group.count} 个素材 · ${esc(group.categories.map(key => categories[key] || key).join('、'))}</small></span><span class="yx-group-drop-label">松开加入素材组</span>`;
        card.addEventListener('click',event => { event.stopPropagation(); open(group.id).catch(error); });
        card.addEventListener('contextmenu',event => { event.preventDefault(); event.stopPropagation(); open(group.id).catch(error); });
        if (strip) strip.append(card); else nodes[0].before(card);
        for (const node of nodes) { node.hidden = true; node.setAttribute('data-yx-group-hidden',''); }
      }
      lastRender = inputs();
    }

    function close() {
      openSequence++;
      const current = dialog; dialog = null;
      if (current) { current.memberDrag?.destroy(); if (current.open) current.close(); current.remove(); }
    }
    function shell(title) {
      close();
      const node = document.createElement('dialog'); node.className = 'yx-group-dialog';
      node.setAttribute('aria-label',title);
      node.innerHTML = `<div class="yx-group-dialog-head"><h2>${esc(title)}</h2><button type="button" class="icon-button" data-close aria-label="关闭素材组" title="关闭">×</button></div><div class="yx-group-dialog-body"></div>`;
      document.body.append(node); dialog = node;
      node.querySelector('[data-close]').addEventListener('click',close);
      node.addEventListener('close',() => { node.memberDrag?.destroy(); if (dialog === node) dialog = null; node.remove(); });
      node.showModal(); return node;
    }
    async function changed() {
      const before = sequence;
      await refreshItems();
      // The host's loadItems already refreshes this snapshot. Standalone hosts
      // that only repaint their items still need the module-owned refresh.
      if (sequence === before) await refresh();
    }
    async function mutate(group, action, body) {
      const path = `/api/resource-groups/${group.id}${['add','remove'].includes(action) ? '/members' : ''}`;
      const result = await api(path,json(action === 'rename' ? 'PATCH' : action === 'add' ? 'POST' : 'DELETE',{...body,revision:group.revision}));
      await changed(); return result;
    }
    async function create(values) {
      const ids = uniqueIds(values), current = context();
      if (ids.length < 2) { toast('请至少选择两个素材再创建组。','info'); return null; }
      if (!current.projectId) return null;
      const result = await api('/api/resource-groups',json('POST',{project_id:current.projectId,item_ids:ids}));
      await changed(); toast('已创建素材组，原文件位置保持不变。'); return result;
    }
    async function add(groupId, values) {
      const ids = uniqueIds(values); if (!ids.length) return null;
      const group = await api(`/api/resource-groups/${encodeURIComponent(groupId)}`);
      const result = await mutate(group,'add',{item_ids:ids}); toast('已加入素材组。'); return result;
    }
    async function open(groupId) {
      opening++;
      try { return await openImpl(groupId); }
      finally { opening--; }
    }
    async function openImpl(groupId) {
      const currentProject = context().projectId, opening = ++openSequence;
      if (!currentProject || disposed) return;
      const group = groupId ? await api(`/api/resource-groups/${encodeURIComponent(groupId)}`) : null;
      if (context().projectId !== currentProject || disposed || opening !== openSequence) return;
      if (group && group.project_id !== currentProject) return;
      if (!group) {
        await refresh();
        if (context().projectId !== currentProject || opening !== openSequence) return;
        const node = shell('管理素材组'), body = node.querySelector('.yx-group-dialog-body');
        body.innerHTML = `<p class="yx-group-help">把卡片拖到另一个卡片上稍作停留，即可叠放成组。空组仍可添加素材或解散。</p>${groups.length ? `<div class="yx-group-list">${groups.map(value => `<button type="button" data-open-group="${esc(value.id)}">${thumbnail(value)}<span><strong>${esc(value.name)}</strong><small>${value.count} 个素材</small></span></button>`).join('')}</div>` : '<p class="yx-group-empty">还没有素材组。可先选择两个素材，再从右键菜单创建。</p>'}`;
        body.querySelectorAll('[data-open-group]').forEach(button => button.addEventListener('click',() => open(button.dataset.openGroup).catch(error)));
        return;
      }
      const node = shell(group.name), body = node.querySelector('.yx-group-dialog-body');
      body.innerHTML = `<form class="yx-group-name-form"><label>组名<input name="name" maxlength="80" required value="${esc(group.name)}"></label><button class="button button-secondary" type="submit">重命名</button></form><p class="yx-group-help">${group.count} 个素材 · 拖动成员内容可移到其他组；拖出弹窗可移出组，原文件保留。</p><div class="yx-group-toolbar"><button class="button button-secondary" type="button" data-add>添加素材</button><button class="button button-ghost" type="button" data-dissolve>解散素材组</button></div><div class="yx-group-members">${group.members.length ? group.members.map(item => `<div class="yx-group-member" data-member-drag="${esc(item.id)}"><span class="yx-group-member-copy" title="拖到其他组，或拖出弹窗移出组">${tiny(item)}<span><strong>${esc(item.name)}</strong><small>${esc(caption(item))} · ${esc(item.status || '待开始')}</small></span></span><button type="button" class="button button-ghost button-small" data-open-member="${esc(item.id)}" aria-label="打开 ${esc(item.name)}">打开</button><button type="button" class="button button-ghost button-small" data-remove-member="${esc(item.id)}" aria-label="将 ${esc(item.name)} 移出素材组">移出组</button></div>`).join('') : '<p class="yx-group-empty">组内暂无素材。可以添加素材，或解散这个空组。</p>'}</div><div class="yx-group-confirm" hidden><p>解散后，素材将重新显示为独立卡片，文件不会删除。</p><button type="button" class="button button-primary" data-confirm-dissolve>确认解散</button><button type="button" class="button button-ghost" data-cancel-dissolve>取消</button></div>`;
      let busy = false;
      const perform = async action => {
        if (busy) return; busy = true;
        node.querySelectorAll('button,input').forEach(control => { control.disabled = true; });
        try { await action(); }
        catch (e) { error(e); if (e.status === 409 && dialog === node) await open(group.id).catch(error); }
        finally { busy = false; if (dialog === node) node.querySelectorAll('button,input').forEach(control => { control.disabled = false; }); }
      };
      node.memberDrag = installMemberDrag({node,group,targets:groups,getProject:() => context().projectId,canDrag:() => !busy && !pending && dialog === node,onError:error,
        onDrop:async (itemId,target) => { memberPending++; try { await perform(async () => {
          if (dialog !== node || context().projectId !== currentProject) return;
          try { await transferMember(api,group,itemId,target); }
          catch (e) { if (e.status === 409) await refresh(); throw e; }
          await changed();
          if (dialog === node) await open(group.id);
          toast(target ? `已移到「${target.name}」，原文件保持不变。` : '已移出素材组，原文件保持不变。');
        }); } finally { memberPending--; } }});
      body.querySelector('form').addEventListener('submit',event => { event.preventDefault(); const name = body.querySelector('input[name="name"]').value; perform(async () => { await mutate(group,'rename',{name}); if (dialog === node) await open(group.id); }); });
      body.querySelectorAll('[data-remove-member]').forEach(button => button.addEventListener('click',() => perform(async () => { await mutate(group,'remove',{item_ids:[button.dataset.removeMember]}); if (dialog === node) await open(group.id); })));
      body.querySelectorAll('[data-open-member]').forEach(button => button.addEventListener('click',() => perform(async () => {
        openingMember = true;
        try {
          close();
          if (await guard()) await openItem(button.dataset.openMember);
          else if (context().projectId === currentProject) await open(group.id);
        } finally { openingMember = false; }
      })));
      body.querySelector('[data-add]').addEventListener('click',() => pickMembers(group).catch(error));
      const confirmation = body.querySelector('.yx-group-confirm');
      body.querySelector('[data-dissolve]').addEventListener('click',() => { confirmation.hidden = false; body.querySelector('[data-confirm-dissolve]').focus(); });
      body.querySelector('[data-cancel-dissolve]').addEventListener('click',() => { confirmation.hidden = true; });
      body.querySelector('[data-confirm-dissolve]').addEventListener('click',() => perform(async () => { await mutate(group,'dissolve',{}); if (dialog === node) close(); toast('素材组已解散，文件保持原样。'); }));
    }

    async function pickMembers(group) {
      const node = shell(`添加素材 · ${group.name}`), body = node.querySelector('.yx-group-dialog-body');
      body.innerHTML = '<form class="yx-group-search"><label>搜索整个项目<input type="search" name="q" placeholder="按名称、标签或内容检索"></label><button class="button button-secondary" type="submit">搜索</button></form><p class="yx-group-help">可选择其他分类中的素材。每次最多加入 200 个。</p><div class="yx-group-picker"></div><div class="yx-group-picker-footer"><button type="button" class="button button-ghost" data-prev>上一页</button><span data-page></span><button type="button" class="button button-ghost" data-next>下一页</button><button type="button" class="button button-primary" data-submit-add disabled>加入组（0）</button><button type="button" class="button button-ghost" data-back>返回组</button></div>';
      const chosen = new Set(), occupied = new Set(groups.flatMap(value => value.member_ids));
      let offset = 0, query = '', ticket = 0, loading = false;
      const submit = body.querySelector('[data-submit-add]');
      const update = () => { submit.textContent = `加入组（${chosen.size}）`; submit.disabled = !chosen.size || loading; };
      async function load() {
        const turn = ++ticket; loading = true; update();
        try {
          const result = await api(`/api/items?project=${encodeURIComponent(group.project_id)}&limit=48&offset=${offset}&q=${encodeURIComponent(query)}`);
          if (dialog !== node || turn !== ticket) return;
          body.querySelector('.yx-group-picker').innerHTML = result.items.map(item => `<label class="yx-group-picker-row"><input type="checkbox" value="${esc(item.id)}" ${occupied.has(item.id) ? 'disabled' : ''} ${chosen.has(item.id) ? 'checked' : ''}><span><strong>${esc(item.name)}</strong><small>${esc(caption(item))}${occupied.has(item.id) ? ' · 已在素材组中' : ''}</small></span></label>`).join('') || '<p class="yx-group-empty">没有符合条件的素材。</p>';
          body.querySelector('[data-page]').textContent = `${Math.floor(offset/48)+1} / ${Math.max(1,Math.ceil(result.total/48))}`;
          body.querySelector('[data-prev]').disabled = offset === 0;
          body.querySelector('[data-next]').disabled = offset+48 >= result.total;
          body.querySelectorAll('input[type="checkbox"]').forEach(input => input.addEventListener('change',() => { if (input.checked) { if (chosen.size >= 200) { input.checked = false; toast('每次最多选择 200 个素材。','info'); return; } chosen.add(input.value); } else chosen.delete(input.value); update(); }));
        } finally { if (turn === ticket) { loading = false; update(); } }
      }
      body.querySelector('form').addEventListener('submit',event => { event.preventDefault(); offset = 0; query = body.querySelector('input[name="q"]').value; load().catch(error); });
      body.querySelector('[data-prev]').addEventListener('click',() => { offset = Math.max(0,offset-48); load().catch(error); });
      body.querySelector('[data-next]').addEventListener('click',() => { offset += 48; load().catch(error); });
      body.querySelector('[data-back]').addEventListener('click',() => open(group.id).catch(error));
      submit.addEventListener('click',async () => {
        if (loading || !chosen.size) return; loading = true; update();
        try { await mutate(group,'add',{item_ids:[...chosen]}); if (dialog === node) await open(group.id); }
        catch (e) { error(e); if (e.status === 409 && dialog === node) await open(group.id).catch(error); }
        finally { loading = false; update(); }
      });
      await load();
    }

    function clearHover() {
      clearTimeout(timer); timer = null;
      hover?.node.classList.remove('yx-group-hover','yx-group-armed'); hover = null;
    }
    function beginDrag(values) {
      clearHover();
      const ids = uniqueIds(values), current = context();
      drag = ids.length ? {ids,projectId:current.projectId} : null;
    }
    function endDrag() { clearHover(); drag = null; }
    function candidate(target) {
      const current = context();
      if (!drag || dialog || drag.projectId !== current.projectId || current.section !== 'assets' || !['grid','board'].includes(current.view)) return null;
      return dropTarget(target,drag.ids,root);
    }
    function hoverAt(target) {
      const next = candidate(target);
      if (!next) { clearHover(); return null; }
      if (hover?.key !== next.key) {
        clearHover(); hover = {...next,armed:false}; next.node.classList.add('yx-group-hover');
        timer = setTimeout(() => { if (hover?.key === next.key && drag) { hover.armed = true; hover.node.classList.add('yx-group-armed'); } },550);
      }
      return hover;
    }
    function commitDrop(target) {
      const current = candidate(target);
      if (!current || !hover || !hover.armed || current.key !== hover.key || pending) return false;
      const ids = drag.ids.slice(), destination = {...hover}; endDrag(); pending = true;
      Promise.resolve(destination.groupId ? add(destination.groupId,ids) : create(uniqueIds([destination.itemId,...ids])))
        .catch(error).finally(() => { pending = false; });
      return true;
    }
    function handleNativeDrop(data) {
      if (!data?.released || !data.inside || !(data.width > 0 && data.height > 0)) return false;
      return commitDrop(document.elementFromPoint(data.x*window.innerWidth/data.width,data.y*window.innerHeight/data.height));
    }
    on(document,'dragstart',event => {
      if (event.target.closest('[data-drag-file]')) return;
      const item = event.target.closest('.resource-card[data-item]');
      if (!item || !root?.contains(item)) return;
      const selected = context().selectedIds;
      beginDrag(selected?.has(item.dataset.item) ? [...selected] : [item.dataset.item]);
    },true);
    on(document,'dragover',event => {
      if (!drag) return;
      const target = hoverAt(event.target);
      if (!target) return;
      event.preventDefault(); event.stopImmediatePropagation();
      if (event.dataTransfer) event.dataTransfer.dropEffect = target.armed ? (['move','linkMove'].includes(event.dataTransfer.effectAllowed) ? 'move' : 'copy') : 'none';
    },true);
    on(document,'dragleave',event => { if (hover && !hover.node.contains(event.relatedTarget)) clearHover(); },true);
    on(document,'drop',event => {
      if (!candidate(event.target)) return;
      event.preventDefault(); event.stopImmediatePropagation();
      if (!commitDrop(event.target)) { endDrag(); toast('拖到卡片上停留片刻，出现叠放提示后再松开。','info'); }
    },true);
    on(document,'dragend',endDrag,true);
    on(document,'error',event => {
      // Pending thumbnails may respond before an image is available. Keep the
      // type glyph as a usable preview instead of a broken-image indicator.
      if (event.target?.tagName === 'IMG' && event.target.closest('.yx-group-mini')) event.target.remove();
    },true);
    return {render,refresh,open,create,add,beginDrag,endDrag,handleNativeDrop,isOpen:() => !!dialog?.open || opening > 0 || openingMember || memberPending > 0,destroy() {
      disposed = true; sequence++; endDrag(); close(); subscriptions.forEach(remove => remove());
      if (root) { root.querySelectorAll('[data-yx-group-hidden]').forEach(node => { node.hidden = false; node.removeAttribute('data-yx-group-hidden'); }); root.querySelectorAll('.yx-group-card,.yx-groups-bar,.yx-group-board-strip').forEach(node => node.remove()); }
    }};
  }
  window.YingXuResourceGroups = {install};
  if (typeof module !== 'undefined' && module.exports) module.exports = {install,visibleGroups,dropTarget,uniqueIds,installMemberDrag,transferMember};
})();
