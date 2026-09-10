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
function harness(response = snapshot, shared = false, dragEnvironment = null, write = null) {
  const calls = [],dialogs = [],opened = [],toasts = [];
  function node() { return {value:'',textContent:'',innerHTML:'',listeners:{},addEventListener(name,fn){this.listeners[name]=fn;}}; }
  const api = async (path,options) => { calls.push({path,options}); if(path === '/api/project-library') return response(); if(write)return write(path,options); return {id:'new'}; };
  const ambient = {addEventListener(){},removeEventListener(){}};
  let sharedDialog;
  const showDialog = spec => {
    if (sharedDialog?.open) sharedDialog.close();
    const nodes = new Map();
    const dialog = sharedDialog || {listeners:{},querySelector(selector){if(!this.nodes.has(selector))this.nodes.set(selector,node());return this.nodes.get(selector);},querySelectorAll(){return [];},addEventListener(name,fn){(this.listeners[name] ||= []).push(fn);},close(){if(!this.open)return;this.closed=true;this.open=false;setImmediate(()=>{const callbacks=this.listeners.close||[];this.listeners.close=[];callbacks.forEach(fn=>fn());});}};
    Object.assign(dialog,{spec,nodes,closed:false,open:true,
      ownerDocument:{defaultView:ambient},classList:{add(){},remove(){},toggle(){}},
      setAttribute(){},removeAttribute(){},
      removeEventListener(name,fn){this.listeners[name]=(this.listeners[name]||[]).filter(f=>f!==fn);}}); if(shared)sharedDialog=dialog;
    if(dragEnvironment) {
      const env=dragEnvironment;
      for(const key of ['ownerDocument','classList','append','getBoundingClientRect','setPointerCapture','hasPointerCapture','releasePointerCapture','contains','emit']) dialog[key]=env.dialog[key];
      dialog.children=[];dialog.ownerDocument=env.dialog.ownerDocument;
      dialog.emit=(type,props={})=>{const event={button:0,isPrimary:true,pointerId:1,pointerType:'mouse',clientX:400,clientY:200,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...props};for(const fn of [...(dialog.listeners[type]||[])]){fn(event);if(event.stopped)break;}return event;};
    }
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

function dragHarness({folderId='b',busy=false}={}) {
  function element() {
    const listeners = {},classes=new Set();
    return {listeners,style:{},dataset:{},children:[],disabled:false,
      classList:{add:v=>classes.add(v),remove:v=>classes.delete(v),toggle:(v,on)=>on?classes.add(v):classes.delete(v),contains:v=>classes.has(v)},
      setAttribute(){},removeAttribute(){},append(...nodes){this.children.push(...nodes);nodes.forEach(n=>n.parent=this);},
      remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);},
      addEventListener(type,fn){(listeners[type]||=[]).push(fn);},
      removeEventListener(type,fn){listeners[type]=(listeners[type]||[]).filter(f=>f!==fn);},
      emit(type,props={}){const e={button:0,isPrimary:true,pointerId:1,pointerType:'mouse',clientX:400,clientY:200,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...props};for(const fn of [...(listeners[type]||[])]){fn(e);if(e.stopped)break;}return e;}};
  }
  const win=element();Object.assign(win,{innerWidth:1000,innerHeight:800});
  const dialog=element();dialog.open=true;dialog.getBoundingClientRect=()=>({left:100,right:900,top:100,bottom:700});
  dialog.setPointerCapture=id=>{dialog.captured=id;};dialog.hasPointerCapture=id=>dialog.captured===id;dialog.releasePointerCapture=()=>{dialog.captured=null;};
  dialog.contains=n=>n===row||targets.includes(n);
  const row=element();row.dataset.libraryProject='p1';
  let hit=null;
  const doc={defaultView:win,createElement:element,elementFromPoint:()=>hit};dialog.ownerDocument=doc;
  const targets=['a','b','', '*','missing'].map(id=>{const n=element();n.dataset.libraryFolder=id;n.closest=()=>n;return n;});
  const project={id:'p1',name:'雨夜<script>',folder_id:folderId};
  const calls=[];let blocked=busy;
  const controller=library.bindProjectDrag({dialog,getProject:id=>id==='p1'?project:null,getFolders:()=>folders,isBusy:()=>blocked,move:(...args)=>calls.push(args)});
  const origin=(kind='body')=>({closest:selector=>selector==='[data-library-project]'?row:selector==='[data-library-drag]'?(kind==='grip'?row:null):selector.startsWith('button,')?(kind==='button'?{}:null):null});
  const down=(props={})=>dialog.emit('pointerdown',{target:origin(),...props});
  const move=(id='a',props={})=>{hit=targets.find(n=>n.dataset.libraryFolder===id)||null;return win.emit('pointermove',{clientX:150,clientY:250,...props});};
  const up=(props={})=>win.emit('pointerup',{clientX:150,clientY:250,...props});
  return {dialog,win,targets,project,calls,controller,down,move,up,origin,setBusy:v=>blocked=v};
}
test('drag begins only past threshold and ordinary clicks remain available',()=>{
  const h=dragHarness();h.down();h.move('a',{clientX:403,clientY:204});
  assert.equal(h.dialog.captured,undefined);h.up({clientX:403,clientY:204});
  assert.equal(h.calls.length,0);assert.equal(h.dialog.emit('click').prevented,undefined);
});
test('drag highlights an exact folder and writes only on release',()=>{
  const h=dragHarness();h.down();h.move('a');
  assert.equal(h.calls.length,0);assert.equal(h.targets[0].classList.contains('project-library-drop-target'),true);
  assert.match(h.dialog.children[0].textContent,/松手移到/);assert.match(h.dialog.children[0].textContent,/<script>/);
  h.up();assert.deepEqual(plain(h.calls),[['p1','a']]);assert.equal(h.dialog.children.length,0);
  assert.equal(h.dialog.emit('click').prevented,true);assert.equal(h.dialog.emit('click').prevented,undefined);
});
test('uncategorized target and clearly marked modal exterior remove classification',()=>{
  for(const outside of [false,true]){
    const h=dragHarness();h.down();h.move('',outside?{clientX:950}:{});
    if(outside){assert.equal(h.dialog.classList.contains('project-library-drop-outside'),true);assert.match(h.dialog.children[1].textContent,/松手移到未分类/);}
    h.up(outside?{clientX:950}:{});assert.deepEqual(plain(h.calls),[['p1',null]]);
  }
});
test('all-projects, same folder, stale targets, unknown space and window edge cancel',()=>{
  for(const [target,x] of [['*',150],['b',150],['missing',150],['unknown',150],['a',2]]){
    const h=dragHarness();h.down();h.move(target,{clientX:x});h.up({clientX:x});assert.equal(h.calls.length,0,target);
  }
  const h=dragHarness({folderId:null});h.down();h.move('',{clientX:950});h.up({clientX:950});assert.equal(h.calls.length,0);
});
test('pointer cancel, capture loss, Esc, blur and close never move a project',()=>{
  for(const type of ['pointercancel','lostpointercapture','keydown','blur','close']){
    const h=dragHarness();h.down();h.move();
    const event=(type==='blur'?h.win:h.dialog).emit(type,{key:'Escape'});
    if(type==='keydown')assert.equal(event.prevented,true);
    h.up();assert.equal(h.calls.length,0,type);assert.equal(h.dialog.children.length,0,type);
  }
});
test('buttons do not start drag and touch scrolling is preserved outside grip',()=>{
  for(const props of [{target:'button'}, {pointerType:'touch'}, {button:2}, {isPrimary:false}]){
    const h=dragHarness();h.down({...props,...(props.target?{target:h.origin(props.target)}:{})});h.move();h.up();assert.equal(h.calls.length,0);
  }
  const h=dragHarness();h.down({pointerType:'touch',target:h.origin('grip')});h.move();h.up();assert.equal(h.calls.length,1);
});
test('valid pointer origin prevents default text drag while buttons and touch body retain defaults',()=>{
  const h=dragHarness();assert.equal(h.down().prevented,true);h.up();
  assert.equal(h.down({target:h.origin('button')}).prevented,undefined);
  assert.equal(h.down({pointerType:'touch'}).prevented,undefined);
  assert.equal(h.down({pointerType:'touch',target:h.origin('grip')}).prevented,true);h.up();
  assert.equal(h.dialog.emit('click').prevented,undefined);
});
test('native text dragstart cannot steal an armed pointer gesture before its movement threshold',()=>{
  const h=dragHarness();assert.equal(h.dialog.emit('dragstart').prevented,undefined);h.down();
  h.move('a',{clientX:404,clientY:202});assert.equal(h.dialog.captured,undefined);
  assert.equal(h.dialog.emit('dragstart').prevented,true);h.move('a');h.up();assert.deepEqual(plain(h.calls),[['p1','a']]);
});
test('busy prevents gestures and closing; changing busy mid-drag cancels',()=>{
  const h=dragHarness({busy:true});h.down();h.move();h.up();assert.equal(h.calls.length,0);
  assert.equal(h.dialog.emit('cancel').prevented,true);assert.equal(h.dialog.emit('click').prevented,true);
  h.setBusy(false);h.down();h.move();h.setBusy(true);h.up();assert.equal(h.calls.length,0);
});
test('drop resolves latest pointer position instead of stale highlighted target',()=>{
  const h=dragHarness();h.down();h.move('a');h.up({clientX:950});assert.deepEqual(plain(h.calls),[['p1',null]]);
});
test('destroy removes global listeners and releases capture for shared modal reuse',()=>{
  const h=dragHarness();h.down();h.move();h.controller.destroy();h.controller.destroy();
  assert.equal(h.dialog.captured,null);assert.equal(h.dialog.children.length,0);
  assert.ok(Object.values(h.win.listeners).every(list=>list.length===0));h.up();assert.equal(h.calls.length,0);
});

test('a fresh button press after cancelled drag is not swallowed as a stale click',()=>{
  const h=dragHarness();h.down();h.move();h.dialog.emit('pointercancel');
  h.down({target:h.origin('button')});assert.equal(h.dialog.emit('click').prevented,undefined);
});
test('integrated drag submits one metadata patch while pending and refreshes rendered membership',async()=>{
  let finish;
  const env=dragHarness();env.controller.destroy();
  const db={folders,projects:plain(projects)};
  const h=harness(()=>db,false,env,()=>new Promise(resolve=>{finish=resolve;}));
  await h.app.open();const d=h.dialogs[0];
  d.emit('pointerdown',{target:env.origin()});env.move('a');env.up();
  assert.equal(h.calls.filter(c=>c.options).length,1);
  assert.deepEqual(plain(h.calls[1]),{path:'/api/project-library/p1',options:{method:'PATCH',body:{folder_id:'a'}}});
  assert.equal(db.projects[0].folder_id,'b');
  d.emit('pointerdown',{target:env.origin()});env.move('');env.up();
  assert.equal(h.calls.filter(c=>c.options).length,1);assert.equal(d.emit('cancel').prevented,true);
  finish({});await new Promise(setImmediate);
  assert.equal(db.projects[0].folder_id,'a');assert.match(d.querySelector('[data-library-results]').innerHTML,/长篇 ·/);
  assert.equal(h.opened.length,0);assert.equal(h.toasts.length,1);
  d.close();await new Promise(setImmediate);
});
test('failed drag write preserves previous classification and unlocks the dialog',async()=>{
  const env=dragHarness();env.controller.destroy();
  const db={folders,projects:plain(projects)};
  const h=harness(()=>db,false,env,async()=>{throw new Error('分类已移除，请刷新');});
  await h.app.open();const d=h.dialogs[0];
  d.emit('pointerdown',{target:env.origin()});env.move('a');env.up();await new Promise(setImmediate);
  assert.equal(db.projects[0].folder_id,'b');assert.equal(h.toasts[0][1],'error');
  assert.equal(d.emit('cancel').prevented,undefined);assert.equal(d.children.length,0);
  d.close();await new Promise(setImmediate);
});
(async()=>{for(const {name,fn} of tests){await fn();console.log('PASS',name);}console.log(`${tests.length} tests passed`);})().catch(e=>{console.error(e);process.exitCode=1;});
