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
  const window={innerWidth:1000,innerHeight:700,addEventListener(){},YingXuGlobalSearch:{install:()=>({open:()=>{calls.push(['global-search']);return true;},isOpen:()=>false})}};
  const context=vm.createContext({document,window,localStorage:{getItem:() => null},console,setTimeout,clearTimeout,URLSearchParams,AbortController,calls});
  let source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/, '');
  vm.runInContext(source+'\napi=async (...args)=>calls.push(args); report=error=>{throw error;}; globalThis.app={state,wireEvents,showMenu,runMenu,contextMenuTarget,resourcePasteAllowed,renderNavigation};',context);
  context.app.wireEvents();
  const event=(target,x=100,y=100)=>({target,clientX:x,clientY:y,preventDefault(){this.prevented=true;}});
  function element(selector,id,attribute='data-item') { const self={getAttribute:key=>key===attribute?id:null,dataset:{},closest:key=>key===selector?self:null,getBoundingClientRect:()=>({right:200,bottom:50}),focus(){document.activeElement=self;}};return self; }
  return {app:context.app,node,listeners,calls,event,element,context};
}


test('overview entries are separated from script and shot categories',()=>{
  const s=setup();s.app.state.projectId='p';s.app.renderNavigation();
  const html=s.node('#categoryNav').innerHTML;
  assert.ok(html.indexOf('data-category="all"')<html.indexOf('data-category="unclassified"'));
  assert.ok(html.indexOf('data-category="unclassified"')<html.indexOf('role="separator"'));
  assert.ok(html.indexOf('role="separator"')<html.indexOf('data-category="scripts"'));
});
test('context menu exposes paste, folder and canvas at the clicked location',async()=>{
  const s=setup();s.app.state.projectId='p';s.app.state.category='scripts';
  const target={project_id:'p',category:'unclassified',folder_id:'child'};
  s.app.showMenu(s.node('anchor'),'location',target);
  const html=s.node('#resourceMenu').innerHTML;
  for(const action of ['paste-files','new-folder','new-canvas','new-note'])assert.ok(html.includes(action));
  assert.deepEqual({...s.app.state.menu.location},target);
  vm.runInContext('newFolderDialog=async target=>calls.push(target)',s.context);
  await s.app.runMenu('new-folder',s.app.state.menu);
  assert.deepEqual({...s.calls.at(-1)},target);
});
test('paste preserves text editors and blocks during another upload',()=>{
  const s=setup();s.app.state.projectId='p';
  assert.equal(s.app.resourcePasteAllowed({closest:()=>null}),true);
  assert.equal(s.app.resourcePasteAllowed({closest:()=>({})}),false);
  s.app.state.uploading=true;assert.equal(s.app.resourcePasteAllowed({closest:()=>null}),false);
});
test('file paste in all resources targets unclassified and ignores ordinary text editing',()=>{
  const s=setup();s.app.state.projectId='p';s.app.state.category='all';
  vm.runInContext('uploadFiles=(files,category,folder)=>calls.push({count:files.length,category,folder})',s.context);
  const event={target:{closest:()=>null},clipboardData:{files:[{name:'scene.png'}]},preventDefault(){this.prevented=true;}};
  s.listeners.get('paste')(event);assert.equal(event.prevented,true);assert.equal(s.calls.at(-1).category,'unclassified');
  const typed={...event,target:{closest:()=>({})},prevented:false};s.listeners.get('paste')(typed);assert.equal(typed.prevented,false);
});
