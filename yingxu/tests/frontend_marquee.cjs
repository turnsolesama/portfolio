'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {test}=require('node:test');
class Events {
 constructor(){this.events=new Map();}
 addEventListener(type,fn){const entries=this.events.get(type)||[];entries.push(fn);this.events.set(type,entries);}
 removeEventListener(type,fn){this.events.set(type,(this.events.get(type)||[]).filter(value=>value!==fn));}
 emit(type,values={}){const event={button:0,pointerType:'mouse',pointerId:1,clientX:180,clientY:180,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...values};for(const fn of this.events.get(type)||[]){fn(event);if(event.stopped)break;}return event;}
}
function setup({base=[],reduced=false,scrollHeight=200}={}){
 const win=new Events(),doc=new Events(),viewport=new Events(),frames=new Map(),boxes=[];let seq=0,scrollTop=0,context='page1',selected=new Set(base),changes=0,starts=0,enabled=true;
 win.requestAnimationFrame=fn=>{frames.set(++seq,fn);return seq;};win.cancelAnimationFrame=id=>frames.delete(id);win.matchMedia=()=>({matches:reduced});
 doc.defaultView=win;doc.body={append:box=>boxes.push(box)};doc.createElement=()=>({style:{},setAttribute(){},remove(){this.removed=true;}});
 Object.assign(viewport,{ownerDocument:doc,clientLeft:0,clientTop:0,clientWidth:200,clientHeight:200,scrollLeft:0,classList:{add(){},remove(){}},getBoundingClientRect:()=>({left:0,top:0,right:200,bottom:200}),contains:node=>!node.detached,closest:()=>null,setPointerCapture:id=>viewport.capture=id,hasPointerCapture:id=>viewport.capture===id,releasePointerCapture:()=>viewport.capture=null});
 Object.defineProperty(viewport,'scrollTop',{get:()=>scrollTop,set:value=>scrollTop=Math.max(0,Math.min(scrollHeight-200,value))});
 const make=(id,left,top,right,bottom,hidden=false)=>({dataset:{item:id},hidden,hasAttribute:()=>hidden,getClientRects:()=>hidden?[]:[{}],getBoundingClientRect:()=>({left,top:top-scrollTop,right,bottom:bottom-scrollTop})});
 const nodes=[make('a',10,10,80,70),make('b',100,10,170,70),make('hidden',10,90,170,140,true)];
 const sandbox=vm.createContext({window:win});vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/marquee.js'),'utf8'),sandbox);
 const controller=win.YingXuMarquee.install({viewport,getItems:()=>nodes,getSelection:()=>selected,onChange:ids=>{selected=new Set(ids);changes++;},onStart:()=>starts++,enabled:()=>enabled,getContext:()=>context});
 const emit=(type,values={})=>viewport.emit(type,{target:viewport,...values});
 const tick=()=>{const current=[...frames.values()];frames.clear();current.forEach(fn=>fn());};
 return {win,doc,viewport,frames,boxes,nodes,controller,emit,tick,selected:()=>[...selected].sort(),changes:()=>changes,starts:()=>starts,setContext:value=>context=value,disable:()=>enabled=false};
}
test('dragging upward from blank space below cards selects touched cards and excludes hidden group members',()=>{
 const s=setup();assert.equal(s.frames.size,0);s.emit('pointerdown');s.emit('pointermove',{clientX:5,clientY:5});assert.equal(s.frames.size,1);s.tick();assert.deepEqual(s.selected(),['a','b']);s.emit('pointerup',{clientX:5,clientY:5});assert.equal(s.frames.size,0);assert.equal(s.boxes[0].removed,true);
 const click=s.emit('click');assert.equal(click.prevented,true);assert.equal(click.stopped,true);
});
test('Ctrl toggles hits against the initial selection while Shift adds without repeated toggling',()=>{
 const ctrl=setup({base:['a']});ctrl.emit('pointerdown',{ctrlKey:true});ctrl.emit('pointermove',{clientX:5,clientY:5});ctrl.tick();assert.deepEqual(ctrl.selected(),['b']);ctrl.emit('pointermove',{clientX:6,clientY:5});ctrl.tick();assert.deepEqual(ctrl.selected(),['b']);assert.equal(ctrl.changes(),1);
 const shift=setup({base:['a']});shift.emit('pointerdown',{shiftKey:true});shift.emit('pointermove',{clientX:90,clientY:5});shift.tick();assert.deepEqual(shift.selected(),['a','b']);
});
test('Escape and pointercancel restore the initial selection and stop scheduled work',()=>{
 for(const cancel of ['Escape','pointercancel']){const s=setup({base:['a']});s.emit('pointerdown');s.emit('pointermove',{clientX:90,clientY:5});s.tick();assert.deepEqual(s.selected(),['b']);if(cancel==='Escape')assert.equal(s.doc.emit('keydown',{key:'Escape'}).prevented,true);else s.emit(cancel);assert.deepEqual(s.selected(),['a']);assert.equal(s.frames.size,0);}
});
test('card controls, editable content, touch, right button and scrollbar never start a marquee',()=>{
 for(const options of [{target:{closest:()=>({})}},{pointerType:'touch'},{button:2},{clientX:201}]){const s=setup();const down=s.emit('pointerdown',options);s.emit('pointermove',{clientX:5,clientY:5});assert.equal(down.prevented,undefined);assert.equal(s.frames.size,0);assert.equal(s.boxes.length,0);}
});
test('plain blank clicks clear full or partial selection without opening a drag rectangle',()=>{
 for(const base of [['a'],['a','b']]) { const s=setup({base});s.emit('pointerdown');s.emit('pointermove',{clientX:182,clientY:181});s.emit('pointerup',{clientX:182,clientY:181});assert.deepEqual(s.selected(),[]);assert.equal(s.boxes.length,0);assert.equal(s.emit('click').stopped,undefined); }
});

test('modified blank clicks, cancellation and stale context preserve selection',()=>{
 for(const options of [{ctrlKey:true},{metaKey:true},{shiftKey:true}]) { const s=setup({base:['a','b']});s.emit('pointerdown',options);s.emit('pointerup');assert.deepEqual(s.selected(),['a','b']); }
 for(const action of [s=>s.emit('pointercancel'),s=>s.disable(),s=>s.setContext('page2')]) { const s=setup({base:['a','b']});s.emit('pointerdown');action(s);s.emit('pointerup');assert.deepEqual(s.selected(),['a','b']); }
});
test('pointer move events share one frame and unchanged selection does not call update again',()=>{
 const s=setup();s.emit('pointerdown');for(let i=0;i<50;i++)s.emit('pointermove',{clientX:5,clientY:5});assert.equal(s.frames.size,1);s.tick();assert.equal(s.changes(),1);s.emit('pointermove',{clientX:6,clientY:5});s.tick();assert.equal(s.changes(),1);s.controller.cancel();assert.equal(s.frames.size,0);
});
test('rectangle is clipped to the resource viewport even when pointer leaves it',()=>{
 const s=setup();s.emit('pointerdown');s.emit('pointermove',{clientX:-50,clientY:-100});s.tick();assert.deepEqual({...s.boxes[0].style},{left:'0px',top:'0px',width:'180px',height:'180px'});
});
test('edge scrolling runs only while dragging and stops at cancel; reduced motion uses manual scrolling',()=>{
 const s=setup({scrollHeight:600});s.emit('pointerdown',{clientX:190,clientY:100});s.emit('pointermove',{clientX:190,clientY:199});s.tick();assert.equal(s.viewport.scrollTop,12);assert.equal(s.frames.size,1);s.controller.cancel();assert.equal(s.frames.size,0);
 const r=setup({scrollHeight:600,reduced:true});r.emit('pointerdown',{clientX:190,clientY:100});r.emit('pointermove',{clientX:190,clientY:199});r.tick();assert.equal(r.viewport.scrollTop,0);assert.equal(r.frames.size,0);
});
test('navigation or replaced cards abort the gesture without restoring stale page selection',()=>{
 const s=setup({base:['a']});s.emit('pointerdown');s.setContext('page2');s.emit('pointermove',{clientX:90,clientY:5});s.tick();assert.equal(s.changes(),0);assert.equal(s.frames.size,0);
 const r=setup();r.emit('pointerdown');r.nodes[0].detached=true;r.emit('pointermove',{clientX:5,clientY:5});r.tick();assert.equal(r.changes(),0);
});
test('disabled views and destroyed handlers never select resources',()=>{
 const s=setup();s.disable();s.emit('pointerdown');s.emit('pointermove',{clientX:5,clientY:5});assert.equal(s.frames.size,0);s.controller.destroy();assert.equal([...s.viewport.events.values()].flat().length,0);assert.equal([...s.doc.events.values()].flat().length,0);
});
test('app integration is restricted to assets and routes changes through updateSelection',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8');const region=source.slice(source.indexOf('function installResourceMarquee()'),source.indexOf('function wireEvents()'));
 assert.match(region,/state\.section === 'assets'/);assert.match(region,/!state\.loadingItems/);assert.match(region,/onStart:hideMenu/);assert.match(region,/state\.selectedIds = new Set\(ids\); updateSelection\(\)/);assert.doesNotMatch(region,/openItem|insertText|selectionStart/);
 const html=fs.readFileSync(path.join(__dirname,'../frontend/index.html'),'utf8');assert.ok(html.indexOf('/marquee.js')<html.indexOf('/app.js'));assert.match(html,/\/marquee\.css/);
});
test('start callback hides the old menu only after a valid blank drag crosses the threshold',()=>{
 const s=setup();s.emit('pointerdown',{target:{closest:()=>({})}});s.emit('pointermove',{clientX:5,clientY:5});assert.equal(s.starts(),0);
 s.emit('pointerdown');s.emit('pointermove',{clientX:181,clientY:181});assert.equal(s.starts(),0);s.emit('pointermove',{clientX:5,clientY:5});assert.equal(s.starts(),1);s.emit('pointermove',{clientX:6,clientY:5});assert.equal(s.starts(),1);s.controller.cancel();
});
