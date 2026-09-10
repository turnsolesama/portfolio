'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

function setup(desktop = false, groups = false) {
  const listeners = new Map(), nodes = [], moves = [], uploads = [], messages = [], groupEvents = [];
  function node(dataset = {}) {
    const classes = new Set();
    const element = {dataset, classList:{add:(...names)=>names.forEach(n=>classes.add(n)), remove:(...names)=>names.forEach(n=>classes.delete(n)), contains:n=>classes.has(n)},
      hasAttribute:name=>name==='data-folder-drop' && 'folderDrop' in dataset,
      closest:selector=>selector==='[data-item]' && dataset.item ? element : selector==='[data-drag-file]' && dataset.dragFile ? element : selector==='[data-folder-drop],[data-category]' && ('folderDrop' in dataset || 'category' in dataset) ? element : null};
    nodes.push(element); return element;
  }
  const document = {body:node(), addEventListener:(type,fn)=>{const previous=listeners.get(type);listeners.set(type,previous ? e=>{previous(e);return fn(e);} : fn);}, querySelectorAll:()=>nodes};
  const hostListeners = new Map();
  const context = vm.createContext({document, window:{innerWidth:1000,innerHeight:600,yingxuDesktopDrag:desktop,chrome:{webview:{postMessage:m=>messages.push(m),addEventListener:(type,fn)=>hostListeners.set(type,fn)}}}, localStorage:{getItem:()=>null}, console, setTimeout, clearTimeout, moves, uploads});
  if (groups) context.window.YingXuResourceGroups = {install:() => ({beginDrag:ids=>groupEvents.push(['begin',...ids]),endDrag:()=>groupEvents.push(['end']),handleNativeDrop:()=>false})};
  const source = fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/, '');
  vm.runInContext(source+`\nhideMenu=()=>{}; performMove=async (...args)=>moves.push(args); uploadFiles=async (...args)=>uploads.push(args); report=error=>{throw error;}; globalThis.app={state,wireDragAndDrop,cardHtml,rowHtml};`,context);
  Object.assign(context.app.state,{projectId:'synthetic',section:'assets',category:'references',folderId:'current'});
  context.app.wireDragAndDrop();
  function transfer(files=[],data={}) {
    return {files, data:{...data}, get types(){return [...Object.keys(this.data),...(files.length?['Files']:[])];}, clearData(){this.data={};}, setData(k,v){this.data[k]=v;}, getData(k){return this.data[k]||'';}};
  }
  function fire(type,target,dataTransfer) { const e={type,target,dataTransfer,button:0,preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;}}; return {event:e,result:listeners.get(type)(e)}; }
  return {app:context.app,document,node,transfer,fire,moves,uploads,messages,hostListeners,groupEvents};
}

test('thumbnail drag with browser Files payload moves the selected resources without an import overlay',async()=>{
  const s=setup(), card=s.node({item:'a'}), category=s.node({category:'previs'});
  s.app.state.selectedIds.add('a');s.app.state.selectedIds.add('b');
  const transfer=s.transfer([{name:'thumbnail.png'}],{'text/uri-list':'http://localhost/thumbnail'});
  s.fire('dragstart',card,transfer);
  assert.equal(transfer.getData('text/uri-list'),'');assert.equal(transfer.effectAllowed,'move');
  s.fire('dragenter',category,transfer);s.fire('dragover',category,transfer);
  assert.equal(s.document.body.classList.contains('external-drag'),false);assert.equal(transfer.dropEffect,'move');
  assert.equal(category.classList.contains('drop-category'),true);
  await s.fire('drop',category,transfer).result;
  assert.deepEqual(JSON.parse(JSON.stringify(s.moves)),[[['a','b'],'previs',null]]);assert.equal(s.uploads.length,0);
  s.fire('dragend',card,transfer);assert.equal(card.classList.contains('dragging-card'),false);
  assert.equal(category.classList.contains('drop-category'),false);
});

test('internal resources drop into nested folders and category-root breadcrumbs',async()=>{
  for (const folder of ['nested','root']) {
    const s=setup(), transfer=s.transfer([],{'application/x-yingxu-item':'a'});
    const target=s.node({folderDrop:folder,folderCategory:'characters'});
    s.fire('dragover',target,transfer);assert.equal(transfer.dropEffect,'move');
    await s.fire('drop',target,transfer).result;
    assert.deepEqual(JSON.parse(JSON.stringify(s.moves)),[[['a'],'characters',folder==='root'?null:folder]]);
  }
});

test('invalid internal drop never becomes a file upload or browser navigation',async()=>{
  for (const dataset of [{},{category:'all'}]) {
    const s=setup(), target=s.node(dataset), transfer=s.transfer([{name:'thumbnail.png'}],{'application/x-yingxu-item':'a'});
    s.fire('dragover',target,transfer);assert.equal(transfer.dropEffect,'none');
    const drop=s.fire('drop',target,transfer);await drop.result;
    assert.equal(drop.event.prevented,true);assert.equal(s.moves.length,0);assert.equal(s.uploads.length,0);
  }
});

test('external files still show the copy overlay and import into the destination',async()=>{
  for (const dataset of [{},{category:'props'},{folderDrop:'nested',folderCategory:'characters'}]) {
    const s=setup(), target=s.node(dataset), transfer=s.transfer([{name:'external.png'}]);
    s.fire('dragenter',target,transfer);assert.equal(s.document.body.classList.contains('external-drag'),true);
    s.fire('dragover',target,transfer);assert.equal(transfer.dropEffect,'copy');
    await s.fire('drop',target,transfer).result;
    assert.equal(s.moves.length,0);assert.equal(s.uploads.length,1);
    assert.equal(s.uploads[0][1],dataset.folderCategory||dataset.category||'references');
    assert.equal(s.uploads[0][2],dataset.folderDrop||(dataset.category?null:'current'));
    assert.equal(s.document.body.classList.contains('external-drag'),false);
  }
});

test('external overlay and target highlight clear after leaving or cancelling a drag',()=>{
  const s=setup(), target=s.node({category:'props'}), transfer=s.transfer([{name:'external.png'}]);
  s.fire('dragenter',target,transfer);s.fire('dragover',target,transfer);s.fire('dragleave',target,transfer);
  assert.equal(s.document.body.classList.contains('external-drag'),false);assert.equal(target.classList.contains('drop-category'),false);
});

test('native drag-out handle still sends the desktop file request',()=>{
  const s=setup();s.fire('pointerdown',s.node({dragFile:'a'}));
  assert.deepEqual(JSON.parse(JSON.stringify(s.messages)),[{action:'drag-file',id:'a'}]);
});

test('desktop card enables grouping while dedicated drag-out handle cancels grouping and preserves file drag',()=>{
  const s=setup(true,true),card=s.node({item:'a'});
  s.fire('dragstart',card,s.transfer());
  assert.deepEqual(s.groupEvents,[['begin','a']]);
  s.hostListeners.get('message')({data:{action:'native-drag-ended'}});
  s.groupEvents.length=0;s.messages.length=0;
  s.fire('pointerdown',s.node({dragFile:'a'}));
  assert.deepEqual(s.groupEvents,[['end']]);
  assert.deepEqual(JSON.parse(JSON.stringify(s.messages)),[{action:'drag-files',ids:['a']}]);
});

test('card and list thumbnails defer dragging to their resource container',()=>{
  const s=setup();
  for (const kind of ['image','video']) for (const render of [s.app.cardHtml,s.app.rowHtml]) {
    const html=render({id:'a',kind,name:'Synthetic',category:'references'});
    assert.match(html,/draggable="true" data-item="a"/);
    const images=html.match(/<img\b[^>]*>/g);assert.ok(images.length);
    images.forEach(img=>assert.match(img,/draggable="false"/));
  }
});

test('direct desktop card drag sends real-file request for the whole selection and cancels HTML drag',()=>{
  const s=setup(true), card=s.node({item:'a'});
  s.app.state.selectedIds.add('a');s.app.state.selectedIds.add('b');
  const e=s.fire('dragstart',card,s.transfer());
  assert.equal(e.event.prevented,true);
  assert.deepEqual(JSON.parse(JSON.stringify(s.messages)),[{action:'drag-files',ids:['a','b']}]);
  s.fire('dragend',card,s.transfer());assert.equal(card.classList.contains('dragging-card'),true);
  s.hostListeners.get('message')({data:{action:'native-drag-ended'}});
  assert.equal(card.classList.contains('dragging-card'),false);
});

test('native Files dropped back inside the app move the captured selection without making copies',async()=>{
  const s=setup(true), card=s.node({item:'a'}), folder=s.node({folderDrop:'nested',folderCategory:'characters'});
  s.app.state.selectedIds.add('a');s.app.state.selectedIds.add('b');s.fire('dragstart',card,s.transfer());
  const native=s.transfer([{name:'a.png'},{name:'b.png'}]);
  s.fire('dragenter',folder,native);s.fire('dragover',folder,native);
  assert.equal(s.document.body.classList.contains('external-drag'),false);
  await s.fire('drop',folder,native).result;
  assert.deepEqual(JSON.parse(JSON.stringify(s.moves)),[[['a','b'],'characters','nested']]);assert.equal(s.uploads.length,0);
  s.hostListeners.get('message')({data:{action:'native-drag-ended'}});
  await s.fire('drop',folder,native).result;assert.equal(s.uploads.length,1);
});

test('host release fallback moves once using CSS-scaled target coordinates when WebView omits drop',()=>{
  const s=setup(true), card=s.node({item:'a'}), target=s.node({category:'props'});
  s.document.elementFromPoint=(x,y)=>{assert.equal(x,100);assert.equal(y,200);return target;};
  s.fire('dragstart',card,s.transfer());
  s.hostListeners.get('message')({data:{action:'native-drag-ended',released:true,inside:true,x:150,y:300,width:1500,height:900}});
  assert.deepEqual(JSON.parse(JSON.stringify(s.moves)),[[['a'],'props',null]]);assert.equal(s.uploads.length,0);
});
test('Escape and drops outside this window cannot trigger fallback moves',()=>{
  for (const result of [{released:false,inside:true},{released:true,inside:false}]) {
    const s=setup(true);s.document.elementFromPoint=()=>{throw Error('Must not hit-test another app or cancelled drag');};
    s.fire('dragstart',s.node({item:'a'}),s.transfer());s.hostListeners.get('message')({data:{action:'native-drag-ended',width:1,height:1,...result}});
    assert.equal(s.moves.length,0);assert.equal(s.uploads.length,0);
  }
});
test('hover and pointer down prepare selected files before starting Windows drag',()=>{
  const s=setup(true),card=s.node({item:'a'});s.app.state.selectedIds.add('a');s.app.state.selectedIds.add('b');
  s.fire('pointerover',card);s.fire('pointerover',card);s.fire('pointerdown',card);
  assert.deepEqual(JSON.parse(JSON.stringify(s.messages)),[{action:'prepare-drag-files',ids:['a','b']},{action:'prepare-drag-files',ids:['a','b']}]);
});
