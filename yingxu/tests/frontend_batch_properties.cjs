'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {test}=require('node:test');
const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
function setup(){
  const nodes=new Map(),calls=[],dialogs=[];
  const node=key=>{if(!nodes.has(key))nodes.set(key,{open:false,hidden:true,innerHTML:'',style:{},getBoundingClientRect:()=>({right:200,bottom:50}),focus(){},querySelector:()=>node('button')});return nodes.get(key);};
  const context=vm.createContext({localStorage:{getItem:()=>null},document:{querySelector:node,querySelectorAll:()=>[]},window:{innerWidth:1000,innerHeight:800},FormData:class{constructor(data){this.data=data;}get(k){return this.data[k];}},setTimeout,console,dialogs,calls,
    fakeApi:async(url,opt)=>{calls.push({url,...opt});if(context.failure)throw new Error('409 标签超限');if(context.pending)await context.pending;return {items:opt.body.ids.map(id=>({id,status:opt.body.status||'待开始',tags:['原标签',...(opt.body.tags_add||[])],updated:'new'}))};}});
  vm.runInContext(source+`\nshowDialog=options=>dialogs.push(options);api=fakeApi;selectableResourceIds=()=>state.items.filter(i=>!i.hidden).map(i=>i.id);guardProperties=async tab=>{calls.push({guard:tab.id});return globalThis.guardAllowed!==false;};persistDrafts=()=>{};renderTabs=()=>{};renderInspector=()=>{};renderEditorStatus=()=>{};refreshProjects=async()=>{};loadItems=async()=>{calls.push({reload:true});};toast=()=>{};report=()=>{};globalThis.app={state,batchPropertiesDialog,runMenu,showMenu};`,context);
  const s=context.app.state;Object.assign(s,{projectId:'p',items:[{id:'a',project_id:'p'},{id:'b',project_id:'p'}],selectedIds:new Set(['a','b'])});
  return {...context.app,context,nodes,node,calls,dialogs,writes:()=>calls.filter(c=>c.url)};
}
test('batch tags append a deduplicated list without sending status or replacement tags',async()=>{
  const s=setup();await s.batchPropertiesDialog();assert.match(s.dialogs[0].title,/2 项/);assert.match(s.dialogs[0].body,/保持各自状态/);
  await s.dialogs[0].onSubmit({tags_add:' 夜景，人物,夜景\n 主角 '});const body=s.writes()[0].body;
  assert.equal(s.writes().length,1);assert.equal(s.writes()[0].method,'POST');assert.deepEqual(JSON.parse(JSON.stringify(body)),{project_id:'p',ids:['a','b'],tags_add:['夜景','人物','主角']});
});
test('status-only change leaves tags unspecified; combined update uses a single request',async()=>{
  for(const tags of ['', '夜景']){const s=setup();await s.batchPropertiesDialog();await s.dialogs[0].onSubmit({tags_add:tags,status:'已完成'});assert.equal(s.writes().length,1);assert.equal(s.writes()[0].body.status,'已完成');assert.equal('tags_add' in s.writes()[0].body,!!tags);}
});
test('empty form, invalid status, and oversized tags never write',async()=>{
  for(const form of [{},{status:'bad'},{tags_add:'x'.repeat(81)},{tags_add:Array.from({length:51},(_,i)=>'tag'+i).join(',')}]){const s=setup();await s.batchPropertiesDialog();await assert.rejects(s.dialogs[0].onSubmit(form));assert.equal(s.writes().length,0);}
});
test('modal, loading, empty or hidden/stale/cross-project selection cannot start',async()=>{
  for(const flag of ['modal','loading','empty','hidden','stale','other']){const s=setup();if(flag==='modal')s.node('#appDialog').open=true;if(flag==='loading')s.state.loadingItems=true;if(flag==='empty')s.state.selectedIds.clear();if(flag==='hidden')s.state.items[0].hidden=true;if(flag==='stale')s.state.selectedIds.add('missing');if(flag==='other')s.state.items[0].project_id='other';try{await s.batchPropertiesDialog();}catch{}assert.equal(s.dialogs.length,0,flag);assert.equal(s.writes().length,0);}
});
test('existing property edit is guarded; cancellation never opens another modal',async()=>{
  const s=setup();s.state.tabs=[{id:'a',source:'file',detailReady:true,propertiesDirty:true}];s.context.guardAllowed=false;await s.batchPropertiesDialog();assert.equal(s.dialogs.length,0);assert.equal(s.calls[0].guard,'a');
});
test('project changes and concurrent property edits prevent stale submission',async()=>{
  for(const flag of ['project','dirty','saving']){const s=setup();await s.batchPropertiesDialog();if(flag==='project')s.state.projectId='other';else s.state.tabs=[{id:'a',source:'file',detailReady:true,[flag==='dirty'?'propertiesDirty':'propertiesSaving']:true}];await assert.rejects(s.dialogs[0].onSubmit({status:'进行中'}));assert.equal(s.writes().length,0);}
});
test('open text draft and unrelated metadata survive successful update',async()=>{
  const s=setup(),tab={id:'a',key:'file:a',source:'file',detailReady:true,dirty:true,draft:'未保存正文',content:{etag:'original'},item:{id:'a',name:'原标题',notes:'原备注',metadata:{duration:5}}};s.state.tabs=[tab];s.state.activeKey=tab.key;
  await s.batchPropertiesDialog();await s.dialogs[0].onSubmit({tags_add:'新标签',status:'已完成'});assert.equal(tab.draft,'未保存正文');assert.equal(tab.dirty,true);assert.equal(tab.content.etag,'original');assert.equal(tab.item.name,'原标题');assert.equal(tab.item.metadata.duration,5);assert.equal(tab.item.status,'已完成');assert.deepEqual(Array.from(tab.item.tags),['原标签','新标签']);
});
test('failed batch preserves local items, selection and allows an explicit retry',async()=>{
  const s=setup();await s.batchPropertiesDialog();s.context.failure=true;await assert.rejects(s.dialogs[0].onSubmit({status:'进行中'}));assert.equal(s.state.selectedIds.size,2);assert.equal(s.calls.some(c=>c.reload),false);s.context.failure=false;await s.dialogs[0].onSubmit({status:'进行中'});assert.equal(s.writes().length,2);
});
test('an unchanged inspector snapshot cannot mask the newly saved batch status or tags',async()=>{
  const s=setup(),tab={id:'a',source:'file',detailReady:true,item:{id:'a',status:'待开始',tags:['旧标签']},propertiesDirty:false,propertiesDraft:{status:'待开始',tags:['旧标签']}};
  s.state.tabs=[tab];await s.batchPropertiesDialog();await s.dialogs[0].onSubmit({tags_add:'新标签',status:'已完成'});
  assert.equal(tab.propertiesDraft,null);assert.equal(tab.item.status,'已完成');assert.ok(tab.item.tags.includes('新标签'));
});
test('pending submission is sent once even with repeated clicks',async()=>{
  const s=setup();await s.batchPropertiesDialog();let release;s.context.pending=new Promise(r=>release=r);const first=s.dialogs[0].onSubmit({status:'进行中'});assert.equal(await s.dialogs[0].onSubmit({status:'进行中'}),false);assert.equal(s.writes().length,1);release();await first;
});
test('context menu acts on selected group or only the unselected clicked resource',async()=>{
  for(const id of ['a','b']){const s=setup();s.state.selectedIds=new Set(['a']);await s.runMenu('batch-status',{id});assert.equal(s.dialogs.length,1);assert.match(s.dialogs[0].body,/id="batchStatus"[^>]*autofocus/);await s.dialogs[0].onSubmit({status:'待审核'});assert.deepEqual(Array.from(s.writes()[0].body.ids),[id]);}
  const s=setup();s.showMenu(s.node('anchor'),'item','a');assert.match(s.node('#resourceMenu').innerHTML,/添加标签（2 项）/);assert.match(s.node('#resourceMenu').innerHTML,/修改状态（2 项）/);
});


function delayedItemDetail(s) {
  let release;
  s.context.itemReply=new Promise(resolve=>{release=resolve;});
  vm.runInContext(`guardProperties=async()=>true;renderWorkspace=()=>{};applyDraft=()=>{};
    api=async(url,opt)=>url==='/api/items/a'?itemReply:fakeApi(url,opt);
    globalThis.openForReview=openItem;`,s.context);
  return {open:()=>s.context.openForReview('a'),release:()=>release({id:'a',project_id:'p',name:'旧快照',kind:'image',status:'待开始',tags:['原标签']})};
}

test('an outstanding real openItem detail request must finish before opening batch editing',async()=>{
  const s=setup(),detail=delayedItemDetail(s),opening=detail.open();await new Promise(setImmediate);
  assert.equal(s.state.tabs[0].loading,true);
  await assert.rejects(s.batchPropertiesDialog(),/尚未载入/);
  assert.equal(s.dialogs.length,0);assert.equal(s.writes().length,0);
  detail.release();await opening;
  assert.equal(s.state.tabs[0].detailReady,true);assert.equal(s.state.tabs[0].loading,false);
  await s.batchPropertiesDialog();await s.dialogs[0].onSubmit({tags_add:'新标签',status:'已完成'});
  assert.equal(s.writes().length,1);assert.equal(s.state.tabs[0].item.status,'已完成');assert.ok(s.state.tabs[0].item.tags.includes('新标签'));
});

test('detail loading started after the batch dialog opens blocks submission until it settles',async()=>{
  const s=setup();await s.batchPropertiesDialog();
  const detail=delayedItemDetail(s),opening=detail.open();await new Promise(setImmediate);
  await assert.rejects(s.dialogs[0].onSubmit({tags_add:'新标签',status:'已完成'}),/尚未载入/);
  assert.equal(s.writes().length,0);
  detail.release();await opening;
  await s.dialogs[0].onSubmit({tags_add:'新标签',status:'已完成'});
  assert.equal(s.writes().length,1);assert.equal(s.state.tabs[0].item.status,'已完成');assert.ok(s.state.tabs[0].item.tags.includes('新标签'));
});

test('saving guarded properties can remove an item from the filter and invalidates the captured batch',async()=>{
  const s=setup();s.state.tabs=[{id:'a',source:'file',detailReady:true,propertiesDirty:true}];
  vm.runInContext(`guardProperties=async tab=>{tab.propertiesDirty=false;state.items=state.items.filter(i=>i.id!=='a');state.selectedIds.clear();return true;};`,s.context);
  await assert.rejects(s.batchPropertiesDialog(),/重新选择/);
  assert.equal(s.dialogs.length,0);assert.equal(s.writes().length,0);
});

test('the visible range is checked again at submission after refresh or hidden group membership changes',async()=>{
  for(const change of ['hidden','removed','loading']) {
    const s=setup();await s.batchPropertiesDialog();
    if(change==='hidden')s.state.items[0].hidden=true;
    if(change==='removed')s.state.items=s.state.items.filter(i=>i.id!=='a');
    if(change==='loading')s.state.loadingItems=true;
    await assert.rejects(s.dialogs[0].onSubmit({status:'已完成'}),/重新选择/);
    assert.equal(s.writes().length,0,change);
  }
});

test('successful batch write remains successful when project and list refreshes fail',async()=>{
  const s=setup();vm.runInContext(`refreshProjects=async()=>{throw new Error('project refresh failed');};loadItems=async()=>{throw new Error('list refresh failed');};`,s.context);
  await s.batchPropertiesDialog();await s.dialogs[0].onSubmit({status:'已完成'});
  assert.equal(s.writes().length,1);
});
