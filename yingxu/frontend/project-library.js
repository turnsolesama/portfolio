/* Long-term project organisation; files stay at their original paths. */
(() => {
  'use strict';
  function folderRows(folders) {
    const rows = [], seen = new Set();
    const walk = (parent, depth, path) => {
      for (const folder of folders.filter(f => (f.parent_id || null) === parent)) {
        if (seen.has(folder.id)) continue;
        seen.add(folder.id);
        const label = [...path, folder.name].join(' / ');
        rows.push({...folder, depth, label});
        walk(folder.id, depth + 1, [...path, folder.name]);
      }
    };
    walk(null, 0, []);
    return rows;
  }
  function eligibleParents(folders, id) {
    const excluded = new Set([id]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const folder of folders) if (excluded.has(folder.parent_id) && !excluded.has(folder.id)) {
        excluded.add(folder.id); changed = true;
      }
    }
    return folderRows(folders).filter(folder => !excluded.has(folder.id));
  }
  function filterProjects(data, folder, query) {
    const term = query.trim().toLocaleLowerCase();
    // A search is deliberately global, including projects in collapsed folders.
    return data.projects.filter(project => term
      ? `${project.name}\n${project.description || ''}`.toLocaleLowerCase().includes(term)
      : folder === '*' || (project.folder_id || '') === folder);
  }
  // Pointer capture stays on the stable dialog, never a row that may be redrawn.
  function bindProjectDrag({dialog,getProject,getFolders,isBusy,move}) {
    const doc = dialog.ownerDocument, win = doc.defaultView;
    let drag = null, ghost = null, outsideHint = null, highlight = null, suppressClick = false, disposed = false;
    const listeners = [];
    function listen(node,type,fn,options) { node.addEventListener(type,fn,options); listeners.push(() => node.removeEventListener(type,fn,options)); }
    function clearHighlight() { highlight?.classList.remove('project-library-drop-target'); highlight = null; dialog.classList.remove('project-library-drop-outside'); }
    function cleanup() {
      const previous = drag; drag = null;
      clearHighlight(); ghost?.remove(); outsideHint?.remove(); ghost = outsideHint = null;
      previous?.row.classList.remove('project-library-drag-source');
      dialog.classList.remove('project-library-dragging');
      if (previous && dialog.hasPointerCapture?.(previous.pointerId)) dialog.releasePointerCapture(previous.pointerId);
    }
    function targetAt(event) {
      const {clientX:x,clientY:y} = event, rect = dialog.getBoundingClientRect();
      const project = getProject(drag.projectId);
      if (!project || x < 8 || y < 8 || x > win.innerWidth-8 || y > win.innerHeight-8) return null;
      if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
        return project.folder_id ? {id:null,label:'未分类',outside:true} : null;
      }
      const button = doc.elementFromPoint(x,y)?.closest('[data-library-folder]');
      if (!button || !dialog.contains(button) || button.disabled) return null;
      const id = button.dataset.libraryFolder;
      if (id === '*' || (project.folder_id || '') === id) return null;
      const folder = id && getFolders().find(f => f.id === id);
      if (id && !folder) return null;
      return {id:id || null,label:folder ? folder.name : '未分类',button};
    }
    function update(event) {
      const target = targetAt(event); clearHighlight();
      if (target?.button) { highlight = target.button; highlight.classList.add('project-library-drop-target'); }
      dialog.classList.toggle('project-library-drop-outside',Boolean(target?.outside));
      ghost.textContent = `${getProject(drag.projectId)?.name || '项目'} · ${target ? `松手移到“${target.label}”` : '拖到分类；Esc 取消'}`;
      ghost.style.left = `${Math.max(8,Math.min(event.clientX+14,win.innerWidth-288))}px`;
      ghost.style.top = `${Math.max(8,Math.min(event.clientY+18,win.innerHeight-72))}px`;
      outsideHint.textContent = target?.outside ? '松手移到未分类（仅更改归类）' : '拖出弹窗可移到未分类 · Esc 取消';
      outsideHint.classList.toggle('is-active',Boolean(target?.outside));
      return target;
    }
    listen(dialog,'pointerdown',event => {
      if (disposed || drag || isBusy() || event.button !== 0 || event.isPrimary === false) return;
      suppressClick = false;
      const row = event.target.closest('[data-library-project]');
      if (!row || !dialog.contains(row) || event.target.closest('button,input,textarea,select,a,[contenteditable]')) return;
      // Touch users can scroll the body normally; the dedicated grip owns dragging.
      if (event.pointerType === 'touch' && !event.target.closest('[data-library-drag]')) return;
      if (!getProject(row.dataset.libraryProject)) return;
      // Prevent text selection/native text drag before the pointer threshold;
      // buttons and touch scrolling returned above keep their default behavior.
      event.preventDefault();
      drag = {projectId:row.dataset.libraryProject,row,pointerId:event.pointerId,x:event.clientX,y:event.clientY,started:false};
    });
    listen(dialog,'dragstart',event => { if (drag) event.preventDefault(); });
    listen(win,'pointermove',event => {
      if (!drag || drag.pointerId !== event.pointerId) return;
      if (isBusy() || !dialog.open) { cleanup(); return; }
      if (!drag.started && Math.hypot(event.clientX-drag.x,event.clientY-drag.y) < 8) return;
      if (!drag.started) {
        try { dialog.setPointerCapture(event.pointerId); } catch (_) { cleanup(); return; }
        drag.started = true; suppressClick = true;
        drag.row.classList.add('project-library-drag-source'); dialog.classList.add('project-library-dragging');
        ghost = doc.createElement('div'); ghost.className = 'project-library-drag-ghost'; ghost.setAttribute('role','status');
        outsideHint = doc.createElement('div'); outsideHint.className = 'project-library-outside-hint';
        dialog.append(ghost,outsideHint);
      }
      event.preventDefault(); update(event);
    });
    listen(win,'pointerup',event => {
      if (!drag || drag.pointerId !== event.pointerId) return;
      const projectId = drag.projectId, target = drag.started && !isBusy() && dialog.open ? update(event) : null;
      if (drag.started) event.preventDefault();
      cleanup();
      if (target) move(projectId,target.id);
    });
    const cancel = () => cleanup();
    listen(dialog,'pointercancel',event => { if (drag?.pointerId === event.pointerId) cleanup(); });
    listen(dialog,'lostpointercapture',event => { if (drag?.pointerId === event.pointerId) cleanup(); });
    listen(win,'blur',cancel);
    listen(dialog,'keydown',event => {
      if (event.key === 'Escape' && drag) { event.preventDefault(); event.stopImmediatePropagation(); cleanup(); }
    },true);
    listen(dialog,'cancel',event => {
      if (drag || isBusy()) { event.preventDefault(); cleanup(); }
    });
    listen(dialog,'click',event => {
      if (suppressClick || drag?.started || isBusy()) {
        suppressClick = false; event.preventDefault(); event.stopImmediatePropagation();
      }
    },true);
    function destroy() { if (disposed) return; disposed = true; cleanup(); listeners.forEach(remove => remove()); }
    listen(dialog,'close',destroy,{once:true});
    return {cancel,destroy};
  }
  function install({api,showDialog,choose,toast,escapeHtml:esc,selectProject,refreshProjects}) {
    let data = {folders:[],projects:[]}, folder = '*', query = '', page = 0, sequence = 0, activeDialog = null, dialogGeneration = 0, dragController = null;
    const size = 40;
    const error = e => toast(e.message || '项目库操作未完成。', 'error');
    const folderName = id => folderRows(data.folders).find(f => f.id === id)?.label || '未分类';
    const optionsHtml = (folders, selected, emptyLabel = '未分类') => `<option value="">${emptyLabel}</option>` + folders.map(f => `<option value="${esc(f.id)}" ${f.id === selected ? 'selected' : ''}>${esc(f.label)}</option>`).join('');
    async function closeCurrent() {
      const dialog = activeDialog;
      if (!dialog) return;
      dragController?.destroy(); dragController = null;
      activeDialog = null; dialogGeneration++;
      // Native dialog.close() queues its close event. Drain that event before
      // reusing the shared element, or it can cancel the next dialog instead.
      if (dialog.open) await new Promise(resolve => {
        dialog.addEventListener('close',resolve,{once:true}); dialog.close();
      });
    }
    function returnOnClose(dialog) {
      activeDialog = dialog; const generation = ++dialogGeneration;
      dialog.addEventListener('close', () => {
        if (activeDialog !== dialog || generation !== dialogGeneration) return;
        activeDialog = null; open().catch(error);
      }, {once:true});
    }
    async function editFolder(id = null) {
      const current = data.folders.find(f => f.id === id);
      const parents = id ? eligibleParents(data.folders, id) : folderRows(data.folders);
      const parent = current ? current.parent_id : (folder === '*' ? null : folder || null);
      await closeCurrent();
      const dialog = showDialog({title:id ? '编辑项目分类' : '新建项目分类',
        subtitle:'分类用于整理项目库，项目文件仍保存在原来的位置。',
        body:`<div class="field"><label for="libraryFolderName">分类名称</label><input id="libraryFolderName" name="name" maxlength="80" required value="${esc(current?.name || '')}" autofocus></div><div class="field"><label for="libraryFolderParent">上级分类</label><select id="libraryFolderParent" name="parent_id">${optionsHtml(parents,parent,'项目库顶层')}</select></div>`,
        submit:id ? '保存分类' : '创建分类', onSubmit:async form => {
          const result = await api(id ? `/api/project-folders/${encodeURIComponent(id)}` : '/api/project-folders', {
            method:id ? 'PATCH' : 'POST', body:{name:form.elements.name.value.trim(),parent_id:form.elements.parent_id.value || null}});
          folder = result.id; query = ''; page = 0;
          await refreshProjects(); toast(id ? '分类已保存。' : '分类已创建。');
        }});
      returnOnClose(dialog);
    }
    async function renameProject(projectId) {
      const project = data.projects.find(p => p.id === projectId);
      if (!project) { toast('项目已不在项目库中，请刷新后重试。','error'); return; }
      await closeCurrent();
      const dialog = showDialog({title:'重命名项目',subtitle:'修改项目显示名称，磁盘目录、素材和归类保持不变。',
        body:`<div class="field"><label for="libraryProjectName">项目名称</label><input id="libraryProjectName" name="name" maxlength="80" required value="${esc(project.name)}" autofocus></div>`,
        submit:'保存名称',onSubmit:async form => {
          const name = form.elements.name.value.trim();
          if (!name) throw new Error('请输入项目名称。');
          if ([...name].length > 80) throw new Error('项目名称最多 80 字。');
          if (name === project.name) return;
          await api(`/api/projects/${encodeURIComponent(projectId)}`,{method:'PATCH',body:{name}});
          project.name = name;
          // Keep the library location/search on return. A renamed search hit
          // naturally leaves the results if it no longer matches the query.
          try { await refreshProjects(); }
          catch (_) { toast('名称已保存，页面刷新未完成；重新打开项目库可查看。','error'); return; }
          toast('项目名称已保存。');
        }});
      returnOnClose(dialog);
    }
    async function assignProject(projectId) {
      const project = data.projects.find(p => p.id === projectId);
      if (!project) { toast('项目已不在项目库中，请刷新后重试。','error'); return; }
      await closeCurrent();
      const dialog = showDialog({title:'移动到项目分类', subtitle:project.name,
        body:`<div class="field"><label for="libraryProjectFolder">项目分类</label><select id="libraryProjectFolder" name="folder_id">${optionsHtml(folderRows(data.folders),project.folder_id)}</select></div><p class="dialog-hint">只更改项目库中的归属，不移动磁盘上的文件。</p>`,
        submit:'保存归类',onSubmit:async form => {
          await api(`/api/project-library/${encodeURIComponent(projectId)}`,{method:'PATCH',body:{folder_id:form.elements.folder_id.value || null}});
          await refreshProjects(); toast('项目归类已保存。');
        }});
      returnOnClose(dialog);
    }
    async function deleteFolder(id) {
      const current = data.folders.find(f => f.id === id);
      await closeCurrent();
      const result = await choose('删除空分类', `删除“${current?.name || ''}”？只允许删除没有项目和子分类的分类。历史回收项目以后恢复时会进入未分类。`, [
        {key:'cancel',label:'取消'}, {key:'delete',label:'删除空分类',style:'danger'}]);
      try {
        if (result === 'delete') { await api(`/api/project-folders/${encodeURIComponent(id)}`,{method:'DELETE'}); folder = '*'; await refreshProjects(); toast('空分类已删除。'); }
      } finally { await open(); }
    }
    function projectHtml(project) {
      return `<article class="project-library-card" data-library-project="${esc(project.id)}"><span class="project-library-drag-grip" data-library-drag aria-hidden="true" title="拖动归类">⠿</span><div role="button" tabindex="0" class="project-library-open" data-library-open="${esc(project.id)}"><strong>${esc(project.name)}</strong><span>${esc(folderName(project.folder_id))} · ${Number(project.counts?.total) || 0} 项素材</span>${project.description ? `<small>${esc(project.description)}</small>` : ''}</div><div class="project-library-card-actions"><button type="button" class="button button-ghost" data-library-rename="${esc(project.id)}" aria-label="重命名项目 ${esc(project.name)}">重命名</button><button type="button" class="button button-secondary" data-library-assign="${esc(project.id)}" aria-label="归类 ${esc(project.name)}">归类</button></div></article>`;
    }
    function drawResults(dialog) {
      const projects = filterProjects(data, folder, query);
      page = Math.min(page, Math.max(0,Math.ceil(projects.length / size) - 1));
      const title = query.trim() ? '全库搜索结果' : folder === '*' ? '全部项目' : folderName(folder);
      dialog.querySelector('[data-library-heading]').textContent = `${title} · ${projects.length} 个项目`;
      dialog.querySelector('[data-library-results]').innerHTML = projects.slice(page*size,(page+1)*size).map(projectHtml).join('') || '<p class="project-library-empty">这里还没有项目。可以先在项目空间创建项目，再选择“归类”。</p>';
      dialog.querySelector('[data-library-page]').textContent = `${page + 1} / ${Math.max(1,Math.ceil(projects.length/size))}`;
      dialog.querySelector('[data-library-prev]').disabled = page === 0;
      dialog.querySelector('[data-library-next]').disabled = (page+1)*size >= projects.length;
      for (const button of dialog.querySelectorAll('[data-library-folder]')) {
        button.setAttribute('aria-current', button.dataset.libraryFolder === folder && !query.trim() ? 'true' : 'false');
        if (button.dataset.libraryFolder === '') button.title = '未分类是系统分组；可新建自定义分类，再将项目归类。';
      }
      const tools = dialog.querySelector('[data-library-folder-tools]');
      tools.hidden = folder === '*' || folder === '' || Boolean(query.trim());
    }
    async function open(options = {}) {
      const ticket = ++sequence;
      const loaded = await api('/api/project-library');
      if (ticket !== sequence) return;
      data = loaded;
      if (folder !== '*' && folder && !data.folders.some(f => f.id === folder)) folder = '*';
      if (options.projectId) { await assignProject(options.projectId); return; }
      await closeCurrent();
      if (ticket !== sequence) return;
      const rows = folderRows(data.folders);
      const dialog = showDialog({title:'项目库',subtitle:'拖动项目到左侧分类，或拖出弹窗移到未分类；只更改归类。触屏可用项目左侧握柄，亦可点击“归类”。',wide:true,
        body:`<div class="project-library-toolbar"><label class="project-library-search"><span class="sr-only">搜索全部项目</span><input type="search" data-library-search placeholder="搜索全部项目…" value="${esc(query)}"></label><button type="button" class="button button-secondary" data-library-new>＋ 新建分类</button></div><div class="project-library-layout"><nav class="project-library-folders" aria-label="项目分类"><button type="button" data-library-folder="*">全部项目 <span>${data.projects.length}</span></button><button type="button" data-library-folder="">未分类</button>${rows.map(f => `<button type="button" data-library-folder="${esc(f.id)}" title="${esc(f.label)}" style="padding-left:${12+Math.min(f.depth,12)*12}px">▱ ${esc(f.name)}</button>`).join('')}</nav><section class="project-library-content"><div class="project-library-section-head"><strong data-library-heading></strong><div data-library-folder-tools><button type="button" class="button button-ghost" data-library-edit>编辑分类</button><button type="button" class="button button-ghost" data-library-delete>删除空分类</button></div></div><div class="project-library-results" data-library-results></div><div class="project-library-pagination"><button type="button" class="button button-ghost" data-library-prev>上一页</button><span data-library-page></span><button type="button" class="button button-ghost" data-library-next>下一页</button></div></section></div>`,
        actions:'<button type="button" class="button button-primary" data-dialog-cancel>完成</button>'});
      activeDialog = dialog; dialogGeneration++;
      const search = dialog.querySelector('[data-library-search]');
      search.addEventListener('input',() => { if (busy) return; dragController?.cancel(); query = search.value; page = 0; drawResults(dialog); });
      let busy = false;
      const generation = dialogGeneration;
      dragController = bindProjectDrag({dialog,getProject:id => data.projects.find(p => p.id === id),getFolders:() => data.folders,isBusy:() => busy,
        move:async (projectId,folderId) => {
          if (busy || generation !== dialogGeneration) return;
          busy = true; dialog.setAttribute('aria-busy','true');
          const controls = [...dialog.querySelectorAll('button,input')].map(node => [node,node.disabled]);
          controls.forEach(([node]) => { node.disabled = true; });
          try {
            await api(`/api/project-library/${encodeURIComponent(projectId)}`,{method:'PATCH',body:{folder_id:folderId}});
            const project = data.projects.find(p => p.id === projectId);
            if (project) project.folder_id = folderId;
            await refreshProjects();
            toast('项目归类已保存。磁盘文件位置不变。');
          } catch (e) { error(e); }
          finally {
            busy = false;
            if (generation === dialogGeneration) {
              dialog.removeAttribute('aria-busy'); controls.forEach(([node,disabled]) => { node.disabled = disabled; });
              if (dialog.open) drawResults(dialog);
            }
          }
        }});
      dialog.querySelector('.project-library-layout').addEventListener('keydown',event => {
        if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('[data-library-open]')) {
          event.preventDefault(); event.target.click();
        }
      });
      dialog.querySelector('.project-library-layout').addEventListener('click', async event => {
        const button = event.target.closest('[data-library-open],button');
        if (!button || busy) return;
        dragController?.cancel();
        if (button.hasAttribute('data-library-folder')) { folder = button.dataset.libraryFolder; query = ''; search.value = ''; page = 0; drawResults(dialog); return; }
        if (button.hasAttribute('data-library-prev')) { page--; drawResults(dialog); return; }
        if (button.hasAttribute('data-library-next')) { page++; drawResults(dialog); return; }
        busy = true;
        try {
          if (button.dataset.libraryOpen) { await closeCurrent(); const result = await selectProject(button.dataset.libraryOpen); if (result === false) await open(); }
          else if (button.dataset.libraryRename) await renameProject(button.dataset.libraryRename);
          else if (button.dataset.libraryAssign) await assignProject(button.dataset.libraryAssign);
          else if (button.hasAttribute('data-library-edit')) await editFolder(folder);
          else if (button.hasAttribute('data-library-delete')) await deleteFolder(folder);
        } catch(e) { error(e); } finally { busy = false; }
      });
      dialog.querySelector('[data-library-new]').addEventListener('click',async () => {
        if (busy) return; busy = true;
        try { await editFolder(); } catch(e) { error(e); } finally { busy = false; }
      });
      drawResults(dialog);
    }
    return {open};
  }
  window.YingXuProjectLibrary = {install,folderRows,eligibleParents,filterProjects,bindProjectDrag};
})();
