/* Safe-zone setup and a reversible, local classification library. */
((root, factory) => {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.AIHubOrganizer = factory();
})(globalThis, () => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const count = value => Math.max(0, Number(value) || 0).toLocaleString('zh-CN');
  const size = value => {
    let n = Math.max(0, Number(value) || 0), i = 0;
    while (n >= 1024 && i < 4) { n /= 1024; i++; }
    return `${i ? n.toFixed(1) : n} ${['B','KiB','MiB','GiB','TiB'][i]}`;
  };
  const warningText = value => typeof value === 'string' ? value : value?.message || value?.reason || JSON.stringify(value);
  const PREVIEW_LIMIT = 200, PAGE_SIZE = 25;
  function categoryLabel(value) {
    const parts = String(value || '').split('/');
    const groups = {'02_Images':'图片素材','03_Videos':'视频素材','04_Audio':'音频素材','05_Workflows':'工作流','06_Documents':'文档资料'};
    if (groups[value]) return groups[value];
    if (parts[0] !== '01_Models') return String(value || '分类待确认');
    const domains = {image:'图片创作',video:'视频制作',language:'语言与对话',audio:'语音与音乐',vision:'视觉工具',shared:'通用组件',unknown:'用途待确认'};
    const kinds = {Unknown:'类型待确认',Checkpoint:'主模型',Diffusion:'扩散模型',TextEncoder:'文本编码器',CLIPVision:'视觉编码器',Embedding:'嵌入模型',Upscaler:'放大修复',Vision:'视觉识别',LLM:'语言模型',TTS:'语音模型',VideoAI:'视频处理'};
    const purposes = {style:'风格画风',character:'角色人物',lighting:'光照氛围',detail:'细节材质',composition:'姿态构图',outfit:'服饰造型',scene:'场景物件',motion:'动作运镜',acceleration:'采样加速',concept:'其他概念',uncategorized:'用途待补充',multiple:'多种用途'};
    return ['模型', domains[parts[1]] || parts[1], kinds[parts[2]] || parts[2], parts[3] ? purposes[parts[3]] || parts[3] : ''].filter(Boolean).join(' · ');
  }

  function workspaceBanner(status) {
    const workspace = status?.workspace || {};
    if (workspace.configured && workspace.available) return '';
    return `<section class="setup-banner organizer-welcome ${workspace.configured ? 'is-unavailable' : ''}" role="status"><div><div class="eyebrow">${workspace.configured ? 'WORKSPACE OFFLINE' : 'MAKE IT YOUR WORKSPACE'}</div><h3>${workspace.configured ? '资产目录暂时不可访问' : '让 AI Hub 适应这台电脑'}</h3><p>${esc(workspace.message || (workspace.configured ? '检查硬盘连接，或重新选择安全区。已有记录会保留。' : '选择你自己的资产文件夹。模型、素材与工作流会按本机路径建立分类入口。'))}</p></div><a class="btn primary" href="#/organizer">${workspace.configured ? '检查安全区' : '设置安全区'} <span aria-hidden="true">→</span></a></section>`;
  }

  function planTable(plan, category = '', page = 1) {
    const all = Array.isArray(plan?.items) ? plan.items : [];
    const preview = all.slice(0, PREVIEW_LIMIT);
    const rows = preview.filter(item => !category || item.category === category);
    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    page = Math.max(1, Math.min(Number(page) || 1, pages));
    const html = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map(item => `<tr><td><div class="organizer-path" title="${esc(item.source)}">${esc(item.source)}</div><div class="organizer-destination"><span aria-hidden="true">↳</span><span>${esc(item.target)}</span></div></td><td><span class="badge">${esc(categoryLabel(item.category))}</span><p class="organizer-reason">${esc(item.reason)}</p></td><td class="organizer-size">${size(item.size)}</td></tr>`).join('');
    return {html, page, pages, total: rows.length, shown: preview.length, all: all.length};
  }

  function renderRuns(runs, busy) {
    if (!runs?.length) return '<div class="organizer-empty">尚未执行整理。每次创建的入口会保留独立记录，方便撤销。</div>';
    const labels = {completed:'已完成',complete:'已完成',done:'已完成',success:'已完成',partial:'部分完成',undone:'已撤销',rolled_back:'已撤销',failed:'未完成',error:'未完成',interrupted:'已中断',running:'进行中'};
    return `<div class="table-wrap"><table class="tbl organizer-runs"><thead><tr><th>执行时间 / 记录</th><th>建立入口</th><th>跳过</th><th>状态与说明</th><th>操作</th></tr></thead><tbody>${runs.slice(0, 20).map(run => `<tr><td>${esc(run.created_at || '时间未记录')}<span class="file-sub">${esc(run.id || run.run_id)}</span></td><td>${count(run.created)}${Number(run.undone) ? `<span class="file-sub">已撤销 ${count(run.undone)}</span>` : ''}</td><td>${count(run.skipped)}</td><td>${esc(labels[run.status] || run.status || '已记录')}${Number(run.pending) ? `<span class="file-sub">未完成 ${count(run.pending)} 项</span>` : ''}${Number(run.errors) ? `<details class="organizer-run-errors"><summary>${count(run.errors)} 条错误说明</summary>${(run.error_messages || []).slice(0,10).map(message => `<p>${esc(warningText(message))}</p>`).join('')}</details>` : ''}</td><td>${Number(run.created) > 0 && !['undone','rolled_back','running'].includes(run.status) ? `<button class="btn small" data-organizer-undo="${esc(run.id || run.run_id)}" ${busy ? 'disabled' : ''}>撤销入口</button>` : '<span class="muted">—</span>'}</td></tr>`).join('')}</tbody></table></div>${runs.length > 20 ? '<p class="caption-note organizer-inset">显示最近 20 次记录。</p>' : ''}`;
  }

  function capture(el) {
    if (!el?.querySelector) return {};
    const root = el.querySelector('#organizer-root');
    return root ? {
      root: root.value, create: Boolean(el.querySelector('#organizer-create')?.checked),
      on_startup: Boolean(el.querySelector('#organizer-startup')?.checked),
      category: el.querySelector('#organizer-category')?.value || '',
      page: Number(el.dataset.organizerPage) || 1,
    } : {};
  }

  function createPage({api, icon, heading, toast, pollJobs, openModal, closeModal, refresh}) {
    return async function organizerPage(el, params, restored) {
      const $ = selector => el.querySelector(selector);
      const $$ = selector => [...el.querySelectorAll(selector)];
      el.innerHTML = '<div class="muted">正在读取安全区与整理记录…</div>';
      try {
        const status = await api('/api/organizer/status');
        if (!el.isConnected) return;
        const workspace = status.workspace || {}, ready = status.enabled === true && workspace.configured && workspace.available;
        let plan = null;
        if (ready) { try { plan = await api('/api/organizer/plan'); } catch { /* A saved plan is optional before the first preview. */ } }
        if (!el.isConnected) return;
        if (plan?.root !== status.root || !plan?.id) plan = null;
        const busy = Boolean(status.busy), root = restored?.root ?? (status.root || workspace.suggested_root || '');
        const checked = restored?.on_startup ?? Boolean(status.on_startup);
        const summary = plan?.summary || {};
        const metric = (label, value, detail) => `<div class="organizer-stat"><span>${label}</span><b>${count(value)}</b><small>${detail}</small></div>`;
        const categories = Object.entries(summary.categories || {});
        const warningList = Array.isArray(plan?.warnings) ? plan.warnings : [];
        el.innerHTML = heading('安全区整理', '使用这台电脑的目录，建立可撤销的分类入口。', 'WORKSPACE ORGANIZER') + `
          <section class="organizer-hero"><div class="organizer-hero-icon">${icon('shield', 28)}</div><div><h3>文件留在原处，资产按用途归类。</h3><p>在安全区内生成 <code>00_AIHub_Library</code>。图片、视频、音频、模型与工作流按文件和元数据分类；无法确认的用途会标明待确认。</p></div><span class="badge ${ready ? 'b-green' : 'b-yellow'}">${busy ? '后台任务运行中' : ready ? '安全区已就绪' : workspace.available ? '等待启用整理' : workspace.configured ? '目录不可访问' : '等待设置'}</span></section>
          <div class="organizer-layout"><section class="panel organizer-setup"><div class="panel-head"><h3>${icon('folder', 17)} 本机安全区</h3><span class="caption-note">01 / SETUP</span></div><div class="body">
            <form id="organizer-form"><label class="organizer-field" for="organizer-root">允许整理的文件夹<input class="inp" id="organizer-root" name="root" required autocomplete="off" spellcheck="false" value="${esc(root)}" placeholder="例如：F:\\AI 或 D:\\CreativeAssets" ${busy ? 'disabled' : ''}></label><p class="caption-note">只处理你指定的文件夹内部，不要求与其他电脑使用相同盘符。请选择专门存放 AI 资产的目录。</p>
            ${!workspace.available && workspace.message ? `<p class="organizer-notice" role="status">${esc(workspace.message)}</p>` : ''}
            ${workspace.configured && workspace.available && status.enabled !== true ? '<p class="organizer-notice" role="status">先保存本机安全区以启用整理。已有资产目录可直接确认使用。</p>' : ''}
            <label class="organizer-check"><input type="checkbox" id="organizer-create" ${restored?.create ? 'checked' : ''} ${busy ? 'disabled' : ''}><span>目录不存在时创建它<small>初始化所需目录；已有文件保持原样。</small></span></label>
            <label class="organizer-check"><input type="checkbox" id="organizer-startup" ${checked ? 'checked' : ''} ${busy ? 'disabled' : ''}><span>后台服务启动时自动整理<small>每次服务启动时建立新增文件的分类入口。关闭窗口会保留后台，重开窗口不会重复触发；不添加系统开机项，也不实时监听。</small></span></label>
            <p id="organizer-error" class="dialog-error" role="alert"></p><div class="organizer-form-actions"><button type="submit" class="btn primary" id="organizer-save" ${busy ? 'disabled' : ''}>保存安全区</button><span class="caption-note">保存后可先预览分类方案</span></div></form>
          </div></section><aside class="panel organizer-rules"><div class="panel-head"><h3>整理方式</h3></div><div class="body"><div class="organizer-rule"><span>01</span><div><b>边界明确</b><p>仅扫描安全区。应用环境、缓存和目录联接等内容会略过。</p></div></div><div class="organizer-rule"><span>02</span><div><b>原路径保留</b><p>分类目录使用硬链接，共用原文件内容，不复制大模型数据。编辑任意入口也会改变原文件，建议从 Hub 只读浏览。</p></div></div><div class="organizer-rule"><span>03</span><div><b>每次都能追溯</b><p>记录新建和跳过的入口。撤销只移除本次入口，保留原件。</p></div></div></div></aside></div>
          <section class="panel organizer-preview"><div class="panel-head"><div><h3>${icon('scan', 17)} 分类预览</h3><span class="caption-note">02 / REVIEW & ORGANIZE</span></div><button class="btn" id="organizer-preview" ${!ready || busy ? 'disabled' : ''}>${icon('scan', 15)} ${plan ? '重新扫描预览' : '扫描并预览'}</button></div>
            ${plan ? `<div class="organizer-stats">${metric('发现文件', summary.scanned, '本次扫描范围')}${metric('待建立入口', summary.planned, '执行整份计划')}${metric('已有入口', summary.already_linked, '重复整理自动略过')}${metric('未识别文件', summary.unknown, '已略过，不建立入口')}</div><div class="organizer-plan-info"><span>分类内容逻辑大小 <b>${size(summary.logical_bytes)}</b> · 不等于额外磁盘占用</span><span>另有 ${count(summary.excluded)} 项已排除</span></div>
            ${categories.length ? `<div class="organizer-category-summary">${categories.map(([name, total]) => `<span>${esc(categoryLabel(name))} <b>${count(total)}</b></span>`).join('')}</div>` : ''}
            ${warningList.length ? `<details class="organizer-warnings"><summary>${count(warningList.length)} 条扫描说明</summary><ul>${warningList.slice(0,20).map(w => `<li>${esc(warningText(w))}</li>`).join('')}</ul>${warningList.length > 20 ? '<p>显示前 20 条说明。</p>' : ''}</details>` : ''}
            <div class="organizer-table-tools"><label for="organizer-category">预览分类 <select id="organizer-category"><option value="">全部分类</option>${[...new Set((plan.items || []).slice(0,PREVIEW_LIMIT).map(item => item.category))].map(category => `<option value="${esc(category)}">${esc(categoryLabel(category))}</option>`).join('')}</select></label><span id="organizer-preview-count" class="caption-note"></span></div><div class="table-wrap"><table class="tbl organizer-plan-table"><thead><tr><th>原文件 → 分类入口</th><th>分类与依据</th><th>逻辑大小</th></tr></thead><tbody id="organizer-plan-rows"></tbody></table></div><div id="organizer-plan-empty"></div><div class="organizer-plan-footer"><div class="organizer-pagination"><button class="btn small" id="organizer-prev" aria-label="上一页分类预览">←</button><span id="organizer-page-number"></span><button class="btn small" id="organizer-next" aria-label="下一页分类预览">→</button></div><button class="btn primary" id="organizer-apply" ${busy || !Number(summary.planned) ? 'disabled' : ''}>${icon('folder',15)} 建立 ${count(summary.planned)} 个分类入口</button></div>` : `<div class="organizer-empty">${icon('folder', 28)}<h4>${ready ? '先看看文件会如何归类' : '先设置这台电脑的安全区'}</h4><p>${busy ? '后台任务完成后将更新预览。' : ready ? '扫描预览只读取文件信息。确认后再建立分类入口。' : '完成上方设置后，即可扫描文件并查看分类依据。'}</p></div>`}
          </section><section class="panel organizer-history"><div class="panel-head"><h3>${icon('clock',17)} 整理记录</h3><span class="caption-note">03 / HISTORY</span></div>${renderRuns(status.runs || [], busy)}</section>`;

        const start = async (path, body, message) => {
          $$('button').forEach(button => { button.disabled = true; });
          try {
            await api(path, {body});
            toast(message, 'ok');
            pollJobs();
            if (el.isConnected) await refresh();
          } catch (error) {
            toast(error.message, 'err');
            if (el.isConnected) { $('#organizer-error').textContent = error.message; await refresh(); }
          }
        };
        $('#organizer-form').onsubmit = async event => {
          event.preventDefault();
          const body = {root: $('#organizer-root').value.trim(), create: $('#organizer-create').checked, on_startup: $('#organizer-startup').checked};
          if (!body.root) { $('#organizer-error').textContent = '请选择或填写一个资产文件夹。'; $('#organizer-root').focus(); return; }
          const button = $('#organizer-save'); button.disabled = true; $('#organizer-error').textContent = '';
          try {
            await api('/api/workspace/setup', {body});
            toast('安全区已保存，可以扫描预览分类方案', 'ok');
            if (el.isConnected) await refresh();
          } catch (error) { if (el.isConnected) { $('#organizer-error').textContent = error.message; button.disabled = false; } }
        };
        $('#organizer-preview').onclick = () => start('/api/organizer/preview', {}, '分类预览已开始，完成后会显示方案');

        if (plan) {
          let page = restored?.page || 1;
          const category = $('#organizer-category'); category.value = restored?.category || '';
          const render = () => {
            const table = planTable(plan, category.value, page); page = table.page;
            el.dataset.organizerPage = String(page);
            $('#organizer-plan-rows').innerHTML = table.html;
            $('#organizer-plan-empty').innerHTML = table.total ? '' : '<div class="organizer-empty">这一分类没有待建立的入口。</div>';
            $('#organizer-preview-count').textContent = `预览前 ${count(table.shown)} 项 · 当前分类 ${count(table.total)} 项` + (Number(summary.planned) > PREVIEW_LIMIT ? `；执行包含完整 ${count(summary.planned)} 项` : '');
            $('#organizer-page-number').textContent = `${page} / ${table.pages}`;
            $('#organizer-prev').disabled = page <= 1;
            $('#organizer-next').disabled = page >= table.pages;
          };
          category.onchange = () => { page = 1; render(); };
          $('#organizer-prev').onclick = () => { page--; render(); };
          $('#organizer-next').onclick = () => { page++; render(); };
          render();
          $('#organizer-apply').onclick = () => {
            openModal(`<div class="organizer-confirm"><div class="eyebrow">CREATE CLASSIFIED LIBRARY</div><h2>建立 ${count(summary.planned)} 个分类入口</h2><p>将在下方安全区内创建 <code>00_AIHub_Library</code> 分类入口。</p><div class="organizer-confirm-root">${esc(status.root)}</div><p>原文件保持原路径。入口与原文件共用内容，编辑任一处会同时改变另一处。可以在整理记录中撤销本次创建的入口。</p><div class="dialog-actions"><button class="btn" id="organizer-confirm-cancel">取消</button><button class="btn primary" id="organizer-confirm-apply">确认建立入口</button></div></div>`);
            document.querySelector('#organizer-confirm-cancel').onclick = closeModal;
            document.querySelector('#organizer-confirm-apply').onclick = () => { closeModal(); start('/api/organizer/apply', {plan_id: plan.id}, '正在建立分类入口，完成后可查看记录'); };
          };
        }
        $$('[data-organizer-undo]').forEach(button => {
          button.onclick = () => {
            const runId = button.dataset.organizerUndo;
            openModal(`<div class="organizer-confirm"><div class="eyebrow">UNDO LIBRARY ENTRIES</div><h2>撤销这次整理</h2><p>仅移除记录中由本次创建、且仍能安全核对的分类入口。原件保留；不符合核对条件的入口会跳过并记录。</p><div class="organizer-confirm-root">${esc(runId)}</div><div class="dialog-actions"><button class="btn" id="organizer-confirm-cancel">取消</button><button class="btn primary" id="organizer-confirm-undo">撤销本次入口</button></div></div>`);
            document.querySelector('#organizer-confirm-cancel').onclick = closeModal;
            document.querySelector('#organizer-confirm-undo').onclick = () => { closeModal(); start('/api/organizer/undo', {run_id: runId}, '正在撤销本次分类入口'); };
          };
        });
      } catch (error) {
        if (el.isConnected) {
          el.innerHTML = `<div class="page-error"><h3>暂时无法读取安全区</h3><p>${esc(error.message)}</p><button class="btn" id="organizer-retry">重试</button></div>`;
          $('#organizer-retry').onclick = refresh;
        }
      }
    };
  }
  return {createPage, capture, workspaceBanner, planTable, renderRuns, categoryLabel, PREVIEW_LIMIT, PAGE_SIZE};
});
