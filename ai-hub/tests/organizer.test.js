'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const organizer = require('../frontend/organizer.js');

test('classification labels translate storage categories without changing target paths', () => {
  assert.equal(organizer.categoryLabel('03_Videos'),'视频素材');
  assert.equal(organizer.categoryLabel('01_Models/unknown/Unknown'),'模型 · 用途待确认 · 类型待确认');
  assert.equal(organizer.categoryLabel('01_Models/image/LoRA/lighting'),'模型 · 图片创作 · LoRA · 光照氛围');
  const html=organizer.planTable({items:[{category:'03_Videos',target:'D:\\Assets\\00_AIHub_Library\\03_Videos\\clip.mp4'}]}).html;
  assert.match(html,/视频素材/);
  assert.match(html,/00_AIHub_Library\\03_Videos\\clip.mp4/);
});

test('first-run and disconnected workspaces have an internal setup link and escaped messages', () => {
  const fresh = organizer.workspaceBanner({workspace:{configured:false,message:'<script>unsafe</script>'}});
  assert.match(fresh, /href="#\/organizer"/);
  assert.match(fresh, /让 AI Hub 适应这台电脑/);
  assert.match(fresh, /&lt;script&gt;/);
  assert.doesNotMatch(fresh, /<script>/);
  assert.match(organizer.workspaceBanner({workspace:{configured:true,available:false}}), /资产目录暂时不可访问/);
  assert.equal(organizer.workspaceBanner({workspace:{configured:true,available:true}}), '');
});

test('classification preview is bounded to 200 rows and paginated after filtering', () => {
  const plan = {items:Array.from({length:230}, (_,i) => ({source:`source-${i}`,target:`target-${i}`,category:i%2?'video':'image',reason:'evidence',size:100}))};
  const first = organizer.planTable(plan);
  assert.equal(first.shown,200);
  assert.equal(first.pages,8);
  assert.equal((first.html.match(/<tr>/g)||[]).length,25);
  assert.match(first.html,/source-24</);
  assert.doesNotMatch(first.html,/source-25</);
  const filtered = organizer.planTable(plan,'video',99);
  assert.equal(filtered.page,4);
  assert.equal(filtered.total,100);
  assert.match(filtered.html,/source-199</);
  assert.doesNotMatch(filtered.html,/source-20[01]</);
});

test('plan paths, category, and metadata evidence remain literal text', () => {
  const html = organizer.planTable({items:[{source:'" onmouseover="evil',target:'<img src=x>',category:'<script>unsafe</script>',reason:'<svg onload=evil>',size:1024}]}).html;
  assert.match(html,/&quot; onmouseover=&quot;/);
  assert.match(html,/&lt;img src=x&gt;/);
  assert.match(html,/&lt;svg onload=evil&gt;/);
  assert.doesNotMatch(html,/<(?:script|svg|img)/);
  assert.match(html,/1.0 KiB/);
});

test('run history bounds rows, escapes errors and prevents repeated undo for undone runs', () => {
  const html=organizer.renderRuns([
    {id:'" unsafe',created_at:'<img src=x>',status:'partial',created:2,errors:1,error_messages:['<script>reason</script>']},
    {id:'finished',status:'undone',created:2,undone:2},
  ],false);
  assert.match(html,/data-organizer-undo="&quot; unsafe"/);
  assert.match(html,/&lt;script&gt;reason&lt;\/script&gt;/);
  assert.match(html,/已撤销 2/);
  assert.doesNotMatch(html,/data-organizer-undo="finished"/);
  assert.doesNotMatch(html,/<script>/);
  assert.equal((organizer.renderRuns(Array.from({length:25},(_,i)=>({id:String(i),created:1})),true).match(/data-organizer-undo/g)||[]).length,20);
});

function harness({status,plan,error} = {}) {
  const nodes = new Map(), requests = [], messages = [];
  const node = selector => {
    if(!nodes.has(selector))nodes.set(selector,{value:'',checked:false,disabled:false,textContent:'',innerHTML:'',focus(){}});
    return nodes.get(selector);
  };
  const el={isConnected:true,innerHTML:'',dataset:{},querySelector:node,querySelectorAll:()=>[]};
  let refreshes=0,polls=0;
  const render=organizer.createPage({
    api:async(url,opts)=>{
      requests.push({url,body:opts?.body});
      if(url==='/api/organizer/status')return status || {root:'',on_startup:false,workspace:{configured:false,available:false,suggested_root:'D:\\CreativeAssets'},runs:[],busy:false};
      if(url==='/api/organizer/plan') {if(plan)return plan;throw new Error('No saved plan');}
      if(error)throw new Error(error);
      return {ok:true};
    },
    icon:()=>'',heading:()=>'',toast:message=>messages.push(message),pollJobs:()=>{polls++;},
    openModal(){},closeModal(){},refresh:async()=>{refreshes++;},
  });
  return {el,node,render,requests,messages,get refreshes(){return refreshes;},get polls(){return polls;}};
}

test('fresh setup suggests a local directory without enabling automation or launching a write task', async () => {
  const h=harness(); await h.render(h.el);
  assert.match(h.el.innerHTML,/value="D:\\CreativeAssets"/);
  assert.doesNotMatch(h.el.innerHTML,/id="organizer-startup"[^>]*checked/);
  assert.doesNotMatch(h.el.innerHTML,/id="organizer-create"[^>]*checked/);
  assert.match(h.el.innerHTML,/id="organizer-preview" disabled/);
  assert.deepEqual(h.requests.map(r=>r.url),['/api/organizer/status']);
  h.node('#organizer-root').value='E:\\MyAssets';
  h.node('#organizer-create').checked=true;
  await h.node('#organizer-form').onsubmit({preventDefault(){}});
  assert.deepEqual(h.requests.at(-1),{url:'/api/workspace/setup',body:{root:'E:\\MyAssets',create:true,on_startup:false}});
  assert.equal(h.refreshes,1);
  assert.equal(h.polls,0);
  assert(!h.requests.some(r=>r.url==='/api/organizer/apply'));
});

test('setup failures remain visible and allow correction without discarding the typed path', async () => {
  const h=harness({error:'Selected path is not safe'});await h.render(h.el);
  h.node('#organizer-root').value='C:\\Windows';
  await h.node('#organizer-form').onsubmit({preventDefault(){}});
  assert.equal(h.node('#organizer-error').textContent,'Selected path is not safe');
  assert.equal(h.node('#organizer-root').value,'C:\\Windows');
  assert.equal(h.node('#organizer-save').disabled,false);
  assert.equal(h.refreshes,0);
});

test('preview starts only the preview job and joins existing job polling', async () => {
  const status={root:'D:\\Assets',enabled:true,on_startup:false,workspace:{configured:true,available:true},runs:[],busy:false};
  const h=harness({status});await h.render(h.el);
  await h.node('#organizer-preview').onclick();
  assert.equal(h.requests.at(-1).url,'/api/organizer/preview');
  assert.equal(h.polls,1);
  assert.equal(h.refreshes,1);
  assert(!h.requests.some(r=>r.url==='/api/organizer/apply'));
});

test('busy state disables mutations, and plans from a former root are not offered for apply', async () => {
  const status={root:'D:\\Assets',enabled:true,workspace:{configured:true,available:true},runs:[],busy:true};
  const h=harness({status,plan:{id:'old',root:'E:\\OldAssets',items:[{}],summary:{planned:1}}});await h.render(h.el);
  assert.match(h.el.innerHTML,/id="organizer-save" disabled/);
  assert.match(h.el.innerHTML,/id="organizer-preview" disabled/);
  assert.doesNotMatch(h.el.innerHTML,/id="organizer-apply"/);
});

test('a completed request cannot write into a page that was navigated away from', async () => {
  let resolve;
  const h=harness();
  const render=organizer.createPage({api:()=>new Promise(done=>{resolve=done;})});
  const pending=render(h.el);h.el.isConnected=false;const before=h.el.innerHTML;
  resolve({root:'',workspace:{configured:false}});await pending;
  assert.equal(h.el.innerHTML,before);
});

test('existing asset directories require saving the safe zone before organizer preview is enabled', async () => {
  const status={root:'F:\\AI',enabled:false,on_startup:false,workspace:{configured:true,available:true},runs:[],busy:false};
  const h=harness({status});await h.render(h.el);
  assert.match(h.el.innerHTML,/先保存本机安全区以启用整理/);
  assert.match(h.el.innerHTML,/等待启用整理/);
  assert.match(h.el.innerHTML,/id="organizer-preview" disabled/);
  assert.doesNotMatch(h.el.innerHTML,/id="organizer-save" disabled/);
  assert(!h.requests.some(r=>r.url==='/api/organizer/plan'));
  h.node('#organizer-root').value='F:\\AI';
  await h.node('#organizer-form').onsubmit({preventDefault(){}});
  assert.equal(h.requests.at(-1).url,'/api/workspace/setup');
  assert.equal(h.refreshes,1);
});

test('navigation integration loads the module before the app and snapshots only in-memory view fields', () => {
  const index=fs.readFileSync(path.join(__dirname,'../frontend/index.html'),'utf8');
  assert(index.indexOf('src="organizer.js"')<index.indexOf('src="app.js"'));
  assert.match(index,/href="#\/organizer" data-page="organizer"/);
  const h=harness();h.node('#organizer-root').value='D:\\Assets';h.node('#organizer-startup').checked=true;
  h.el.dataset.organizerPage='3';
  assert.deepEqual(organizer.capture(h.el),{root:'D:\\Assets',create:false,on_startup:true,category:'',page:3});
  const app=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8');
  assert.match(app,/activePage === 'organizer'\) state = AIHubOrganizer.capture\(view\)/);
  assert.doesNotMatch(fs.readFileSync(path.join(__dirname,'../frontend/organizer.js'),'utf8'),/localStorage|sessionStorage/);
});
