'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const id = n => n.toString(16).padStart(32,'0');

function setup() {
  const listeners = new Map(), clocks = new Map(), calls = [], notices = [], elements = [];
  let clockId = 0;
  function node(dataset = {}) {
    const children = [], classes = new Set(), handlers = new Map(), queries = new Map();
    const element = {dataset,children,hidden:false,open:false,innerHTML:'',className:'',
      classList:{add:(...values)=>values.forEach(value=>classes.add(value)),remove:(...values)=>values.forEach(value=>classes.delete(value)),contains:value=>classes.has(value)},
      addEventListener(type,fn){handlers.set(type,fn);},removeEventListener(type){handlers.delete(type);},
      fire(type,event={}){return handlers.get(type)?.({preventDefault(){},stopPropagation(){},...event});},
      querySelector(selector){if (!queries.has(selector)) queries.set(selector,node());return queries.get(selector);},
      querySelectorAll(selector){
        if(selector==='[data-open-member]') {
          if(!queries.has(selector)) queries.set(selector,[...element.innerHTML.matchAll(/data-open-member="([^"]+)"/g)].map(match=>node({openMember:match[1]})));
          return queries.get(selector);
        }
        return [];
      }, setAttribute(name,value){element[name]=value;},removeAttribute(name){delete element[name];},
      contains(target){return target===element || children.some(child=>child.contains(target));},
      append(child){children.push(child);child.parent=element;},prepend(child){children.unshift(child);child.parent=element;},
      remove(){if(element.parent){const index=element.parent.children.indexOf(element);if(index>=0)element.parent.children.splice(index,1);element.parent=null;}},
      before(child){element.parent?.append(child);},after(child){element.parent?.append(child);},
      focus(){},showModal(){element.open=true;},close(){element.open=false;queueMicrotask(()=>element.fire('close'));},
      closest(selector){if(selector==='[data-drag-file]')return dataset.dragFile?element:null;
        if(selector==='[data-resource-group]')return dataset.resourceGroup?element:null;
        if(selector==='.resource-card[data-item]')return dataset.item?element:null;return null;}
    };
    Object.defineProperties(element,{firstChild:{get:()=>children[0] || null},lastChild:{get:()=>children.at(-1) || null}});
    elements.push(element); return element;
  }
  const document = {body:node(),createElement:()=>node(),addEventListener:(type,fn)=>listeners.set(type,fn),removeEventListener:type=>listeners.delete(type),elementFromPoint:()=>document.point};
  const ctx = {projectId:id(100),section:'assets',category:'all',view:'grid',items:[],selectedIds:new Set(),q:'',status:'',kind:''};
  let responder = async path => path.startsWith('/api/resource-groups?') ? {groups:[]} : {id:id(10),project_id:ctx.projectId,revision:7}, guardResponder = async()=>true, refreshResponder = async()=>{};
  const opened = [];
  const sandbox = {document,window:{innerWidth:1000,innerHeight:500},module:{exports:{}},console,queueMicrotask,
    setTimeout:fn=>{clocks.set(++clockId,fn);return clockId;},clearTimeout:key=>clocks.delete(key)};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../frontend/resource-groups.js'),'utf8'),sandbox);
  const library = sandbox.module.exports;
  const controller = library.install({api:async (...args)=>{calls.push(args);return responder(...args);},toast:(...args)=>notices.push(args),escapeHtml:value=>String(value),openItem:async value=>opened.push(value),guard:()=>guardResponder(),refresh:()=>refreshResponder(),getContext:()=>ctx});
  const root = node();controller.render(root);
  function fire(type,target,extra={}){const event={target,dataTransfer:{effectAllowed:'move'},preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...extra};listeners.get(type)?.(event);return event;}
  const arm = () => { const pending=[...clocks.values()];clocks.clear();pending.forEach(fn=>fn()); };
  return {library,controller,root,node,document,ctx,calls,notices,elements,fire,arm,opened,setResponder:fn=>{responder=fn;},setGuard:fn=>{guardResponder=fn;},setRefresh:fn=>{refreshResponder=fn;}};
}
const flush = () => new Promise(resolve=>setImmediate(resolve));

test('grouped page includes cross-category members, board and grid, but preserves all filtered/list results',()=>{
  const s=setup(), group={project_id:id(100),member_ids:[id(1),id(2)]};
  s.ctx.items=[{id:id(2),category:'references'}];
  assert.equal(s.library.visibleGroups([group],s.ctx).length,1);
  s.ctx.view='board';assert.equal(s.library.visibleGroups([group],s.ctx).length,1);
  for(const field of ['q','status','kind']){s.ctx[field]='filtered';assert.equal(s.library.visibleGroups([group],s.ctx).length,0);s.ctx[field]='';}
  s.ctx.view='list';assert.equal(s.library.visibleGroups([group],s.ctx).length,0);
  s.ctx.view='grid';s.ctx.items=[{id:id(3)}];assert.equal(s.library.visibleGroups([group],s.ctx).length,0);
});

test('HTML move drag waits for the hover timer then creates one logical group with target first',async()=>{
  const s=setup(), source=s.node({item:id(1)}),target=s.node({item:id(2)});s.root.append(source);s.root.append(target);
  s.fire('dragstart',source);const over=s.fire('dragover',target);assert.equal(over.prevented,true);assert.equal(over.dataTransfer.dropEffect,'none');
  assert.equal(s.calls.length,0);s.arm();assert.equal(target.classList.contains('yx-group-armed'),true);
  const ready=s.fire('dragover',target);assert.equal(ready.dataTransfer.dropEffect,'move');
  s.fire('drop',target);await flush();
  const write=s.calls.find(([,options])=>options?.method==='POST');assert.deepEqual(JSON.parse(JSON.stringify(write[1].body.item_ids)),[id(2),id(1)]);
  s.fire('drop',target);await flush();assert.equal(s.calls.filter(([,options])=>options?.method==='POST').length,1);
});

test('quick drop is swallowed without grouping or falling through into file import',async()=>{
  const s=setup(),target=s.node({item:id(2)});s.root.append(target);s.controller.beginDrag([id(1)]);
  s.fire('dragover',target);const drop=s.fire('drop',target);await flush();
  assert.equal(drop.stopped,true);assert.equal(s.calls.length,0);assert.equal(s.notices.length,1);
});

test('external files, self drops, native drag-out handles and category destinations remain untouched',()=>{
  const s=setup(),target=s.node({item:id(2)});s.root.append(target);
  assert.equal(s.fire('dragover',target).prevented,undefined);
  s.controller.beginDrag([id(2)]);assert.equal(s.fire('dragover',target).prevented,undefined);
  const handle=s.node({item:id(1),dragFile:id(1)});s.root.append(handle);s.controller.endDrag();s.fire('dragstart',handle);
  assert.equal(s.fire('dragover',target).prevented,undefined);
  s.controller.beginDrag([id(1)]);const category=s.node({category:'scripts'});
  assert.equal(s.fire('drop',category).stopped,undefined);
});

test('selected cards form one group and cross-project switches cancel the pending target',async()=>{
  const s=setup(),source=s.node({item:id(1)}),target=s.node({item:id(3)});s.root.append(source);s.root.append(target);
  s.ctx.selectedIds=new Set([id(1),id(2)]);s.fire('dragstart',source);s.fire('dragover',target);s.arm();
  s.ctx.projectId=id(101);assert.equal(s.fire('drop',target).stopped,undefined);await flush();assert.equal(s.calls.length,0);
  s.ctx.projectId=id(100);s.fire('dragstart',source);s.fire('dragover',target);s.arm();s.fire('drop',target);await flush();
  assert.deepEqual(JSON.parse(JSON.stringify(s.calls[0][1].body.item_ids)),[id(3),id(1),id(2)]);
});

test('native board release is accepted only after armed hover and actual release inside the app',async()=>{
  const s=setup(),target=s.node({item:id(2)});s.root.append(target);s.ctx.view='board';s.document.point=target;
  s.controller.beginDrag([id(1)]);s.fire('dragover',target);s.arm();
  assert.equal(s.controller.handleNativeDrop({released:false,inside:true,width:100,height:100,x:20,y:20}),false);
  assert.equal(s.controller.handleNativeDrop({released:true,inside:false,width:100,height:100,x:20,y:20}),false);
  assert.equal(s.controller.handleNativeDrop({released:true,inside:true,width:100,height:100,x:20,y:20}),true);
  assert.equal(s.controller.handleNativeDrop({released:true,inside:true,width:100,height:100,x:20,y:20}),false);
  await flush();assert.equal(s.calls.filter(([,o])=>o?.method==='POST').length,1);
});

test('drop on existing group fetches current revision and updates membership rather than moving paths',async()=>{
  const s=setup(),target=s.node({resourceGroup:id(10)});s.root.append(target);s.controller.beginDrag([id(1)]);
  s.fire('dragover',target);s.arm();s.fire('drop',target);await flush();
  const write=s.calls.find(([,o])=>o?.method==='POST');assert.equal(write[0],`/api/resource-groups/${id(10)}/members`);
  assert.equal(write[1].body.revision,7);assert.equal(s.calls.some(([p])=>p==='/api/move'),false);
});

test('leaving a hovered target resets the timer and destroy removes handlers',async()=>{
  const s=setup(),target=s.node({item:id(2)});s.root.append(target);s.controller.beginDrag([id(1)]);
  s.fire('dragover',target);s.fire('dragleave',target,{relatedTarget:null});s.arm();assert.equal(target.classList.contains('yx-group-armed'),false);
  s.controller.destroy();s.fire('dragover',target);s.arm();s.fire('drop',target);await flush();assert.equal(s.calls.length,0);
});

test('stale project refresh is discarded without replacing the new project groups',async()=>{
  const s=setup();let resolve;
  s.setResponder(()=>new Promise(done=>{resolve=done;}));const pending=s.controller.refresh();s.ctx.projectId=id(101);
  resolve({groups:[{id:id(10),project_id:id(100),member_ids:[],preview:[]}]});await pending;
  assert.equal(s.root.children.length,0);
});

test('latest dialog request wins and queued close of previous dialog cannot close its replacement',async()=>{
  const s=setup();const group=n=>({id:id(n),project_id:id(100),name:`组${n}`,count:0,preview:[],members:[],revision:1});let old;
  s.setResponder(path=>path.endsWith(id(10))?new Promise(resolve=>{old=resolve;}):Promise.resolve(group(11)));
  const previous=s.controller.open(id(10));assert.equal(s.controller.isOpen(),true);await s.controller.open(id(11));old(group(10));await previous;
  assert.equal(s.controller.isOpen(),true);assert.match(s.document.body.children[0].innerHTML,/组11/);
  s.setResponder(async()=>group(12));await s.controller.open(id(12));await flush();
  assert.equal(s.controller.isOpen(),true);assert.equal(s.document.body.children.length,1);assert.match(s.document.body.children[0].innerHTML,/组12/);
});

test('opening a member remains guarded while unsaved properties are resolved and cancellation restores the group',async()=>{
  const s=setup(),group={id:id(10),project_id:id(100),name:'保留修改',count:1,preview:[],members:[{id:id(1),name:'文稿',kind:'markdown',category:'scripts'}],revision:1};
  s.setResponder(async()=>group);await s.controller.open(group.id);
  let decide;s.setGuard(()=>new Promise(resolve=>{decide=resolve;}));
  const button=s.document.body.children[0].querySelector('.yx-group-dialog-body').querySelectorAll('[data-open-member]')[0];
  button.fire('click');assert.equal(s.document.body.children.length,0);assert.equal(s.controller.isOpen(),true);
  decide(false);await flush();assert.equal(s.opened.length,0);assert.equal(s.document.body.children.length,1);assert.equal(s.controller.isOpen(),true);
});

test('server errors are surfaced once and do not retry a stale grouping automatically',async()=>{
  const s=setup(),target=s.node({item:id(2)});s.root.append(target);s.setResponder(async()=>{throw Object.assign(new Error('部分素材已在其他组'),{status:409});});
  s.controller.beginDrag([id(1)]);s.fire('dragover',target);s.arm();s.fire('drop',target);await flush();
  assert.equal(s.calls.length,1);assert.equal(s.notices[0][0],'部分素材已在其他组');
});

test('host loadItems refresh is reused and standalone hosts still fetch one updated snapshot',async()=>{
  for(const hostRefreshesGroups of [false,true]) {
    const s=setup();
    if(hostRefreshesGroups) s.setRefresh(()=>s.controller.refresh());
    await s.controller.create([id(1),id(2)]);
    assert.equal(s.calls.filter(([url])=>url.startsWith('/api/resource-groups?')).length,1);
  }
});

test('host selection repaint reuses unchanged group DOM instead of recreating preview images',async()=>{
  const s=setup();s.setResponder(async()=>({groups:[{id:id(10),project_id:id(100),member_ids:[],preview:[],count:0}]}));
  await s.controller.refresh();const count=s.elements.length,first=s.root.firstChild;
  s.controller.render(s.root);assert.equal(s.elements.length,count);assert.equal(s.root.firstChild,first);
  s.root.append(s.node());const changed=s.elements.length;s.controller.render(s.root);assert.ok(s.elements.length>changed);
});
