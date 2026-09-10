'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

function setup() {
  const listeners = new Map(), nodes = new Map(), calls = [];
  const document = {activeElement:null,querySelector:selector => node(selector),querySelectorAll:() => [],addEventListener:(type,fn) => listeners.set(type,fn)};
  function node(key) {
    if (!nodes.has(key)) nodes.set(key, {hidden:true,open:false,style:{setProperty(){}},dataset:{},classList:{add(){},remove(){},toggle(){}},offsetWidth:210,offsetHeight:220,innerHTML:'',value:'',addEventListener(){},insertAdjacentHTML(){},getBoundingClientRect:() => ({left:0,right:200,top:0,bottom:50,width:900}),querySelector:() => node('menu-first'),querySelectorAll:() => [],focus(){document.activeElement=this;},select(){},contains:element=>element===node('menu-first'),closest:() => null});
    return nodes.get(key);
  }
  document.body=node('body');
  const window={innerWidth:1000,innerHeight:700,addEventListener(){}};
  const context=vm.createContext({document,window,localStorage:{getItem:() => null},console,setTimeout,clearTimeout,URLSearchParams,AbortController,calls});
  let source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/, '');
  vm.runInContext(source+'\napi=async (...args)=>calls.push(args); report=error=>{throw error;}; globalThis.app={state,wireEvents,showMenu,runMenu,contextMenuTarget};',context);
  context.app.wireEvents();
  const event=(target,x=100,y=100)=>({target,clientX:x,clientY:y,preventDefault(){this.prevented=true;}});
  function element(selector,id,attribute='data-item') { const self={getAttribute:key=>key===attribute?id:null,dataset:{},closest:key=>key===selector?self:null,getBoundingClientRect:()=>({right:200,bottom:50}),focus(){document.activeElement=self;}};return self; }
  return {app:context.app,node,listeners,calls,event,element};
}

test('right click shows an action list and reveals clicked file without replacing the editor',async()=>{
  const s=setup();s.app.state.activeKey='file:editing';s.app.state.tabs=[{key:'file:editing',draft:'unsaved'}];
  const e=s.event(s.element('.resource-card[data-item],.resource-row[data-item]','clicked'));
  s.listeners.get('contextmenu')(e);
  assert.equal(e.prevented,true);assert.equal(s.node('#resourceMenu').hidden,false);
  assert.match(s.node('#resourceMenu').innerHTML,/打开所在文件夹/);assert.match(s.node('#resourceMenu').innerHTML,/移动到/);
  await s.app.runMenu('reveal-item',s.app.state.menu);
  assert.equal(s.calls[0][0],'/api/open');assert.deepEqual(JSON.parse(JSON.stringify(s.calls[0][1].body)),{id:'clicked',action:'reveal'});
  assert.equal(s.app.state.activeKey,'file:editing');assert.equal(s.app.state.tabs[0].draft,'unsaved');
});

test('folder menu distinguishes workbench navigation from Windows folder opening',async()=>{
  const s=setup();s.app.state.projectId='project';
  s.listeners.get('contextmenu')(s.event(s.element('[data-folder-open]','nested','data-folder-open')));
  assert.match(s.node('#resourceMenu').innerHTML,/在工作台中进入/);assert.match(s.node('#resourceMenu').innerHTML,/打开文件夹/);
  await s.app.runMenu('reveal-folder',s.app.state.menu);
  assert.equal(s.calls[0][0],'/api/open-folder');assert.equal(s.calls[0][1].body.folder_id,'nested');
});

test('blank area captures the current location and category menu opens its own category',async()=>{
  const s=setup();Object.assign(s.app.state,{projectId:'project',category:'characters',folderId:'shared'});
  const blank=s.element('#resourceViewport,#folderStrip,#folderToolbar','unused');
  s.listeners.get('contextmenu')(s.event(blank));const captured=s.app.state.menu;
  s.app.state.projectId='changed';await s.app.runMenu('reveal-location',captured);
  assert.deepEqual(JSON.parse(JSON.stringify(s.calls[0][1].body)),{project_id:'project',category:'characters',folder_id:'shared'});
  const category=s.element('[data-category]','unused');category.dataset.category='props';
  s.listeners.get('contextmenu')(s.event(category));await s.app.runMenu('reveal-location',s.app.state.menu);
  assert.equal(s.calls[1][1].body.category,'props');assert.equal(s.calls[1][1].body.folder_id,undefined);
});

test('text editing keeps its own context menu and popup stays inside screen edges',()=>{
  const s=setup();const input={closest:key=>key.startsWith('input,textarea')?{}:null};
  const editing=s.event(input);s.listeners.get('contextmenu')(editing);assert.equal(editing.prevented,undefined);
  s.listeners.get('contextmenu')(s.event(s.element('.resource-card[data-item],.resource-row[data-item]','file'),999,699));
  assert.equal(s.node('#resourceMenu').style.left,'780px');assert.equal(s.node('#resourceMenu').style.top,'470px');
  const esc={key:'Escape',preventDefault(){this.prevented=true;}};s.listeners.get('keydown')(esc);
  assert.equal(s.node('#resourceMenu').hidden,true);assert.equal(esc.prevented,true);
});

test('category-root breadcrumb opens the category directory without invalid delete commands',async()=>{
  const s=setup();s.app.state.projectId='project';s.app.state.category='characters';
  const root=s.element('[data-folder-open]','root','data-folder-open');root.dataset.folderCategory='characters';
  s.listeners.get('contextmenu')(s.event(root));
  assert.doesNotMatch(s.node('#resourceMenu').innerHTML,/删除|重命名/);
  await s.app.runMenu('reveal-location',s.app.state.menu);
  assert.deepEqual(JSON.parse(JSON.stringify(s.calls[0][1].body)),{project_id:'project',category:'characters'});
});

test('search focus does not inherit popup arrow keys and Ctrl K closes the menu',()=>{
  const s=setup();const file=s.element('.resource-card[data-item],.resource-row[data-item]','file');
  s.listeners.get('contextmenu')(s.event(file));s.node('#searchInput').focus();
  const home={key:'Home',preventDefault(){this.prevented=true;}};
  s.listeners.get('keydown')(home);assert.equal(home.prevented,undefined);
  s.listeners.get('keydown')({key:'k',ctrlKey:true,preventDefault(){}});
  assert.equal(s.node('#resourceMenu').hidden,true);
});

test('Ctrl F is the primary search shortcut and Ctrl K remains compatible',()=>{
  for (const key of ['f','F','k']) {
    const s=setup();let focused=false,selected=false;s.node('#searchInput').focus=()=>{focused=true;};s.node('#searchInput').select=()=>{selected=true;};
    const event={key,ctrlKey:true,preventDefault(){this.prevented=true;}};s.listeners.get('keydown')(event);
    assert.equal(event.prevented,true);assert.equal(focused,true);assert.equal(selected,true);
  }
});

test('search shortcut cannot escape a confirmation dialog or focus a disabled search',()=>{
  for (const mode of ['dialog','disabled']) {
    const s=setup();let focused=false;s.node('#searchInput').focus=()=>{focused=true;};
    if(mode==='dialog')s.node('#appDialog').open=true;else s.node('#searchInput').disabled=true;
    s.listeners.get('keydown')({key:'f',ctrlKey:true,preventDefault(){}});assert.equal(focused,false);
  }
});
