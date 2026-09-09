'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const registry=require('../frontend/registry.js');
const {readFileSync}=require('node:fs');
const path=require('node:path');

function harness(items, snapshot={projects:[],runs:[],templates:[]}) {
  const nodes=new Map(),requests=[];
  const node=s=>{if(!nodes.has(s))nodes.set(s,{value:'',innerHTML:'',isConnected:true});return nodes.get(s);};
  const el={isConnected:true,innerHTML:'',querySelector:node,querySelectorAll:()=>[]};
  const page=registry.createProjects({api:async(url,opts)=>{requests.push({url,body:opts?.body});return url==='/api/projects'?{items,coverage:'范围说明'}:snapshot;},heading:()=>'',toast(){},openModal(){},closeModal(){},refresh(){},nav(){},copyPath(){}});
  return {el,node,page,requests};
}
test('projects cover types, escape text, and distinguish discovery from registration',async()=>{
  const h=harness([{name:'Creative <b>',type:'creative',path:'D:/AI/40_Projects/Film',description:'draft',registered:false},{name:'Training',type:'training',path:'D:/AI/50_Training/Projects/Train',registered:true,delivery:'D:/AI/50_Training/Projects/Train/Delivery'}]);
  await h.page(h.el);
  assert.match(h.node('#project-list').innerHTML,/Creative &lt;b&gt;/);
  assert.match(h.node('#project-list').innerHTML,/未登记/);
  assert.match(h.node('#project-list').innerHTML,/已登记/);
  assert.doesNotMatch(h.node('#project-list').innerHTML,/待对照验证/);
  h.node('#project-type').value='training';h.node('#project-type').onchange();
  assert.doesNotMatch(h.node('#project-list').innerHTML,/Creative/);
  assert.match(h.node('#project-list').innerHTML,/Training/);
  assert(!h.requests.some(r=>r.body));
});
test('project navigation restores filters without browser storage',async()=>{
  const h=harness([{name:'Alpha',type:'tool',path:'D:/AI/10_Apps/Tool'}]);
  await h.page(h.el,new URLSearchParams('q=old&type=training'),{query:'Alpha',type:'tool'});
  assert.deepEqual(registry.capture(h.el),{query:'Alpha',type:'tool'});
  assert.match(h.node('#project-list').innerHTML,/Alpha/);
});
test('only current verification has a success color',()=>{
  for(const state of ['pending','path_checked','historical_passed','bad'])assert(!registry.verificationBadge(state).includes('b-green'));
  assert(registry.verificationBadge('current_passed').includes('b-green'));
});
test('stale run state uses effective evidence result',async()=>{
  const h=harness([],{projects:[],templates:[],runs:[{id:'run',validation_status:'current_passed',effective_validation_status:'historical_passed'}]});
  await h.page(h.el);
  assert.match(h.el.innerHTML,/历史执行通过/);
  assert.doesNotMatch(h.el.innerHTML,/当前复验通过/);
});
test('late project requests do not replace a navigated-away page',async()=>{
  const releases=[];
  const h=harness([]),page=registry.createProjects({api:()=>new Promise(done=>releases.push(done))});
  const pending=page(h.el);h.el.isConnected=false;
  h.el.innerHTML='new page';releases.forEach(done=>done({items:[]}));
  await pending;assert.equal(h.el.innerHTML,'new page');
});
test('knowledge and project links share history and registry loads before app',()=>{
  const html=readFileSync(path.join(__dirname,'../frontend/index.html'),'utf8');
  assert.match(html,/href="#\/projects" data-page="projects"/);
  assert(html.indexOf('src="registry.js"')<html.indexOf('src="app.js"'));
  const js=readFileSync(path.join(__dirname,'../frontend/registry.js'),'utf8');
  assert.doesNotMatch(js,/localStorage|sessionStorage/);
  assert.match(js,/nav\('reports'/);
});
