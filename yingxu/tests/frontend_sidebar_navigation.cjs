'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {test}=require('node:test');
const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
const key='yingxu:sidebar-project-order';
function setup(saved=new Map(),unavailable=false){
  const calls=[],writes=[],nodes=new Map();
  const context=vm.createContext({setTimeout,clearTimeout,URLSearchParams,console,window:{},document:{querySelector:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);}},
    localStorage:{getItem:k=>{if(unavailable)throw Error('storage unavailable');return saved.get(k)??null;},setItem:(k,value)=>{if(unavailable)throw Error('storage unavailable');saved.set(k,String(value));writes.push([k,String(value)]);}},calls});
  vm.runInContext(source+`\nrenderNavigation=()=>{sidebarProjects();calls.push('render');};renderHero=()=>{};renderInspector=()=>{};loadSection=async()=>calls.push('load');guardProperties=async()=>{calls.push('guard');return true;};api=async(url,options)=>{calls.push({url,options});return {};};globalThis.app={state,sidebarProjects,selectSidebarProject};`,context);
  Object.assign(context.app.state,{projects:'abcdef'.split('').map(id=>({id,name:id})),projectId:'a',projectLibrary:{recent_ids:['a','b','c','d','e','f']},bootstrap:{capabilities:{project_library:true}}});
  return {...context.app,context,calls,writes,saved,ids:()=>Array.from(context.app.sidebarProjects(),p=>p.id)};
}
function location(s){return {project:s.state.projectId,folder:s.state.folderId,page:s.state.folderPage,offset:s.state.offset,selected:Array.from(s.state.selectedIds),active:s.state.activeKey};}
function setLocation(s){Object.assign(s.state,{folderId:'nested',folderPage:2,offset:48,activeKey:'file:editing',tabs:[{key:'file:editing',dirty:true,draft:'保留正文'}]});s.state.selectedIds.add('selected');}

test('first launch chooses current and four recent live projects with deduplication',()=>{
  const s=setup();s.state.projectLibrary.recent_ids=['missing','a','b','b','c','d','e','f'];assert.deepEqual(s.ids(),['a','b','c','d','e']);
});
test('selecting a visible project preserves every displayed position while recording recency',async()=>{
  const s=setup();const before=s.ids();await s.selectSidebarProject('c');assert.deepEqual(s.ids(),before);assert.equal(s.state.projectId,'c');assert.equal(s.state.projectLibrary.recent_ids[0],'c');assert.equal(s.calls.filter(v=>v?.url?.endsWith('/c/visit')).length,1);assert.ok(s.calls.includes('load'));
});
test('a newly opened project enters the five-project set and only the least recent member leaves',()=>{
  const s=setup();assert.deepEqual(s.ids(),['a','b','c','d','e']);s.state.projectId='f';s.state.projectLibrary.recent_ids=['f','b','a','c','d','e'];const result=s.ids();assert.equal(result.length,5);assert.ok(result.includes('f'));assert.ok(!result.includes('e'));assert.deepEqual(result.filter(id=>id!=='f'),['a','b','c','d']);
});
test('deleted projects are removed without disturbing surviving order',()=>{
  const s=setup();s.ids();s.state.projects=s.state.projects.filter(p=>p.id!=='b');assert.deepEqual(s.ids(),['a','c','d','e','f']);
});
test('empty and stale candidate sets contain no undefined entries',()=>{
  const s=setup();s.state.projects=[];s.state.projectId='gone';assert.deepEqual(s.ids(),[]);s.state.projects=[{id:'live'}];s.state.projectId=null;s.state.projectLibrary.recent_ids=['missing'];assert.deepEqual(s.ids(),[]);s.state.projectId='live';assert.deepEqual(s.ids(),['live']);
});
test('stored display order survives a restart even when recency changes',async()=>{
  const saved=new Map(),first=setup(saved);first.ids();await first.selectSidebarProject('d');assert.ok(saved.has(key));const second=setup(saved);second.state.projectId='d';second.state.projectLibrary.recent_ids=['d','a','b','c','e'];assert.deepEqual(second.ids(),['a','b','c','d','e']);
});
test('stored stale ids and duplicates cannot hide the current project',()=>{
  const s=setup(new Map([[key,JSON.stringify(['gone','c','c','b','a','x'])]]));const ids=s.ids();assert.equal(ids.length,5);assert.equal(new Set(ids).size,5);assert.ok(ids.includes('a'));assert.deepEqual(ids.filter(id=>['a','b','c'].includes(id)),['c','b','a']);
});
test('malformed or non-array saved order falls back to a valid initial sidebar',()=>{
  for(const raw of ['{broken','null','42','"c"','{}']){const s=setup(new Map([[key,raw]]));assert.deepEqual(s.ids(),['a','b','c','d','e']);}
});
test('blocked local storage does not block navigation or stable in-memory ordering',async()=>{
  const s=setup(new Map(),true);const ids=s.ids();await s.selectSidebarProject('b');assert.deepEqual(s.ids(),ids);assert.equal(s.state.projectId,'b');
});
test('repeated current-project click preserves folder, page, selection, draft and makes no requests',async()=>{
  const s=setup();s.ids();setLocation(s);const before=location(s);s.calls.length=0;s.writes.length=0;assert.equal(await s.selectSidebarProject('a'),false);assert.deepEqual(location(s),before);assert.equal(s.state.tabs[0].draft,'保留正文');assert.equal(s.state.tabs[0].dirty,true);assert.deepEqual(s.calls,[]);assert.deepEqual(s.writes,[]);
});
test('same project numeric and string ids are equivalent for the no-op check',async()=>{
  const s=setup();s.state.projectId=7;setLocation(s);const before=location(s);assert.equal(await s.selectSidebarProject('7'),false);assert.deepEqual(location(s),before);assert.deepEqual(s.calls,[]);
});
test('cancelling unsaved-property confirmation preserves location, sidebar and draft',async()=>{
  const s=setup();const ids=s.ids();setLocation(s);const before=location(s);vm.runInContext('guardProperties=async()=>{calls.push("guard-cancel");return false;}',s.context);s.calls.length=0;await s.selectSidebarProject('b');assert.deepEqual(location(s),before);assert.deepEqual(s.ids(),ids);assert.equal(s.state.tabs[0].draft,'保留正文');assert.deepEqual(s.calls,['guard-cancel']);
});
test('accepted project navigation retains existing reset semantics and preserves an open dirty tab',async()=>{
  const s=setup();s.ids();setLocation(s);await s.selectSidebarProject('b');assert.equal(s.state.projectId,'b');assert.equal(s.state.folderId,null);assert.equal(s.state.folderPage,0);assert.equal(s.state.offset,0);assert.equal(s.state.selectedIds.size,0);assert.equal(s.state.activeKey,'file:editing');assert.equal(s.state.tabs[0].draft,'保留正文');assert.equal(s.state.tabs[0].dirty,true);
});
test('visit failure leaves location unchanged and does not load another project',async()=>{
  const s=setup();const ids=s.ids();setLocation(s);const before=location(s);vm.runInContext('api=async()=>{throw Error("visit unavailable");}',s.context);s.calls.length=0;await assert.rejects(s.selectSidebarProject('b'),/visit unavailable/);assert.deepEqual(location(s),before);assert.deepEqual(s.ids(),ids);assert.ok(!s.calls.includes('load'));
});
