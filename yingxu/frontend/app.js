'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const iconPaths = {
  plus:'<path d="M12 5v14M5 12h14"/>', close:'<path d="m6 6 12 12M18 6 6 18"/>', chevron:'<path d="m9 5 7 7-7 7"/>', left:'<path d="m15 5-7 7 7 7"/>', down:'<path d="m6 9 6 6 6-6"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.4"/><rect x="14" y="3" width="7" height="7" rx="1.4"/><rect x="3" y="14" width="7" height="7" rx="1.4"/><rect x="14" y="14" width="7" height="7" rx="1.4"/>',
  list:'<path d="M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1"/>', board:'<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="11" rx="1"/><rect x="17" y="4" width="4" height="14" rx="1"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>', filter:'<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2" fill="currentColor" stroke="none"/><circle cx="16" cy="12" r="2" fill="currentColor" stroke="none"/><circle cx="10" cy="18" r="2" fill="currentColor" stroke="none"/>',
  folder:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>', file:'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 14h8M8 17h5"/>',
  script:'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 13h8M8 17h6"/>',
  film:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4M7 12h10"/>',
  user:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>', scene:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.4"/><path d="m3 16 5-5 4 4 3-3 6 6"/>',
  cube:'<path d="m12 3 9 5v9l-9 5-9-5V8Z"/><path d="m3 8 9 5 9-5M12 13v9M7.5 5.5l9 5"/>', video:'<rect x="3" y="5" width="13" height="14" rx="2"/><path d="m16 10 5-3v10l-5-3"/>',
  sparkle:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/><path d="M20 2v4M18 4h4"/>', delivery:'<path d="M5 8h14v13H5Z"/><path d="m4 8 16-4 1 4M8 7l1-3M13 6l1-3M7 15l3 3 7-7"/>',
  image:'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-6-6-8 12M3 15l4-4 4 4"/>', audio:'<path d="M9 18V5l11-2v13M9 9l11-2"/><ellipse cx="6" cy="18" rx="3" ry="2.5"/><ellipse cx="17" cy="16" rx="3" ry="2.5"/>',
  upload:'<path d="M12 16V3M7 8l5-5 5 5M4 15v5h16v-5"/>', refresh:'<path d="M20 10a8 8 0 0 0-14-5L3 8M3 3v5h5M4 14a8 8 0 0 0 14 5l3-3M16 16h5v5"/>',
  help:'<circle cx="12" cy="12" r="9"/><path d="M9.3 9a2.8 2.8 0 0 1 5.4 1c0 2-2.7 2-2.7 4M12 17h.01"/>', check:'<path d="m5 12 4 4L19 6"/>', alert:'<path d="m12 3 10 18H2Z"/><path d="M12 9v5M12 17h.01"/>',
  save:'<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2Z"/><path d="M7 3v6h9V3M7 21v-8h10v8"/>', open:'<path d="M14 3h7v7M21 3l-12 12M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
  eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>', info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  link:'<path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" transform="translate(0 -1) scale(.96)"/>',
  lock:'<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>', copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>', play:'<path d="m8 5 11 7-11 7Z"/>',
  panel:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/>', minus:'<path d="M5 12h14"/>', history:'<path d="M3 11a9 9 0 1 1 2 7M3 5v6h6M12 7v5l3 2"/>', trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  skills:'<path d="m9 3-3 7H2l7 11 3-7h4l6-11h-7l-3 7"/>', context:'<path d="M4 4h10v16H4zM17 8h3v12h-3M7 8h4M7 12h4M7 16h3"/>', clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>', move:'<path d="M12 4H4v16h16v-8M12 12l9-9M15 3h6v6"/>', restore:'<path d="M4 11a8 8 0 1 1 2 7M4 5v6h6M12 8v5l3 2"/>'
};
const icon = (name, cls = '') => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name] || iconPaths.file}</svg>`;
const categoryDefs = [
  {key:'all',label:'全部资源',icon:'grid'}, {key:'scripts',label:'剧本与文档',icon:'script'}, {key:'shots',label:'分镜',icon:'film'},
  {key:'characters',label:'角色',icon:'user'}, {key:'scenes',label:'场景',icon:'scene'}, {key:'props',label:'道具',icon:'cube'},
  {key:'previs',label:'白模预演',icon:'video'}, {key:'generated',label:'生成素材',icon:'sparkle'}, {key:'delivery',label:'成片交付',icon:'delivery'}, {key:'references',label:'参考资料',icon:'folder'}
];
const kindLabels = {markdown:'Markdown',text:'文本',docx:'Word',html:'HTML',svg:'SVG',image:'图片',video:'视频',audio:'音频',pdf:'PDF',model:'3D 模型',file:'文件',skill:'SKILL'};
const kindIcons = {markdown:'script',text:'script',docx:'file',html:'file',svg:'image',image:'image',video:'video',audio:'audio',pdf:'file',model:'cube',file:'file',skill:'skills'};
const statuses = ['待开始','进行中','待审核','已完成'];
const categoryLabel = key => categoryDefs.find(category => category.key === key)?.label || key || '未分类';
const storage = {get(key){try{return localStorage.getItem(key);}catch{return null;}},set(key,value){try{localStorage.setItem(key,value);}catch{/* Browser storage is optional. */}}};
const state = {bootstrap:null,projects:[],projectId:null,section:'assets',category:'all',folderId:null,folderScope:'current',folders:[],selectedIds:new Set(),trashEntries:[],q:'',status:'',kind:'',sort:'updated',view:storage.get('yingxu:view') || 'grid',offset:0,limit:48,items:[],total:0,counts:[],listSequence:0,listController:null,tabs:[],activeKey:null,skills:[],context:null,modalSequence:0,modalBusy:false,thumbCache:new Map(),thumbPending:new Set(),thumbTimers:new Set(),jobs:new Map(),drafts:{}};
let searchTimer, draftTimer, observer;
const defaultSettings = {confirm_delete:true,confirm_trash_delete:true,close_to_tray:true,default_view:'grid',default_sort:'updated',autoplay_media:false,capture_enabled:true,capture_hotkey:'Ctrl+Alt+Shift+S',capture_mode:'annotate'};
function systemTrashName() { return globalThis.window?.yingxuMac ? 'macOS 废纸篓' : 'Windows 回收站'; }
function preference(key) { return state.bootstrap?.settings?.[key] ?? defaultSettings[key]; }
function desktopMessage(action,extra={}) {
  if (!window.chrome?.webview?.postMessage) { toast('请在映序桌面窗口中使用此功能。','info'); return false; }
  window.chrome.webview.postMessage({action,...extra}); return true;
}
async function confirmRemoval(title,subtitle,choices) { return preference('confirm_delete') ? choose(title,subtitle,choices) : 'delete'; }

async function api(path, options = {}) {
  const init = {...options,headers:{Accept:'application/json',...(options.headers || {})}};
  if (options.body !== undefined) { init.body = JSON.stringify(options.body); init.headers['Content-Type'] = 'application/json'; }
  if (options.method && options.method !== 'GET') init.headers['X-YingXu-Token'] = state.bootstrap?.token || '';
  let response;
  try { response = await fetch(path, init); const connection = $('#connectionState'); if (connection) connection.textContent = '本地连接正常'; }
  catch(error) { if (error.name === 'AbortError') throw error; const connection = $('#connectionState'); if (connection) connection.textContent = '连接暂时中断'; throw new Error('本地服务暂时无法连接。请确认映序仍在运行，然后重试。'); }
  let result;
  try { result = await response.json(); } catch { result = {}; }
  if (!response.ok) { const error = new Error(result.error || `请求未完成（${response.status}）`); error.status = response.status; throw error; }
  return result;
}

function toast(message, type = 'success', duration = 4200) {
  const node = document.createElement('div'); node.className = `toast ${type}`; node.innerHTML = `${icon(type === 'error' ? 'alert' : type === 'info' ? 'info' : 'check')}<span>${escapeHtml(message)}</span>`;
  $('#toastRegion').append(node); setTimeout(() => node.remove(), duration);
}
function report(error) { if (error.name !== 'AbortError') toast(error.message || '操作没有完成，请重试。','error',7000); }
function currentProject() { return state.projects.find(project => String(project.id) === String(state.projectId)); }
function activeTab() { return state.tabs.find(tab => tab.key === state.activeKey); }
function formatSize(bytes) { const number = Number(bytes) || 0; return number < 1024 ? `${number} B` : number < 1048576 ? `${(number/1024).toFixed(1)} KB` : number < 1073741824 ? `${(number/1048576).toFixed(1)} MB` : `${(number/1073741824).toFixed(2)} GB`; }
function asDate(value) { if (!value) return null; if (typeof value === 'number') { if (value > 1e16) value /= 1e6; else if (value < 1e12) value *= 1000; } const date = new Date(value); return Number.isNaN(date.getTime()) ? null : date; }
function formatDate(value, detail = false) { const date = asDate(value); return date ? date.toLocaleString('zh-CN',detail ? {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'} : {month:'2-digit',day:'2-digit'}) : '—'; }
function statusHtml(value) { return `<span class="status-label" data-status="${escapeHtml(value || '待开始')}">${escapeHtml(value || '待开始')}</span>`; }
function optionHtml(options, selected) { return options.map(value => `<option value="${escapeHtml(typeof value === 'object' ? value.key : value)}" ${String(selected) === String(typeof value === 'object' ? value.key : value) ? 'selected' : ''}>${escapeHtml(typeof value === 'object' ? value.label : value)}</option>`).join(''); }
function debounce(callback, delay = 250) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => callback(...args), delay); }; }
function sidebarProjects() {
  const ids = [state.projectId,...(state.projectLibrary?.recent_ids || [])].filter(Boolean);
  return [...new Set(ids.map(String))].map(id => state.projects.find(project => String(project.id) === id)).filter(Boolean).slice(0,5);
}
let resourceGroups;
function groupsIsOpen() { return !!resourceGroups?.isOpen(); }
function groupController() {
  if (!resourceGroups && window.YingXuResourceGroups) resourceGroups = window.YingXuResourceGroups.install({api,toast,escapeHtml,openItem,
    refresh:async () => { if (state.section === 'assets') await loadItems(); },getContext:() => ({projectId:state.projectId,section:state.section,category:state.category,folderId:state.folderId,folderScope:state.folderScope,items:state.items,q:state.q,status:state.status,kind:state.kind,view:state.view,offset:state.offset,selectedIds:state.selectedIds}),guard:() => guardProperties()});
  return resourceGroups;
}
function selectableResourceIds() { const hidden = new Set($$('#resourceItems [data-yx-group-hidden]').map(node => String(node.dataset.item))); return state.items.map(item => String(item.id)).filter(id => !hidden.has(id)); }
function deleteSelectionShortcut(event) {
  if (event.key !== 'Delete' || event.defaultPrevented || event.repeat || event.isComposing || event.keyCode === 229 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return false;
  const editing = node => {
    if (node?.isContentEditable || node?.closest?.('textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],.cm-editor')) return true;
    const input = node?.closest?.('input');
    if (!input) return false;
    const card = input.closest('#resourceItems .resource-card[data-item],#resourceItems .resource-row[data-item]');
    return input.type !== 'checkbox' || !input.hasAttribute('data-select-item') || !card || String(input.dataset.selectItem) !== String(card.dataset.item);
  };
  if (editing(event.target) || editing(document.activeElement)) return false;
  if (state.section !== 'assets' || !state.projectId || state.loadingItems || state.deleteShortcutBusy || state.modalBusy || state.trashBusy || state.exitBusy || state.globalOpening || state.uploading || state.restoringDrafts || state.jobs.size) return false;
  if ($('#appDialog').open || $('dialog[open]') || globalSearchIsOpen() || groupsIsOpen() || captureUI?.isBusy() || !$('#resourceMenu').hidden || $('.dragging-card,.external-drag')) return false;
  if (state.tabs.some(tab => tab.saving || tab.propertiesSaving || tab.markdownEditor?.isComposing())) return false;
  const selectable = new Set(selectableResourceIds());
  const visible = new Set($$('#resourceItems .resource-card[data-item],#resourceItems .resource-row[data-item]')
    .filter(node => !node.hidden && !node.closest('[hidden],[data-yx-group-hidden]')).map(node => String(node.dataset.item)));
  const ids = state.items.filter(item => String(item.project_id) === String(state.projectId) && /^[a-f0-9]{32}$/.test(String(item.id)))
    .map(item => String(item.id)).filter(id => state.selectedIds.has(id) && selectable.has(id) && visible.has(id));
  if (!ids.length) return false;
  event.preventDefault(); state.deleteShortcutBusy = true;
  // Reuse confirmation, unsaved-draft guards and the recoverable app trash API.
  trashItems([...new Set(ids)]).catch(report).finally(() => { state.deleteShortcutBusy = false; });
  return true;
}
function renderResourceGroups() { groupController()?.render($('#resourceItems')); const ids = new Set(selectableResourceIds()); state.selectedIds = new Set([...state.selectedIds].filter(id => ids.has(String(id)))); updateSelection(); }
let captureUI;
function markdownImageURL(tab,url) { return window.YingXuCapture?.imageURL(tab?.source === 'file' && tab.item.kind === 'markdown' ? tab.id : null,url) || null; }
function captureTarget() {
  const tab = activeTab(), target = {projectId:state.projectId || '',itemId:''};
  if ($('#appDialog').open || groupsIsOpen() || globalSearchIsOpen() || tab?.source !== 'file' || tab.item.kind !== 'markdown' || !tab.content?.editable || tab.loading || tab.saving || tab.mode === 'preview' || !tab.markdownEditor || !markdownInputReady(tab)) return target;
  if (String(tab.item.project_id) !== String(state.projectId)) return target;
  return {...target,itemId:tab.id,key:tab.key,draft:tab.draft,selection:tab.markdownEditor.getSelection()};
}
async function insertCapture(target,markdownText) {
  const tab = state.tabs.find(value => value.key === target.key);
  if (!tab || tab.id !== target.itemId || String(tab.item.project_id) !== String(target.projectId) || String(state.projectId) !== String(target.projectId) || state.activeKey !== tab.key || !tab.content?.editable || tab.mode === 'preview' || tab.saving || tab.markdownEditor?.isComposing() || tab.draft !== target.draft || !tab.markdownEditor?.insertText) return false;
  const at = target.selection || {from:tab.draft.length,to:tab.draft.length};
  const position = at.to;
  const separator = tab.draft.match(/\r\n|\r|\n/)?.[0] || '\n';
  const text = (position && !/[\r\n]$/.test(tab.draft.slice(0,position)) ? separator : '') + markdownText + separator;
  return tab.markdownEditor.insertText(text,position,position);
}
function captureController() {
  if (!captureUI && window.YingXuCapture) captureUI = window.YingXuCapture.install({api,getTarget:captureTarget,insert:insertCapture,toast,send:desktopMessage,
    refresh:async projectId => { await refreshProjects({preserveLocation:true}); if (state.section === 'assets' && String(state.projectId) === String(projectId)) await loadItems(); }});
  return captureUI;
}
function captureScreen() { hideMenu(); return desktopMessage('capture-request'); }
let globalSearchUI;
function globalSearchIsOpen() { return !!globalSearchUI?.isOpen(); }
function globalSearchDialog() {
  if (!globalSearchIsOpen() && (groupsIsOpen() || $('#appDialog').open || state.modalBusy || state.exitBusy || state.trashBusy || state.globalOpening || !markdownInputReady())) return false;
  if (!window.YingXuGlobalSearch) { toast('全局搜索尚未载入，请重新打开工作台。','error'); return false; }
  if (!globalSearchUI) globalSearchUI = window.YingXuGlobalSearch.install({api,openResult:openGlobalSearchResult,escapeHtml,toast,categoryLabel,
    canOpen:() => !groupsIsOpen() && !$('#appDialog').open && !state.modalBusy && !state.exitBusy && !state.trashBusy && !state.globalOpening && markdownInputReady()});
  hideMenu(); return globalSearchUI.open();
}
function searchShortcut(event) {
  if (!(event.ctrlKey || event.metaKey) || event.altKey || !['f','k'].includes(event.key.toLowerCase())) return false;
  event.preventDefault();
  if (event.key.toLowerCase() === 'k') { globalSearchDialog(); return true; }
  if ($('#appDialog').open || groupsIsOpen() || globalSearchIsOpen() || $('#searchInput').disabled) return true;
  hideMenu(); $('#searchInput').focus(); $('#searchInput').select(); return true;
}
function globalSearchLocation() {
  return JSON.stringify([state.projectId,state.section,state.category,state.folderId,state.folderScope,state.activeKey,
    state.q,state.status,state.kind,state.sort,state.offset,state.listSequence,$('#searchInput').value]);
}
async function openGlobalSearchResult(result) {
  if (state.globalOpening || !result || !['project','item','skill'].includes(result.type)) return false;
  state.globalOpening = true;
  try {
    if (!await guardProperties()) return false;
    const origin = globalSearchLocation();
    // Resolve the live record before changing navigation. Search results may be stale.
    const record = result.type === 'item' ? await api(`/api/items/${encodeURIComponent(result.id)}`) : result.type === 'skill' ? await api(`/api/skills/${encodeURIComponent(result.id)}`) : (await api('/api/projects')).projects.find(project => String(project.id) === String(result.id));
    if (origin !== globalSearchLocation()) return false;
    if (!record) throw new Error('这个搜索结果已不存在，请重新搜索。');
    const projectId = result.type === 'project' ? record.id : result.type === 'item' ? record.project_id : null;
    if (projectId) { await refreshProjects({preserveLocation:true}); await recordProjectVisit(projectId); }
    if (origin !== globalSearchLocation() || !await guardProperties()) return false;
    clearTimeout(searchTimer); state.q = ''; state.status = ''; state.kind = ''; state.offset = 0; state.selectedIds.clear();
    $('#searchInput').value = ''; $('#statusFilter').value = ''; $('#kindFilter').value = '';
    if (result.type === 'skill') {
      state.section = 'skills'; renderNavigation(); renderHero(); configureSection();
      const loading = loadSkills(), destination = globalSearchLocation();
      await loading;
      if (destination !== globalSearchLocation() || $('#appDialog').open || state.modalBusy) return false;
      await openSkill(record.id);
    } else {
      state.projectId = projectId; storage.set('yingxu:project',String(projectId)); state.section = 'assets';
      state.category = result.type === 'item' ? record.category : 'all'; state.folderId = result.type === 'item' ? record.folder_id || null : null;
      state.folderScope = 'current'; state.folderPage = 0; state.folders = []; state.counts = [];
      if (result.type === 'project') state.activeKey = null;
      renderNavigation(); renderHero(); configureSection(); renderWorkspace();
      const loading = loadItems(), destination = globalSearchLocation();
      await loading;
      if (destination !== globalSearchLocation() || $('#appDialog').open || state.modalBusy) return false;
      if (result.type === 'item') await openItem(record.id);
    }
    return true;
  } finally { state.globalOpening = false; }
}

let projectLibraryUI;
async function projectLibraryDialog(projectId) {
  if ($('#appDialog').open) return;
  if (!window.YingXuProjectLibrary) throw new Error('项目库尚未载入，请重新打开工作台。');
  if (!projectLibraryUI) projectLibraryUI = window.YingXuProjectLibrary.install({api,showDialog,choose,toast,escapeHtml,refreshProjects:async () => { await refreshProjects(); renderInspector(); },
    selectProject:async id => { if (!await guardProperties()) return false; state.section = 'assets'; state.activeKey = null; await selectProject(id); renderWorkspace(); configureSection(); return true; }});
  return projectLibraryUI.open(projectId ? {projectId} : undefined);
}

function renderNavigation() {
  $('#projectList').innerHTML = state.projects.length ? sidebarProjects().map(project => `<div class="project-row ${String(project.id) === String(state.projectId) ? 'active' : ''}"><button class="project-button ${String(project.id) === String(state.projectId) ? 'active' : ''}" data-project="${escapeHtml(project.id)}" title="${escapeHtml(project.name)}"><span class="project-initial">${escapeHtml(project.name?.slice(0,1) || '映')}</span><span class="project-name">${escapeHtml(project.name)}</span></button><button class="icon-button project-menu-button" data-project-menu="${escapeHtml(project.id)}" aria-label="${escapeHtml(project.name)} 项目选项" title="项目选项">${icon('more')}</button></div>`).join('') : '<button class="project-button" data-action="new-project"><span class="project-initial">+</span><span class="project-name">创建第一个项目</span></button>';
  if ($('#projectLibraryCount')) $('#projectLibraryCount').textContent = state.projects.length;
  const counts = Object.fromEntries((state.counts || []).map(category => [category.key, category.count]));
  $('#categoryNav').innerHTML = categoryDefs.map((category,index) => `${index === 3 || index === 6 ? '<div class="nav-category-gap"></div>' : ''}<button class="nav-item ${state.section === 'assets' && state.category === category.key ? 'active' : ''}" data-category="${category.key}">${icon(category.icon)}<span>${category.label}</span>${counts[category.key] ? `<small class="nav-count">${counts[category.key]}</small>` : ''}</button>`).join('') + `<div class="nav-category-gap"></div><button class="nav-item ${state.section === 'skills' ? 'active' : ''}" data-section="skills">${icon('skills')}<span>SKILL 库</span></button><button class="nav-item ${state.section === 'context' ? 'active' : ''}" data-section="context">${icon('context')}<span>AI 协作</span></button><button class="nav-item ${state.section === 'trash' ? 'active' : ''}" data-section="trash">${icon('trash')}<span>回收站</span></button>`;
  $('#sidebarTotal').textContent = currentProject()?.counts?.total || '0';
  $('#breadcrumbProject').textContent = currentProject()?.name || '开始创作';
  $('#importButton').disabled = !state.projectId || state.section !== 'assets';
  $('#rescanButton').disabled = !state.projectId;
}

function renderHero() {
  const project = currentProject(); const counts = project?.counts || {};
  const title = state.section === 'skills' ? 'SKILL 库' : state.section === 'context' ? 'AI 协作' : state.section === 'trash' ? '回收站' : project?.name || '我的项目';
  const description = state.section === 'skills' ? '管理创作规范，选择项目需要的能力。' : state.section === 'context' ? '复制项目交接文件，让 AI 接着处理当前进度。' : state.section === 'trash' ? '可以恢复，也可以确认后删除到 '+systemTrashName()+'。外部引用的原文件保留。' : project?.description || '';
  $('#projectHero').innerHTML = `<div class="compact-project-header"><div><h1 class="hero-title">${escapeHtml(title)}</h1>${description ? `<p class="hero-description">${escapeHtml(description)}</p>` : ''}</div>${state.section === 'trash' ? `<button class="button button-secondary" data-action="empty-trash" ${state.trashBusy ? 'disabled' : ''}>${icon('trash')}清空回收站</button>` : state.section === 'assets' && project ? `<span class="project-summary-inline">${counts.total || 0} 项资源 · ${counts.completed || 0}/${counts.shots || 0} 分镜完成</span>` : ''}</div>`;
}

async function refreshProjects({preserveLocation = false} = {}) {
  const previousProject = state.projectId; const result = await api('/api/projects'); state.projects = result.projects || [];
  if (state.bootstrap?.capabilities?.project_library) state.projectLibrary = await api('/api/project-library');
  if (!preserveLocation && (!state.projectId || !state.projects.some(project => String(project.id) === String(state.projectId)))) {
    const saved = storage.get('yingxu:project'); state.projectId = state.projects.find(project => String(project.id) === saved)?.id || state.projects[0]?.id || null;
  }
  if (!preserveLocation && (!state.projectId || String(previousProject) !== String(state.projectId))) { state.counts = []; state.folderId = null; state.folders = []; state.selectedIds.clear(); }
  renderNavigation(); renderHero();
}
async function refreshCategoryCounts() {
  const projectId = state.projectId; if (!projectId) { state.counts = []; renderNavigation(); return; }
  const result = await api(`/api/items?${new URLSearchParams({project:projectId,limit:1,offset:0})}`);
  if (String(projectId) === String(state.projectId)) { state.counts = result.categories || []; renderNavigation(); }
}
async function recordProjectVisit(id) {
  if (state.bootstrap?.capabilities?.project_library) { await api(`/api/project-library/${encodeURIComponent(id)}/visit`,{method:'POST',body:{}}); state.projectLibrary = {...state.projectLibrary,recent_ids:[String(id),...(state.projectLibrary?.recent_ids || []).filter(value => String(value) !== String(id))].slice(0,20)}; }
}
async function selectProject(id) {
  if (String(id) !== String(state.projectId) && !await guardProperties()) return;
  await recordProjectVisit(id);
  state.projectId = id; state.offset = 0; state.counts = []; state.folderId = null; state.folderPage = 0; state.folders = []; state.selectedIds.clear(); storage.set('yingxu:project',String(id)); renderNavigation(); renderHero();
  if (!activeTab()) renderInspector(); await loadSection();
}
async function selectCategory(category) { if ((state.section !== 'assets' || state.category !== category || state.folderId) && !await guardProperties()) return; state.section = 'assets'; state.category = category; state.folderId = null; state.folderPage = 0; state.folderScope = 'current'; state.selectedIds.clear(); state.offset = 0; renderNavigation(); renderHero(); configureSection(); await loadItems(); }
async function selectSection(section) { if (!await guardProperties()) return; state.section = section; state.offset = 0; state.activeKey = null; state.selectedIds.clear(); renderWorkspace(); renderNavigation(); renderHero(); configureSection(); await loadSection(); }
function configureSection() {
  const isAssets = state.section === 'assets'; $('.filterbar').hidden = !isAssets; $('.view-switch').hidden = !isAssets; $('.library-footer').hidden = state.section === 'context'; $('#folderToolbar').hidden = !isAssets; $('#folderStrip').hidden = !isAssets;
  $('#sectionTitle').textContent = state.section === 'skills' ? '全部 SKILL' : state.section === 'context' ? '项目交接文件' : state.section === 'trash' ? '已删除的内容' : state.folderId ? state.folders.find(folder => String(folder.id) === String(state.folderId))?.name || categoryLabel(state.category) : categoryLabel(state.category);
  $('#searchInput').placeholder = state.section === 'skills' ? '搜索 SKILL 名称与用途…' : state.section === 'trash' ? '搜索回收站…' : '搜索素材、剧本、标签…';
  $('#advancedSearch').disabled = !isAssets; $('#searchInput').disabled = state.section === 'context'; $('#folderScope').hidden = state.category === 'all'; $('#folderScope').value = state.folderScope;
  $$('.view-switch button').forEach(button => button.classList.toggle('active',button.dataset.view === state.view));
  if (state.section !== 'assets') $('#activeQuery').hidden = true;
}
async function loadSection() { if (state.section === 'skills') return loadSkills(); if (state.section === 'context') return loadContext(); if (state.section === 'trash') return loadTrash(); return loadItems(); }

async function loadItems() {
  state.listController?.abort(); const controller = new AbortController(); state.listController = controller; const sequence = ++state.listSequence;
  state.loadingItems = true; state.selectedIds.clear(); state.selectionAnchor = null; hideMenu(); updateSelection(); configureSection(); renderQuery();
  if (!state.projectId) { state.items = []; state.total = 0; state.loadingItems = false; renderItems(); renderInspector(); return; }
  $('#resourceItems').className = 'resource-grid'; $('#resourceItems').innerHTML = Array.from({length:4},() => '<div class="skeleton" aria-hidden="true"></div>').join('');
  const params = new URLSearchParams({project:state.projectId,limit:state.limit,offset:state.offset,sort:state.sort});
  if (state.category !== 'all') { params.set('category',state.category); params.set('folder',state.folderScope === 'all' ? '' : state.folderId || 'root'); } if (state.q) params.set('q',state.q); if (state.status) params.set('status',state.status); if (state.kind) params.set('kind',state.kind);
  try {
    const [result,folders] = await Promise.all([api(`/api/items?${params}`,{signal:controller.signal}),state.category !== 'all' ? api(`/api/folders?${new URLSearchParams({project:state.projectId,category:state.category})}`,{signal:controller.signal}) : Promise.resolve({folders:[]})]); if (sequence !== state.listSequence || state.section !== 'assets') return;
    state.loadingItems = false; state.folders = folders.folders || []; state.foldersTruncated = !!folders.truncated; state.items = result.items || []; state.total = result.total || 0; state.counts = result.categories || []; state.selectedIds = new Set([...state.selectedIds].filter(id => state.items.some(item => String(item.id) === String(id)))); renderItems(); renderNavigation();
    $('#searchTiming').textContent = state.q && result.elapsed_ms != null ? `${Math.round(result.elapsed_ms)} ms` : '';
    try { await groupController()?.refresh(); if (sequence === state.listSequence && state.section === 'assets') renderResourceGroups(); } catch(error) { report(error); }
  } catch(error) { if (error.name === 'AbortError' || sequence !== state.listSequence || state.section !== 'assets') return; state.loadingItems = false; state.items = []; updateSelection(); $('#resourceItems').innerHTML = emptyHtml('暂时没能读取资源',error.message,'refresh','重试','retry'); report(error); }
}
function renderQuery() { $('#activeQuery').hidden = !state.q; $('#activeQuery').innerHTML = `<span>检索：${escapeHtml(state.q)}</span><button class="icon-button" data-action="clear-search" aria-label="清除检索">${icon('close')}</button>`; }
function emptyHtml(title,description,iconName='folder',buttonLabel='',action='') { return `<div class="empty-state"><div class="empty-state-icon">${icon(iconName)}</div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p>${buttonLabel ? `<div class="empty-state-actions"><button class="button button-secondary" data-action="${action}">${escapeHtml(buttonLabel)}</button></div>` : ''}</div>`; }
function visualHtml(item) {
  const isMedia = ['image','video'].includes(item.kind); const isDocument = ['markdown','text','docx'].includes(item.kind);
  const thumb = isMedia ? `<img draggable="false" data-thumbnail="${escapeHtml(item.id)}" data-url="${escapeHtml(item.thumbnail_url || `/api/thumbnail/${encodeURIComponent(item.id)}`)}" alt="${escapeHtml(item.name)}" loading="lazy" decoding="async">` : '';
  const document = isDocument ? `<div class="document-preview ${item.kind === 'docx' ? 'docx' : ''}">${icon(kindIcons[item.kind])}<span>${escapeHtml(kindLabels[item.kind])}</span></div>` : `<div class="card-fallback">${icon(kindIcons[item.kind])}</div>`;
  const duration = item.metadata?.duration; return `<div class="card-visual ${escapeHtml(item.kind)}">${document}${thumb}<span class="file-kind">${icon(kindIcons[item.kind])}${escapeHtml(item.ext?.replace('.','').toUpperCase() || kindLabels[item.kind] || 'FILE')}</span><span class="card-drag-handle" data-drag-file="${escapeHtml(item.id)}" draggable="false" role="button" tabindex="0" title="按住拖出真实文件（桌面版）" aria-label="拖出 ${escapeHtml(item.name)}">${icon('upload')}</span>${item.kind === 'video' ? `<span class="card-play">${icon('play')}</span>` : ''}${duration ? `<span class="card-duration">${escapeHtml(duration)} 秒</span>` : ''}</div>`;
}
function itemCheckbox(item) { return `<label class="item-selection"><input type="checkbox" data-select-item="${escapeHtml(item.id)}" aria-label="选择 ${escapeHtml(item.name)}" ${state.selectedIds.has(String(item.id)) ? 'checked' : ''}></label>`; }
function itemMenuButton(item) { return `<button class="icon-button resource-more-button" data-item-menu="${escapeHtml(item.id)}" aria-label="${escapeHtml(item.name)} 文件选项" title="文件选项">${icon('more')}</button>`; }
function cardHtml(item,board = false) { const metadata = item.metadata || {}; return `<article class="resource-card ${state.activeKey === `file:${item.id}` ? 'selected' : ''} ${state.selectedIds.has(String(item.id)) ? 'checked' : ''}" tabindex="0" role="button" draggable="true" data-item="${escapeHtml(item.id)}" aria-label="打开 ${escapeHtml(item.name)}" title="${escapeHtml(item.name)}">${itemCheckbox(item)}${itemMenuButton(item)}${visualHtml(item)}<div class="card-copy"><h3 class="card-name">${escapeHtml(item.name)}</h3><div class="card-meta">${statusHtml(item.status)}<span>${escapeHtml(item.folder_path || categoryLabel(item.category))}</span></div>${board && (metadata.shot_number || metadata.shot_size || metadata.duration) ? `<div class="board-shot-details">${[metadata.shot_number ? `镜 ${metadata.shot_number}` : '',metadata.shot_size,metadata.duration ? `${metadata.duration}s` : ''].filter(Boolean).map(value => `<span>${escapeHtml(value)}</span>`).join('')}</div>` : ''}${item.tags?.length ? `<div class="card-tags">${item.tags.slice(0,3).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}</div>` : ''}</div></article>`; }
function rowHtml(item) { return `<div class="resource-row ${state.activeKey === `file:${item.id}` ? 'selected' : ''} ${state.selectedIds.has(String(item.id)) ? 'checked' : ''}" tabindex="0" role="button" draggable="true" data-item="${escapeHtml(item.id)}" aria-label="打开 ${escapeHtml(item.name)}">${itemCheckbox(item)}<div class="row-thumb">${icon(kindIcons[item.kind])}${['image','video'].includes(item.kind) ? `<img draggable="false" data-thumbnail="${escapeHtml(item.id)}" data-url="${escapeHtml(item.thumbnail_url || `/api/thumbnail/${encodeURIComponent(item.id)}`)}" alt="" loading="lazy" decoding="async" hidden>` : ''}</div><div class="row-copy"><div class="row-name">${escapeHtml(item.name)}</div><div class="row-tags">${escapeHtml((item.tags || []).join(' · ') || item.folder_path || kindLabels[item.kind] || '文件')}</div></div><span class="row-category">${escapeHtml(categoryLabel(item.category))}</span>${statusHtml(item.status)}<span class="row-date">${formatDate(item.updated || item.mtime)}</span>${itemMenuButton(item)}</div>`; }
function renderItems() {
  const root = $('#resourceItems'); $('#resourceCount').textContent = state.total; $('#resourceViewport').scrollTop = 0;
  if (!state.projectId) { root.className = 'resource-grid'; root.innerHTML = `<div class="empty-state"><div class="empty-state-icon">${icon('folder')}</div><h3>创建一个项目</h3><p>按剧本、分镜、角色、场景和道具整理文件。</p><div class="empty-state-actions"><button class="button button-primary" data-action="new-project">${icon('plus')}创建项目</button><button class="button button-secondary" data-action="demo">打开示例</button></div></div>`; }
  else if (!state.items.length) { root.className = 'resource-grid'; const filtered = state.q || state.status || state.kind; root.innerHTML = emptyHtml(filtered ? '没有符合条件的文件' : '这个位置还没有文件',filtered ? '可以减少筛选条件，或选择“此分类全部”。' : '导入文件、新建文档，或把文件拖到这里。',filtered ? 'search' : 'folder',filtered ? '清除筛选' : '导入文件',filtered ? 'clear-filters' : 'import'); }
  else if (state.view === 'list') { root.className = 'resource-list'; root.innerHTML = '<div class="list-header"><span></span><span></span><span>资源名称</span><span>分类</span><span>制作状态</span><span>更新</span><span></span></div>' + state.items.map(rowHtml).join(''); }
  else if (state.view === 'board') { root.className = 'storyboard'; root.innerHTML = statuses.map(status => { const items = state.items.filter(item => (item.status || '待开始') === status); return `<section class="board-column"><div class="board-column-heading">${statusHtml(status)}<span class="board-count">${items.length}</span></div>${items.length ? items.map(item => cardHtml(item,true)).join('') : '<div class="board-empty">这个阶段还没有资源</div>'}</section>`; }).join(''); }
  else { root.className = 'resource-grid'; root.innerHTML = state.items.map(item => cardHtml(item)).join(''); }
  renderFolders(); updateSelection(); updatePagination(); observeThumbnails();
  renderResourceGroups();
}
function updatePagination() { const total = state.section === 'skills' ? state.skills.length : state.total; const current = Math.floor(state.offset/state.limit)+1; const pages = Math.max(1,Math.ceil(total/state.limit)); $('#pageNumber').textContent = `${current} / ${pages}`; $('#previousPage').disabled = state.offset <= 0; $('#nextPage').disabled = state.offset + state.limit >= total; $('#resultSummary').textContent = total ? `第 ${state.offset+1}–${Math.min(state.offset+state.limit,total)} 项 · 共 ${total} 项${state.view === 'board' && state.section === 'assets' ? ' · 看板展示本页' : ''}` : '本地文件，安心创作'; }

function currentFolder() { return state.folders.find(folder => String(folder.id) === String(state.folderId)); }
function renderFolders() {
  const isCategory = state.section === 'assets' && state.category !== 'all' && !!state.projectId;
  const map = new Map(state.folders.map(folder => [String(folder.id),folder])); const chain = []; let folder = currentFolder();
  while (folder && chain.length < 40 && !chain.some(value => String(value.id) === String(folder.id))) { chain.unshift(folder); folder = map.get(String(folder.parent_id)); }
  $('#folderBreadcrumb').innerHTML = isCategory ? `<button data-folder-open="root" data-folder-drop="root" data-folder-category="${escapeHtml(state.category)}">${icon('folder')}${escapeHtml(categoryLabel(state.category))}</button>${chain.map(value => `<span class="breadcrumb-slash">/</span><button data-folder-open="${escapeHtml(value.id)}" data-folder-drop="${escapeHtml(value.id)}" data-folder-category="${escapeHtml(value.category)}">${escapeHtml(value.name)}</button>`).join('')}` : `<span>${state.projectId ? '全部分类中的文件' : '先创建一个项目'}</span>`;
  const folderTerms = state.q.split(/\s+/).filter(term => term && !term.includes(':')).map(term => term.toLocaleLowerCase());
  const children = isCategory ? state.folders.filter(value => String(value.parent_id || '') === String(state.folderId || '') && folderTerms.every(term => `${value.name} ${value.folder_path || ''}`.toLocaleLowerCase().includes(term))) : [];
  const folderPages = Math.max(1,Math.ceil(children.length/12)); state.folderPage = Math.min(state.folderPage || 0,folderPages-1); const visibleChildren = children.slice(state.folderPage*12,state.folderPage*12+12);
  $('#folderStrip').hidden = !children.length;
  $('#folderStrip').innerHTML = visibleChildren.map(value => `<div class="folder-card" tabindex="0" role="button" data-folder-open="${escapeHtml(value.id)}" data-folder-drop="${escapeHtml(value.id)}" data-folder-category="${escapeHtml(value.category)}" aria-label="打开文件夹 ${escapeHtml(value.name)}">${icon('folder')}<span class="folder-card-copy"><strong>${escapeHtml(value.name)}</strong><small>${value.count || 0} 个文件</small></span><button class="icon-button folder-menu-button" data-folder-menu="${escapeHtml(value.id)}" title="文件夹选项" aria-label="${escapeHtml(value.name)} 文件夹选项">${icon('more')}</button></div>`).join('') + (folderPages > 1 ? `<div class="folder-pager"><span>${children.length} 个文件夹 · ${state.folderPage+1}/${folderPages}</span><button class="icon-button" data-folder-page="-1" title="上一页文件夹" ${state.folderPage === 0 ? 'disabled' : ''}>${icon('left')}</button><button class="icon-button" data-folder-page="1" title="下一页文件夹" ${state.folderPage >= folderPages-1 ? 'disabled' : ''}>${icon('chevron')}</button></div>` : '');
  if (state.foldersTruncated) $('#folderBreadcrumb').insertAdjacentHTML('beforeend','<span class="folder-limit-note">当前分类文件夹过多，仅展示索引中的前 5000 项</span>');
  $('#newFolderButton').disabled = !state.projectId; $('#sectionTitle').textContent = currentFolder()?.name || categoryLabel(state.category);
}
function updateSelection() {
  $('#batchPropertiesButton').disabled = !state.selectedIds.size || !!state.loadingItems;
  const count = state.selectedIds.size; $('#selectionCount').hidden = !count; $('#selectionCount').textContent = `已选 ${count} 项`; $('#moveSelectionButton').disabled = !count || !!state.loadingItems; $('#deleteSelectionButton').disabled = (!count && !state.folderId) || !!state.loadingItems;
  $('#deleteSelectionButton').innerHTML = `${icon('trash')}${count || !state.folderId ? '删除' : '删除文件夹'}`;
  const visibleCount = selectableResourceIds().length; $('#selectPageButton').disabled = !visibleCount || !!state.loadingItems; $('#selectPageButton').textContent = count && count === visibleCount ? '取消选择' : '全选本页';
  $$('#resourceItems [data-item]').forEach(node => node.classList.toggle('checked',state.selectedIds.has(String(node.dataset.item))));
  $$('[data-select-item]').forEach(input => input.checked = state.selectedIds.has(String(input.dataset.selectItem)));
  if (count && window.yingxuDesktopDrag && window.chrome?.webview?.postMessage) window.chrome.webview.postMessage({action:'prepare-drag-files',ids:[...state.selectedIds].slice(0,200)});
}
function selectResource(id,event = {},toggle = false) {
  id = String(id);
  // Use displayed order, including status columns in board view.
  const ids = $$('#resourceItems [data-item]').filter(node => !node.hasAttribute?.('data-yx-group-hidden')).map(node => String(node.dataset.item));
  const end = ids.indexOf(id); if (end < 0) return;
  const start = ids.indexOf(state.selectionAnchor);
  if (event.shiftKey && start >= 0) {
    if (!event.ctrlKey && !event.metaKey) state.selectedIds.clear();
    ids.slice(Math.min(start,end),Math.max(start,end)+1).forEach(value => state.selectedIds.add(value));
  } else {
    if (toggle || event.ctrlKey || event.metaKey) {
      if (state.selectedIds.has(id)) state.selectedIds.delete(id); else state.selectedIds.add(id);
    } else { state.selectedIds.clear(); state.selectedIds.add(id); }
    state.selectionAnchor = id;
  }
  updateSelection();
}
async function openFolder(id) {
  const next = id === 'root' ? null : id; if (String(next || '') !== String(state.folderId || '') && !await guardProperties()) return;
  state.folderId = next; state.folderPage = 0; state.folderScope = 'current'; state.offset = 0; state.selectedIds.clear(); configureSection(); await loadItems(); if (!activeTab()) renderInspector();
}
async function batchPropertiesDialog(ids = [...state.selectedIds], focus = 'tags') {
  if (state.section !== 'assets' || !state.projectId || state.loadingItems || state.batchPropertiesOpening || $('#appDialog').open) return;
  const projectId = state.projectId, visible = new Set(selectableResourceIds());
  const selected = [...new Set(ids.map(String))];
  if (!selected.length) return;
  if (selected.length > 200 || selected.some(id => !visible.has(id) || !state.items.some(item => String(item.id) === id && String(item.project_id) === String(projectId)))) throw new Error('所选素材已变化，请重新选择后批量编辑。');
  state.batchPropertiesOpening = true;
  try {
    for (const tab of fileTabs(selected)) {
      if (tab.loading || tab.error || !tab.detailReady) throw new Error('所选素材信息尚未载入，请稍后重试。');
      if (tab.saving || tab.propertiesSaving || !await guardProperties(tab)) return;
    }
    if (state.projectId !== projectId || state.section !== 'assets' || $('#appDialog').open) return;
    if (selected.some(id => !selectableResourceIds().includes(id))) throw new Error('所选素材已不在当前列表，请重新选择后批量编辑。');
    let submitting = false;
    showDialog({title:`批量编辑 ${selected.length} 项素材`,subtitle:'仅修改下方指定的信息；新增标签会保留每项素材原有的标签。',submit:'应用到所选素材',body:`<div class="field"><label for="batchTags">添加标签</label><input id="batchTags" name="tags_add" placeholder="多个标签用逗号分隔，留空则不修改" maxlength="5000" ${focus === 'tags' ? 'autofocus' : ''}></div><div class="field"><label for="batchStatus">制作状态</label><select id="batchStatus" name="status" ${focus === 'status' ? 'autofocus' : ''}><option value="">保持各自状态</option>${statuses.map(status => `<option value="${escapeHtml(status)}">${escapeHtml(status)}</option>`).join('')}</select></div>`,onSubmit:async form => {
      if (submitting) return false;
      if (state.projectId !== projectId || state.section !== 'assets') throw new Error('当前项目已变化，请重新选择素材。');
      if (state.loadingItems || selected.some(id => !selectableResourceIds().includes(id))) throw new Error('所选素材已不在当前列表，请重新选择后批量编辑。');
      if (fileTabs(selected).some(tab => tab.loading || tab.error || !tab.detailReady || tab.saving || tab.propertiesSaving || tab.propertiesDirty || !markdownInputReady(tab))) throw new Error('所选素材信息尚未载入或正在编辑，请载入并保存制作信息后重试。');
      const data = new FormData(form), tags = [...new Set(String(data.get('tags_add') || '').split(/[,，\n]/).map(value => value.trim()).filter(Boolean))];
      const status = String(data.get('status') || '');
      if (!tags.length && !status) throw new Error('请添加标签或选择制作状态。');
      if (tags.length > 50 || tags.some(tag => [...tag].length > 80)) throw new Error('最多添加 50 个标签，每个标签最多 80 字。');
      if (status && !statuses.includes(status)) throw new Error('请选择有效的制作状态。');
      const body = {project_id:projectId,ids:selected}; if (tags.length) body.tags_add = tags; if (status) body.status = status;
      submitting = true;
      try {
        const result = await api('/api/items/batch-properties',{method:'POST',body});
        for (const updated of result.items) {
          for (const tab of fileTabs([updated.id])) {
            tab.item = {...tab.item,status:updated.status,tags:updated.tags,updated:updated.updated};
            if (!tab.propertiesDirty) tab.propertiesDraft = null;
          }
        }
        persistDrafts(true); renderTabs(); renderInspector(); if (activeTab()) renderEditorStatus(activeTab());
        await refreshProjects().catch(report); if (state.projectId === projectId && state.section === 'assets') await loadItems().catch(report);
        toast(`已更新 ${result.items.length} 项素材。`);
      } finally { submitting = false; }
    }});
  } finally { state.batchPropertiesOpening = false; }
}
function folderOptions(folders,selected) { return '<option value="">分类根目录</option>' + [...folders].sort((a,b) => String(a.relative_path || a.folder_path || a.name).localeCompare(String(b.relative_path || b.folder_path || b.name),'zh-CN')).map(folder => `<option value="${escapeHtml(folder.id)}" ${String(selected) === String(folder.id) ? 'selected' : ''}>${escapeHtml(folder.folder_path || folder.relative_path || folder.name)}</option>`).join(''); }
async function folderChoices(projectId,category) { const result = await api(`/api/folders?${new URLSearchParams({project:projectId,category})}`); return result.folders || []; }
function bindFolderSelector(dialog,categorySelector,folderSelector,projectId,initialCategory,initialFolderId) {
  let request = 0; const modal = state.modalSequence;
  const populate = async () => { const sequence = ++request; const category = $(categorySelector).value; const select = $(folderSelector); select.disabled = true; select.dataset.loadState = 'loading';
    try { const folders = await folderChoices(projectId,category); if (dialog.open && state.modalSequence === modal && sequence === request) { if (category === initialCategory && initialFolderId && !folders.some(folder => String(folder.id) === String(initialFolderId))) throw new Error('原文件夹已不存在，请重新选择创建位置。'); select.innerHTML = folderOptions(folders,category === initialCategory ? initialFolderId : null); select.dataset.loadState = 'ready'; } }
    catch(error) { if (dialog.open && state.modalSequence === modal && sequence === request) { select.dataset.loadState = 'error'; $('#dialogError').textContent = error.message; $('#dialogError').hidden = false; } }
    finally { if (dialog.open && state.modalSequence === modal && sequence === request) select.disabled = false; }
  }; $(categorySelector).addEventListener('change',populate); populate();
}
function requireFolderSelection(selector) { const select = $(selector); if (select.disabled || select.dataset.loadState === 'loading') throw new Error('文件夹列表正在加载，请稍后重试。'); if (select.dataset.loadState === 'error') throw new Error('文件夹列表未能读取，请重新选择分类或重新打开此窗口。'); }
async function newFolderDialog() {
  if (!state.projectId) return newProjectDialog(); if (!await guardProperties()) return;
  const initial = state.category === 'all' ? 'scripts' : state.category; const projectId = state.projectId;
  const dialog = showDialog({title:'新建文件夹',subtitle:'用第 1 集、共用角色等子文件夹继续组织项目。',submit:'创建文件夹',body:`<div class="field"><label for="folderName">文件夹名称</label><input id="folderName" name="name" placeholder="例如：第 1 集、共用角色" required maxlength="100" autofocus></div><div class="field"><label for="folderCategory">分类</label><select id="folderCategory" name="category">${optionHtml(categoryDefs.filter(value => value.key !== 'all'),initial)}</select></div><div class="field"><label for="folderParent">创建在</label><select id="folderParent" name="parent_id">${folderOptions(state.category === initial ? state.folders : [],state.category === initial ? state.folderId : null)}</select></div>`,onSubmit:async form => { const data = new FormData(form); const category = data.get('category'); const created = await api('/api/folders',{method:'POST',body:{project_id:projectId,category,parent_id:data.get('parent_id') || null,name:String(data.get('name')).trim()}}); state.section = 'assets'; state.category = category; state.folderId = data.get('parent_id') || null; state.folderScope = 'current'; state.offset = 0; state.selectedIds.clear(); renderNavigation(); renderHero(); await loadItems(); toast(`已创建文件夹「${created.name}」。`); }});
  let sequence = 0; const populate = async () => { const seq = ++sequence; const category = $('#folderCategory').value; try { const folders = await folderChoices(projectId,category); if (dialog.open && seq === sequence) $('#folderParent').innerHTML = folderOptions(folders,category === initial ? state.folderId : null); } catch(error) { if (dialog.open) { $('#dialogError').textContent = error.message; $('#dialogError').hidden = false; } } };
  $('#folderCategory').addEventListener('change',populate); await populate();
}

function hideMenu(restoreFocus = false) { const anchor = state.menu?.anchor; $('#resourceMenu').hidden = true; state.menu = null; if (restoreFocus) anchor?.focus(); }
function showMenu(anchor,kind,id,point = null) {
  const item = kind === 'skill' ? state.skills.find(value => String(value.id) === String(id)) || state.tabs.find(tab => tab.source === 'skill' && String(tab.id) === String(id))?.item : null;
  const commands = kind === 'project' ? [['new-note','新建笔记','script'],['classify-project','移到项目分类…','folder'],['reveal-project','打开项目文件夹','folder'],['rename-project','编辑项目名称','file'],['trash-project','删除项目','trash']] : kind === 'folder' ? [['open-folder','在工作台中进入','open'],['new-note','新建笔记','script'],['reveal-folder','打开文件夹','folder'],['rename-folder','重命名文件夹','file'],['trash-folder','删除文件夹','trash']] : kind === 'location' ? [['new-note','新建笔记','script'],['reveal-location','打开文件夹','folder']] : kind === 'skill' ? [['open-skill','打开 SKILL','skills'],['reveal-skill','打开 SKILL 所在位置','folder'],['trash-skill',item?.editable ? '删除自建 SKILL' : '隐藏这个 SKILL','trash']] : [['open-item','打开','file'],['new-note','新建笔记','script'],['reveal-item','打开所在文件夹','folder'],['group-items','将所选素材合为一组','folder'],['manage-groups','管理素材组','folder'],['batch-tags','批量添加标签…','plus'],['batch-status','批量修改制作状态…','check'],['move-items','移动到…','move'],['rename-item','重命名文件','file'],['trash-items','删除文件','trash']];
  const folder = kind === 'folder' ? state.folders.find(value => String(value.id) === String(id)) : null;
  const resource = kind === 'item' ? state.items.find(value => String(value.id) === String(id)) : null;
  const location = kind === 'location' ? {...id} : kind === 'project' ? {project_id:id,category:'scripts',folder_id:null} : {project_id:state.projectId,category:folder?.category || resource?.category || state.category,folder_id:kind === 'folder' ? id : resource ? resource.folder_id : state.folderId};
  const menu = $('#resourceMenu'); state.menu = {kind,id,projectId:state.projectId,location,anchor}; menu.innerHTML = commands.map(([command,label,iconName]) => `<button type="button" role="menuitem" data-menu-command="${command}" class="${command.startsWith('trash-') ? 'menu-danger' : ''}">${icon(iconName)}<span>${label}</span></button>`).join('');
  menu.hidden = false; const rect = anchor.getBoundingClientRect(); menu.style.left = `${Math.max(8,Math.min(point ? point.x : rect.right-menu.offsetWidth,window.innerWidth-menu.offsetWidth-10))}px`; menu.style.top = `${Math.max(8,Math.min(point ? point.y : rect.bottom+5,window.innerHeight-menu.offsetHeight-10))}px`; $('button',menu)?.focus();
}
function contextMenuTarget(target) {
  if (target.closest('input,textarea,select,[contenteditable],#appDialog,#resourceMenu')) return null;
  for (const [selector,kind,attribute] of [['[data-folder-open]','folder','data-folder-open'],['.resource-card[data-item],.resource-row[data-item]','item','data-item'],['.project-row','project',null],['[data-skill]','skill','data-skill']]) {
    const anchor = target.closest(selector);
    if (anchor) { const id = attribute ? anchor.getAttribute(attribute) : $('[data-project]',anchor)?.dataset.project; if (kind === 'folder' && id === 'root') return {anchor,kind:'location',id:{project_id:state.projectId,category:anchor.dataset.folderCategory || state.category}}; if (id) return {anchor,kind,id}; }
  }
  const category = target.closest('[data-category]');
  if (category && state.projectId) return {anchor:category,kind:'location',id:{project_id:state.projectId,category:category.dataset.category}};
  const area = target.closest('#resourceViewport,#folderStrip,#folderToolbar');
  if (area && state.section === 'assets' && state.projectId) return {anchor:area,kind:'location',id:{project_id:state.projectId,category:state.category,folder_id:state.folderId}};
  return null;
}
async function runMenu(command,context) {
  const id = context.id;
  try {
    if (command === 'new-note') return newItemDialog(null,{note:true,location:context.location});
    if (command === 'open-item') return openItem(id); if (command === 'open-skill') return openSkill(id); if (command === 'open-folder') return openFolder(id);
    if (command === 'reveal-skill') return api('/api/open-folder',{method:'POST',body:{skill_id:id}});
    if (command === 'reveal-item') return api('/api/open',{method:'POST',body:{id,action:'reveal'}});
    if (command === 'reveal-project') return api('/api/open-folder',{method:'POST',body:{project_id:id}});
    if (command === 'reveal-folder') return api('/api/open-folder',{method:'POST',body:{project_id:context.projectId,folder_id:id}});
    if (command === 'reveal-location') return api('/api/open-folder',{method:'POST',body:id});
    if (command === 'classify-project') return projectLibraryDialog(id);
    if (command === 'rename-project') return projectRenameDialog(id); if (command === 'rename-folder') return folderRenameDialog(id);
    if (command === 'rename-item') { await openItem(id); if (String(activeTab()?.id) === String(id)) return renameDialog(); return; }
    const ids = state.selectedIds.has(String(id)) ? [...state.selectedIds] : [id];
    if (command === 'batch-tags' || command === 'batch-status') return batchPropertiesDialog(ids,command === 'batch-status' ? 'status' : 'tags');
    if (command === 'group-items') return groupController()?.create(ids); if (command === 'manage-groups') return groupController()?.open();
    if (command === 'move-items') return moveDialog(ids); if (command === 'trash-items') return trashItems(ids);
    if (command === 'trash-project') return trashProject(id); if (command === 'trash-folder') return trashFolder(id); if (command === 'trash-skill') return trashSkill(id);
  } catch(error) { report(error); }
}
async function prepareTabs(tabs) {
  for (const tab of tabs) {
    if (!await guardProperties(tab)) return false;
    if (tab.dirty) { const choice = await choose('文档还有未保存的修改',`先处理「${tab.item.name}」的修改，再继续整理文件。`,[{key:'cancel',label:'继续编辑',style:'ghost'},{key:'discard',label:'放弃修改',style:'secondary'},{key:'save',label:'保存文档',style:'primary'}]); if (!choice || choice === 'cancel') return false; if (choice === 'save' && !await saveTab(tab)) return false; if (choice === 'discard') { tab.dirty = false; tab.draft = String(tab.content?.content || ''); tab.paragraphs = (tab.content?.paragraphs || []).map(paragraph => ({...paragraph})); delete state.drafts[tab.key]; } }
  }
  persistDrafts(true); renderTabs();
  if (tabs.some(tab => tab.dirty || tab.propertiesDirty || tab.saving || tab.propertiesSaving || !markdownInputReady(tab))) return false;
  if (tabs.includes(activeTab())) { renderEditorBody(activeTab()); renderEditorStatus(activeTab()); } return true;
}
function fileTabs(ids) { const keys = new Set(ids.map(String)); return state.tabs.filter(tab => tab.source === 'file' && keys.has(String(tab.id))); }
function removeOpenTabs(tabs) { const keys = new Set(tabs.map(tab => tab.key)); state.tabs = state.tabs.filter(tab => !keys.has(tab.key)); for (const key of keys) delete state.drafts[key]; if (keys.has(state.activeKey)) state.activeKey = state.tabs.at(-1)?.key || null; persistDrafts(true); renderWorkspace(); }
async function refreshOpenItems(projectId) {
  const tabs = state.tabs.filter(tab => tab.source === 'file' && !tab.loading && (!projectId || String(tab.item.project_id) === String(projectId)));
  for (let index = 0; index < tabs.length; index += 4) { const batch = tabs.slice(index,index+4); const results = await Promise.allSettled(batch.map(tab => api(`/api/items/${encodeURIComponent(tab.id)}`))); results.forEach((result,i) => { if (result.status === 'fulfilled') batch[i].item = result.value; else report(result.reason); }); }
  renderTabs(); renderInspector();
}
async function moveDialog(ids) {
  if (!ids.length || !await prepareTabs(fileTabs(ids))) return;
  const sample = state.items.find(item => String(item.id) === String(ids[0])) || state.tabs.find(tab => String(tab.id) === String(ids[0]))?.item; if (!sample) throw new Error('请重新选择要移动的文件。');
  const projectId = sample.project_id; const initial = sample.category || 'references'; let sequence = 0;
  const dialog = showDialog({title:ids.length === 1 ? '移动文件' : `移动 ${ids.length} 个文件`,subtitle:'项目内文件会移到目标目录；外部引用只调整工作台位置。',submit:'移动到这里',body:`<div class="field"><label for="moveCategory">目标分类</label><select id="moveCategory" name="category">${optionHtml(categoryDefs.filter(value => value.key !== 'all'),initial)}</select></div><div class="field"><label for="moveFolder">目标文件夹</label><select id="moveFolder" name="folder_id"><option value="">分类根目录</option></select></div><p class="dialog-hint">同名文件不会覆盖。项目内文件路径改变后，外部工具中引用的旧路径可能需要更新。</p>`,onSubmit:async form => { const data = new FormData(form); await performMove(ids,data.get('category'),data.get('folder_id') || null); }});
  const populate = async () => { const seq = ++sequence; const category = $('#moveCategory').value; $('#moveFolder').disabled = true; try { const folders = await folderChoices(projectId,category); if (dialog.open && seq === sequence) $('#moveFolder').innerHTML = folderOptions(folders,null); } catch(error) { if (dialog.open) { $('#dialogError').textContent = error.message; $('#dialogError').hidden = false; } } finally { if (dialog.open && seq === sequence) $('#moveFolder').disabled = false; } }; $('#moveCategory').addEventListener('change',populate); await populate();
}
async function performMove(ids,category,folderId) {
  if (!ids.length || !await prepareTabs(fileTabs(ids))) return false;
  const result = await api('/api/move',{method:'POST',body:{ids,category,folder_id:folderId || null}});
  for (const item of result.items || []) { const tab = state.tabs.find(tab => tab.source === 'file' && String(tab.id) === String(item.id)); if (tab) tab.item = {...tab.item,...item}; }
  state.selectedIds.clear(); await refreshProjects(); if (state.section === 'assets') await loadItems(); renderTabs(); renderInspector();
  const stats = result.stats || {}; toast(`整理完成${stats.moved ? `：${stats.moved} 个项目文件已移动` : ''}${stats.referenced ? `，${stats.referenced} 个外部引用保留原位` : ''}。`); return true;
}

async function projectRenameDialog(id) {
  const project = state.projects.find(value => String(value.id) === String(id)); if (!project) return;
  showDialog({title:'编辑项目',subtitle:'修改显示名称和简介，项目磁盘目录保持不变。',submit:'保存',body:`<div class="field"><label for="renameProjectName">项目名称</label><input id="renameProjectName" name="name" value="${escapeHtml(project.name)}" required maxlength="80"></div><div class="field"><label for="renameProjectDescription">简介</label><textarea id="renameProjectDescription" name="description">${escapeHtml(project.description || '')}</textarea></div>`,onSubmit:async form => { const data = new FormData(form); await api(`/api/projects/${encodeURIComponent(id)}`,{method:'PATCH',body:{name:String(data.get('name')).trim(),description:String(data.get('description')).trim()}}); await refreshProjects(); renderInspector(); toast('项目已更新。'); }});
}
function descendantFolderIds(id) { const result = new Set([String(id)]); let changed = true; while (changed && result.size <= state.folders.length) { changed = false; for (const folder of state.folders) if (result.has(String(folder.parent_id)) && !result.has(String(folder.id))) { result.add(String(folder.id)); changed = true; } } return result; }
async function folderRenameDialog(id) {
  const folder = state.folders.find(value => String(value.id) === String(id)); if (!folder) return; const descendants = descendantFolderIds(id); const tabs = state.tabs.filter(tab => tab.source === 'file' && descendants.has(String(tab.item.folder_id))); if (!await prepareTabs(tabs)) return;
  showDialog({title:'重命名文件夹',subtitle:'项目里的真实目录也会改名，外部软件使用的旧路径需要同步更新。',submit:'重命名',body:`<div class="field"><label for="renameFolderName">文件夹名称</label><input id="renameFolderName" name="name" value="${escapeHtml(folder.name)}" required maxlength="100"></div>`,onSubmit:async form => { await api(`/api/folders/${encodeURIComponent(id)}`,{method:'PATCH',body:{name:String(new FormData(form).get('name')).trim()}}); await refreshOpenItems(folder.project_id); await loadItems(); toast('文件夹已重命名。'); }});
}
function undoToast(message,result,kind) {
  const id = result.batch_id || result.id; if (!id) { toast(message); return; }
  const node = document.createElement('div'); node.className = 'toast undo-toast'; node.innerHTML = `${icon('trash')}<span>${escapeHtml(message)}</span><button class="button button-ghost button-small" data-restore-id="${escapeHtml(id)}" data-restore-kind="${escapeHtml(kind)}">撤回</button>`; $('#toastRegion').append(node); setTimeout(() => node.remove(),14000);
}
async function trashItems(ids) {
  if (!ids.length) return; const choice = await confirmRemoval(`删除 ${ids.length === 1 ? '这个文件' : `${ids.length} 个文件`}？`,'移到映序回收站，可以恢复。磁盘原文件保留。',[{key:'cancel',label:'取消',style:'ghost'},{key:'delete',label:'移到回收站',style:'danger'}]); if (choice !== 'delete') return;
  const tabs = fileTabs(ids); if (!await prepareTabs(tabs)) return; const result = await api('/api/trash/items',{method:'POST',body:{ids}}); removeOpenTabs(tabs); state.selectedIds.clear(); await refreshProjects(); await loadSection(); undoToast(`${ids.length} 个文件已移到回收站。`,result,'items');
}
async function trashProject(id) {
  const project = state.projects.find(value => String(value.id) === String(id)); if (!project) return;
  const choice = await confirmRemoval(`删除项目「${project.name}」？`,'项目及当前资源会移到回收站，可以整批恢复。磁盘目录和原文件保留。',[{key:'cancel',label:'取消',style:'ghost'},{key:'delete',label:'删除项目',style:'danger'}]); if (choice !== 'delete') return;
  const tabs = state.tabs.filter(tab => tab.source === 'file' && String(tab.item.project_id) === String(id)); if (!await prepareTabs(tabs)) return; const result = await api(`/api/projects/${encodeURIComponent(id)}`,{method:'DELETE'}); removeOpenTabs(tabs); state.folderId = null; state.folders = []; state.offset = 0; await refreshProjects(); await loadSection(); undoToast(`项目「${project.name}」已移到回收站。`,result,'project');
}
async function trashFolder(id) {
  const folder = state.folders.find(value => String(value.id) === String(id)); if (!folder) return;
  const choice = await confirmRemoval(`删除文件夹「${folder.name}」？`,'这个文件夹、子文件夹及当前资源会一起移到回收站。磁盘原件保留。',[{key:'cancel',label:'取消',style:'ghost'},{key:'delete',label:'删除文件夹',style:'danger'}]); if (choice !== 'delete') return;
  const descendants = descendantFolderIds(id); const tabs = state.tabs.filter(tab => tab.source === 'file' && descendants.has(String(tab.item.folder_id))); if (!await prepareTabs(tabs)) return;
  const result = await api(`/api/folders/${encodeURIComponent(id)}`,{method:'DELETE'}); removeOpenTabs(tabs); if (descendants.has(String(state.folderId))) state.folderId = folder.parent_id || null; state.offset = 0; state.selectedIds.clear(); await refreshProjects(); await loadItems(); undoToast(`文件夹「${folder.name}」已移到回收站。`,result,'folder');
}
async function trashSkill(id) {
  const skill = state.skills.find(value => String(value.id) === String(id)) || state.tabs.find(tab => tab.source === 'skill' && String(tab.id) === String(id))?.item; if (!skill) return;
  const choice = await confirmRemoval(skill.editable ? `删除 SKILL「${skill.name}」？` : `隐藏 SKILL「${skill.name}」？`,skill.editable ? '移到回收站，可恢复。磁盘原文件保留。' : '只在映序里隐藏，不卸载或改动原工具。可以从回收站恢复显示。',[{key:'cancel',label:'取消',style:'ghost'},{key:'delete',label:skill.editable ? '移到回收站' : '隐藏',style:'danger'}]); if (choice !== 'delete') return;
  const tabs = state.tabs.filter(tab => tab.source === 'skill' && String(tab.id) === String(id)); if (!await prepareTabs(tabs)) return; const result = await api(`/api/skills/${encodeURIComponent(id)}`,{method:'DELETE'}); removeOpenTabs(tabs); await loadSection(); undoToast(skill.editable ? 'SKILL 已移到回收站。' : 'SKILL 已隐藏，原工具保持不变。',result,'skill');
}
async function loadTrash() {
  const sequence = ++state.listSequence; state.listController?.abort(); configureSection(); $('#resourceItems').className = 'recycle-list'; $('#resourceItems').innerHTML = '<div class="subtle-loading">正在读取回收站…</div>';
  try { const result = await api(`/api/trash?${new URLSearchParams({q:state.q,limit:state.limit,offset:state.offset})}`); if (sequence !== state.listSequence || state.section !== 'trash') return; state.trashEntries = result.entries || []; state.total = result.total || 0; if (!state.trashEntries.length && state.offset > 0 && state.total <= state.offset) { state.offset = Math.max(0,Math.floor(Math.max(0,state.total-1)/state.limit)*state.limit); return loadTrash(); } renderTrash(); renderInspector(); } catch(error) { if (error.name === 'AbortError' || sequence !== state.listSequence || state.section !== 'trash') return; $('#resourceItems').innerHTML = emptyHtml('暂时无法读取回收站',error.message,'trash','重试','retry'); report(error); }
}
function renderTrash() {
  const labels = {project:'项目',folder:'文件夹',items:'文件',skill:'SKILL'}; $('#resourceCount').textContent = state.total; $('#searchTiming').textContent = ''; const entries = state.trashEntries;
  $('#resourceItems').innerHTML = entries.length ? entries.map(entry => `<div class="recycle-row"><span class="recycle-icon">${icon(entry.kind === 'project' || entry.kind === 'folder' ? 'folder' : entry.kind === 'skill' ? 'skills' : 'file')}</span><span class="recycle-copy"><strong>${escapeHtml(entry.name || labels[entry.kind] || '已删除内容')}</strong><small>${escapeHtml(entry.kind === 'skill' && !entry.editable ? '隐藏的外部 SKILL' : labels[entry.kind] || '资源')} · ${entry.count || 1} 项 · ${formatDate(entry.created,true)}</small></span><div class="recycle-actions"><button class="button button-secondary button-small" data-restore-id="${escapeHtml(entry.id || entry.batch_id)}" data-restore-kind="${escapeHtml(entry.kind)}" ${state.trashBusy ? 'disabled' : ''}>${icon('restore')}恢复</button><button class="button button-ghost button-small recycle-delete" data-delete-trash-id="${escapeHtml(entry.id || entry.batch_id)}" data-delete-trash-kind="${escapeHtml(entry.kind)}" title="预览删除范围，再确认" ${state.trashBusy ? 'disabled' : ''}>${icon('trash')}删除</button></div></div>`).join('') : emptyHtml('回收站是空的','删除的项目、文件、文件夹和 SKILL 会保留在这里。','trash'); updatePagination();
}
async function restoreTrash(id,kind,button) {
  if (state.trashBusy) return;
  if (button) button.disabled = true;
  try { await api(`/api/trash/${encodeURIComponent(id)}/restore`,{method:'POST',body:{kind}}); if (button) button.closest('.undo-toast')?.remove(); await refreshProjects(); await refreshCategoryCounts(); await loadSection(); toast('已恢复。'); } catch(error) { if (button) button.disabled = false; report(error); }
}
function trashDeletePreviewHtml(plan) {
  return `<p class="recycle-note">以下文件会移入 ${systemTrashName()}，可到那里还原。成功处理后，这些条目不能再从映序恢复；外部引用与外部 SKILL 只清理映序记录。</p><div class="trash-delete-preview">${(plan.entries || []).map(entry => `<section class="trash-preview-entry"><strong>${escapeHtml(entry.name || '已删除内容')}</strong>${entry.error ? `<p class="trash-preview-error">暂不能删除：${escapeHtml(entry.error)}</p>` : ''}${(entry.paths || []).map(path => `<p class="trash-preview-path">${escapeHtml(path)}</p>`).join('')}${(entry.warnings || []).map(warning => `<p class="trash-preview-warning">${escapeHtml(warning)}</p>`).join('')}</section>`).join('')}</div>`;
}
async function deleteTrash(id,kind,all=false) {
  if (state.trashBusy || state.section !== 'trash') return;
  state.trashBusy = true; renderHero(); renderTrash();
  try {
    const plan = await api('/api/trash/delete-preview',{method:'POST',body:all ? {all:true} : {entries:[{id,kind}]}});
    if (state.section !== 'trash') return;
    if (!plan.total) { toast('回收站是空的。'); return; }
    const actionable = (plan.entries || []).filter(entry => !entry.error).length;
    const result = !preference('confirm_trash_delete') && actionable === plan.total ? await api('/api/trash/delete',{method:'POST',body:{token:plan.token}}) : await new Promise(resolve => {
      let outcome = null;
      const dialog = showDialog({title:all ? '清空映序回收站？' : '删除到 '+systemTrashName()+'？',wide:true,
        subtitle:all ? `包含全部回收条目，不受当前搜索或分页影响。${actionable} 项可处理，${plan.total-actionable} 项暂不能删除。` : '请核对原文件位置和处理说明，再确认删除。',
        body:trashDeletePreviewHtml(plan),
        actions:`<button type="button" class="button button-ghost" data-dialog-cancel>${actionable ? '取消' : '关闭'}</button>${actionable ? `<button type="submit" class="button button-danger">确认处理 ${actionable} 项</button>` : ''}`,
        onSubmit:async () => { outcome = await api('/api/trash/delete',{method:'POST',body:{token:plan.token}}); }});
      dialog.addEventListener('close',() => resolve(outcome),{once:true});
    });
    if (!result) return;
    await refreshProjects(); await refreshCategoryCounts(); await loadSection();
    const failed = result.failed || [];
    toast(`已清理 ${result.deleted || 0} 项${failed.length ? `，${failed.length} 项未删除` : ''}。`);
    if (failed.length) showDialog({title:'部分条目仍在回收站',subtitle:'失败的条目保留记录，请处理原因后重新预览。',body:`<div class="trash-delete-preview">${failed.map(entry => `<section class="trash-preview-entry"><strong>${escapeHtml(entry.name || '已删除内容')}</strong><p class="trash-preview-error">${escapeHtml(entry.error || '未完成删除')}</p></section>`).join('')}</div>`,actions:'<button type="button" class="button button-secondary" data-dialog-cancel>知道了</button>'});
  } catch(error) { report(error); }
  finally { state.trashBusy = false; if (state.section === 'trash') { renderHero(); renderTrash(); } }
}

function observeThumbnails() {
  observer?.disconnect(); for (const timer of state.thumbTimers) clearTimeout(timer); state.thumbTimers.clear();
  if (!('IntersectionObserver' in window)) { $$('img[data-thumbnail]').forEach(image => loadThumbnail(image)); return; }
  observer = new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) { observer.unobserve(entry.target); loadThumbnail(entry.target); } }),{root:$('#resourceViewport'),rootMargin:'160px'}); $$('img[data-thumbnail]').forEach(image => observer.observe(image));
}
async function loadThumbnail(image,attempt = 0) {
  if (!image.isConnected) return; const key = `${image.dataset.thumbnail}:${image.dataset.url}`; const cached = state.thumbCache.get(key);
  if (cached) { image.src = cached; image.hidden = false; image.classList.add('loaded'); image.parentElement.classList.add('has-preview'); return; }
  try {
    const response = await fetch(image.dataset.url,{headers:{Accept:'image/*'}});
    if (response.status === 202) { if (attempt < 5 && image.isConnected) { const timer = setTimeout(() => { state.thumbTimers.delete(timer); loadThumbnail(image,attempt+1); },[650,1100,1900,3200,5200][attempt]); state.thumbTimers.add(timer); } return; }
    if (!response.ok || !response.headers.get('content-type')?.startsWith('image/')) return;
    const blob = await response.blob(); if (!image.isConnected) return; const url = URL.createObjectURL(blob); state.thumbCache.set(key,url);
    if (state.thumbCache.size > 120) { const oldest = state.thumbCache.keys().next().value; URL.revokeObjectURL(state.thumbCache.get(oldest)); state.thumbCache.delete(oldest); }
    image.src = url; image.hidden = false; image.classList.add('loaded'); image.parentElement.classList.add('has-preview');
  } catch { /* A missing preview never blocks the asset list. */ }
}

function readDrafts() { try { const value = localStorage.getItem('yingxu:drafts'); if (value && value.length*2 <= 2*1024*1024) { const parsed = JSON.parse(value); if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) state.drafts = parsed; } } catch { state.drafts = {}; } }
function persistDrafts(immediate = false) {
  clearTimeout(draftTimer); const write = () => {
    const candidates = {...state.drafts}; let length = 0; const drafts = {};
    for (const tab of state.tabs) { if (!tab.dirty && !tab.propertiesDirty) { if (!tab.loading && !tab.error) delete candidates[tab.key]; continue; } candidates[tab.key] = {id:tab.id,source:tab.source,projectId:tab.item.project_id,path:tab.source === 'external' ? tab.item.path : undefined,name:tab.item.name,draft:tab.dirty ? tab.draft : undefined,paragraphs:tab.dirty ? tab.paragraphs?.map(({id,text}) => ({id,text})) : undefined,etag:tab.content?.etag,propertiesDraft:tab.propertiesDirty ? tab.propertiesDraft : undefined,when:Date.now()}; }
    for (const [key,value] of Object.entries(candidates).sort((a,b) => b[1].when-a[1].when)) { const size = JSON.stringify(value).length*2; if (Date.now()-value.when > 7*86400000 || size > 512*1024 || length+size > 2*1024*1024-4096) continue; drafts[key] = value; length += size; }
    state.drafts = drafts; let stored = false; try { localStorage.setItem('yingxu:drafts',JSON.stringify(drafts)); stored = true; } catch { /* The open tab still retains the draft. */ }
    for (const tab of state.tabs) if (tab.dirty || tab.propertiesDirty) tab.draftStorage = stored && drafts[tab.key] ? 'saved' : 'memory';
    if (activeTab()) renderEditorStatus(activeTab());
  }; if (immediate) write(); else draftTimer = setTimeout(write,400);
}
function applyDraft(tab) {
  let draft = state.drafts[tab.key];
  if (!draft && tab.source === 'external' && tab.item.path) {
    const normalize = path => String(path || '').replace(/\\/g,'/').toLowerCase();
    const recovered = Object.entries(state.drafts).find(([,value]) => value.source === 'external' && value.path && normalize(value.path) === normalize(tab.item.path));
    if (recovered) { draft = recovered[1]; delete state.drafts[recovered[0]]; state.drafts[tab.key] = draft; }
  }
  if (!draft || Date.now()-draft.when > 7*86400000) return;
  if (tab.content && (draft.draft != null || draft.paragraphs)) { if (draft.draft != null) tab.draft = draft.draft; if (draft.paragraphs) { const saved = new Map(draft.paragraphs.map(p => [String(p.id),p.text])); tab.paragraphs = (tab.paragraphs || []).map(p => saved.has(String(p.id)) ? {...p,text:saved.get(String(p.id))} : p); } tab.dirty = true; if (draft.etag !== tab.content.etag) { tab.conflict = true; tab.content.etag = draft.etag; } }
  if (tab.source === 'file' && draft.propertiesDraft) { tab.propertiesDraft = draft.propertiesDraft; tab.propertiesDirty = true; }
  tab.restored = true;
  toast('已恢复这个文件的本地未保存草稿。','info',6000);
}
// Textareas normalize line endings. Preserve every untouched source span.
function preserveTextNewlines(previous, next) {
  const before = previous.replace(/\r\n?/g,'\n'), after = next.replace(/\r\n?/g,'\n');
  if (before === after) return previous;
  let start = 0, end = 0;
  while (start < before.length && start < after.length && before[start] === after[start]) start++;
  while (end < before.length-start && end < after.length-start && before[before.length-1-end] === after[after.length-1-end]) end++;
  const rawOffset = offset => { let raw = 0, normalized = 0; while (normalized < offset) { if (previous[raw] === '\r' && previous[raw+1] === '\n') raw++; raw++; normalized++; } return raw; };
  const separator = previous.match(/\r\n|\r|\n/)?.[0] || '\n';
  return previous.slice(0,rawOffset(start)) + after.slice(start,after.length-end).replace(/\n/g,separator) + previous.slice(rawOffset(before.length-end));
}

const markdownEditorTabs = new Set();
function editableMarkdown(tab) { return ['markdown','skill'].includes(tab?.item?.kind) && !!tab.content?.editable; }
function canUseMarkdownEditor(tab) { return editableMarkdown(tab) && !!window.YingXuMarkdown && (!!tab.markdownEditor || window.YingXuMarkdown.supports(tab.draft)); }
function markdownInputReady(tab = activeTab()) { if (!tab?.markdownEditor?.isComposing() && !tab?.docxEditor?.isComposing()) return true; toast('请先确认正在输入的文字，再继续操作。','info'); return false; }
let activeDocxEditorTab = null;
function unmountDocxEditor() { if (!activeDocxEditorTab) return; const tab = activeDocxEditorTab; tab.docxPage = tab.docxEditor.getPage(); tab.docxEditor.destroy(); delete tab.docxEditor; activeDocxEditorTab = null; }
function discardUnusedMarkdownEditors() { for (const tab of markdownEditorTabs) { if (!state.tabs.includes(tab)) { tab.markdownEditor.destroy(); delete tab.markdownEditor; markdownEditorTabs.delete(tab); } } }
function mountMarkdownEditor(tab,parent) {
  if (!tab.markdownEditor) {
    tab.markdownEditor = window.YingXuMarkdown.create({parent,value:tab.draft,mode:tab.mode === 'live' ? 'live' : 'source',label:`${tab.item.name} Markdown 编辑`,imageResolver:url => markdownImageURL(tab,url),onChange:(value,meta) => {
      if (meta?.origin === 'setValue') return; tab.draft = value; markDirty(tab); if (state.activeKey === tab.key && $('#markdownPreview')) updatePreview(tab);
    }}); markdownEditorTabs.add(tab);
  } else { tab.markdownEditor.setValue(tab.draft); tab.markdownEditor.setMode(tab.mode === 'live' ? 'live' : 'source'); tab.markdownEditor.mount(parent); }
}
function draftStateLabel(tab) { return tab.draftStorage === 'saved' ? '尚未保存 · 本地草稿已暂存' : tab.draftStorage === 'memory' ? '尚未保存 · 仅在当前窗口保留，请及时保存' : '尚未保存'; }

async function openItem(id) {
  const key = `file:${id}`; if (state.activeKey !== key && !await guardProperties()) return; let tab = state.tabs.find(value => value.key === key);
  if (tab) { state.activeKey = key; renderWorkspace(); return; }
  tab = {key,id,source:'file',item:state.items.find(item => String(item.id) === String(id)) || {id,name:'正在打开…',kind:'file'},loading:true,dirty:false,mode:'edit'}; state.tabs.push(tab); state.activeKey = key; renderWorkspace();
  try {
    tab.item = await api(`/api/items/${encodeURIComponent(id)}`); tab.detailReady = true;
    if (['markdown','text','docx','svg','html'].includes(tab.item.kind)) { tab.content = await api(`/api/content/${encodeURIComponent(id)}`); tab.draft = String(tab.content.content ?? ''); tab.paragraphs = (tab.content.paragraphs || []).map(paragraph => ({...paragraph})); tab.mode = tab.item.kind === 'docx' ? 'preview' : tab.content.editable ? (canUseMarkdownEditor(tab) ? 'live' : 'edit') : 'preview'; }
    applyDraft(tab);
    tab.loading = false; if (state.activeKey === key) renderWorkspace(); else renderTabs();
  } catch(error) { tab.loading = false; tab.error = error.message; if (state.activeKey === key) renderWorkspace(); report(error); }
}
async function closeTab(key) {
  const tab = state.tabs.find(value => value.key === key); if (!tab) return;
  if (!await guardProperties(tab)) return;
  if (tab.dirty) {
    const choice = await choose('保留这次编辑吗？',`「${tab.item.name}」还有未保存的修改。`,[{key:'cancel',label:'继续编辑',style:'ghost'},{key:'discard',label:'放弃修改',style:'secondary'},{key:'save',label:'保存并关闭',style:'primary'}]);
    if (!choice || choice === 'cancel') return; if (choice === 'save' && !await saveTab(tab)) return;
  }
  if (!markdownInputReady(tab) || tab.propertiesDirty || tab.propertiesSaving || tab.saving) return;
  const index = state.tabs.indexOf(tab); if (index < 0) return; state.tabs.splice(index,1); delete state.drafts[key]; if (state.activeKey === key) state.activeKey = state.tabs[Math.min(index,state.tabs.length-1)]?.key || null; persistDrafts(); renderWorkspace();
}
function renderTabs() {
  $('#editorTabs').innerHTML = state.tabs.map(tab => `<div class="editor-tab ${tab.key === state.activeKey ? 'active' : ''}" role="tab" tabindex="0" aria-selected="${tab.key === state.activeKey}" data-tab="${escapeHtml(tab.key)}">${icon(kindIcons[tab.item.kind])}<span class="editor-tab-name" title="${escapeHtml(tab.item.name)}">${escapeHtml(tab.item.name)}</span>${tab.dirty || tab.propertiesDirty ? '<span class="dirty-dot" title="文稿或制作信息未保存"></span>' : ''}<button class="tab-close" data-close-tab="${escapeHtml(tab.key)}" aria-label="关闭 ${escapeHtml(tab.item.name)}">${icon('close')}</button></div>`).join('');
}
function renderWorkspace() {
  const tab = activeTab(); const editing = !!tab; $('#workspace').classList.toggle('editing',editing); $('#editor').hidden = !editing; $('#editorDivider').hidden = !editing;
  discardUnusedMarkdownEditors(); renderTabs(); renderInspector(); if (state.section === 'assets') $$('#resourceItems [data-item]').forEach(node => node.classList.toggle('selected',state.activeKey === `file:${node.dataset.item}`));
  if (!tab) { unmountDocxEditor(); stopImageZoomTracking(); stopPreviewMedia(true); $('#editorContent').replaceChildren(); return; }
  renderEditorToolbar(tab); renderEditorBody(tab); renderEditorStatus(tab);
}
let imageZoomObserver = null;
function stopPreviewMedia(release = false) {
  for (const media of $$('#editorContent video,#editorContent audio')) {
    try { media.pause(); } catch (_) { }
    if (release) {
      media.removeAttribute('autoplay'); media.removeAttribute('src');
      for (const source of $$('source',media)) source.removeAttribute('src');
      try { media.load(); } catch (_) { }
    }
  }
}
function stopImageZoomTracking() { imageZoomObserver?.disconnect(); imageZoomObserver = null; }
function imageZoomRatio(image) {
  if (!image?.naturalWidth || !image.naturalHeight) return 0;
  const bounds = image.getBoundingClientRect();
  return Math.min(bounds.width / image.naturalWidth, bounds.height / image.naturalHeight);
}
function updateImageZoomLabel(image = $('#mainImage')) {
  const label = $('#imageZoomPercent'); if (!label) return;
  const ratio = imageZoomRatio(image);
  label.textContent = ratio > 0 ? `图片 ${Math.round(ratio * 100)}%` : '图片 —';
}
function trackImageZoom(tab, image) {
  const update = () => { if (activeTab() === tab && $('#mainImage') === image) updateImageZoomLabel(image); };
  image.addEventListener('load',update,{once:true});
  if (typeof ResizeObserver !== 'undefined') { imageZoomObserver = new ResizeObserver(update); imageZoomObserver.observe(image); }
  update();
}
function changeImageZoom(action) {
  const image = $('#mainImage'), tab = activeTab();
  if (!image || !tab || !image.naturalWidth || !['zoom-fit','zoom-in','zoom-out'].includes(action)) return;
  if (action === 'zoom-fit') { tab.zoom = null; image.classList.remove('zoomed'); image.style.width = ''; image.style.height = ''; }
  else {
    tab.zoom = Math.min(4,Math.max(.25,(imageZoomRatio(image) || 1)*(action === 'zoom-in' ? 1.25 : .8)));
    image.classList.add('zoomed'); image.style.width = `${image.naturalWidth * tab.zoom}px`; image.style.height = 'auto';
  }
  updateImageZoomLabel(image);
}
function markdownToolbarHtml(tab) {
  if (!canUseMarkdownEditor(tab) || tab.mode === 'preview') return '';
  const commands = [['undo','↶','撤销'],['redo','↷','重做'],['bold','B','粗体'],['italic','I','斜体'],['strike','S','删除线'],['bullet','•','项目列表'],['ordered','1.','编号列表'],['task','☑','任务列表'],['quote','❞','引用'],['link','↗','链接'],['rule','—','分隔线'],['codeblock','{}','代码块']];
  return `<div class="markdown-format-tools" role="group" aria-label="Markdown 格式"><select class="markdown-heading-select" data-markdown-heading aria-label="标题层级" title="标题层级"><option value="">标题</option><option value="paragraph">正文</option>${[1,2,3,4,5,6].map(level => `<option value="heading${level}">H${level}</option>`).join('')}</select>${commands.map(([command,label,title]) => `<button class="icon-button" type="button" data-markdown-format="${command}" title="${title}" aria-label="${title}">${label}</button>`).join('')}</div>`;
}
function markdownDocumentHeading(tab) {
  const filename = tab.item.kind !== 'skill' && tab.item.path ? String(tab.item.path).replace(/\\/g,'/').split('/').at(-1) : tab.item.name;
  const title = tab.item.kind !== 'skill' && tab.item.path ? String(filename || tab.item.name).replace(/^(.+)\.[^.]+$/,'$1') : filename || tab.item.name;
  const writable = tab.source === 'file' && tab.content?.editable && !tab.loading;
  return `<header class="document-heading" contenteditable="false"><h1>${writable ? `<button type="button" class="document-title-button" data-action="rename-title" title="点击修改标题" aria-label="修改标题：${escapeHtml(title)}">${escapeHtml(title)}</button>` : escapeHtml(title)}</h1></header>`;
}
function applyMarkdownFormat(command) {
  const tab = activeTab();
  if (!tab?.markdownEditor || !editableMarkdown(tab) || tab.mode === 'preview' || !markdownInputReady(tab)) return false;
  return tab.markdownEditor.format(command);
}
function renderEditorToolbar(tab) {
  const text = ['markdown','text','skill'].includes(tab.item.kind); const editable = tab.content?.editable || (tab.source === 'skill' && tab.item.editable);
  const htmlModes = tab.item.kind === 'html' ? `<div class="editor-mode-switch" role="group" aria-label="HTML 视图"><button data-editor-mode="preview" class="${tab.mode === 'preview' ? 'active' : ''}">静态预览</button><button data-editor-mode="edit" class="${tab.mode === 'edit' ? 'active' : ''}">查看源码</button></div>` : '';
  const wordModes = tab.item.kind === 'docx' ? `<div class="editor-mode-switch" role="group" aria-label="Word 视图"><button data-editor-mode="preview" class="${tab.mode === 'preview' ? 'active' : ''}">文档预览</button>${editable ? `<button data-editor-mode="edit" class="${tab.mode === 'edit' ? 'active' : ''}">编辑文字</button>` : ''}</div>` : '';
  $('#editorToolbar').innerHTML = `${htmlModes}${wordModes}${text ? `<div class="editor-mode-switch" role="group" aria-label="文档视图">${canUseMarkdownEditor(tab) ? `<button data-editor-mode="live" class="${tab.mode === 'live' ? 'active' : ''}">实时预览</button>` : ''}<button data-editor-mode="edit" class="${tab.mode === 'edit' ? 'active' : ''}">${editableMarkdown(tab) ? '源码' : '编辑'}</button><button data-editor-mode="split" class="${tab.mode === 'split' ? 'active' : ''}">双栏</button><button data-editor-mode="preview" class="${tab.mode === 'preview' ? 'active' : ''}">预览</button></div>${markdownToolbarHtml(tab)}` : `<span class="editor-type-label">${icon(kindIcons[tab.item.kind])}${kindLabels[tab.item.kind] || '资源预览'}</span>`}<div class="editor-tool-actions"><button type="button" class="icon-button" data-action="capture-screen" title="截图到当前项目并复制图片" aria-label="截图">${icon('image')}</button>${['image','svg'].includes(tab.item.kind) ? `<button class="icon-button" data-action="zoom-out" aria-label="缩小" title="缩小">${icon('minus')}</button><button class="button button-ghost button-small" data-action="zoom-fit">适应</button><span id="imageZoomPercent" class="image-zoom-percent" aria-live="polite" title="图片相对于原始尺寸的比例">图片 —</span><button class="icon-button" data-action="zoom-in" aria-label="放大" title="放大">${icon('plus')}</button>` : ''}${editable && !tab.loading ? `<button class="button button-primary button-small" id="saveContentButton" data-action="save-content" ${!tab.dirty || tab.saving ? 'disabled' : ''}>${icon('save')}${tab.saving ? '保存中' : '保存'}</button>` : ''}${tab.source === 'file' ? `<button class="icon-button" data-action="open-native" title="用本机应用打开" aria-label="用本机应用打开">${icon('open')}</button>` : ''}<button class="icon-button inspector-toggle" data-action="toggle-inspector" title="显示资源信息与关联" aria-label="显示资源信息与关联">${icon('panel')}</button></div>`;
}
function renderEditorBody(tab) {
  if (tab.markdownEditor?.isComposing() || activeDocxEditorTab?.docxEditor?.isComposing()) return;
  unmountDocxEditor();
  stopImageZoomTracking();
  stopPreviewMedia(true);
  const root = $('#editorContent'); if (tab.loading) { root.innerHTML = '<div class="editor-loading"><span class="spinner"></span><span>正在打开文件…</span></div>'; return; }
  if (tab.error) { root.innerHTML = emptyHtml('这个文件暂时无法打开',tab.error,'alert','重新载入','retry-detail'); return; }
  const item = tab.item;
  if (['markdown','text','skill'].includes(item.kind)) {
    const enhanced = canUseMarkdownEditor(tab); if (tab.mode === 'live' && !enhanced) tab.mode = 'edit';
    const editorMarkup = enhanced ? '<div id="liveMarkdownHost" class="live-markdown-host"></div>' : `<textarea id="textEditor" class="text-editor" aria-label="${escapeHtml(item.name)} 文本编辑" spellcheck="false" ${!tab.content?.editable ? 'readonly' : ''}></textarea>`;
    root.innerHTML = `<div class="document-workspace">${markdownDocumentHeading(tab)}${editableMarkdown(tab) && window.YingXuMarkdown && !enhanced ? '<p class="markdown-source-notice">此文档使用源码编辑，以保留混合换行或较大的完整内容。</p>' : ''}<div class="text-workspace ${tab.mode === 'split' ? 'split' : ''}">${tab.mode !== 'preview' ? editorMarkup : ''}${['split','preview'].includes(tab.mode) ? '<article id="markdownPreview" class="markdown-preview"></article>' : ''}</div></div>`;
    if (enhanced && tab.mode !== 'preview') mountMarkdownEditor(tab,$('#liveMarkdownHost'));
    const editor = $('#textEditor'); if (editor) { editor.value = tab.draft; editor.addEventListener('input',() => { tab.draft = preserveTextNewlines(tab.draft,editor.value); markDirty(tab); if ($('#markdownPreview')) updatePreview(tab); }); editor.addEventListener('keydown',event => { if (event.key === 'Tab' && !editor.readOnly) { event.preventDefault(); const start = editor.selectionStart,end = editor.selectionEnd; editor.setRangeText('  ',start,end,'end'); tab.draft = preserveTextNewlines(tab.draft,editor.value); markDirty(tab); updatePreview(tab); } }); }
    updatePreview(tab);
  } else if (item.kind === 'docx') {
    const notice = `<div class="docx-notice">${icon('info')}<span>${escapeHtml(tab.content?.notice || '结构预览保留正文、表格和图片。精确分页及复杂浮动版式请使用 Word。')}</span></div>`;
    const preview = tab.mode === 'preview' && window.YingXuDocx;
    root.innerHTML = `<div class="docx-editor">${notice}${preview ? window.YingXuDocx.render(tab.content,tab.paragraphs) : '<div class="docx-editor-mount"></div>'}</div>`;
    if (!preview) {
      const parent = $('.docx-editor-mount',root);
      if (!window.YingXuDocxEditor) { parent.textContent = '文字编辑组件未载入，请重新打开映序后重试。'; return; }
      tab.docxEditor = window.YingXuDocxEditor.mount({parent,paragraphs:tab.paragraphs || [],editable:!!tab.content?.editable,page:tab.docxPage || 0,
        onChange:() => markDirty(tab),onPageChange:page => { tab.docxPage = page; },onBlocked:() => toast('请先确认正在输入的文字，再翻页。','info')});
      activeDocxEditorTab = tab;
    }
  } else if (item.kind === 'html') {
    const notice = `<p class="html-preview-notice">${escapeHtml(tab.content?.notice || '静态预览，不运行脚本或联网；源码只读。')}</p>`;
    if (tab.mode === 'edit') {
      root.innerHTML = `<div class="html-workspace">${notice}<textarea id="htmlSource" class="text-editor" aria-label="HTML 源码（只读）" readonly spellcheck="false"></textarea></div>`;
      $('#htmlSource',root).value = tab.content?.content || '';
    } else {
      const safe = window.YingXuHtmlPreview.document(tab.content?.preview_html || '');
      root.innerHTML = `<div class="html-workspace">${notice}<iframe class="html-preview-frame" sandbox="" referrerpolicy="no-referrer" title="${escapeHtml(item.name)} 静态预览" srcdoc="${escapeHtml(safe)}"></iframe></div>`;
    }
  } else if (['image','svg'].includes(item.kind)) root.innerHTML = `<div class="media-stage ${item.kind === 'svg' ? 'svg-stage' : ''}"><img id="mainImage" src="${escapeHtml(item.kind === 'svg' ? tab.content?.preview_url || '' : item.media_url || `/api/media/${encodeURIComponent(item.id)}`)}" alt="${escapeHtml(item.name)}" decoding="async">${item.kind === 'svg' ? '<span class="svg-preview-notice">SVG 静态预览 · 原文件保持不变</span>' : ''}</div>`;
  else if (item.kind === 'video') root.innerHTML = `<div class="media-stage"><video controls ${preference('autoplay_media') ? 'autoplay' : ''} preload="metadata" playsinline src="${escapeHtml(item.media_url || `/api/media/${encodeURIComponent(item.id)}`)}" aria-label="${escapeHtml(item.name)}"></video></div>`;
  else if (item.kind === 'audio') root.innerHTML = `<div class="media-stage"><div class="audio-stage"><div class="audio-disc">${icon('audio')}</div><h3>${escapeHtml(item.name)}</h3><audio controls ${preference('autoplay_media') ? 'autoplay' : ''} preload="metadata" src="${escapeHtml(item.media_url || `/api/media/${encodeURIComponent(item.id)}`)}"></audio></div></div>`;
  else if (item.kind === 'pdf') root.innerHTML = `<div class="media-stage pdf-stage"><iframe title="${escapeHtml(item.name)} PDF 预览" src="${escapeHtml(item.media_url || `/api/media/${encodeURIComponent(item.id)}`)}"></iframe></div>`;
  else root.innerHTML = emptyHtml(item.kind === 'model' ? '3D 模型已归入项目' : '文件已归入项目',item.kind === 'model' ? '可管理分类、制作状态与镜头关联。打开本机的 3D 工具继续编辑，渲染的白模视频可以在这里直接播放。' : '可管理分类、标签与关联，使用本机应用查看这个文件。',kindIcons[item.kind],'用本机应用打开','open-native');
  const media = $('video,audio,#mainImage',root); if (media) media.addEventListener('error',() => toast(tab.source === 'external' ? '当前播放环境无法预览此文件；可复制右侧文件路径，使用其他应用打开。' : '预览未能打开；可使用“用本机应用打开”查看文件。','error',6000),{once:true});
  if (['image','svg'].includes(item.kind)) trackImageZoom(tab,$('#mainImage',root));
}
function markDirty(tab) { tab.dirty = true; tab.saved = false; tab.draftStorage = 'pending'; renderTabs(); renderEditorToolbar(tab); renderEditorStatus(tab); persistDrafts(); }
function renderEditorStatus(tab) { const dirty = tab.dirty || tab.propertiesDirty; $('#editorStatus').innerHTML = `<span class="${dirty ? 'unsaved-state' : 'saved-state'}">${dirty ? (tab.conflict ? '检测到外部更改 · 草稿已保留' : tab.propertiesDirty ? '制作信息未保存' : draftStateLabel(tab)) : `${icon('check')}${tab.saved ? '已保存 · 原版本已备份' : tab.content?.editable ? '文件已载入' : '预览模式'}`}</span><span>${tab.content ? `${(tab.item.kind === 'docx' ? tab.paragraphs?.map(value => value.text).join('') || '' : tab.draft || '').length.toLocaleString()} 字符` : formatSize(tab.item.size)}${tab.content?.editable || tab.propertiesDirty ? ' · Ctrl S 保存' : ''}</span>`; }
let previewTimer;
function updatePreview(tab) { clearTimeout(previewTimer); previewTimer = setTimeout(() => { if ($('#markdownPreview') && state.activeKey === tab.key) $('#markdownPreview').innerHTML = markdown(tab.draft,tab); },120); }
function inlineMarkdown(text,imageResolver = () => null) {
  const tokens = []; let raw = String(text).replace(/\u0000/g,'');
  const token = html => { const key = `\u0000${tokens.length}\u0000`; tokens.push(html); return key; };
  raw = raw.replace(/`([^`]+)`/g,(_,code) => token(`<code>${escapeHtml(code)}</code>`));
  raw = raw.replace(/!\[([^\]\n]*)\]\((?:<([^>\n]+)>|([^\s)]+))\)/g,(source,alt,angle,url) => {
    const resolved = imageResolver(angle || url);
    return token(resolved ? `<img class="markdown-attachment" src="${escapeHtml(resolved)}" alt="${escapeHtml(alt)}" loading="lazy" decoding="async">` : escapeHtml(source));
  });
  let value = escapeHtml(raw);
  value = value.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,(_,label,url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`);
  value = value.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/__([^_]+)__/g,'<strong>$1</strong>').replace(/(?<!\*)\*([^*]+)\*(?!\*)/g,'<em>$1</em>').replace(/~~([^~]+)~~/g,'<del>$1</del>');
  return value.replace(/\u0000(\d+)\u0000/g,(_,index) => tokens[Number(index)] || '');
}
function markdown(raw,tab) {
  const inline = text => inlineMarkdown(text,url => markdownImageURL(tab,url));
  const maximum = 140000; const source = String(raw || ''); const truncated = source.length > maximum; const lines = source.slice(0,maximum).replace(/\r\n?/g,'\n').split('\n'); let output = truncated ? '<div class="preview-notice">为保持流畅，预览显示前 14 万字符。编辑区保留完整内容。</div>' : ''; let code = false,buffer = [],list = '';
  const closeList = () => { if (list) { output += `</${list}>`; list = ''; } };
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index]; if (/^\s*```/.test(line)) { closeList(); if (code) { output += `<pre><code>${escapeHtml(buffer.join('\n'))}</code></pre>`; buffer = []; } code = !code; continue; }
    if (code) { buffer.push(line); continue; }
    if (!line.trim()) { closeList(); continue; }
    if (/^\s*\|?.+\|.+/.test(line) && /^\s*\|?\s*:?-{3,}/.test(lines[index+1] || '')) {
      closeList(); const cells = value => value.trim().replace(/^\||\|$/g,'').split('|').map(cell => cell.trim()); const headers = cells(line); output += `<table><thead><tr>${headers.map(cell => `<th>${inline(cell)}</th>`).join('')}</tr></thead><tbody>`; index += 2; let rowCount = 0;
      while (index < lines.length && lines[index].includes('|') && rowCount < 1000) { output += `<tr>${cells(lines[index]).map(cell => `<td>${inline(cell)}</td>`).join('')}</tr>`; index++; rowCount++; } index--; output += '</tbody></table>'; continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/); if (heading) { closeList(); output += `<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`; continue; }
    if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) { closeList(); output += '<hr>'; continue; }
    const li = line.match(/^\s*(?:([-*+])|(\d+)\.)\s+(.+)$/); if (li) { const kind = li[2] ? 'ol' : 'ul'; if (list !== kind) { closeList(); list = kind; output += `<${kind}>`; } const value = li[3].replace(/^\[ \]\s*/,'☐ ').replace(/^\[x\]\s*/i,'☑ '); output += `<li>${inline(value)}</li>`; continue; }
    closeList(); if (/^>\s?/.test(line)) output += `<blockquote><p>${inline(line.replace(/^>\s?/,''))}</p></blockquote>`; else output += `<p>${inline(line)}</p>`;
  }
  closeList(); if (code) output += `<pre><code>${escapeHtml(buffer.join('\n'))}</code></pre>`; return output || '<p style="color:var(--subtle)">从第一句话开始。</p>';
}

async function saveTab(tab = activeTab()) {
  if (!markdownInputReady(tab)) return false;
  if (!tab || !tab.dirty || tab.saving || !tab.content?.editable) return !tab?.dirty; tab.saving = true; if (activeTab() === tab) renderEditorToolbar(tab);
  try {
    const savingDraft = tab.draft; const savingParagraphs = JSON.stringify((tab.paragraphs || []).map(({id,text}) => ({id,text})));
    const originals = new Map((tab.content.paragraphs || []).map(paragraph => [String(paragraph.id),paragraph.text]));
    const body = tab.item.kind === 'docx' ? {etag:tab.content.etag,paragraphs:tab.paragraphs.filter(paragraph => paragraph.editable && paragraph.text !== originals.get(String(paragraph.id))).map(({id,text}) => ({id,text}))} : {etag:tab.content.etag,content:savingDraft};
    const response = await api(tab.source === 'external' ? `/api/external/${encodeURIComponent(tab.id)}/content` : tab.source === 'skill' ? `/api/skills/${encodeURIComponent(tab.id)}` : `/api/content/${encodeURIComponent(tab.id)}`,{method:tab.source === 'external' ? 'POST' : 'PUT',body});
    const result = tab.source === 'external' ? response.content : response;
    tab.content = {...tab.content,...result}; tab.dirty = tab.draft !== savingDraft || JSON.stringify((tab.paragraphs || []).map(({id,text}) => ({id,text}))) !== savingParagraphs; tab.conflict = false; tab.saved = !tab.dirty; tab.saving = false; if (!tab.dirty) delete state.drafts[tab.key]; persistDrafts();
    if (activeTab() === tab) { renderTabs(); renderEditorToolbar(tab); renderEditorStatus(tab); } toast('已保存，原版本已备份。');
    if (tab.source === 'file') { const item = await api(`/api/items/${encodeURIComponent(tab.id)}`); tab.item = item; if (activeTab() === tab) renderInspector(); await refreshProjects(); if (state.section === 'assets') loadItems(); }
    else if (tab.source === 'external') { tab.item = {...tab.item,...response}; delete tab.item.content; renderTabs(); if (activeTab() === tab) renderInspector(); }
    else { tab.item = {...tab.item,...result,kind:'skill',bound:tab.item.bound}; state.skills = state.skills.map(skill => String(skill.id) === String(tab.id) ? {...skill,...tab.item} : skill); if (state.section === 'skills') renderSkills(); renderTabs(); if (activeTab() === tab) renderInspector(); }
    return !tab.dirty && markdownInputReady(tab);
  } catch(error) {
    tab.saving = false; if (error.status === 409) { tab.conflict = true; toast('文件已被其他程序修改。你的草稿仍保留，请先复制草稿，再重新打开文件核对。','error',11000); }
    else report(error); if (activeTab() === tab) { renderEditorToolbar(tab); renderEditorStatus(tab); } return false;
  }
}

function renderInspector() {
  const tab = activeTab(); const root = $('#inspector');
  if (!tab) { root.innerHTML = projectInspectorHtml(); return; }
  if (tab.error) { root.innerHTML = `<div class="inspector-heading"><span>资源信息尚未载入</span>${icon('alert')}</div><div class="project-panel"><p>完整制作信息未能读取，暂时不能修改属性。</p><p style="margin:12px 0 20px">${escapeHtml(tab.error)}</p><button class="button button-secondary" data-action="retry-detail">${icon('refresh')}重新载入</button></div>`; return; }
  if (tab.loading || (tab.source === 'file' && !tab.detailReady)) { root.innerHTML = '<div class="inspector-heading"><span>正在载入资源信息</span></div><div class="project-panel"><span class="spinner"></span><p style="margin-top:15px">正在读取完整制作信息与关联资源…</p></div>'; return; }
  if (tab.source === 'external') { root.innerHTML = `<div class="inspector-heading"><span>本地文件</span>${icon('eye')}</div><div class="project-panel"><h3>${escapeHtml(tab.item.name)}</h3><p>${escapeHtml(tab.content?.editable ? '直接编辑原文件，保存前自动备份。未加入项目。' : '此文件仅预览，未加入项目。')}</p><p class="trash-preview-path">${escapeHtml(tab.item.path)}</p><p>${escapeHtml(kindLabels[tab.item.kind] || '文件')} · ${formatSize(tab.item.size)}</p><button class="button button-secondary" data-action="copy-path">复制文件路径</button></div>`; return; }
  if (tab.source === 'skill') { renderSkillInspector(tab); return; }
  const item = tab.item; const properties = {...item,...tab.propertiesDraft}; const metadata = {...item.metadata,...tab.propertiesDraft?.metadata}; const relations = item.relations || []; const versions = item.versions || [];
  root.innerHTML = `<div class="inspector-heading"><span>资源信息</span><button class="icon-button" data-action="toggle-inspector" aria-label="收起资源信息" title="收起资源信息">${icon('panel')}</button></div><div class="inspector-section"><h2 class="inspector-item-title">${escapeHtml(item.name)}</h2><div class="inspector-filetype">${escapeHtml(kindLabels[item.kind] || '文件')} · ${formatSize(item.size)} · ${escapeHtml(categoryLabel(item.category))}</div><div class="inspector-actions"><button class="button button-secondary" data-action="reveal">${icon('folder')}定位文件</button><button class="button button-secondary" data-action="open-native">${icon('open')}本机打开</button></div><div class="inspector-actions"><button class="button button-ghost" data-action="rename-file">${icon('file')}文件重命名</button><button class="button button-ghost native-drag-handle" data-drag-file="${escapeHtml(item.id)}" title="按住，把真实文件拖到其他软件">${icon('upload')}拖出文件</button></div></div><form id="propertiesForm" class="inspector-section"><h3>制作信息</h3><div class="field"><label for="propertyName">显示名称</label><input id="propertyName" name="name" value="${escapeHtml(properties.name)}" maxlength="240" required><p class="field-hint">仅改变工作台名称；磁盘文件名请用上方重命名。</p></div><div class="fields-two"><div class="field"><label for="propertyCategory">资源分类</label><select id="propertyCategory" disabled>${optionHtml(categoryDefs.filter(value => value.key !== 'all'),properties.category)}</select></div><div class="field"><input type="hidden" name="category" value="${escapeHtml(properties.category)}"><label for="propertyStatus">制作状态</label><select id="propertyStatus" name="status">${optionHtml(statuses,properties.status || '待开始')}</select></div></div><div class="field"><label for="propertyTags">标签</label><input id="propertyTags" name="tags" value="${escapeHtml((properties.tags || []).join('，'))}" placeholder="夜景，主角，第一集"><p class="field-hint">用逗号分隔，可在高级检索中组合查询。</p></div><div class="field"><label for="propertyNotes">制作备注</label><textarea id="propertyNotes" name="notes" placeholder="记下需要调整或继续推进的地方…">${escapeHtml(properties.notes || '')}</textarea></div><details class="metadata-details" ${properties.category === 'shots' ? 'open' : ''}><summary>分镜与生成参数</summary><div class="fields-two">${metadataInput('镜号','shot_number',metadata.shot_number)}${metadataInput('时长（秒）','duration',metadata.duration)}${metadataInput('景别','shot_size',metadata.shot_size)}${metadataInput('摄影机 / 运镜','camera',metadata.camera)}</div><div class="field"><label for="meta_prompt">生成提示词</label><textarea id="meta_prompt" name="meta_prompt" placeholder="这个版本使用的提示词…">${escapeHtml(metadata.prompt || '')}</textarea></div><div class="field"><label for="meta_negative_prompt">反向提示词</label><textarea id="meta_negative_prompt" name="meta_negative_prompt">${escapeHtml(metadata.negative_prompt || '')}</textarea></div><div class="fields-two">${metadataInput('种子','seed',metadata.seed)}${metadataInput('版本','version',metadata.version)}</div>${metadataInput('模型','model',metadata.model)}</details><button class="button button-secondary properties-save" type="submit" disabled>${icon('save')}保存制作信息</button></form><div class="inspector-section"><h3>关联资源<span>${relations.length}</span></h3>${relations.length ? relations.map(relation => { const related = relation.item || {}; return `<div class="relation-item"><button data-item="${escapeHtml(related.id || relation.target_id)}">${icon(kindIcons[related.kind])}<span class="relation-copy"><span class="relation-name">${escapeHtml(related.name || '关联资源')}</span><span class="relation-type">${escapeHtml(relation.relation || '关联')}</span></span></button><button class="icon-button" data-remove-relation="${escapeHtml(relation.id)}" title="解除关联" aria-label="解除关联">${icon('close')}</button></div>`; }).join('') : '<p class="relation-empty">把这个分镜用到的角色、场景、道具、白模或生成版本连接起来。</p>'}<button class="button button-secondary button-small add-relation" data-action="add-relation">${icon('plus')}添加关联</button></div><div class="inspector-section"><h3>文件信息</h3><dl class="file-details"><dt>本地路径</dt><dd class="file-path">${escapeHtml(item.path)}</dd><dt>更新时间</dt><dd>${formatDate(item.mtime || item.updated,true)}</dd><dt>资源大小</dt><dd>${formatSize(item.size)}</dd></dl><button class="inline-link-button" data-action="copy-path">复制文件路径</button></div>${versions.length ? `<div class="inspector-section"><h3>保存前的版本<span>${versions.length}</span></h3>${versions.slice(0,5).map(version => `<div class="version-row"><span>${formatDate(version.created,true)}</span><span>${formatSize(version.size)}</span></div>`).join('')}<p class="field-hint">备份保存在本地，原版本不会被覆盖。</p></div>` : ''}<button class="remove-item-button" data-action="remove-item">删除文件（可恢复）</button>`;
  const form = $('#propertiesForm');
  $('.inspector-actions',root)?.insertAdjacentHTML('beforeend',`<button class="button button-secondary" data-action="move-active">${icon('move')}移动到</button>`);
  const sourceFields = [['source_prompt','原始提示词 / 节点参数'],['source_parameters','原始生成参数'],['source_workflow','原始工作流']].filter(([key]) => metadata[key]);
  if (sourceFields.length) form.insertAdjacentHTML('afterend',`<div class="inspector-section"><details class="metadata-details"><summary>原文件中的生成信息</summary><p class="field-hint" style="margin-bottom:14px">从文件中读取，保留原始内容。这里查看与复制，不改变你自己的制作参数。</p>${sourceFields.map(([key,label]) => { const value = typeof metadata[key] === 'string' ? metadata[key] : JSON.stringify(metadata[key],null,2); return `<div class="field"><label>${label}</label><textarea readonly aria-label="${label}" spellcheck="false">${escapeHtml(value.slice(0,20000))}</textarea>${value.length > 20000 ? '<p class="field-hint">此处显示前 2 万字符，复制可获取完整内容。</p>' : ''}<button class="inline-link-button" type="button" data-copy-source="${key}">复制完整内容</button></div>`; }).join('')}</details></div>`);
  $('.properties-save',form).disabled = !tab.propertiesDirty || !!tab.propertiesSaving;
  const changed = () => { captureProperties(tab,form); $('.properties-save',form).disabled = !!tab.propertiesSaving; renderTabs(); renderEditorStatus(tab); persistDrafts(); };
  form.addEventListener('input',changed); form.addEventListener('change',changed);
  form.addEventListener('submit',async event => { event.preventDefault(); captureProperties(tab,form); await saveProperties(tab); });
}
function projectInspectorHtml() {
  const project = currentProject(); const folder = currentFolder(); const counts = project?.counts || {};
  if (state.section === 'trash') return `<div class="inspector-heading"><span>回收站说明</span>${icon('restore')}</div><div class="project-panel"><h3>恢复，或确认后清理</h3><p>“恢复”将条目放回映序。点击“删除”或“清空回收站”，先核对文件位置，再将项目内文件移入 Windows 回收站。</p><div class="panel-separator"></div><p>成功清理后请到 Windows 回收站找回原文件；映序不再提供恢复。外部引用与外部 SKILL 的原文件保留。被其他项目使用或已变化的内容会提示原因。</p></div>`;
  if (state.section === 'skills') return `<div class="inspector-heading"><span>SKILL 管理</span>${icon('skills')}</div><div class="project-panel"><p>打开 SKILL 查看说明、编辑自建版本，或绑定到当前项目。</p><div class="panel-separator"></div><button class="button button-secondary" data-action="new-skill">${icon('plus')}创建 SKILL</button><p style="margin-top:16px">卡片右上角可删除自建 SKILL，或隐藏外部来源；回收站支持恢复。</p></div>`;
  if (state.section === 'context') return `<div class="inspector-heading"><span>项目交接</span>${icon('context')}</div><div class="project-panel"><p>更新项目进度后，把交接文件路径或交接指令发给 Codex，让它继续处理现有项目。</p><div class="panel-separator"></div><p>交接文件保存在项目目录中，可以用其他本地工具直接读取。</p></div>`;
  if (folder) return `<div class="inspector-heading"><span>文件夹信息</span>${icon('folder')}</div><div class="project-panel"><h3>${escapeHtml(folder.name)}</h3><p>${escapeHtml(categoryLabel(folder.category))} · ${folder.count || 0} 个直属文件</p><div class="panel-separator"></div><dl class="file-details"><dt>位置</dt><dd class="file-path">${escapeHtml(folder.path)}</dd></dl><div class="inspector-actions"><button class="button button-secondary" data-action="rename-current-folder">重命名</button><button class="button button-ghost" data-action="trash-current-folder">${icon('trash')}删除</button></div></div>`;
  return `<div class="inspector-heading"><span>项目信息</span>${icon('folder')}</div><div class="project-panel"><h3>${escapeHtml(project?.name || '尚未选择项目')}</h3>${project?.description ? `<p>${escapeHtml(project.description)}</p>` : ''}<dl class="project-detail-list"><div><dt>资源</dt><dd>${counts.total || 0}</dd></div><div><dt>分镜</dt><dd>${counts.shots || 0}</dd></div><div><dt>已完成分镜</dt><dd>${counts.completed || 0}</dd></div></dl>${project ? `<div class="panel-separator"></div><div class="field-label">项目目录</div><p class="file-path" style="margin-top:9px">${escapeHtml(project.root)}</p><div class="panel-separator"></div><button class="quick-start-link" data-action="new-item">${icon('file')}<span>新建文档</span></button><button class="quick-start-link" data-action="new-folder">${icon('folder')}<span>新建文件夹</span></button><button class="quick-start-link" data-action="edit-current-project">${icon('more')}<span>编辑项目</span></button>` : '<button class="button button-primary" data-action="new-project">创建项目</button>'}</div>`;
}
function metadataInput(label,name,value) { return `<div class="field"><label for="meta_${name}">${label}</label><input id="meta_${name}" name="meta_${name}" value="${escapeHtml(value ?? '')}"></div>`; }

function captureProperties(tab,form) {
  if (!tab || tab.loading || tab.error || !tab.detailReady || tab.source !== 'file') return;
  const data = new FormData(form); const metadata = {};
  ['shot_number','duration','shot_size','camera','prompt','negative_prompt','seed','version','model'].forEach(key => { metadata[key] = String(data.get(`meta_${key}`) || '').trim(); });
  tab.propertiesDraft = {name:String(data.get('name') || '').trim(),category:data.get('category'),status:data.get('status'),tags:String(data.get('tags') || '').split(/[,，\n]/).map(tag => tag.trim()).filter(Boolean),notes:String(data.get('notes') || ''),metadata};
  tab.propertiesDirty = true;
}
async function saveProperties(tab = activeTab()) {
  if (!tab || !tab.propertiesDirty) return true;
  if (tab.loading || tab.error || !tab.detailReady || tab.source !== 'file') { toast('完整资源信息尚未载入，暂时不能保存制作信息。','error'); return false; }
  if (tab.propertiesSaving) return false;
  const snapshot = JSON.stringify(tab.propertiesDraft); const draft = JSON.parse(snapshot);
  if (!draft.name?.trim()) { toast('请填写显示名称后再保存。','error'); return false; }
  tab.propertiesSaving = true; if (activeTab() === tab && $('#propertiesForm')) $('.properties-save',$('#propertiesForm')).disabled = true;
  try {
    const result = await api(`/api/items/${encodeURIComponent(tab.id)}`,{method:'PATCH',body:{...draft,metadata:{...tab.item.metadata,...draft.metadata}}});
    tab.item = {...tab.item,...result}; tab.propertiesDirty = JSON.stringify(tab.propertiesDraft) !== snapshot;
    if (!tab.propertiesDirty) tab.propertiesDraft = null; tab.propertiesSaving = false; persistDrafts(true); renderTabs();
    if (activeTab() === tab) { renderInspector(); renderEditorStatus(tab); }
    toast('制作信息已更新。'); await refreshProjects().catch(report); if (state.section === 'assets') await loadItems(); return !tab.propertiesDirty;
  } catch(error) { tab.propertiesSaving = false; if (activeTab() === tab && $('#propertiesForm')) $('.properties-save',$('#propertiesForm')).disabled = false; persistDrafts(true); report(error); return false; }
}
async function guardProperties(tab = activeTab()) {
  if (!markdownInputReady(tab)) return false;
  if (state.restoringDrafts) return true;
  if (!tab?.propertiesDirty) return true;
  const choice = await choose('制作信息还没有保存',`「${tab.item.name}」的名称、标签、备注或分镜参数有未保存修改。`,[{key:'cancel',label:'继续编辑',style:'ghost'},{key:'discard',label:'放弃修改',style:'secondary'},{key:'save',label:'保存制作信息',style:'primary'}]);
  if (!choice || choice === 'cancel') return false;
  if (choice === 'save') return saveProperties(tab);
  tab.propertiesDirty = false; tab.propertiesDraft = null; persistDrafts(true); renderTabs(); if (activeTab() === tab) { renderInspector(); renderEditorStatus(tab); } return true;
}
async function saveCurrent() {
  const tab = activeTab(); if (!tab) return;
  if (tab.dirty && !await saveTab(tab)) return;
  if (tab.propertiesDirty) await saveProperties(tab);
}

function showDialog({title,subtitle='',body='',submit='确定',wide=false,onSubmit,actions}) {
  const dialog = $('#appDialog'); if (dialog.open) dialog.close(); const sequence = ++state.modalSequence; state.modalBusy = false; dialog.classList.toggle('wide',wide);
  $('#dialogTitle').textContent = title; $('#dialogSubtitle').textContent = subtitle; $('#dialogBody').innerHTML = body; $('#dialogError').hidden = true;
  $('#dialogActions').innerHTML = actions || `<button type="button" class="button button-ghost" data-dialog-cancel>取消</button><button type="submit" class="button button-primary">${escapeHtml(submit)}</button>`;
  $('#dialogForm').onsubmit = async event => { event.preventDefault(); if (state.modalBusy || !onSubmit) return; state.modalBusy = true; $('#dialogError').hidden = true; const submitButton = $('#dialogActions button[type="submit"]'); if (submitButton) submitButton.disabled = true;
    try { const close = await onSubmit($('#dialogForm')); if (sequence === state.modalSequence && close !== false) dialog.close(); }
    catch(error) { if (sequence === state.modalSequence) { $('#dialogError').textContent = error.message; $('#dialogError').hidden = false; } }
    finally { if (sequence === state.modalSequence) { state.modalBusy = false; if (submitButton) submitButton.disabled = false; } }
  };
  $$('[data-dialog-cancel]').forEach(button => button.addEventListener('click',() => { if (!state.modalBusy) dialog.close(); })); dialog.showModal(); return dialog;
}
function choose(title,subtitle,choices) { return new Promise(resolve => { const dialog = showDialog({title,subtitle,actions:choices.map(choice => `<button type="button" class="button button-${choice.style || 'secondary'}" data-choice="${choice.key}">${choice.label}</button>`).join('')}); let resolved = false; $$('[data-choice]',dialog).forEach(button => button.addEventListener('click',() => { resolved = true; dialog.close(); resolve(button.dataset.choice); })); dialog.addEventListener('close',() => { if (!resolved) resolve(null); },{once:true}); }); }
async function newProjectDialog() {
  if (!await guardProperties()) return;
  showDialog({title:'建立一个创作项目',subtitle:'映序会为剧本、分镜与素材建立清晰的本地目录。',submit:'创建项目',body:'<div class="field"><label for="projectName">项目名称</label><input id="projectName" name="name" placeholder="例如：雨巷来信 · 第一季" maxlength="80" required autofocus></div><div class="field"><label for="projectDescription">一句话介绍这个故事</label><textarea id="projectDescription" name="description" placeholder="创作主题、风格，或这个项目想要表达的内容…" maxlength="2000"></textarea></div><p class="dialog-hint">项目文件保存在本机。创建后可以直接编写文档，也可以引用已有素材目录。</p>',onSubmit:async form => { const data = new FormData(form); const project = await api('/api/projects',{method:'POST',body:{name:String(data.get('name')).trim(),description:String(data.get('description')).trim()}}); await refreshProjects(); state.projectId = project.id; state.section = 'assets'; state.category = 'all'; state.offset = 0; await selectProject(project.id); toast('项目已建立，可以开始写下第一幕。'); }});
}
async function newItemDialog(category,options = {}) {
  if (!await guardProperties()) return;
  if (state.section === 'skills' && !category && !options.note) { newSkillDialog(); return; } if (!(options.location?.project_id || state.projectId)) { newProjectDialog(); return; }
  const location = options.location || {project_id:state.projectId,category:state.category,folder_id:state.folderId};
  const selected = category || (location.category === 'all' ? 'scripts' : location.category) || 'scripts'; const projectId = location.project_id; const folderId = selected === location.category ? location.folder_id || null : null;
  const dialog = showDialog({title:options.note ? '新建笔记' : selected === 'shots' ? '新建分镜' : '新建文档',subtitle:'保存为本地 Markdown 文件。',submit:'创建并打开',body:`<div class="field"><label for="itemName">${options.note ? '笔记名称' : selected === 'shots' ? '分镜名称' : '文档名称'}</label><input id="itemName" name="name" placeholder="例如：001 · 雨中的相遇" maxlength="150" required autofocus></div><div class="fields-two"><div class="field"><label for="itemCategory">分类</label><select id="itemCategory" name="category">${optionHtml(categoryDefs.filter(value => value.key !== 'all'),selected)}</select></div><div class="field"><label for="itemFolder">文件夹</label><select id="itemFolder" name="folder_id">${folderOptions(projectId === state.projectId && selected === state.category ? state.folders : [],folderId)}</select></div></div>`,onSubmit:async form => { requireFolderSelection('#itemFolder'); const data = new FormData(form); const name = String(data.get('name')).trim(); const category = data.get('category'); const targetFolder = data.get('folder_id') || null; const content = !options.note && category === 'shots' ? `# ${name}\n\n## 画面与表演\n\n\n## 镜头与声音\n\n\n## 制作备注\n\n` : ''; if (String(projectId) !== String(state.projectId)) await recordProjectVisit(projectId); const item = await api('/api/items',{method:'POST',body:{project_id:projectId,category,folder_id:targetFolder,name,content,status:'待开始'}}); state.projectId = projectId; storage.set('yingxu:project',String(projectId)); state.section = 'assets'; state.category = category; state.folderId = targetFolder; state.folderScope = 'current'; state.offset = 0; state.selectedIds.clear(); await refreshProjects(); await loadItems(); await openItem(item.id); toast(options.note ? '笔记已创建。' : '文档已创建。'); }});
  bindFolderSelector(dialog,'#itemCategory','#itemFolder',projectId,selected,folderId);
}
function importDialog() {
  if (!state.projectId) { newProjectDialog(); return; }
  const selected = state.category === 'all' ? 'references' : state.category; const projectId = state.projectId;
  const dialog = showDialog({title:'导入文件',subtitle:'选择文件、目录，或粘贴本地路径。',submit:'开始导入',body:`<div class="fields-two"><div class="field"><label for="importCategory">分类</label><select id="importCategory" name="category">${optionHtml(categoryDefs.filter(value => value.key !== 'all'),selected)}</select></div><div class="field"><label for="importFolder">文件夹</label><select id="importFolder" name="folder_id">${folderOptions(selected === state.category ? state.folders : [],state.folderId)}</select></div></div><div class="import-pickers"><button class="button button-secondary" type="button" data-pick="files">${icon('file')}选择文件</button><button class="button button-secondary" type="button" data-pick="folder">${icon('folder')}选择文件夹</button></div><div class="field"><label for="importPaths">文件路径（每行一个）</label><textarea class="selected-paths" id="importPaths" name="paths" placeholder="F:\\我的视频项目\\角色素材&#10;F:\\我的视频项目\\剧本.docx" required></textarea></div><p class="dialog-hint">引用原位置的文件，不复制或移动。直接把文件拖入页面，则会保存项目副本。</p>`,onSubmit:async form => { requireFolderSelection('#importFolder'); const data = new FormData(form); const paths = String(data.get('paths')).split(/\r?\n/).map(path => path.trim().replace(/^"|"$/g,'')).filter(Boolean); if (!paths.length) throw new Error('请选择文件，或填写至少一个本地路径。'); const result = await api('/api/import',{method:'POST',body:{project_id:projectId,category:data.get('category'),folder_id:data.get('folder_id') || null,paths}}); monitorJob(result.job_id,'正在整理导入的素材'); }});
  bindFolderSelector(dialog,'#importCategory','#importFolder',projectId,selected,state.folderId);
  $$('[data-pick]',dialog).forEach(button => button.addEventListener('click',async () => { button.disabled = true; try { const result = await api('/api/pick',{method:'POST',body:{kind:button.dataset.pick}}); if (result.paths?.length && dialog.open) { const existing = $('#importPaths').value.trim(); $('#importPaths').value = [...new Set([...existing.split(/\r?\n/).filter(Boolean),...result.paths])].join('\n'); } } catch(error) { $('#dialogError').textContent = error.message; $('#dialogError').hidden = false; } finally { button.disabled = false; } }));
}
async function monitorJob(id,label) {
  if (!id) return; const token = {}; state.jobs.set(id,token); const tray = $('#jobTray'); tray.hidden = false; tray.innerHTML = `<span class="spinner"></span><span>${escapeHtml(label)}…</span>`;
  try {
    for (let count = 0; count < 7200 && state.jobs.get(id) === token; count++) {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`); tray.innerHTML = `<span class="spinner"></span><span>${escapeHtml(job.message || label)} · 已处理 ${job.done || 0} 项</span>`;
      if (job.state === 'done' || job.state === 'error') {
        if (job.state === 'error') throw new Error(job.message || job.errors?.[0] || '素材整理未完成。');
        state.jobs.delete(id); tray.hidden = true; await refreshProjects(); if (state.section === 'assets') await loadItems(); toast(`素材已整理：${job.done || 0} 项${job.skipped ? `，跳过 ${job.skipped} 项` : ''}。`); if (job.errors?.length) toast(`部分文件未导入：${String(job.errors[0])}`,'info',8000); return;
      }
      await new Promise(resolve => setTimeout(resolve,1100));
    }
    toast('整理任务仍在后台运行，可稍后使用“同步项目文件”查看。','info',6000);
  } catch(error) { report(error); } finally { state.jobs.delete(id); if (!state.jobs.size) tray.hidden = true; }
}
function advancedSearchDialog() {
  showDialog({title:'高级检索',subtitle:'多个条件同时满足，快速找到需要继续制作的素材。',submit:'应用筛选',body:`<div class="field"><label for="queryText">关键词与查询条件</label><input id="queryText" name="q" value="${escapeHtml(state.q)}" placeholder="雨巷 tag:夜景 type:video"><p class="field-hint">支持 tag:夜景、type:video、status:已完成、category:scenes。普通文字检索名称与可搜索内容。</p></div><div class="fields-two"><div class="field"><label for="advancedStatus">制作状态</label><select id="advancedStatus" name="status"><option value="">全部状态</option>${optionHtml(statuses,state.status)}</select></div><div class="field"><label for="advancedKind">文件类型</label><select id="advancedKind" name="kind"><option value="">全部类型</option>${optionHtml(Object.entries(kindLabels).filter(([key]) => key !== 'skill').map(([key,label]) => ({key,label})),state.kind)}</select></div></div><div class="dialog-hint">例：<strong>夜景 tag:主角 type:video</strong><br>查找文字包含“夜景”、带“主角”标签的视频。</div>`,onSubmit:async form => { const data = new FormData(form); state.q = String(data.get('q')).trim(); state.status = data.get('status'); state.kind = data.get('kind'); state.offset = 0; $('#searchInput').value = state.q; $('#statusFilter').value = state.status; $('#kindFilter').value = state.kind; await loadItems(); }});
}
async function relationDialog() {
  const tab = activeTab(); if (!tab || tab.source !== 'file') return; let selected = null; let request = 0;
  const dialog = showDialog({title:'连接相关的创作资源',subtitle:`为「${tab.item.name}」关联角色、场景、道具或生成版本。`,submit:'添加关联',body:'<div class="field"><label for="relationType">关联的用途</label><select id="relationType" name="relation"><option>角色</option><option>场景</option><option>道具</option><option>白模参考</option><option>生成版本</option><option>关联文档</option><option>参考资料</option></select></div><div class="field"><label for="relationSearch">搜索当前项目的资源</label><input id="relationSearch" type="search" placeholder="输入名称或标签…" autocomplete="off"></div><div id="relationResults" class="relation-results"><div class="subtle-loading">正在读取资源…</div></div>',onSubmit:async form => { if (!selected) throw new Error('请先选择一个要关联的资源。'); await api('/api/relations',{method:'POST',body:{source_id:tab.id,target_id:selected,relation:new FormData(form).get('relation')}}); tab.item = await api(`/api/items/${encodeURIComponent(tab.id)}`); if (activeTab() === tab) renderInspector(); toast('资源已关联。'); }});
  const find = async () => { const seq = ++request; try { const params = new URLSearchParams({project:tab.item.project_id,q:$('#relationSearch').value,limit:30,offset:0}); const result = await api(`/api/items?${params}`); if (!dialog.open || seq !== request || !$('#relationResults')) return; const items = (result.items || []).filter(item => String(item.id) !== String(tab.id)); $('#relationResults').innerHTML = items.length ? items.map(item => `<label class="relation-option"><input type="radio" name="target" value="${escapeHtml(item.id)}">${icon(kindIcons[item.kind])}<span class="relation-option-text"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(categoryLabel(item.category))} · ${escapeHtml(item.status || '待开始')}</small></span></label>`).join('') : '<div class="subtle-loading">没有找到可关联的资源。</div>'; $$('input[name="target"]',dialog).forEach(input => input.addEventListener('change',() => selected = input.value)); } catch(error) { if ($('#relationResults')) $('#relationResults').textContent = error.message; } };
  $('#relationSearch').addEventListener('input',debounce(find)); await find();
}
function filenameParts(tab) {
  const filename = String(tab.item.path || tab.item.name).split(/[\\/]/).pop();
  const dot = filename.lastIndexOf('.');
  return dot > 0 ? {title:filename.slice(0,dot),extension:filename.slice(dot)} : {title:filename,extension:''};
}
async function renameTabFile(tab,title) {
  if (!tab || tab.source !== 'file' || tab.loading || tab.saving || tab.propertiesSaving || !markdownInputReady(tab)) throw new Error('请等待当前保存或输入完成，再修改标题。');
  const parts = filenameParts(tab), name = String(title).trim();
  if (!name) throw new Error('标题不能为空。');
  if (name.length+parts.extension.length > 100) throw new Error(`标题最多 ${100-parts.extension.length} 个字符。`);
  const previousName = tab.item.name;
  const result = await api('/api/rename',{method:'POST',body:{id:tab.id,name:name+parts.extension}});
  tab.item = result.item || result;
  if (!tab.item.id) tab.item = await api(`/api/items/${encodeURIComponent(tab.id)}`);
  if (tab.propertiesDraft?.name === previousName) tab.propertiesDraft.name = tab.item.name;
  persistDrafts(true); renderTabs();
  if (activeTab() === tab) {
    const heading = $('#editorContent .document-heading'); if (heading) heading.outerHTML = markdownDocumentHeading(tab);
    renderInspector();
  }
  await loadItems(); toast('标题和文件名称已更新。');
}
function renameDialog({titleOnly = false} = {}) {
  const tab = activeTab(); if (!tab || tab.source !== 'file' || tab.loading || tab.saving || tab.propertiesSaving || !markdownInputReady(tab)) return;
  if (titleOnly && !tab.content?.editable) return;
  const parts = filenameParts(tab);
  showDialog({title:titleOnly ? '修改标题' : '重命名文件',subtitle:'修改后同步更新文件名称，正文保持不变。',submit:'保存名称',body:`<div class="field"><label for="diskFilename">${titleOnly ? '标题' : '文件名称'}</label><input id="diskFilename" name="name" value="${escapeHtml(parts.title)}" required maxlength="${100-parts.extension.length}"><p class="field-hint">只需填写名称，文件后缀自动保留。同名文件不会被覆盖；外部软件引用的旧路径需要同步更新。</p></div>`,onSubmit:async form => renameTabFile(tab,String(new FormData(form).get('name')))});
}

async function loadSkills() {
  const sequence = ++state.listSequence; state.listController?.abort(); configureSection(); $('#resourceItems').className = 'resource-grid'; $('#resourceItems').innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
  try { const params = new URLSearchParams({q:state.q}); if (state.projectId) params.set('project',state.projectId); const result = await api(`/api/skills?${params}`); if (sequence !== state.listSequence || state.section !== 'skills') return; state.skills = result.skills || []; for (const tab of state.tabs.filter(value => value.source === 'skill')) { const current = state.skills.find(skill => String(skill.id) === String(tab.id)); if (current) tab.item.bound = !!current.bound; } renderSkills(); renderInspector(); }
  catch(error) { if (error.name === 'AbortError' || sequence !== state.listSequence || state.section !== 'skills') return; $('#resourceItems').innerHTML = emptyHtml('暂时无法读取 SKILL 库',error.message,'skills','重新读取','retry'); report(error); }
}
function renderSkills() {
  const root = $('#resourceItems'); root.className = 'resource-grid skill-grid'; $('#resourceCount').textContent = state.skills.length; $('#searchTiming').textContent = '';
  root.innerHTML = `<div class="skill-actions"><span>将创作规范变成可复用的能力。</span><button class="button button-secondary button-small" data-action="refresh-skills">${icon('refresh')}扫描本机 SKILL</button></div>` + (state.skills.length ? state.skills.slice(state.offset,state.offset+state.limit).map(skill => `<article class="skill-card" tabindex="0" role="button" data-skill="${escapeHtml(skill.id)}"><button class="icon-button resource-more-button skill-menu-button" data-skill-menu="${escapeHtml(skill.id)}" title="SKILL 选项" aria-label="${escapeHtml(skill.name)} SKILL 选项">${icon('more')}</button><div class="skill-card-top"><span class="skill-symbol">${icon('skills')}</span>${skill.bound ? '<span class="skill-bound">项目已启用</span>' : `<span class="skill-source">${escapeHtml(skill.source_label || skill.source || (skill.editable ? '映序自定义' : '本机 SKILL'))}</span>`}</div><h3>${escapeHtml(skill.name)}</h3><p>${escapeHtml(skill.description || '打开阅读能力说明与操作规范。')}</p><div class="skill-card-bottom"><span>${skill.editable ? '可编辑' : '只读源文件'}</span>${icon('chevron')}</div></article>`).join('') : emptyHtml('积累属于你的创作方法','先扫描本机已有的 SKILL，或者创建一份新的创作规范。','skills','创建 SKILL','new-skill'));
  updatePagination();
}
async function openSkill(id) {
  const key = `skill:${id}`; if (state.activeKey !== key && !await guardProperties()) return; let tab = state.tabs.find(value => value.key === key); if (tab) { state.activeKey = key; renderWorkspace(); return; }
  const found = state.skills.find(skill => String(skill.id) === String(id)); tab = {key,id,source:'skill',item:{...found,name:found?.name || '正在打开 SKILL…',kind:'skill'},loading:true,dirty:false,mode:'preview'}; state.tabs.push(tab); state.activeKey = key; renderWorkspace();
  try { const skill = await api(`/api/skills/${encodeURIComponent(id)}`); tab.item = {...found,...skill,bound:found?.bound ?? skill.bound,kind:'skill'}; tab.content = {format:'markdown',content:skill.content,etag:skill.etag,editable:!!skill.editable}; tab.draft = String(skill.content || ''); tab.loading = false; applyDraft(tab); if (tab.content.editable && canUseMarkdownEditor(tab)) tab.mode = 'live'; if (state.activeKey === key) renderWorkspace(); else renderTabs(); }
  catch(error) { tab.loading = false; tab.error = error.message; if (state.activeKey === key) renderWorkspace(); report(error); }
}
function renderSkillInspector(tab) {
  const skill = tab.item; $('#inspector').innerHTML = `<div class="inspector-heading"><span>SKILL 信息</span>${icon('skills')}</div><div class="inspector-section"><h2 class="inspector-item-title">${escapeHtml(skill.name)}</h2><p class="field-hint">${escapeHtml(skill.description || '')}</p><div class="storage-card"><div class="storage-card-heading">${icon(skill.editable ? 'file' : 'lock')}${skill.editable ? '映序自己的 SKILL' : '已有 SKILL · 只读'}</div><p>${skill.editable ? '可以在编辑区修改内容，保存时保留原版本。' : '为保护已有工具，这里阅读原文件。需要修改时可以复制为自己的 SKILL。'}</p></div></div><div class="inspector-section"><h3>当前项目</h3><p class="relation-empty">${state.projectId ? `将这个能力加入「${escapeHtml(currentProject()?.name)}」的交接文件，让 AI 了解该遵循的工作方法。` : '选择或创建一个项目后，即可为它绑定 SKILL。'}</p><button class="button ${skill.bound ? 'button-secondary' : 'button-primary'} properties-save" data-action="bind-skill" ${!state.projectId ? 'disabled' : ''}>${icon(skill.bound ? 'check' : 'plus')}${skill.bound ? '项目已启用 · 点击解绑' : '加入当前项目'}</button></div><div class="inspector-section"><h3>来源</h3><dl class="file-details"><dt>位置</dt><dd class="file-path">${escapeHtml(skill.path || '映序本地 SKILL 库')}</dd><dt>来源</dt><dd>${escapeHtml(skill.source_label || skill.source || '本机')}</dd></dl><button class="inline-link-button" data-action="copy-path">复制路径</button></div><div class="inspector-section"><button class="button button-secondary properties-save" data-action="copy-skill">${icon('copy')}复制为我的 SKILL</button></div>`;
  $('#inspector').insertAdjacentHTML('beforeend',`<div class="inspector-section"><button class="button button-ghost properties-save" data-action="delete-skill">${icon('trash')}${skill.editable ? '删除自建 SKILL' : '隐藏这个 SKILL'}</button></div>`);
}
async function newSkillDialog(template) {
  if (!await guardProperties()) return;
  showDialog({title:template ? '保存为自己的 SKILL' : '创建一份创作 SKILL',subtitle:'能力说明采用 Markdown 格式，创建后即可编辑完整内容。',submit:'创建并编辑',body:`<div class="field"><label for="skillName">能力名称</label><input id="skillName" name="name" value="${escapeHtml(template ? `${template.name} · 我的版本` : '')}" placeholder="例如：电影感分镜审阅" required maxlength="100"></div><div class="field"><label for="skillDescription">用途说明</label><textarea id="skillDescription" name="description" placeholder="这个能力用于什么场景，应当如何帮助你…" maxlength="2000">${escapeHtml(template?.description || '')}</textarea></div>`,onSubmit:async form => { const data = new FormData(form); const name = String(data.get('name')).trim(); const description = String(data.get('description')).trim(); const content = template?.content?.replace(/^\uFEFF?---\r?\n[\s\S]*?\r?\n(?:---|\.\.\.)(?:\r?\n|$)/,'').trimStart() || `# ${name}\n\n${description}\n\n## 适用场景\n\n\n## 工作步骤\n\n1. \n\n## 输出要求\n\n`; const result = await api('/api/skills',{method:'POST',body:{name,description,content}}); state.section = 'skills'; renderNavigation(); renderHero(); await loadSkills(); await openSkill(result.id); const tab = activeTab(); if (tab) { tab.mode = canUseMarkdownEditor(tab) ? 'live' : 'edit'; renderWorkspace(); } toast('SKILL 已创建。'); }});
}
async function loadContext() {
  const sequence = ++state.listSequence; state.listController?.abort(); configureSection(); $('#resourceItems').className = 'context-page'; $('#resourceCount').textContent = ''; $('#searchTiming').textContent = '';
  if (!state.projectId) { $('#resourceItems').innerHTML = emptyHtml('先建立一个创作项目','项目创建后，这里会汇总进度与创作资源，方便 Codex 等协作者读取。','context','创建项目','new-project'); return; }
  $('#resourceItems').innerHTML = '<div class="editor-loading" style="min-height:260px"><span class="spinner"></span><span>正在读取项目交接…</span></div>';
  try { const result = await api(`/api/context?project=${encodeURIComponent(state.projectId)}`); if (sequence !== state.listSequence || state.section !== 'context') return; state.context = result; renderContext(); renderInspector(); } catch(error) { if (error.name === 'AbortError' || sequence !== state.listSequence || state.section !== 'context') return; $('#resourceItems').innerHTML = emptyHtml('暂时无法读取项目交接',error.message,'context','重试','retry'); report(error); }
}
function renderContext() {
  const context = state.context || {}; const counts = currentProject()?.counts || {};
  $('#resourceItems').innerHTML = `<div class="context-actions"><div><span class="context-ready">${icon(context.stale ? 'clock' : 'check')}${context.stale ? '项目进度有新变化' : '项目进度已准备好'}</span><p>${context.stale ? '刷新后，就可以交给下一位协作者。' : `最近汇总：${formatDate(context.updated,true)}`}</p></div><button class="button button-secondary" data-action="refresh-context">${icon('refresh')}刷新进度</button></div><div class="handoff-card"><div class="handoff-symbol">${icon('context')}</div><h3>继续创作，不必重新解释整个项目。</h3><p>把交接文件发给 Codex。它就能读到项目进度、分镜状态、资源关系和创作规范，在现有成果上接着工作。</p><div class="handoff-counts"><span><strong>${counts.total || 0}</strong> 项创作资源</span><span><strong>${counts.shots || 0}</strong> 个分镜</span><span><strong>${counts.completed || 0}</strong> 个分镜已完成</span></div><button class="button button-primary" data-action="copy-handoff">${icon('copy')}复制给 AI 的交接指令</button><span class="handoff-caption">粘贴后，补上一句你接下来想做的事。</span></div><div class="context-path"><span>${icon('file')}这份交接文件保存在你的项目里</span><code>${escapeHtml(context.path || '')}</code><button class="inline-link-button" data-action="copy-context-path">复制文件路径</button></div><details class="context-details"><summary>查看完整交接内容<span>供 AI 读取的项目记录 ${icon('down')}</span></summary><div class="context-detail-actions"><button class="button button-ghost button-small" data-action="copy-context">${icon('copy')}复制完整内容</button></div><article class="markdown-preview context-preview">${markdown(context.markdown || '暂无交接内容，请点击刷新进度。')}</article></details>`;
}

async function copyText(value,message='已复制。') { try { await navigator.clipboard.writeText(String(value || '')); toast(message); } catch { showDialog({title:'复制内容',subtitle:'当前窗口不能直接访问剪贴板，可在下方选择并复制。',body:`<div class="field"><textarea id="copyFallback" readonly style="min-height:200px">${escapeHtml(value)}</textarea></div>`,actions:'<button class="button button-primary" type="button" data-dialog-cancel>完成</button>'}); $('#copyFallback').select(); } }
async function runNative(action) { const tab = activeTab(); if (!tab || tab.source !== 'file') return; await api('/api/open',{method:'POST',body:{id:tab.id,action}}); }
function runtimeSummary() { if (window.yingxuMac) return '<p class="muted">macOS 试用版 · 原文件可通过 Finder 定位后拖出。截图与菜单栏常驻暂未提供。</p>';  const caps = state.bootstrap?.capabilities || {}; return `<p class="muted">图片缩略图：${caps.image_thumbnails === false ? '组件缺失，请重新解压完整包' : '可用'} · 视频缩略图：${caps.ffmpeg ? '可用' : '组件缺失，请使用完整包'} · 拖出原文件：${window.yingxuDesktopDrag ? '可用' : '请从桌面程序打开'}</p>`; }
function helpDialog() { showDialog({title:'让每个镜头都有来处',subtitle:'映序把本地创作文件串成项目，你可以从最熟悉的一步开始。',wide:true,body:`${runtimeSummary()}<div class="guide-grid"><div class="guide-item"><strong>${icon('folder')}项目与分类</strong><p>创建项目，再用剧本、分镜、角色、场景、道具等分类整理内容。卡片可拖到左侧分类。</p></div><div class="guide-item"><strong>${icon('script')}像笔记一样写作</strong><p>右键空白处、项目或文件夹可新建笔记。单击打开文件，多标签自由切换；Markdown 支持实时预览编辑，Word 可修改正文段落。Ctrl+K 可跨项目查找名称与已索引正文，点击结果直接打开。</p></div><div class="guide-item"><strong>${icon('link')}把创作线索连起来</strong><p>在右侧信息面板把角色、场景、白模视频、生成版本关联到具体分镜，并记录状态与提示词。</p></div><div class="guide-item"><strong>${icon('upload')}导入与拖放</strong><p>导入目录引用原文件；把文件拖进页面会保存项目副本。桌面版直接拖动图片或卡片即可拖到其他软件。先点第一项，按住 Shift 点最后一项可连续多选并一起拖动。</p></div><div class="guide-item"><strong>${icon('skills')}集中管理 SKILL</strong><p>阅读已有 SKILL，创建自己的创作规范。右键 SKILL 可打开其所在位置；绑定到项目后，交接文件会记录相关能力与位置。</p></div><div class="guide-item"><strong>${icon('context')}把进度交给 AI</strong><p>在 AI 协作中刷新项目进度，将本地交接文件路径发给 Codex，继续处理已有项目。</p></div></div><div class="shortcut-list"><span>当前页面搜索<kbd>Ctrl F</kbd></span><span>全局搜索<kbd>Ctrl K</kbd></span><span>保存<kbd>Ctrl S</kbd></span><span>帮助<kbd>?</kbd></span></div>`,actions:'<button class="button button-primary" type="button" data-dialog-cancel>开始创作</button>'}); }

async function handleAction(action,target) {
  if (action === 'capture-screen') return captureScreen();
  if (action === 'global-search') return globalSearchDialog();
  if (action === 'settings') return settingsDialog();
  if (action === 'project-library') return projectLibraryDialog();
  if (['choose-external-files','register-open-with','unregister-open-with'].includes(action)) return desktopMessage(action);
  try {
    if (action === 'empty-trash') return deleteTrash(null,null,true);
    if (action === 'reload') return location.reload(); if (action === 'new-project') return newProjectDialog(); if (action === 'new-item') return newItemDialog(); if (action === 'new-shot') return newItemDialog('shots'); if (action === 'import') return importDialog(); if (action === 'save-content') return saveTab();
    if (action === 'new-folder') return newFolderDialog(); if (action === 'rename-current-folder') return folderRenameDialog(state.folderId); if (action === 'trash-current-folder') return trashFolder(state.folderId); if (action === 'edit-current-project') return projectRenameDialog(state.projectId);
    if (action === 'move-active') { const tab = activeTab(); if (tab?.source === 'file') return moveDialog([tab.id]); return; }
    if (action === 'delete-skill') { const tab = activeTab(); if (tab?.source === 'skill') return trashSkill(tab.id); return; }
    if (action === 'retry') return loadSection();
    if (action === 'retry-detail') { const tab = activeTab(); if (!tab || tab.loading) return; persistDrafts(true); state.tabs = state.tabs.filter(value => value.key !== tab.key); if (tab.source === 'skill') return openSkill(tab.id); if (tab.source === 'external') return openExternal(tab.id); return openItem(tab.id); }
    if (action === 'demo') { target.disabled = true; const project = await api('/api/demo',{method:'POST',body:{}}); await refreshProjects(); await selectProject(project.id); toast('已打开示例项目，所有示例文件都可以放心体验。'); return; }
    if (action === 'clear-search' || action === 'clear-filters') { state.q = ''; $('#searchInput').value = ''; if (action === 'clear-filters') { state.status = ''; state.kind = ''; $('#statusFilter').value = ''; $('#kindFilter').value = ''; } state.offset = 0; return loadSection(); }
    if (action === 'toggle-inspector') { $('#workspace').classList.toggle('show-inspector'); return; }
    if (action === 'open-native') return runNative('open'); if (action === 'reveal') return runNative('reveal');
    if (action === 'rename-title') return renameDialog({titleOnly:true});
    if (action === 'copy-path') return copyText(activeTab()?.item.path,'文件路径已复制。'); if (action === 'add-relation') return relationDialog(); if (action === 'rename-file') return renameDialog();
    if (action === 'show-context') return selectSection('context'); if (action === 'new-skill') return newSkillDialog();
    if (action === 'refresh-skills') { target.disabled = true; await api('/api/skills/refresh',{method:'POST',body:{}}); await loadSkills(); toast('本机 SKILL 已刷新。'); return; }
    if (action === 'bind-skill') { const tab = activeTab(); if (!tab) return; target.disabled = true; await api('/api/skills/bind',{method:'POST',body:{project_id:state.projectId,skill_id:tab.id,bound:!tab.item.bound}}); tab.item.bound = !tab.item.bound; renderSkillInspector(tab); if (state.section === 'skills') { const result = await api(`/api/skills?project=${encodeURIComponent(state.projectId)}&q=${encodeURIComponent(state.q)}`); state.skills = result.skills || []; renderSkills(); } toast(tab.item.bound ? '已加入当前项目的能力说明。' : '已从当前项目解绑。'); return; }
    if (action === 'copy-skill') { const tab = activeTab(); return newSkillDialog({...tab.item,content:tab.draft}); }
    if (action === 'refresh-context') { target.disabled = true; state.context = await api('/api/context/refresh',{method:'POST',body:{project_id:state.projectId}}); renderContext(); toast('项目交接文件已更新。'); return; }
    if (action === 'copy-context') return copyText(state.context?.markdown,'项目交接内容已复制。'); if (action === 'copy-context-path') return copyText(state.context?.path,'交接文件路径已复制，可以发给 Codex。');
    if (action === 'copy-handoff') return copyText(`请先读取这个本地项目交接文件，了解项目进度、分镜、素材关联和已绑定的 SKILL，再基于现有项目继续协作：\n\n${state.context?.path || ''}\n\n接下来我想：`,'交接指令已复制，粘贴给 Codex 后补上你想继续做的事。');
    if (action === 'remove-item') { const tab = activeTab(); if (tab?.source === 'file') return trashItems([tab.id]); return; }
    if (action.startsWith('zoom-')) changeImageZoom(action);
  } catch(error) { if (target) target.disabled = false; report(error); }
}

function installResourceMarquee() {
  return window.YingXuMarquee?.install({viewport:$('#resourceViewport'),getItems:() => $$('#resourceItems [data-item]'),getSelection:() => state.selectedIds,
    onStart:hideMenu,
    enabled:() => state.section === 'assets' && !state.loadingItems && !document.querySelector('dialog[open]'),
    getContext:() => [state.projectId,state.section,state.category,state.folderId,state.offset,state.view,state.listSequence].join('|'),
    onChange:ids => { state.selectedIds = new Set(ids); updateSelection(); }});
}
function wireEvents() {
  $('#batchPropertiesButton').addEventListener('click',() => batchPropertiesDialog().catch(report));
  installResourceMarquee();
  if ($('#projectLibraryIcon')) $('#projectLibraryIcon').innerHTML = icon('folder'); if ($('#settingsIcon')) $('#settingsIcon').innerHTML = icon('filter'); if ($('#openLocalIcon')) $('#openLocalIcon').innerHTML = icon('open');
  $('#addProject').innerHTML = icon('plus'); $('#helpIcon').innerHTML = icon('help'); $('#searchIcon').innerHTML = icon('search'); $('#globalSearchButton').innerHTML = icon('search'); if ($('#captureButton')) $('#captureButton').innerHTML = icon('image'); $('#advancedSearch').innerHTML = icon('filter'); $('#importIcon').innerHTML = icon('upload'); $('#newItemIcon').innerHTML = icon('plus'); $('#rescanButton').innerHTML = icon('refresh'); $('#previousPage').innerHTML = icon('left'); $('#nextPage').innerHTML = icon('chevron'); $('#closeDialog').innerHTML = icon('close');
  $('#newFolderButton').innerHTML = `${icon('folder')}新建文件夹`; $('#moveSelectionButton').innerHTML = `${icon('move')}移动到`; $('#deleteSelectionButton').innerHTML = `${icon('trash')}删除`;
  $('#newFolderButton').addEventListener('click',() => newFolderDialog().catch(report)); $('#moveSelectionButton').addEventListener('click',() => moveDialog([...state.selectedIds]).catch(report)); $('#deleteSelectionButton').addEventListener('click',() => (state.selectedIds.size ? trashItems([...state.selectedIds]) : trashFolder(state.folderId)).catch(report));
  $('#selectPageButton').addEventListener('click',() => { if (state.loadingItems) return; const ids = selectableResourceIds(); state.selectedIds = state.selectedIds.size === ids.length ? new Set() : new Set(ids); updateSelection(); });
  $('#folderScope').addEventListener('change',event => { state.folderScope = event.target.value; state.offset = 0; state.selectedIds.clear(); loadItems(); });
  $$('.view-switch button').forEach(button => { button.innerHTML = icon(button.dataset.view); button.addEventListener('click',() => { state.view = button.dataset.view; storage.set('yingxu:view',state.view); configureSection(); renderItems(); }); });
  $('#statusFilter').insertAdjacentHTML('beforeend',optionHtml(statuses,'')); $('#addProject').addEventListener('click',newProjectDialog); $('#newItemButton').addEventListener('click',() => newItemDialog()); $('#importButton').addEventListener('click',importDialog); $('#advancedSearch').addEventListener('click',advancedSearchDialog); $('#helpButton').addEventListener('click',helpDialog);
  $('#closeDialog').addEventListener('click',() => { if (!state.modalBusy) $('#appDialog').close(); }); $('#appDialog').addEventListener('cancel',event => { if (state.modalBusy) event.preventDefault(); });
  $('#searchInput').addEventListener('input',() => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.q = $('#searchInput').value.trim(); state.offset = 0; loadSection(); },250); });
  ['status','kind','sort'].forEach(key => $(`#${key}Filter`).addEventListener('change',event => { state[key] = event.target.value; state.offset = 0; loadItems(); }));
  $('#previousPage').addEventListener('click',() => { state.offset = Math.max(0,state.offset-state.limit); state.section === 'skills' ? renderSkills() : state.section === 'trash' ? loadTrash() : loadItems(); }); $('#nextPage').addEventListener('click',() => { state.offset += state.limit; state.section === 'skills' ? renderSkills() : state.section === 'trash' ? loadTrash() : loadItems(); });
  $('#rescanButton').addEventListener('click',async () => { try { const result = await api('/api/rescan',{method:'POST',body:{project_id:state.projectId}}); monitorJob(result.job_id,'正在同步项目文件'); } catch(error) { report(error); } });
  document.addEventListener('mousedown',event => { if (event.target.closest('[data-markdown-format]')) event.preventDefault(); });
  document.addEventListener('change',event => {
    if (!event.target.matches('[data-markdown-heading]') || !event.target.value) return;
    applyMarkdownFormat(event.target.value); event.target.value = '';
  });
  document.addEventListener('contextmenu',event => {
    const target = contextMenuTarget(event.target); if (!target) return;
    event.preventDefault(); showMenu(target.anchor,target.kind,target.id,{x:event.clientX,y:event.clientY});
  });
  document.addEventListener('click',async event => {
    const command = event.target.closest('[data-menu-command]'); if (command && state.menu) { const context = {...state.menu}; hideMenu(); runMenu(command.dataset.menuCommand,context).catch(report); return; }
    const deleteEntry = event.target.closest('[data-delete-trash-id]'); if (deleteEntry) { deleteTrash(deleteEntry.dataset.deleteTrashId,deleteEntry.dataset.deleteTrashKind); return; }
    const restore = event.target.closest('[data-restore-id]'); if (restore) { restoreTrash(restore.dataset.restoreId,restore.dataset.restoreKind,restore); return; }
    for (const [attribute,kind] of [['data-project-menu','project'],['data-folder-menu','folder'],['data-item-menu','item'],['data-skill-menu','skill']]) { const anchor = event.target.closest(`[${attribute}]`); if (anchor) { event.stopPropagation(); showMenu(anchor,kind,anchor.getAttribute(attribute)); return; } }
    if (!event.target.closest('#resourceMenu')) hideMenu();
    const selection = event.target.closest('[data-select-item]'); if (selection) { selectResource(selection.dataset.selectItem,event,true); return; }
    if (event.target.closest('.item-selection')) return;
    const folderPage = event.target.closest('[data-folder-page]'); if (folderPage) { state.folderPage = Math.max(0,(state.folderPage || 0)+Number(folderPage.dataset.folderPage)); renderFolders(); return; }
    const folder = event.target.closest('[data-folder-open]'); if (folder) { openFolder(folder.dataset.folderOpen).catch(report); return; }
    const source = event.target.closest('[data-copy-source]'); if (source) { const value = activeTab()?.item.metadata?.[source.dataset.copySource]; copyText(typeof value === 'string' ? value : JSON.stringify(value,null,2),'原文件生成信息已复制。'); return; }
    const close = event.target.closest('[data-close-tab]'); if (close) { event.stopPropagation(); closeTab(close.dataset.closeTab); return; }
    const action = event.target.closest('[data-action]'); if (action) { handleAction(action.dataset.action,action).catch(report); return; }
    const project = event.target.closest('[data-project]'); if (project) { selectProject(project.dataset.project).catch(report); return; }
    const category = event.target.closest('[data-category]'); if (category) { selectCategory(category.dataset.category).catch(report); return; }
    const section = event.target.closest('[data-section]'); if (section) { selectSection(section.dataset.section).catch(report); return; }
    const tab = event.target.closest('[data-tab]'); if (tab) { if (state.activeKey !== tab.dataset.tab && !await guardProperties()) return; state.activeKey = tab.dataset.tab; renderWorkspace(); return; }
    const format = event.target.closest('[data-markdown-format]'); if (format) { applyMarkdownFormat(format.dataset.markdownFormat); return; }
    const mode = event.target.closest('[data-editor-mode]'); if (mode) { const tab = activeTab(); if (tab && markdownInputReady(tab)) { tab.mode = mode.dataset.editorMode; renderEditorToolbar(tab); renderEditorBody(tab); } return; }
    const item = event.target.closest('[data-item]'); if (item && !event.target.closest('[data-drag-file]')) { selectResource(item.dataset.item,event); if (!event.shiftKey && !event.ctrlKey && !event.metaKey) openItem(item.dataset.item); return; }
    const skill = event.target.closest('[data-skill]'); if (skill) { openSkill(skill.dataset.skill); return; }
    const relation = event.target.closest('[data-remove-relation]'); if (relation) { try { await api(`/api/relations/${encodeURIComponent(relation.dataset.removeRelation)}`,{method:'DELETE'}); const tab = activeTab(); if (tab) { tab.item = await api(`/api/items/${encodeURIComponent(tab.id)}`); renderInspector(); } toast('关联已解除。'); } catch(error) { report(error); } }
  });
  document.addEventListener('keydown',event => {
    if (event.isComposing || activeTab()?.markdownEditor?.isComposing() || activeTab()?.docxEditor?.isComposing()) { if ((event.ctrlKey || event.metaKey) && ['s','f','k'].includes(event.key.toLowerCase())) { event.preventDefault(); markdownInputReady(); } return; }
    if (searchShortcut(event) || globalSearchIsOpen() || groupsIsOpen()) return;
    if (deleteSelectionShortcut(event)) return;
    if ((event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) && !$('#appDialog').open) { const target = contextMenuTarget(event.target); if (target) { event.preventDefault(); showMenu(target.anchor,target.kind,target.id); return; } }
    if (event.key === 'Escape' && !$('#resourceMenu').hidden) { hideMenu(true); event.preventDefault(); return; }
    if (!$('#resourceMenu').hidden && ['ArrowDown','ArrowUp','Home','End'].includes(event.key) && $('#resourceMenu').contains(document.activeElement)) { const buttons = $$('button',$('#resourceMenu')); const current = buttons.indexOf(document.activeElement); const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length-1 : (current+(event.key === 'ArrowDown' ? 1 : -1)+buttons.length)%buttons.length; buttons[next]?.focus(); event.preventDefault(); return; }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); if (!$('#appDialog').open) saveCurrent(); }

    if (event.key === '?' && !event.ctrlKey && !event.metaKey && !event.target.matches('input,textarea,[contenteditable]') && !$('#appDialog').open) { event.preventDefault(); helpDialog(); }
    if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('[role="button"],[role="tab"]')) { event.preventDefault(); event.target.click(); }
  });
  window.addEventListener('resize',hideMenu); $('#resourceViewport').addEventListener('scroll',hideMenu,{passive:true});
  window.addEventListener('beforeunload',event => { persistDrafts(true); if (state.tabs.some(tab => tab.dirty || tab.propertiesDirty || tab.markdownEditor?.isComposing() || tab.docxEditor?.isComposing())) { event.preventDefault(); event.returnValue = ''; } });
  window.addEventListener('pagehide',() => { stopPreviewMedia(); persistDrafts(true); });
  document.addEventListener('visibilitychange',() => { if (document.hidden) stopPreviewMedia(); });
  const divider = $('#editorDivider'); let resizing = false;
  divider.addEventListener('pointerdown',event => { if (event.button !== 0) return; resizing = true; divider.classList.add('dragging'); divider.setPointerCapture(event.pointerId); document.body.style.userSelect = 'none'; });
  divider.addEventListener('pointermove',event => { if (!resizing) return; const workspace = $('#workspace').getBoundingClientRect(); const width = Math.max(215,Math.min(workspace.width*.52,event.clientX-workspace.left)); $('#workspace').style.setProperty('--browser-width',`${width}px`); });
  const stop = () => { resizing = false; divider.classList.remove('dragging'); document.body.style.userSelect = ''; }; divider.addEventListener('pointerup',stop); divider.addEventListener('pointercancel',stop);
  divider.addEventListener('keydown',event => { if (!['ArrowLeft','ArrowRight'].includes(event.key)) return; event.preventDefault(); const workspace = $('#workspace').getBoundingClientRect(); const width = $('#library').getBoundingClientRect().width + (event.key === 'ArrowRight' ? 20 : -20); $('#workspace').style.setProperty('--browser-width',`${Math.max(215,Math.min(workspace.width*.52,width))}px`); });
  window.chrome?.webview?.addEventListener('message',event => handleDesktopMessage(event.data).catch(report));
  wireDragAndDrop();
}

function wireDragAndDrop() {
  let dragDepth = 0;
  let nativeDrag = null;
  const isInternal = transfer => Boolean(nativeDrag) || Array.from(transfer?.types || []).includes('application/x-yingxu-item');
  const isExternal = transfer => !isInternal(transfer) && Array.from(transfer?.types || []).includes('Files');
  const clearDrag = () => { resourceGroups?.endDrag(); nativeDrag = null; dragDepth = 0; $$('.dragging-card,.drop-category').forEach(node => node.classList.remove('dragging-card','drop-category')); document.body.classList.remove('external-drag'); };
  const startNativeDrag = (ids,item,{grouping = true} = {}) => {
    nativeDrag = {ids:ids.slice(0,200)};
    if (grouping) groupController()?.beginDrag(nativeDrag.ids); else resourceGroups?.endDrag();
    item?.classList.add('dragging-card'); hideMenu();
    window.chrome.webview.postMessage({action:'drag-files',ids:nativeDrag.ids});
  };
  let preparedKey = '';
  const prepareNativeDrag = event => {
    if (!window.yingxuDesktopDrag || !window.chrome?.webview?.postMessage || nativeDrag) return;
    const item = event.target.closest('[data-item]'); if (!item) return;
    const id = String(item.dataset.item); const ids = (state.selectedIds.has(id) ? [...state.selectedIds] : [id]).slice(0,200);
    const key = ids.join(','); if (key === preparedKey && event.type !== 'pointerdown') return;
    preparedKey = key; window.chrome.webview.postMessage({action:'prepare-drag-files',ids});
  };
  document.addEventListener('pointerover',prepareNativeDrag);
  document.addEventListener('pointerdown',prepareNativeDrag);
  window.chrome?.webview?.addEventListener?.('message',event => {
    const data = event.data; if (data?.action !== 'native-drag-ended') return;
    if (resourceGroups?.handleNativeDrop(data)) { preparedKey = ''; clearDrag(); return; }
    // Some windowed WebView2 runtimes omit DOM drop events for their own OLE drag.
    // The host reports an actual mouse release over this WebView (never Escape or another app).
    if (nativeDrag && !nativeDrag.handled && data.released && data.inside && data.width > 0 && data.height > 0) {
      const target = document.elementFromPoint(data.x * window.innerWidth / data.width,data.y * window.innerHeight / data.height)?.closest('[data-folder-drop],[data-category]');
      if (target && target.dataset.category !== 'all') {
        const category = target.dataset.folderCategory || target.dataset.category;
        const folderId = target.hasAttribute('data-folder-drop') && target.dataset.folderDrop !== 'root' ? target.dataset.folderDrop : null;
        performMove(nativeDrag.ids,category,folderId).catch(report);
      }
    }
    preparedKey = ''; clearDrag();
  });
  document.addEventListener('dragstart',event => { const item = event.target.closest('[data-item]'); if (!item || !event.dataTransfer) return; const id = String(item.dataset.item); const ids = state.selectedIds.has(id) ? [...state.selectedIds] : [id];
    if (window.yingxuDesktopDrag && window.chrome?.webview?.postMessage) {
      // Cancel Chromium's HTML-only drag; the host supplies real Windows files instead.
      event.preventDefault(); startNativeDrag(ids,item); return;
    }
    // Images can contribute browser file/URL payloads. This drag belongs to the card.
    event.dataTransfer.clearData();
    event.dataTransfer.setData('application/x-yingxu-item',id); event.dataTransfer.setData('application/x-yingxu-items',JSON.stringify(ids)); event.dataTransfer.effectAllowed = 'move'; item.classList.add('dragging-card'); hideMenu(); });
  document.addEventListener('dragend',() => { if (!nativeDrag) clearDrag(); });
  document.addEventListener('dragenter',event => { if (isExternal(event.dataTransfer)) { event.preventDefault(); dragDepth++; document.body.classList.add('external-drag'); } });
  document.addEventListener('dragleave',event => { if (isExternal(event.dataTransfer)) { dragDepth = Math.max(0,dragDepth-1); if (!dragDepth) document.body.classList.remove('external-drag'); } const target = event.target.closest('[data-folder-drop],[data-category]'); if (target) target.classList.remove('drop-category'); });
  document.addEventListener('dragover',event => { const transfer = event.dataTransfer; const target = event.target.closest('[data-folder-drop],[data-category]'); const valid = target && target.dataset.category !== 'all'; if (isInternal(transfer)) { event.preventDefault(); transfer.dropEffect = valid ? (nativeDrag ? 'copy' : 'move') : 'none'; if (valid) target.classList.add('drop-category'); } else if (isExternal(transfer)) { event.preventDefault(); transfer.dropEffect = 'copy'; if (valid) target.classList.add('drop-category'); } });
  document.addEventListener('drop',async event => { const transfer = event.dataTransfer; if (!transfer) return; document.body.classList.remove('external-drag'); dragDepth = 0; $$('.drop-category').forEach(node => node.classList.remove('drop-category'));
    const target = event.target.closest('[data-folder-drop],[data-category]'); const valid = target && target.dataset.category !== 'all'; const category = target?.dataset.folderCategory || (valid ? target.dataset.category : state.category !== 'all' ? state.category : 'references'); const folderId = target?.hasAttribute('data-folder-drop') ? target.dataset.folderDrop === 'root' ? null : target.dataset.folderDrop : valid ? null : state.folderId;
    // Internal moves take precedence even if WebView2 also exposes a Files payload.
    const id = nativeDrag?.ids[0] || transfer.getData('application/x-yingxu-item');
    if (isInternal(transfer) || id) { event.preventDefault(); if (!id || !valid) return; let ids = [id]; try { const parsed = nativeDrag?.ids || JSON.parse(transfer.getData('application/x-yingxu-items') || '[]'); if (Array.isArray(parsed) && parsed.length) ids = [...new Set(parsed.map(String))].slice(0,200); if (nativeDrag) nativeDrag.handled = true; await performMove(ids,category,folderId); } catch(error) { report(error); } return; }
    if (transfer.files.length) { event.preventDefault(); if (!state.projectId) { toast('先创建或选择一个项目，再拖入文件。','info'); return; } if (state.section !== 'assets' && !valid) { toast('请把文件拖到左侧资源分类，或打开一个资源文件夹。','info'); return; } uploadFiles([...transfer.files],category,folderId).catch(report); }
  });
  document.addEventListener('pointerdown',event => { const handle = event.target.closest('[data-drag-file]'); if (!handle || event.button !== 0) return; event.preventDefault(); event.stopPropagation(); if (window.yingxuDesktopDrag && window.chrome?.webview?.postMessage) { const id = String(handle.dataset.dragFile); startNativeDrag(state.selectedIds.has(id) ? [...state.selectedIds] : [id],handle.closest('[data-item]'),{grouping:false}); } else if (window.chrome?.webview?.postMessage) { window.chrome.webview.postMessage({action:'drag-file',id:handle.dataset.dragFile}); } else toast('桌面版支持直接拖出。当前浏览器请使用“定位文件”。','info',6000); });
}
async function uploadFiles(files,category,folderId = null) {
  if (state.uploading) { toast('当前正在导入一批文件，请等这批完成后继续。','info'); return; }
  state.uploading = true; const project = state.projectId; let cancelled = false,xhr = null,completed = 0; const tray = $('#jobTray'); tray.hidden = false;
  try {
    for (let index = 0; index < files.length && !cancelled; index++) {
      const file = files[index]; tray.innerHTML = `<span class="spinner"></span><span id="uploadProgress">正在保存项目副本 ${index+1}/${files.length} · ${escapeHtml(file.name)}</span><button class="button button-ghost button-small" id="cancelUpload">取消</button>`; $('#cancelUpload').onclick = () => { cancelled = true; xhr?.abort(); };
      await new Promise((resolve,reject) => { xhr = new XMLHttpRequest(); const params = new URLSearchParams({project,category,name:file.name}); if (folderId) params.set('folder_id',folderId); xhr.open('POST',`/api/upload?${params}`); xhr.setRequestHeader('X-YingXu-Token',state.bootstrap.token); xhr.setRequestHeader('Content-Type','application/octet-stream'); xhr.upload.onprogress = event => { if (event.lengthComputable && $('#uploadProgress')) $('#uploadProgress').textContent = `正在保存 ${index+1}/${files.length} · ${file.name} · ${Math.round(event.loaded/event.total*100)}%`; }; xhr.onload = () => { let body; try { body = JSON.parse(xhr.responseText); } catch { body = {}; } if (xhr.status >= 200 && xhr.status < 300) resolve(body); else reject(new Error(body.error || `「${file.name}」未能导入。`)); }; xhr.onerror = () => reject(new Error('本地连接中断，文件导入未完成。')); xhr.onabort = () => reject(new Error('已取消后续导入，完成的项目副本会保留。')); xhr.send(file); }); completed++;
    }
    toast(`已将 ${completed} 个文件保存到项目，分类为${categoryLabel(category)}。`);
  } catch(error) { if (cancelled) toast(error.message,'info'); else report(error); }
  finally { state.uploading = false; tray.hidden = true; await refreshProjects(); if (state.section === 'assets') await loadItems(); }
}

async function settingsDialog() {
  if (window.yingxuMac) return window.yingxuMacSettings();
  if ($('#appDialog').open || groupsIsOpen() || globalSearchIsOpen()) { toast('请先完成或关闭当前对话框。','info'); return; }
  const settings = await api('/api/settings'); state.bootstrap.settings = settings;
  const toggle = (key,title,description) => `<label class="setting-row"><span><strong>${title}</strong><small>${description}</small></span><input type="checkbox" name="${key}" ${settings[key] ? 'checked' : ''}></label>`;
  const desktop = Boolean(window.chrome?.webview?.postMessage);
  showDialog({title:'设置',subtitle:'按自己的习惯使用映序。设置保存在本机，重开后仍有效。',wide:true,submit:'保存设置',body:`<div class="settings-section"><h3>删除与恢复</h3>${toggle('confirm_delete','移入映序回收站前确认','项目、文件、文件夹和 SKILL 的删除提示。')}${toggle('confirm_trash_delete','清理回收站前确认','关闭后点击删除会直接移入 Windows 回收站；遇到无法处理的条目仍会说明原因。')}</div><div class="settings-section"><h3>窗口与播放</h3>${toggle('close_to_tray','关闭窗口时保留在托盘','双击任务栏右下角的映序图标重新打开；右键菜单可退出。')}${toggle('autoplay_media','打开音视频时自动播放','默认关闭；部分媒体仍可能需要点击播放。')}</div><div class="settings-section"><h3>工作台</h3><div class="fields-two"><div class="field"><label for="settingView">启动时的视图</label><select id="settingView" name="default_view">${optionHtml([{key:'grid',label:'画廊'},{key:'list',label:'列表'},{key:'board',label:'分镜看板'}],settings.default_view)}</select></div><div class="field"><label for="settingSort">启动时的排序</label><select id="settingSort" name="default_sort">${optionHtml([{key:'updated',label:'最近更新'},{key:'name',label:'文件名称'},{key:'order',label:'分镜顺序'}],settings.default_sort)}</select></div></div><p class="field-hint">当前页面搜索：Ctrl+F；全局搜索：Ctrl+K。保存：Ctrl+S。</p></div><div class="settings-section"><h3>截图</h3>${toggle('capture_enabled','后台截图快捷键','映序留在托盘时也可使用；只在按下快捷键时截取鼠标所在屏幕。')}<div class="field"><label for="captureMode">截图方式</label><select id="captureMode" name="capture_mode">${optionHtml([{key:'annotate',label:'标注后确认（默认）'},{key:'quick',label:'快速完成'}],settings.capture_mode || 'annotate')}</select><p class="field-hint">标注模式在选区后停留，可使用画笔、箭头、矩形和撤销，确认才复制与保存；快速模式在框选松开后立即完成。Esc 取消。</p></div><div class="field"><label for="captureHotkey">截图快捷键</label><input id="captureHotkey" name="capture_hotkey" value="${escapeHtml(settings.capture_hotkey || defaultSettings.capture_hotkey)}" maxlength="40"><p class="field-hint">默认 Ctrl+Alt+Shift+S。使用至少两个 Ctrl/Alt/Shift，加大写字母、数字或 F1–F24（F12 除外）；占用时会提示。截图保存到项目参考资料，并插入当前可编辑 Markdown 草稿；同时复制图片到剪贴板。</p></div></div><div class="settings-section"><h3>Windows 打开方式</h3><p class="field-hint">把映序添加到文件的“打开方式”候选。支持文稿原路径编辑保存，图片、音频与视频按类型预览。</p><div class="settings-buttons"><button type="button" class="button button-secondary" data-action="register-open-with" ${desktop ? '' : 'disabled'}>添加映序到打开方式</button><button type="button" class="button button-ghost" data-action="unregister-open-with" ${desktop ? '' : 'disabled'}>移除候选</button></div>${desktop ? '' : '<p class="field-hint">此项及托盘功能请在映序桌面窗口中使用。</p>'}</div>`,onSubmit:async form => {
    const values = new FormData(form); const patch = {};
    for (const key of ['confirm_delete','confirm_trash_delete','close_to_tray','autoplay_media','capture_enabled']) patch[key] = values.has(key);
    for (const key of ['default_view','default_sort','capture_hotkey','capture_mode']) patch[key] = values.get(key);
    const saved = await api('/api/settings',{method:'PATCH',body:patch}); state.bootstrap.settings = saved;
    state.view = saved.default_view; state.sort = saved.default_sort; $('#sortFilter').value = state.sort; storage.set('yingxu:view',state.view);
    window.chrome?.webview?.postMessage({action:'settings-changed'});
    configureSection(); if (state.section === 'assets') await loadItems(); toast('设置已保存。');
  }});
}
async function openExternal(id) {
  if (!/^[a-f0-9]{32}$/.test(String(id))) throw new Error('本地文件预览标识无效。');
  if (!await guardProperties()) return;
  const key = `external:${id}`; let tab = state.tabs.find(value => value.key === key);
  if (tab) { state.activeKey = key; renderWorkspace(); return; }
  tab = {key,id,source:'external',item:{id,name:'正在打开本地文件…',kind:'file'},loading:true,dirty:false,mode:'preview'};
  state.tabs.push(tab); state.activeKey = key; renderWorkspace();
  try {
    const detail = await api(`/api/external/${encodeURIComponent(id)}`); tab.item = {...detail}; delete tab.item.content;
    tab.content = ['markdown','text','docx','svg','html'].includes(detail.kind) ? detail.content : null; if (tab.content) { tab.draft = String(tab.content.content ?? ''); tab.paragraphs = (tab.content.paragraphs || []).map(value => ({...value})); tab.mode = tab.item.kind === 'docx' ? 'preview' : tab.content.editable ? (canUseMarkdownEditor(tab) ? 'live' : 'edit') : 'preview'; }
    applyDraft(tab);
    tab.detailReady = true; tab.loading = false;
  } catch(error) { tab.loading = false; tab.error = error.message; report(error); }
  if (state.activeKey === key) renderWorkspace(); else renderTabs();
}
async function handleDesktopMessage(data) {
  if (data?.action === 'pause-media') { stopPreviewMedia(); return; }
  if (['capture-context-request','capture-result'].includes(data?.action)) { await captureController()?.handle(data); return; }
  if (data?.action === 'open-settings') return settingsDialog();
  if (data?.action === 'desktop-notice') return toast(String(data.message || '操作已完成。'),data.error ? 'error' : 'info',6500);
  if (data?.action === 'external-open') return queueExternalFiles(Array.isArray(data.entries) ? data.entries : []);
  if (data?.action === 'prepare-exit') {
    let allow = false;
    try { if (!$('#appDialog').open && !globalSearchIsOpen() && !groupsIsOpen() && !captureUI?.isBusy() && !state.globalOpening && !state.modalBusy && !state.trashBusy && !state.uploading && !state.exitBusy) { state.exitBusy = true; allow = await prepareTabs([...state.tabs]); allow = allow && !state.tabs.some(tab => tab.dirty || tab.propertiesDirty || tab.saving || tab.propertiesSaving || !markdownInputReady(tab)); persistDrafts(true); } }
    finally { state.exitBusy = false; window.chrome?.webview?.postMessage({action:'exit-response',requestId:data.requestId,allow}); }
    if (!allow) toast('退出已取消，请先完成当前操作或保存文稿。','info');
  }
}
async function queueExternalFiles(entries) {
  state.externalQueue ||= [];
  if (state.externalQueue.length + entries.length > 256) { toast('等待打开的文件过多，请先处理当前窗口。','error'); return; }
  state.externalQueue.push(...entries.slice(0,32).map(entry => entry.id));
  if (state.externalDraining) return state.externalDraining;
  state.externalDraining = (async () => {
    while (state.externalQueue.length) {
      while ($('#appDialog').open || globalSearchIsOpen() || groupsIsOpen() || captureUI?.isBusy() || state.globalOpening || state.modalBusy || state.exitBusy) await new Promise(resolve => setTimeout(resolve,150));
      const id = state.externalQueue.shift();
      try { await openExternal(id); } catch(error) { report(error); }
    }
  })();
  try { await state.externalDraining; } finally { state.externalDraining = null; }
}
async function boot() {
  wireEvents(); readDrafts();
  try { state.bootstrap = await api('/api/bootstrap'); state.view = preference('default_view'); state.sort = preference('default_sort'); $('#sortFilter').value = state.sort; $('#connectionState').textContent = '本地连接正常'; if (Array.isArray(state.bootstrap.categories)) for (const category of state.bootstrap.categories) { const existing = categoryDefs.find(value => value.key === category.key); if (existing && category.label) existing.label = category.label; } await refreshProjects(); configureSection(); await loadItems(); renderInspector(); const recoverable = Object.values(state.drafts).filter(draft => draft.id && ['file','skill'].includes(draft.source) && Date.now()-draft.when < 7*86400000).slice(0,8); state.restoringDrafts = true; try { for (const draft of recoverable) { if (draft.source === 'skill') await openSkill(draft.id); else await openItem(draft.id); } } finally { state.restoringDrafts = false; } }
  catch(error) { $('#connectionState').textContent = '连接暂时中断'; $('#projectHero').innerHTML = `<div class="fatal-state"><h1>映序还没有连接上本地服务</h1><p>${escapeHtml(error.message)}<br>请从桌面启动“映序”，随后刷新这个窗口。</p><button class="button button-secondary" data-action="reload">重新连接</button></div>`; $('#resourceItems').innerHTML = ''; }
  if (state.bootstrap) window.chrome?.webview?.postMessage({action:'desktop-ready'});
}
boot();
