'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function setup(failed=false) {
  const nodes=new Map(), requests=[], notices=[], errors=[];
  const node=key=>{if(!nodes.has(key))nodes.set(key,{});return nodes.get(key);};
  let finish;
  const job=new Promise(resolve=>finish=()=>resolve({errors:failed?['损坏的 ZIP']:[]}));
  class XHR {
    constructor(){this.upload={};}
    open(method,url){requests.push(url);}
    setRequestHeader(){}
    send(){this.status=201;this.responseText='{"job_id":"zip-job"}';queueMicrotask(()=>this.onload());}
  }
  const context=vm.createContext({window:{},document:{querySelector:node},localStorage:{getItem:()=>null},console,URLSearchParams,XMLHttpRequest:XHR,setTimeout,clearTimeout,job,notices,errors});
  const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
  vm.runInContext(source+'\nmonitorJob=()=>job;toast=m=>notices.push(m);report=e=>errors.push(e.message);refreshProjects=async()=>{};loadItems=async()=>{};globalThis.app={state,uploadFiles};',context);
  Object.assign(context.app.state,{projectId:'synthetic',bootstrap:{token:'fixture'}});
  return {app:context.app,finish,requests,notices,errors};
}
test('ZIP upload retains destination and remains busy until extraction finishes',async()=>{
  const s=setup(), task=s.app.uploadFiles([{name:'素材.zip'}],'characters','nested');
  await new Promise(resolve=>setImmediate(resolve));
  const url=new URL(s.requests[0],'http://localhost');
  assert.equal(url.searchParams.get('category'),'characters');assert.equal(url.searchParams.get('folder_id'),'nested');
  assert.equal(s.app.state.uploading,true);assert.equal(s.notices.length,0);
  s.finish();await task;assert.equal(s.app.state.uploading,false);assert.equal(s.notices.length,1);
});
test('failed ZIP extraction reports failure without a success toast',async()=>{
  const s=setup(true),task=s.app.uploadFiles([{name:'损坏.zip'}],'scripts');
  s.finish();await task;assert.deepEqual(s.errors,['损坏的 ZIP']);assert.equal(s.notices.length,0);assert.equal(s.app.state.uploading,false);
});
