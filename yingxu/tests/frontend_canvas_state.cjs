'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const trackerSource=fs.readFileSync(path.join(__dirname,'../tools/canvas-editor/scene-tracker.js'),'utf8');
const trackerModule=()=>import('data:text/javascript;base64,'+Buffer.from(trackerSource).toString('base64'));
test('hidden canvas cancels native animation work and resumes pending callbacks without losing cancellation',async()=>{
 const source=fs.readFileSync(path.join(__dirname,'../tools/canvas-editor/animation-gate.js'),'utf8');
 const {createAnimationGate}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
 let next=0;const queued=new Map(),calls=[];
 const gate=createAnimationGate(fn=>{const id=++next;queued.set(id,fn);return id;},id=>queued.delete(id));
 const first=gate.request(t=>calls.push(['first',t]));assert.equal(queued.size,1);
 gate.setActive(false);assert.equal(queued.size,0);const second=gate.request(t=>calls.push(['second',t]));assert.equal(queued.size,0);
 gate.cancel(first);gate.setActive(true);gate.setActive(true);assert.equal(queued.size,1);
 const [id,fn]=[...queued][0];queued.delete(id);fn(123);assert.deepEqual(calls,[['second',123]]);
 gate.cancel(second);assert.equal(queued.size,0);
 gate.setActive(false);const cancelled=gate.request(()=>calls.push(['bad']));gate.cancel(cancelled);gate.setActive(true);assert.equal(queued.size,0);
});
test('build adapter replaces the pinned remote font fallback with same-origin assets',async()=>{
 const {pathToFileURL}=require('node:url');
 const {localFontFallback}=await import(pathToFileURL(path.join(__dirname,'../tools/canvas-editor/font-url-plugin.mjs')).href);
 const source='class Font {static ASSETS_FALLBACK_URL = `https://esm.sh/${pkg.name?`${pkg.name}@${pkg.version}`:"@excalidraw/excalidraw"}/dist/prod/`;}';
 const result=localFontFallback(source);assert.equal(result.replacements,1);assert.ok(!result.contents.includes('esm.sh'));
 assert.ok(result.contents.includes('new URL("/canvas/",window.location.origin).href'));
 assert.equal(localFontFallback('class Changed {}').replacements,0);
});
test('view changes avoid scene/image serialization while real document edits are detected',async()=>{
 const {createSceneTracker}=await trackerModule(),t=createSceneTracker();
 const e=[{id:'one',version:1,versionNonce:10,isDeleted:false},{id:'two',version:1,versionNonce:20,isDeleted:false}];
 const files={image:{dataURL:'data:image/png;base64,'+'a'.repeat(1024*1024),mimeType:'image/png',created:1,toJSON(){throw Error('must not serialize image');}}};
 const s={viewBackgroundColor:'#fff',gridSize:20,gridStep:5,gridModeEnabled:false};t.changed(e,s,files);
 for(let i=0;i<200;i++)assert.equal(t.changed(e,{...s,scrollX:i,zoom:{value:i/100+1},selectedElementIds:{one:true}},files),false);
 e[0].version++;assert.equal(t.changed(e,s,files),true);assert.equal(t.changed(e,s,files),false);
 assert.equal(t.changed([...e].reverse(),s,files),true);
 assert.equal(t.changed([...e].reverse(),{...s,viewBackgroundColor:'#000'},files),true);
 files.image.dataURL='data:image/png;base64,other';assert.equal(t.changed([...e].reverse(),{...s,viewBackgroundColor:'#000'},files),true);
 delete files.image;assert.equal(t.changed([...e].reverse(),{...s,viewBackgroundColor:'#000'},files),true);
 t.reset();assert.equal(t.changed([],s,{}),false);
});
test('deletion, undelete and persisted grid controls are document changes',async()=>{
 const {createSceneTracker}=await trackerModule(),t=createSceneTracker(),e=[{id:'a',version:1,versionNonce:1}],s={gridSize:20,gridStep:5,gridModeEnabled:false};t.changed(e,s,{});
 e[0].isDeleted=true;assert.equal(t.changed(e,s,{}),true);e[0].isDeleted=false;assert.equal(t.changed(e,s,{}),true);
 for(const [key,value] of [['gridSize',10],['gridStep',3],['gridModeEnabled',true]]){s[key]=value;assert.equal(t.changed(e,s,{}),true);assert.equal(t.changed(e,s,{}),false);}
});
test('bridge mounts once, retains hidden iframe, flushes latest value and releases only on close',()=>{
 const handlers=new Set(),messages=[],changes=[];let append=0,removed=0,current='draft',composing=false;
 const frame={src:'',title:'',hidden:false,contentWindow:{postMessage:m=>messages.push(m),yingxuCanvas:{getValue:()=>current,isComposing:()=>composing,setActive(){}}},setAttribute(){},remove(){removed++;this.parentNode=null;}};
 const parent={appendChild(node){append++;node.parentNode=this;}};
 const context={window:{addEventListener:(_,fn)=>handlers.add(fn),removeEventListener:(_,fn)=>handlers.delete(fn)},document:{createElement:()=>frame},location:{origin:'http://127.0.0.1:54321'}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../frontend/canvas-bridge.js'),'utf8'),context);
 const api=context.window.YingXuCanvas.create({value:'initial',onChange:v=>changes.push(v),onError:()=>{},onSave:()=>{}});api.mount(parent);api.mount(parent);assert.equal(append,1);
 const receive=[...handlers][0];receive({origin:context.location.origin,source:frame.contentWindow,data:{type:'yingxu-canvas-ready'}});assert.equal(messages[0].value,'initial');
 api.setActive(false);assert.equal(frame.hidden,true);assert.equal(api.getValue(),'draft');api.setActive(true);assert.equal(frame.hidden,false);assert.equal(append,1);
 composing=true;assert.equal(api.isComposing(),true);composing=false;current='latest';assert.equal(api.getValue(),'latest');
 assert.throws(()=>api.mount({appendChild(){}}),/原显示容器/);
 receive({origin:'https://foreign.invalid',source:frame.contentWindow,data:{type:'yingxu-canvas-change',value:'bad'}});assert.deepEqual(changes,[]);
 api.destroy();api.destroy();assert.equal(removed,1);assert.equal(handlers.size,0);assert.equal(api.getValue(),'latest');assert.throws(()=>api.mount(parent),/已经关闭/);
});
