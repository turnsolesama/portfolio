'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup(responses=[]) {
  const nodes=new Map();const calls=[];const dialogs=[];const messages=[];
  const context=vm.createContext({localStorage:{getItem:()=>null},document:{querySelector:selector=>{if(!nodes.has(selector))nodes.set(selector,{textContent:'',innerHTML:''});return nodes.get(selector);}},URLSearchParams,
    fakeApi:async(url,options)=>{calls.push({url,body:JSON.parse(JSON.stringify(options?.body || {}))});const value=responses.shift();if(value instanceof Error)throw value;return value;},
    fakeDialog:options=>{const listeners=[];const dialog={options,addEventListener:(_,fn)=>listeners.push(fn),close:()=>listeners.forEach(fn=>fn())};dialogs.push(dialog);return dialog;},fakeToast:message=>messages.push(message)});
  const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
  vm.runInContext(source+`\nglobalThis.app={state,deleteTrash,trashDeletePreviewHtml,renderTrash};
    api=fakeApi;showDialog=fakeDialog;toast=fakeToast;report=error=>fakeToast(error.message);
    renderHero=()=>{};renderTrash=()=>{};updatePagination=()=>{};refreshProjects=async()=>{};refreshCategoryCounts=async()=>{};loadSection=async()=>{};`,context);
  context.app.state.section='trash';return {...context.app,calls,dialogs,messages,nodes};
}
const plan=()=>({token:'confirmed-snapshot',total:1,entries:[{id:'a',kind:'items',name:'测试文件',paths:['C:\\fixture\\clip.txt'],warnings:[]}]});
test('each recycled entry offers restore and deletion with escaped names',()=>{
  const s=setup();s.state.trashEntries=[{id:'a',kind:'items',name:'<img src=x onerror=boom>',created:'2026-09-10',count:1}];s.renderTrash();
  const html=s.nodes.get('#resourceItems').innerHTML;assert.match(html,/data-delete-trash-id="a"/);assert.match(html,/data-restore-id="a"/);assert.ok(!html.includes('<img src=x'));assert.match(html,/&lt;img/);
});
test('cancelled preview never sends a deletion request and unlocks controls',async()=>{
  const s=setup([plan()]);const pending=s.deleteTrash('a','items');await tick();assert.equal(s.calls.length,1);assert.equal(s.state.trashBusy,true);s.dialogs[0].close();await pending;
  assert.equal(s.calls.length,1);assert.equal(s.state.trashBusy,false);
});
test('confirmation sends only the server snapshot token and refreshes after success',async()=>{
  const s=setup([plan(),{deleted:1,failed:[],remaining:0}]);const pending=s.deleteTrash('a','items');await tick();
  await s.dialogs[0].options.onSubmit();s.dialogs[0].close();await pending;
  assert.deepEqual(s.calls[1],{url:'/api/trash/delete',body:{token:'confirmed-snapshot'}});assert.match(s.messages[0],/已清理 1 项/);assert.equal(s.state.trashBusy,false);
});
test('clear all requests the entire recycle bin and states that search does not limit it',async()=>{
  const s=setup([plan()]);s.state.q='filtered';s.state.offset=48;const pending=s.deleteTrash(null,null,true);await tick();
  assert.deepEqual(s.calls[0].body,{all:true});assert.match(s.dialogs[0].options.subtitle,/不受当前搜索或分页影响/);s.dialogs[0].close();await pending;
});
test('blocked entries cannot be submitted and external-file warnings are shown',async()=>{
  const p=plan();p.entries[0].error='共享项目正在使用';p.entries[0].warnings=['外部原文件保留'];const s=setup([p]);const pending=s.deleteTrash('a','items');await tick();
  assert.ok(!s.dialogs[0].options.actions.includes('type="submit"'));assert.match(s.dialogs[0].options.body,/共享项目正在使用/);assert.match(s.dialogs[0].options.body,/外部原文件保留/);s.dialogs[0].close();await pending;
});
test('partial failure reports retained entries without showing unescaped server content',async()=>{
  const s=setup([plan(),{deleted:0,failed:[{name:'<script>',error:'locked <b>file</b>'}],remaining:1}]);const pending=s.deleteTrash('a','items');await tick();await s.dialogs[0].options.onSubmit();s.dialogs[0].close();await pending;
  assert.equal(s.dialogs.length,2);assert.match(s.dialogs[1].options.body,/&lt;script&gt;/);assert.match(s.messages[0],/1 项未删除/);
});
test('a second click while awaiting confirmation cannot start another request',async()=>{
  const s=setup([plan()]);const pending=s.deleteTrash('a','items');await tick();await s.deleteTrash('a','items');assert.equal(s.calls.length,1);s.dialogs[0].close();await pending;
});
test('preview errors release the busy state and never submit deletion',async()=>{
  const s=setup([new Error('条目已恢复')]);await s.deleteTrash('a','items');assert.equal(s.state.trashBusy,false);assert.equal(s.calls.length,1);assert.equal(s.dialogs.length,0);assert.match(s.messages[0],/条目已恢复/);
});
test('navigation during preview prevents a late confirmation from opening',async()=>{
  const s=setup([plan()]);const pending=s.deleteTrash('a','items');s.state.section='assets';await pending;assert.equal(s.dialogs.length,0);assert.equal(s.state.trashBusy,false);
});
test('confirmation preference can skip the popup while keeping the preview token protocol',async()=>{
  const s=setup([plan(),{deleted:1,failed:[],remaining:0}]);s.state.bootstrap={settings:{confirm_trash_delete:false}};
  await s.deleteTrash('a','items');assert.equal(s.dialogs.length,0);assert.deepEqual(s.calls.map(call=>call.url),['/api/trash/delete-preview','/api/trash/delete']);assert.equal(s.calls[1].body.token,'confirmed-snapshot');
});
test('disabled confirmation still shows blocked entries instead of silently clearing a subset',async()=>{
  const p=plan();p.entries[0].error='项目仍在使用';const s=setup([p]);s.state.bootstrap={settings:{confirm_trash_delete:false}};
  const pending=s.deleteTrash('a','items');await tick();assert.equal(s.dialogs.length,1);assert.equal(s.calls.length,1);s.dialogs[0].close();await pending;
});
