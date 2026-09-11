'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {test}=require('node:test');
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
const preview=(overrides={})=>({token:'preview-bound-token',expires_in:300,groups:[{key:'thumbnails',label:'缩略图',bytes:42,files:1,reclaimable_bytes:42,reclaimable_files:1}],total_bytes:42,reclaimable_bytes:42,reclaimable_files:1,truncated:false,warnings:[],...overrides});
function setup(){
  const nodes=new Map(),calls=[],dialogs=[];let handler=async()=>preview();
  function create(key){
    const listeners={};let html='',text='';
    const n={open:false,isConnected:true,disabled:false,checked:false,value:'',listeners,
      addEventListener:(type,fn)=>(listeners[type]??=[]).push(fn),dispatch(type){for(const fn of listeners[type]||[])fn({target:n});}};
    function clearChild(){if(key==='#maintenanceResult'&&nodes.has('#cleanupMaintenance')){nodes.get('#cleanupMaintenance').isConnected=false;nodes.delete('#cleanupMaintenance');}}
    Object.defineProperties(n,{innerHTML:{get:()=>html,set:value=>{clearChild();html=String(value);text='';if(key==='#maintenanceResult'&&html.includes('id="cleanupMaintenance"')){const child=create('#cleanupMaintenance');child.disabled=/<button[^>]*id="cleanupMaintenance"[^>]*\bdisabled/.test(html);nodes.set('#cleanupMaintenance',child);}}},textContent:{get:()=>text,set:value=>{clearChild();text=String(value);html='';}}});
    return n;
  }
  for(const key of ['#appDialog','#maintenanceResult','#maintenanceCache','#maintenanceVersions','#maintenanceKeep','#maintenanceDays','#previewMaintenance','#sortFilter'])nodes.set(key,create(key));
  nodes.get('#maintenanceCache').checked=true;nodes.get('#maintenanceKeep').value='20';nodes.get('#maintenanceDays').value='30';
  const context=vm.createContext({console,setTimeout,clearTimeout,window:{},document:{querySelector:key=>nodes.get(key)||null},localStorage:{getItem:()=>null,setItem(){}},
    fakeApi:async(url,options)=>{if(url==='/api/settings')return {};calls.push({url,options});return handler(url,options);},
    fakeDialog:options=>{dialogs.push(options);nodes.get('#appDialog').open=true;}});
  const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
  vm.runInContext(source+`\napi=fakeApi;showDialog=fakeDialog;toast=()=>{};globalThis.app={state,settingsDialog,maintenanceAction};`,context);
  context.app.state.bootstrap={version:'0.4.4',settings:{},capabilities:{maintenance:true}};
  return {...context.app,context,calls,dialogs,node:key=>nodes.get(key),respond:fn=>handler=fn};
}

test('settings defaults require explicit history opt-in and wire all option invalidators',async()=>{
  const s=setup();await s.settingsDialog();const body=s.dialogs[0].body;
  assert.match(body,/id="maintenanceCache" checked/);assert.match(body,/id="maintenanceVersions">/);
  assert.match(body,/id="maintenanceKeep"[^>]*min="1"[^>]*value="20"/);
  for(const key of ['#maintenanceCache','#maintenanceVersions','#maintenanceKeep','#maintenanceDays'])assert.equal(s.node(key).listeners.input.length,1);
});

test('preview renders escaped capacity data and cleanup sends only the bound token',async()=>{
  const s=setup();await s.settingsDialog();s.respond(async url=>url.endsWith('preview')?preview({groups:[{label:'<img onerror=x>',bytes:42,reclaimable_bytes:42}]}):{removed_files:1,removed_bytes:42,skipped_files:0,warnings:[]});
  await s.maintenanceAction();assert.match(s.node('#maintenanceResult').innerHTML,/&lt;img onerror=x&gt;/);assert.equal(s.node('#cleanupMaintenance').disabled,false);
  await s.maintenanceAction(true);assert.equal(s.calls[1].url,'/api/maintenance/cleanup');
  assert.deepEqual(JSON.parse(JSON.stringify(s.calls[1].options.body)),{token:'preview-bound-token'});
  assert.match(s.node('#maintenanceResult').innerHTML,/已清理 1 个文件/);assert.equal(s.node('#cleanupMaintenance'),undefined);
});

test('changing any option after preview removes confirmation and blocks the old token',async()=>{
  for(const key of ['#maintenanceCache','#maintenanceVersions','#maintenanceKeep','#maintenanceDays']){
    const s=setup();await s.settingsDialog();await s.maintenanceAction();const old=s.node('#cleanupMaintenance');
    s.node(key).dispatch('input');assert.equal(old.isConnected,false);assert.equal(s.node('#cleanupMaintenance'),undefined);
    assert.match(s.node('#maintenanceResult').textContent,/重新查看/);
    await s.maintenanceAction(true);assert.equal(s.calls.length,1);assert.match(s.node('#maintenanceResult').textContent,/重新预览/);
  }
});

test('changed options during an outstanding preview cannot restore its token or button',async()=>{
  const s=setup(),gate=deferred();await s.settingsDialog();s.respond(()=>gate.promise);
  const pending=s.maintenanceAction();assert.equal(s.node('#previewMaintenance').disabled,true);
  s.node('#maintenanceVersions').checked=true;s.node('#maintenanceVersions').dispatch('input');
  gate.resolve(preview());await pending;assert.equal(s.node('#cleanupMaintenance'),undefined);
  assert.match(s.node('#maintenanceResult').textContent,/选项已改变/);assert.equal(s.node('#previewMaintenance').disabled,false);
  await s.maintenanceAction(true);assert.equal(s.calls.length,1);
});

test('current values are checked again even if a programmatic change omitted an input event',async()=>{
  const s=setup();await s.settingsDialog();await s.maintenanceAction();s.node('#maintenanceKeep').value='100';
  await s.maintenanceAction(true);assert.equal(s.calls.length,1);assert.match(s.node('#maintenanceResult').textContent,/选项已改变/);
});

test('busy requests suppress repeated preview and cleanup while restoring the connected button',async()=>{
  const s=setup(),first=deferred();await s.settingsDialog();s.respond(()=>first.promise);
  const pending=s.maintenanceAction();await s.maintenanceAction();assert.equal(s.calls.length,1);
  first.resolve(preview());await pending;const confirm=s.node('#cleanupMaintenance'),second=deferred();s.respond(()=>second.promise);
  const cleaning=s.maintenanceAction(true);assert.equal(confirm.disabled,true);await s.maintenanceAction(true);await s.maintenanceAction();assert.equal(s.calls.length,2);
  second.resolve({removed_files:1,removed_bytes:42,skipped_files:0,warnings:[]});await cleaning;
  assert.equal(confirm.isConnected,false);assert.equal(confirm.disabled,true);
  s.respond(async()=>preview());await s.maintenanceAction();assert.equal(s.calls.length,3);
});

test('failed preview restores its button and expired cleanup cannot reuse a consumed token',async()=>{
  const s=setup();await s.settingsDialog();s.respond(async()=>{throw Error('预览失败');});await s.maintenanceAction();
  assert.equal(s.node('#previewMaintenance').disabled,false);assert.equal(s.node('#maintenanceResult').textContent,'预览失败');
  s.respond(async()=>preview());await s.maintenanceAction();s.respond(async()=>{throw Error('清理预览已过期');});
  await s.maintenanceAction(true);assert.match(s.node('#maintenanceResult').textContent,/已过期/);
  const count=s.calls.length;await s.maintenanceAction(true);assert.equal(s.calls.length,count);assert.equal(s.node('#cleanupMaintenance'),undefined);
});

test('incomplete and empty previews show disabled confirmation without claiming successful cleanup',async()=>{
  for(const truncated of [true,false]){const s=setup();await s.settingsDialog();s.respond(async()=>preview({reclaimable_files:0,reclaimable_bytes:0,truncated}));await s.maintenanceAction();
    assert.equal(s.node('#cleanupMaintenance').disabled,true);assert.doesNotMatch(s.node('#maintenanceResult').innerHTML,/已清理/);
    if(truncated)assert.match(s.node('#maintenanceResult').innerHTML,/未开放清理/);
  }
});

test('a response to a closed or replaced dialog does not overwrite its successor',async()=>{
  const s=setup(),gate=deferred();await s.settingsDialog();s.respond(()=>gate.promise);const pending=s.maintenanceAction();
  s.state.modalSequence++;s.node('#maintenanceResult').textContent='新的对话框';gate.resolve(preview());await pending;
  assert.equal(s.node('#maintenanceResult').textContent,'新的对话框');assert.equal(s.node('#cleanupMaintenance'),undefined);
});
