'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const A='a'.repeat(32), B='b'.repeat(32), C='c'.repeat(32), D='d'.repeat(32), P='1'.repeat(32);
const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/, '');

function element({id,tag='',editable=false,cm=false,hidden=false,groupHidden=false}={}) {
  return {dataset:{item:id},hidden,isContentEditable:editable,
    closest(selector) {
      if(selector==='input' && tag==='input')return this;
      if(selector.includes('textarea,select') && (['textarea','select'].includes(tag)||editable||cm))return this;
      if(selector.includes('[hidden]')&&(hidden||groupHidden))return this;
      return null;
    },matches:()=>false};
}
function setup() {
  const calls=[],listeners=new Map(),ui={app:{open:false},menu:{hidden:true},dialog:false,drag:false,global:false,groups:false,capture:false};
  const nodes=[element({id:A}),element({id:B})];
  const document={activeElement:null,addEventListener:(name,fn)=>listeners.set(name,fn),
    querySelector(selector){if(selector==='#appDialog')return ui.app;if(selector==='#resourceMenu')return ui.menu;if(selector==='dialog[open]')return ui.dialog?{}:null;if(selector==='.dragging-card,.external-drag')return ui.drag?{}:null;return null;},
    querySelectorAll(selector){if(selector==='#resourceItems [data-yx-group-hidden]')return nodes.filter(node=>node.groupHidden);if(selector.includes('.resource-card[data-item]'))return nodes;return [];}};
  const context=vm.createContext({document,window:{},localStorage:{getItem:()=>null},setTimeout,clearTimeout,console,calls,ui});
  vm.runInContext(source+`
    choose=async()=>{calls.push(['confirm']);return globalThis.choice || 'delete';};
    prepareTabs=async tabs=>{calls.push(['prepare',tabs.map(tab=>tab.id)]);return globalThis.prepareAllowed!==false;};
    api=async(url,options)=>{calls.push(['api',url,options]);if(globalThis.apiPending)await globalThis.apiPending;if(globalThis.apiFailure)throw new Error('synthetic failure');return {batch_id:'batch'};};
    removeOpenTabs=tabs=>calls.push(['remove',tabs.map(tab=>tab.id)]);
    refreshProjects=async()=>{};loadSection=async()=>{};undoToast=(message,result,kind)=>calls.push(['undo',kind]);
    report=error=>calls.push(['error',error.message]);searchShortcut=()=>false;
    globalSearchIsOpen=()=>ui.global;groupsIsOpen=()=>ui.groups;captureUI={isBusy:()=>ui.capture};
    globalThis.app={state,deleteSelectionShortcut};`,context);
  // Bind the actual application keydown listener, including the new routing call.
  const start=source.indexOf("  document.addEventListener('keydown',event => {");
  const end=source.indexOf("  window.addEventListener('resize',hideMenu)",start);
  assert.ok(start>=0&&end>start);vm.runInContext(source.slice(start,end),context);
  const {state}=context.app;
  state.projectId=P;state.items=[{id:A,project_id:P},{id:B,project_id:P}];state.selectedIds.add(A);
  const event=(extra={})=>({key:'Delete',target:element(),preventDefault(){this.defaultPrevented=true;},...extra});
  const press=extra=>{const value=event(extra);listeners.get('keydown')(value);return value;};
  return {state,nodes,ui,calls,document,context,press,event,flush:()=>new Promise(resolve=>setImmediate(resolve)),writes:()=>calls.filter(call=>call[0]==='api')};
}

test('Delete follows existing confirmation, draft preparation and recoverable trash endpoint',async()=>{
  const s=setup();s.state.tabs=[{source:'file',id:A,key:`file:${A}`,dirty:true,draft:'未保存中文'}];
  const event=s.press();await s.flush();assert.equal(event.defaultPrevented,true);
  assert.equal(s.calls.filter(call=>call[0]==='confirm').length,1);
  assert.deepEqual(Array.from(s.calls.find(call=>call[0]==='prepare')[1]),[A]);
  const call=s.writes()[0];assert.equal(call[1],'/api/trash/items');assert.equal(call[2].method,'POST');assert.deepEqual(Array.from(call[2].body.ids),[A]);
  assert.ok(s.calls.some(call=>call[0]==='undo'&&call[1]==='items'));assert.equal(s.state.tabs[0].draft,'未保存中文');assert.equal(s.state.deleteShortcutBusy,false);
});
test('confirm_delete off skips only confirmation and retains draft guard',async()=>{
  const s=setup();s.state.bootstrap={settings:{confirm_delete:false}};s.press();await s.flush();
  assert.equal(s.calls.some(call=>call[0]==='confirm'),false);assert.equal(s.calls.some(call=>call[0]==='prepare'),true);assert.equal(s.writes().length,1);
});
test('confirmation cancellation or unsaved-draft cancellation performs no deletion',async()=>{
  for(const cancel of ['confirm','draft']){const s=setup();if(cancel==='confirm')s.context.choice='cancel';else s.context.prepareAllowed=false;s.press();await s.flush();assert.equal(s.writes().length,0);assert.equal(s.state.deleteShortcutBusy,false);assert.equal(s.state.selectedIds.has(A),true);}
});
test('no selection never falls back to open document or current folder',async()=>{
  const s=setup();s.state.selectedIds.clear();s.state.activeKey=`file:${A}`;s.state.tabs=[{key:`file:${A}`,id:A,source:'file'}];s.state.folderId='folder';
  assert.equal(s.press().defaultPrevented,undefined);await s.flush();assert.deepEqual(s.calls,[]);
});
test('only selected current-project rows on the rendered page survive scope filtering',async()=>{
  const s=setup();s.state.items.push({id:C,project_id:'other'},{id:D,project_id:P});s.nodes.push(element({id:C}));
  s.state.selectedIds=new Set([A,B,C,D,'stale']);s.nodes[1].groupHidden=true;s.nodes[1].hidden=true;
  s.press();await s.flush();assert.deepEqual(Array.from(s.writes()[0][2].body.ids),[A]);
});
test('all hidden group members produce no deletion even if selection state is stale',async()=>{
  const s=setup();s.nodes[0].groupHidden=true;s.nodes[0].hidden=true;s.press();await s.flush();assert.deepEqual(s.calls,[]);
});
for(const input of [{tag:'input'},{tag:'textarea'},{tag:'select'},{editable:true},{cm:true}])test(`editing context blocks Delete: ${JSON.stringify(input)}`,async()=>{
  for(const focused of [false,true]){const s=setup(),node=element(input);if(focused)s.document.activeElement=node;s.press(focused?{}:{target:node});await s.flush();assert.deepEqual(s.calls,[]);}
});
for(const extra of [{ctrlKey:true},{metaKey:true},{altKey:true},{shiftKey:true},{repeat:true},{isComposing:true},{keyCode:229},{defaultPrevented:true},{key:'Backspace'}])test(`modified, repeated or IME event is ignored: ${JSON.stringify(extra)}`,async()=>{
  const s=setup();s.press(extra);await s.flush();assert.deepEqual(s.calls,[]);
});
for(const flag of ['loadingItems','modalBusy','trashBusy','exitBusy','globalOpening','uploading','restoringDrafts','deleteShortcutBusy'])test(`busy state blocks deletion: ${flag}`,async()=>{
  const s=setup();s.state[flag]=true;s.press();await s.flush();assert.deepEqual(s.calls,[]);
});
test('open dialogs, context menu, screenshot, drag and background import block deletion',async()=>{
  for(const flag of ['app','dialog','global','groups','capture','drag','menu','jobs']){const s=setup();if(flag==='app')s.ui.app.open=true;else if(flag==='menu')s.ui.menu.hidden=false;else if(flag==='jobs')s.state.jobs.set('job',{});else s.ui[flag]=true;s.press();await s.flush();assert.deepEqual(s.calls,[],flag);}
});
test('non-resource sections, missing project and any saving or composing editor block deletion',async()=>{
  for(const flag of ['skills','trash','project','saving','propertiesSaving','composing']){const s=setup();if(flag==='skills'||flag==='trash')s.state.section=flag;else if(flag==='project')s.state.projectId=null;else s.state.tabs=[flag==='composing'?{markdownEditor:{isComposing:()=>true}}:{[flag]:true}];s.press();await s.flush();assert.deepEqual(s.calls,[],flag);}
});
test('separate Delete presses during pending request cannot submit twice',async()=>{
  const s=setup();let release;s.context.apiPending=new Promise(resolve=>release=resolve);s.press();await s.flush();s.press();await s.flush();assert.equal(s.writes().length,1);assert.equal(s.state.deleteShortcutBusy,true);release();await s.flush();assert.equal(s.state.deleteShortcutBusy,false);
});
test('failed deletion retains selection and unlocks a deliberate retry',async()=>{
  const s=setup();s.context.apiFailure=true;s.press();await s.flush();assert.equal(s.state.selectedIds.has(A),true);assert.equal(s.state.deleteShortcutBusy,false);assert.ok(s.calls.some(call=>call[0]==='error'));s.context.apiFailure=false;s.press();await s.flush();assert.equal(s.writes().length,2);
});

test('real Chromium DOM permits only the resource selection checkbox to route Delete',async t=>{
  const os=require('node:os'),{execFile}=require('node:child_process'),{promisify}=require('node:util'),{pathToFileURL}=require('node:url');
  const browser=[process.env.YINGXU_TEST_BROWSER,path.resolve(__dirname,'../runtime/webview2/msedgewebview2.exe'),
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(value=>value&&fs.existsSync(value));
  if(!browser){t.skip('An existing local Chromium browser is required; no download occurs');return;}
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'yingxu-delete-dom-'));
  t.after(()=>{const resolved=path.resolve(temporary);assert.ok(resolved.startsWith(path.resolve(os.tmpdir())+path.sep)&&path.basename(resolved).startsWith('yingxu-delete-dom-'));fs.rmSync(resolved,{recursive:true,force:true,maxRetries:10,retryDelay:100});});
  const start=source.indexOf("  document.addEventListener('keydown',event => {"),end=source.indexOf("  window.addEventListener('resize',hideMenu)",start);
  const runner=`
    const actual=[];searchShortcut=()=>false;report=error=>{throw error;};trashItems=async ids=>{actual.push([...ids]);};
    ${source.slice(start,end)}
    (async()=>{
      const results=[];
      async function check(name,html,target,allowed){
        document.querySelector('#resourceItems').innerHTML=html;state.items=[{id:'${A}',project_id:'${P}'}];state.projectId='${P}';state.selectedIds=new Set(['${A}']);state.deleteShortcutBusy=false;actual.length=0;
        const focused=document.querySelector(target);focused.focus();const event=new KeyboardEvent('keydown',{key:'Delete',bubbles:true,cancelable:true});focused.dispatchEvent(event);await Promise.resolve();await Promise.resolve();
        const ok=(actual.length===1)===allowed && (!allowed || actual[0].join()==='${A}') && event.defaultPrevented===allowed;
        results.push({name,ok});
      }
      const card=(control,extra='')=>'<article class="resource-card" data-item="${A}" '+extra+'><label>'+control+'</label></article>';
      const checkbox='<input id="target" type="checkbox" data-select-item="${A}" checked>';
      await check('focused selected card checkbox',card(checkbox),'#target',true);
      await check('focused selected list row checkbox',card(checkbox).replace('resource-card','resource-row'),'#target',true);
      await check('unrelated checkbox outside resource card',checkbox,'#target',false);
      await check('checkbox inside card without selection marker',card('<input id="target" type="checkbox">'),'#target',false);
      await check('checkbox marker must match owning card',card(checkbox.replace('data-select-item="${A}"','data-select-item="${B}"')),'#target',false);
      await check('text input inside card remains protected',card(checkbox.replace('type="checkbox"','type="text"')),'#target',false);
      await check('contenteditable ancestor remains protected',card(checkbox,'contenteditable="true"'),'#target',false);
      await check('hidden grouped checkbox cannot delete its resource',card(checkbox,'hidden data-yx-group-hidden'),'#target',false);
      document.querySelector('#result').textContent=JSON.stringify(results);
    })().catch(error=>document.querySelector('#result').textContent=JSON.stringify({error:String(error)}));`;
  fs.writeFileSync(path.join(temporary,'app.js'),source);
  fs.writeFileSync(path.join(temporary,'runner.js'),runner);
  fs.writeFileSync(path.join(temporary,'fixture.html'),'<!doctype html><meta charset="utf-8"><dialog id="appDialog"></dialog><div id="resourceMenu" hidden></div><div id="resourceItems"></div><pre id="result"></pre><script src="app.js"></script><script src="runner.js"></script>');
  const {stdout}=await promisify(execFile)(browser,['--headless','--disable-gpu','--no-first-run','--disable-background-networking',`--user-data-dir=${path.join(temporary,'profile')}`,'--dump-dom',pathToFileURL(path.join(temporary,'fixture.html')).href],{timeout:30000,maxBuffer:2*1024*1024,windowsHide:true});
  const match=stdout.match(/<pre id="result">([^<]+)<\/pre>/);assert.ok(match,stdout.slice(-2000));
  const results=JSON.parse(match[1].replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'));
  assert.ok(Array.isArray(results),JSON.stringify(results));assert.equal(results.length,8);for(const result of results)assert.equal(result.ok,true,result.name);
});
