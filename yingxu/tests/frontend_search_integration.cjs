'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {test}=require('node:test');
function setup(){
  const nodes=new Map(),opened=[],messages=[],visits=[],reports=[];
  const node=key=>{if(!nodes.has(key))nodes.set(key,{open:false,value:'old-filter',disabled:false,focus(){this.focused=true;},select(){this.selected=true;}});return nodes.get(key);};
  const context=vm.createContext({setTimeout,clearTimeout,console,AbortController,URLSearchParams,document:{querySelector:node},window:{chrome:{webview:{postMessage:m=>messages.push(m)}},YingXuGlobalSearch:{install:options=>({isOpen:()=>!!context.searchOpen,open:()=>{if(!options.canOpen())return false;context.searchOpen=true;return true;}})}},localStorage:{getItem:()=>null,setItem(){}},opened,visits,reports});
  const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
  vm.runInContext(source+`\nconst originalLoaders={loadItems,loadSkills,loadTrash,loadContext};renderNavigation=()=>{};renderHero=()=>{};configureSection=()=>{};renderWorkspace=()=>{};renderInspector=()=>{};renderQuery=()=>{};updateSelection=()=>{};refreshProjects=async()=>{};loadItems=async()=>{};loadSkills=async()=>{};recordProjectVisit=async id=>visits.push(id);guardProperties=async()=>true;openItem=async id=>opened.push(['item',id]);openSkill=async id=>opened.push(['skill',id]);hideMenu=()=>{};toast=()=>{};report=error=>reports.push(error);persistDrafts=()=>{};api=async url=>url.startsWith('/api/items/')?{id:'found',project_id:'other',category:'characters',folder_id:'nested'}:url==='/api/projects'?{projects:[{id:'other'}]}:{id:'skill-found'};globalThis.app={state,openGlobalSearchResult,globalSearchDialog,searchShortcut,handleDesktopMessage,originalLoaders};`,context);
  return {...context.app,context,nodes,node,opened,messages,visits,reports};
}
const flush = async () => { for(let i=0;i<16;i++) await Promise.resolve(); };
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function realNavigationSetup(projectId) {
  const nodes=new Map(),opened=[],calls=[];
  const node=key=>{if(!nodes.has(key))nodes.set(key,{value:'',open:false,hidden:false,innerHTML:'',classList:{toggle(){},add(){},remove(){}},style:{setProperty(){}},addEventListener(){},querySelector:node,querySelectorAll:()=>[],insertAdjacentHTML(){},setAttribute(){},focus(){},select(){}});return nodes.get(key);};
  const context=vm.createContext({console,URLSearchParams,AbortController,setTimeout,clearTimeout,document:{querySelector:node,querySelectorAll:()=>[]},window:{},localStorage:{getItem:()=>null,setItem(){}},IntersectionObserver:class{observe(){}disconnect(){}},opened,calls});
  const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
  // Keep refreshProjects, renderNavigation, configureSection, renderWorkspace,
  // loadItems and renderItems real so internal rendering cannot be hidden by stubs.
  vm.runInContext(source+`\napi=async url=>{calls.push(url);return url==='/api/projects'?{projects:[{id:'first',name:'第一项目',counts:{}},{id:'other',name:'目标项目',counts:{}}]}:url==='/api/project-library'?{recent_ids:[]}:url.startsWith('/api/items/')?{id:'found',name:'合成文稿',project_id:'other',category:'scripts',kind:'markdown',folder_id:null}:url.startsWith('/api/items?')?{items:[],categories:[],total:0}:url.startsWith('/api/folders?')?{folders:[]}:{};};openItem=async id=>opened.push(id);globalThis.app={state,openGlobalSearchResult,refreshProjects};`,context);
  Object.assign(context.app.state,{projectId,projects:[],section:'skills',activeKey:'skill:synthetic',bootstrap:{capabilities:{project_library:true}},tabs:[{key:'skill:synthetic',source:'skill',id:'synthetic',item:{name:'合成能力',kind:'skill'},content:{content:'',editable:false},draft:'',mode:'preview'}]});
  return {...context.app,context,node,opened,calls};
}
test('global query opens independently of current filters and disabled page search',()=>{const s=setup();Object.assign(s.state,{projectId:'current',category:'video',q:'old',section:'context'});s.node('#searchInput').disabled=true;assert.equal(s.globalSearchDialog(),true);assert.equal(s.state.q,'old');assert.equal(s.state.category,'video');assert.equal(s.node('#searchInput').value,'old-filter');});
test('global result crosses projects and resets stale local filters without discarding draft tabs',async()=>{const s=setup(),draft={key:'file:old',dirty:true,draft:'未保存文稿',item:{}};Object.assign(s.state,{projectId:'current',q:'does-not-match',kind:'video',status:'已完成',category:'shots',folderId:'old-folder',activeKey:draft.key,tabs:[draft]});assert.equal(await s.openGlobalSearchResult({type:'item',id:'found',project_id:'untrusted-stale'}),true);assert.equal(s.state.projectId,'other');assert.equal(s.state.category,'characters');assert.equal(s.state.folderId,'nested');assert.equal(s.state.q,'');assert.equal(s.state.kind,'');assert.equal(s.node('#searchInput').value,'');assert.deepEqual(JSON.parse(JSON.stringify(s.opened)),[['item','found']]);assert.equal(s.state.tabs[0],draft);assert.equal(draft.draft,'未保存文稿');assert.equal(s.state.globalOpening,false);});
test('cancelled property confirmation keeps the original location',async()=>{const s=setup();s.state.projectId='current';vm.runInContext('guardProperties=async()=>false',s.context);assert.equal(await s.openGlobalSearchResult({type:'item',id:'found'}),false);assert.equal(s.state.projectId,'current');assert.equal(s.opened.length,0);assert.equal(s.state.globalOpening,false);});
test('deleted or inaccessible search results fail before navigation changes',async()=>{const s=setup();s.state.projectId='current';vm.runInContext('api=async()=>{throw new Error("文件已删除");}',s.context);await assert.rejects(s.openGlobalSearchResult({type:'item',id:'gone'}),/文件已删除/);assert.equal(s.state.projectId,'current');assert.equal(s.state.globalOpening,false);});
test('project results open the project resource page while skill results keep project binding',async()=>{const s=setup();s.state.activeKey='file:old';await s.openGlobalSearchResult({type:'project',id:'other'});assert.equal(s.state.projectId,'other');assert.equal(s.state.section,'assets');assert.equal(s.state.activeKey,null);await s.openGlobalSearchResult({type:'skill',id:'skill-found'});assert.equal(s.state.projectId,'other');assert.equal(s.state.section,'skills');assert.deepEqual(JSON.parse(JSON.stringify(s.opened)),[['skill','skill-found']]);});
test('open global modal blocks background Ctrl F and native exit approval',async()=>{const s=setup();s.globalSearchDialog();let prevented=false;s.searchShortcut({key:'f',ctrlKey:true,preventDefault(){prevented=true;}});assert.equal(prevented,true);assert.equal(s.node('#searchInput').focused,undefined);await s.handleDesktopMessage({action:'prepare-exit',requestId:'exit'});assert.equal(s.messages.at(-1).allow,false);});
test('existing confirmation and composition block opening global search',()=>{const s=setup();s.node('#appDialog').open=true;assert.equal(s.globalSearchDialog(),false);s.node('#appDialog').open=false;s.state.tabs=[{key:'draft',markdownEditor:{isComposing:()=>true}}];s.state.activeKey='draft';assert.equal(s.globalSearchDialog(),false);});
test('external open requests queue until global modal closes',async()=>{const s=setup();s.globalSearchDialog();vm.runInContext('openExternal=async id=>opened.push(["external",id])',s.context);const pending=s.handleDesktopMessage({action:'external-open',entries:[{id:'external'}]});assert.equal(s.opened.length,0);s.context.searchOpen=false;await pending;assert.deepEqual(JSON.parse(JSON.stringify(s.opened)),[['external','external']]);});

for(const [loader,section] of [['loadItems','assets'],['loadSkills','skills'],['loadTrash','trash'],['loadContext','context']]) {
  test(`${loader} ignores a stale failure without clearing the new page or its state`,async()=>{
    const s=setup(),waiting=deferred();Object.assign(s.state,{projectId:'old',section,category:'all'});s.context.waiting=waiting.promise;vm.runInContext('api=()=>waiting',s.context);
    const pending=s.originalLoaders[loader]();s.state.listSequence++;s.state.section=section==='assets'?'skills':'assets';s.state.projectId='new';s.state.items=[{id:'new'}];s.state.loadingItems=true;s.node('#resourceItems').innerHTML='new results';
    waiting.reject(Error('obsolete response'));await pending;assert.equal(s.node('#resourceItems').innerHTML,'new results');assert.equal(s.state.items[0].id,'new');assert.equal(s.state.loadingItems,true);assert.equal(s.reports.length,0);
  });
  test(`${loader} still reports a failure for the current request`,async()=>{
    const s=setup();Object.assign(s.state,{projectId:'current',section,category:'all'});vm.runInContext('api=async()=>{throw new Error("current failure")}',s.context);await s.originalLoaders[loader]();assert.match(s.node('#resourceItems').innerHTML,/current failure/);assert.equal(s.reports.length,1);
  });
}
for(const type of ['item','skill']) test(`${type} search navigation yields when a user changes location during list loading`,async()=>{
  const s=setup(),waiting=deferred(),draft={key:'file:old',dirty:true,draft:'必须保留'};s.state.tabs=[draft];s.state.activeKey=draft.key;s.context.waiting=waiting.promise;vm.runInContext(type==='item'?'loadItems=()=>waiting':'loadSkills=()=>waiting',s.context);
  const pending=s.openGlobalSearchResult({type,id:'found'});await flush();s.state.projectId='manual-project';s.state.section='assets';s.state.category='scripts';s.state.activeKey='file:manual';waiting.resolve();assert.equal(await pending,false);assert.equal(s.state.projectId,'manual-project');assert.equal(s.state.activeKey,'file:manual');assert.equal(s.opened.length,0);assert.equal(draft.draft,'必须保留');assert.equal(draft.dirty,true);assert.equal(s.state.globalOpening,false);
});
test('a superseding request on the same page cancels an older search navigation',async()=>{
  const s=setup(),waiting=deferred();s.context.waiting=waiting.promise;vm.runInContext('loadItems=()=>{state.listSequence++;return waiting}',s.context);const pending=s.openGlobalSearchResult({type:'item',id:'found'});await flush();s.state.listSequence++;waiting.resolve();assert.equal(await pending,false);assert.equal(s.opened.length,0);
});
test('manual navigation while resolving a result preserves the newer filters and active tab',async()=>{
  const s=setup(),waiting=deferred();s.context.waiting=waiting.promise;vm.runInContext('api=()=>waiting',s.context);const pending=s.openGlobalSearchResult({type:'item',id:'found'});await flush();Object.assign(s.state,{projectId:'manual',q:'new query',activeKey:'file:manual'});s.node('#searchInput').value='new query';waiting.resolve({id:'found',project_id:'other',category:'scripts'});assert.equal(await pending,false);assert.equal(s.state.projectId,'manual');assert.equal(s.state.q,'new query');assert.equal(s.state.activeKey,'file:manual');assert.equal(s.opened.length,0);
});
test('typing a local filter during list loading is respected before its debounce runs',async()=>{
  const s=setup(),waiting=deferred();s.context.waiting=waiting.promise;vm.runInContext('loadItems=()=>waiting',s.context);const pending=s.openGlobalSearchResult({type:'item',id:'found'});await flush();s.node('#searchInput').value='next query';waiting.resolve();assert.equal(await pending,false);assert.equal(s.node('#searchInput').value,'next query');assert.equal(s.opened.length,0);
});
test('a new confirmation while lists are loading prevents a result from stealing focus',async()=>{
  const s=setup(),waiting=deferred();s.context.waiting=waiting.promise;vm.runInContext('loadItems=()=>waiting',s.context);const pending=s.openGlobalSearchResult({type:'item',id:'found'});await flush();s.node('#appDialog').open=true;waiting.resolve();assert.equal(await pending,false);assert.equal(s.opened.length,0);assert.equal(s.node('#appDialog').open,true);
});
for(const initial of ['first',null,'removed-project']) test(`real project refresh and item rendering navigate from SKILL with initial project ${initial}`,async()=>{
  const s=realNavigationSetup(initial);assert.equal(await s.openGlobalSearchResult({type:'item',id:'found'}),true);assert.equal(s.state.projectId,'other');assert.equal(s.state.section,'assets');assert.deepEqual(s.opened,['found']);assert.equal(s.state.tabs[0].key,'skill:synthetic');assert.ok(s.calls.includes('/api/projects'));assert.ok(s.calls.includes('/api/project-library'));assert.ok(s.calls.some(url=>url.startsWith('/api/items?project=other')));assert.match(s.node('#projectList').innerHTML,/目标项目/);
});
test('ordinary project refresh still selects a valid fallback outside global navigation',async()=>{
  const s=realNavigationSetup(null);await s.refreshProjects();assert.equal(s.state.projectId,'first');
});
