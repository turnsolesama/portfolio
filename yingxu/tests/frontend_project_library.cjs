const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {window:{}};
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../frontend/project-library.js'),'utf8'),context);
const library = context.window.YingXuProjectLibrary;
const plain = value => JSON.parse(JSON.stringify(value));
const folders = [{id:'a',name:'长篇',parent_id:null},{id:'b',name:'第一季',parent_id:'a'},{id:'c',name:'第二季',parent_id:'b'}];
const projects = [{id:'p1',name:'雨夜<script>',folder_id:'b',description:'港口',counts:{total:3}},{id:'p2',name:'新项目',folder_id:null}];
const snapshot = () => ({folders,projects});
const escapeHtml = value => String(value).replace(/[&<>"']/g,c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function harness(response = snapshot, shared = false) {
  const calls = [],dialogs = [],opened = [],toasts = [];
  function node() { return {value:'',textContent:'',innerHTML:'',listeners:{},addEventListener(name,fn){this.listeners[name]=fn;}}; }
  const api = async (path,options) => { calls.push({path,options}); if(path === '/api/project-library') return response(); return {id:'new'}; };
  let sharedDialog;
  const showDialog = spec => {
    if (sharedDialog?.open) sharedDialog.close();
    const nodes = new Map();
    const dialog = sharedDialog || {listeners:{},querySelector(selector){if(!this.nodes.has(selector))this.nodes.set(selector,node());return this.nodes.get(selector);},querySelectorAll(){return [];},addEventListener(name,fn){(this.listeners[name] ||= []).push(fn);},close(){if(!this.open)return;this.closed=true;this.open=false;setImmediate(()=>{const callbacks=this.listeners.close||[];this.listeners.close=[];callbacks.forEach(fn=>fn());});}};
    Object.assign(dialog,{spec,nodes,closed:false,open:true}); if(shared)sharedDialog=dialog;
    dialogs.push(dialog); return dialog;
  };
  const app = library.install({api,showDialog,choose:async()=> 'cancel',toast:(...v)=>toasts.push(v),escapeHtml,selectProject:async id => opened.push(id),refreshProjects:async()=>{}});
  const click = async (dialog,attrs) => {
    const button = {dataset:Object.fromEntries(Object.entries(attrs).filter(([k])=>k.startsWith('data-')).map(([k,v])=>[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase()),v])),hasAttribute:k=>k in attrs};
    await dialog.querySelector('.project-library-layout').listeners.click({target:{closest:()=>button}});
  };
  return {app,calls,dialogs,opened,toasts,click};
}
const tests = [];
const test = (name,fn) => tests.push({name,fn});
test('nested paths and parent selector exclude whole descendant tree',()=>{
  assert.deepEqual(plain(library.folderRows(folders)).map(f=>f.label),['长篇','长篇 / 第一季','长篇 / 第一季 / 第二季']);
  assert.deepEqual(plain(library.eligibleParents(folders,'a')),[]);
  assert.deepEqual(plain(library.eligibleParents(folders,'b')).map(f=>f.id),['a']);
});
test('browse filters exact folder and search reaches across all folders',()=>{
  assert.deepEqual(plain(library.filterProjects(snapshot(),'','')).map(p=>p.id),['p2']);
  assert.deepEqual(plain(library.filterProjects(snapshot(),'a','港口')).map(p=>p.id),['p1']);
  assert.equal(library.filterProjects(snapshot(),'*','').length,2);
});
test('library escapes project names and exposes classification actions',async()=>{
  const h=harness(); await h.app.open(); const d=h.dialogs[0];
  assert.match(d.querySelector('[data-library-results]').innerHTML,/雨夜&lt;script&gt;/);
  assert.doesNotMatch(d.querySelector('[data-library-results]').innerHTML,/<script>/);
  assert.match(d.querySelector('[data-library-results]').innerHTML,/data-library-assign="p1"/);
  assert.match(d.spec.body,/data-library-new/);
});
test('opening a project closes library and delegates guarded project selection',async()=>{
  const h=harness(); await h.app.open(); const d=h.dialogs[0];
  await h.click(d,{'data-library-open':'p1'});
  assert.equal(d.closed,true); assert.deepEqual(h.opened,['p1']);
  assert.equal(h.calls.filter(c=>c.options).length,0);
});
test('direct project assignment writes only folder metadata',async()=>{
  const h=harness(); await h.app.open({projectId:'p1'}); const d=h.dialogs[0];
  assert.equal(d.spec.title,'移动到项目分类');
  await d.spec.onSubmit({elements:{folder_id:{value:'a'}}});
  assert.deepEqual(plain(h.calls[1]),{path:'/api/project-library/p1',options:{method:'PATCH',body:{folder_id:'a'}}});
  assert.match(d.spec.body,/不移动磁盘/);
});
test('create and edit folder submit parent together with name',async()=>{
  const h=harness(); await h.app.open(); const d=h.dialogs[0];
  await d.querySelector('[data-library-new]').listeners.click();
  await h.dialogs[1].spec.onSubmit({elements:{name:{value:' 广告 '},parent_id:{value:''}}});
  assert.deepEqual(plain(h.calls[1]),{path:'/api/project-folders',options:{method:'POST',body:{name:'广告',parent_id:null}}});
});
test('pagination bounds rendering for large library',async()=>{
  const h=harness(()=>({folders:[],projects:Array.from({length:95},(_,i)=>({id:'p'+i,name:'项目'+i}))}));
  await h.app.open(); const d=h.dialogs[0];
  assert.equal((d.querySelector('[data-library-results]').innerHTML.match(/<article /g)||[]).length,40);
  await h.click(d,{'data-library-next':''}); await h.click(d,{'data-library-next':''});
  assert.equal((d.querySelector('[data-library-results]').innerHTML.match(/<article /g)||[]).length,15);
  assert.equal(d.querySelector('[data-library-next]').disabled,true);
});
test('search is global and selecting a folder resets the query',async()=>{
  const h=harness(); await h.app.open(); const d=h.dialogs[0],search=d.querySelector('[data-library-search]');
  search.value='港口'; search.listeners.input();
  assert.equal(d.querySelector('[data-library-heading]').textContent,'全库搜索结果 · 1 个项目');
  await h.click(d,{'data-library-folder':''});
  assert.equal(search.value,''); assert.match(d.querySelector('[data-library-results]').innerHTML,/新项目/);
});
test('cancel empty-folder removal never calls DELETE',async()=>{
  const h=harness(); await h.app.open(); const d=h.dialogs[0];
  await h.click(d,{'data-library-folder':'a'}); await h.click(d,{'data-library-delete':''});
  assert.equal(h.calls.filter(c=>c.options?.method==='DELETE').length,0);
  assert.equal(h.dialogs.length,2);
});
test('queued native close event cannot dismiss a new form on the shared dialog',async()=>{
  const h=harness(snapshot,true); await h.app.open(); const d=h.dialogs[0];
  await d.querySelector('[data-library-new]').listeners.click();
  await new Promise(setImmediate);
  assert.equal(d.spec.title,'新建项目分类'); assert.equal(d.open,true);
  d.close(); await new Promise(setImmediate); await new Promise(setImmediate);
  assert.equal(d.spec.title,'项目库'); assert.equal(d.open,true);
  await h.click(d,{'data-library-assign':'p1'}); await new Promise(setImmediate);
  assert.equal(d.spec.title,'移动到项目分类'); assert.equal(d.open,true);
});
(async()=>{for(const {name,fn} of tests){await fn();console.log('PASS',name);}console.log(`${tests.length} tests passed`);})().catch(e=>{console.error(e);process.exitCode=1;});
