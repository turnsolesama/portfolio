'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const {test} = require('node:test');
const id = 'a'.repeat(32), oldId = 'b'.repeat(32);
const clone = value => JSON.parse(JSON.stringify(value));
function detail(options = {}) {
  const kind = options.kind || 'markdown';
  return {id, name:'原文', path:'C:\\合成\\原文.md', kind, size:10, external:true,
    content:{format:kind, editable:true, content:'原文\r\n', etag:'old', ...options.content}, ...options};
}
function setup(initial = detail(), drafts = {}) {
  const calls = [], notices = [], store = new Map([['yingxu:drafts', JSON.stringify(drafts)]]), nodes = new Map();
  const context = vm.createContext({console, setTimeout:()=>1, clearTimeout:()=>{},
    localStorage:{getItem:key=>store.get(key) || null, setItem:(key,value)=>store.set(key,value)},
    window:{YingXuMarkdown:{supports:()=>true}},
    document:{querySelector:key=>{if(!nodes.has(key))nodes.set(key,{value:'',textContent:'',innerHTML:''});return nodes.get(key);}, querySelectorAll:()=>[]},
    initial, handler:async(url,options)=>{if(url==='/api/bootstrap')return {settings:{}};return clone(initial);},
    fakeApi:async(url,options)=>{calls.push({url,options});return context.handler(url,options);},
    fakeToast:(...args)=>notices.push(args)});
  const source = fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
  vm.runInContext(source + `\napi=fakeApi;toast=fakeToast;report=()=>{};wireEvents=()=>{};renderWorkspace=()=>{};renderTabs=()=>{};renderInspector=()=>{};renderEditorStatus=()=>{};renderEditorToolbar=()=>{};refreshProjects=async()=>{};configureSection=()=>{};loadItems=async()=>{};guardProperties=async()=>true;globalThis.app={state,openExternal,saveTab,readDrafts,persistDrafts,applyDraft,canUseMarkdownEditor,boot};`,context);
  return {...context.app, context, calls, notices, store};
}
function dirtyTab(s) { const tab=s.state.tabs[0];tab.draft='修改';tab.dirty=true;return tab; }

test('explicitly opened writable Markdown enters live editor with external capability intact',async()=>{
  const s=setup();await s.openExternal(id);const t=s.state.tabs[0];
  assert.equal(t.source,'external');assert.equal(t.mode,'live');assert.equal(t.content.editable,true);
  assert.equal(t.detailReady,true);assert.equal(s.canUseMarkdownEditor(t),true);assert.equal(t.draft,'原文\r\n');
  await s.openExternal(id);assert.equal(s.state.tabs.length,1);assert.equal(s.calls.length,1);
});
test('readonly capability stays preview and save cannot bypass it',async()=>{
  const s=setup(detail({content:{editable:false,content:'只读',etag:'old'}}));await s.openExternal(id);const t=dirtyTab(s);
  assert.equal(t.mode,'preview');assert.equal(s.canUseMarkdownEditor(t),false);assert.equal(await s.saveTab(t),false);
  assert.equal(s.calls.length,1);assert.equal(t.dirty,true);
});
test('external save uses POST capability endpoint and never changes SKILL or project records',async()=>{
  const s=setup();await s.openExternal(id);const t=dirtyTab(s);s.state.skills=[{id,name:'untouched'}];
  s.context.handler=async(url,options)=>({...detail(),size:22,content:{editable:true,etag:'saved',content:options.body.content}});
  assert.equal(await s.saveTab(t),true);assert.equal(s.calls[1].url,`/api/external/${id}/content`);
  assert.equal(s.calls[1].options.method,'POST');assert.deepEqual(clone(s.calls[1].options.body),{etag:'old',content:'修改'});
  assert.equal(s.calls.length,2);assert.equal(t.item.kind,'markdown');assert.equal(t.content.etag,'saved');assert.equal(t.item.size,22);
  assert.equal(s.state.skills[0].name,'untouched');assert.equal(t.dirty,false);
});
test('typing during in-flight external save retains newer draft and updated etag for next save',async()=>{
  const s=setup();await s.openExternal(id);const t=dirtyTab(s);let release;
  s.context.handler=async()=>new Promise(resolve=>{release=resolve;});const saving=s.saveTab(t);
  assert.equal(t.saving,true);t.draft='保存请求发出后的新输入';
  release({...detail(),content:{editable:true,content:'修改',etag:'new'}});
  assert.equal(await saving,false);assert.equal(t.draft,'保存请求发出后的新输入');assert.equal(t.content.etag,'new');assert.equal(t.dirty,true);
  s.persistDrafts(true);assert.equal(s.state.drafts[t.key].draft,t.draft);assert.equal(s.state.drafts[t.key].etag,'new');
});
test('etag conflict retains original edit base and local draft and does not mark saved',async()=>{
  const s=setup();await s.openExternal(id);const t=dirtyTab(s);s.persistDrafts(true);
  s.context.handler=async()=>{throw Object.assign(new Error('conflict'),{status:409});};
  assert.equal(await s.saveTab(t),false);assert.equal(t.conflict,true);assert.equal(t.saving,false);assert.equal(t.dirty,true);
  assert.equal(t.draft,'修改');assert.equal(t.content.etag,'old');assert.equal(s.state.drafts[t.key].draft,'修改');
});
test('saved Word request includes only changed writable paragraphs through external endpoint',async()=>{
  const paragraphs=[{id:'p1',text:'原文',editable:true},{id:'p2',text:'表格',editable:false},{id:'p3',text:'保留',editable:true}];
  const s=setup(detail({kind:'docx',content:{editable:true,etag:'old',paragraphs}}));await s.openExternal(id);const t=s.state.tabs[0];
  t.paragraphs[0].text='修改';t.paragraphs[1].text='忽略非编辑内容';t.dirty=true;
  s.context.handler=async()=>detail({kind:'docx',content:{editable:true,etag:'new',paragraphs:t.paragraphs}});
  assert.equal(await s.saveTab(t),true);assert.deepEqual(clone(s.calls[1].options.body),{etag:'old',paragraphs:[{id:'p1',text:'修改'}]});
});
test('boot retains external drafts but never reopens arbitrary stored paths or stale capabilities',async()=>{
  const draft={id:oldId,source:'external',path:'C:/任意路径/private.md',draft:'私有草稿',etag:'old',when:Date.now()};
  const s=setup(detail(),{[`external:${oldId}`]:draft});await s.boot();
  assert.deepEqual(s.calls.map(call=>call.url),['/api/bootstrap']);assert.equal(s.state.tabs.length,0);
  assert.equal(s.state.drafts[`external:${oldId}`].draft,'私有草稿');
});
test('explicit reopening same path restores draft across capability changes and detects external revision',async()=>{
  const draft={id:oldId,source:'external',path:'c:/合成/原文.md',draft:'恢复的草稿',etag:'old',when:Date.now()};
  const s=setup(detail({content:{editable:true,content:'别的应用修改了内容',etag:'changed'}}),{[`external:${oldId}`]:draft});
  s.readDrafts();await s.openExternal(id);const t=s.state.tabs[0];
  assert.equal(t.draft,'恢复的草稿');assert.equal(t.dirty,true);assert.equal(t.conflict,true);assert.equal(t.content.etag,'old');
  assert.equal(s.state.drafts[`external:${oldId}`],undefined);assert.equal(s.calls[0].url,`/api/external/${id}`);assert.equal(s.calls.length,1);
});
test('different explicit path does not reuse unrelated draft and malformed id never reads a path',async()=>{
  const draft={id:oldId,source:'external',path:'C:/另一个目录/原文.md',draft:'其他草稿',etag:'old',when:Date.now()};
  const s=setup(detail(),{[`external:${oldId}`]:draft});s.readDrafts();await s.openExternal(id);
  assert.equal(s.state.tabs[0].dirty,false);assert.equal(s.state.tabs[0].draft,'原文\r\n');
  await assert.rejects(s.openExternal('C:/任意路径.md'));assert.equal(s.calls.length,1);
});
