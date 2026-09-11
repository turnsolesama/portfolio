'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {test}=require('node:test');
const note='a'.repeat(32),project='b'.repeat(32),image='c'.repeat(32);
function setup(overrides={}){
 const c=vm.createContext({window:{},encodeURIComponent,decodeURIComponent});vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/capture.js'),'utf8'),c);
 const sent=[],notices=[],inserted=[],refreshed=[],queries=[];
 const options={api:async url=>{queries.push(url);return {markdown:'![截图](../reference/test.png)'};},getTarget:()=>({itemId:note,projectId:project,draft:'原文'}),insert:async(...args)=>{inserted.push(args);return true;},refresh:async id=>refreshed.push(id),toast:(...a)=>notices.push(a),send:(...a)=>sent.push(a)};
 Object.assign(options,overrides);const ui=c.window.YingXuCapture.install(options);return {ui,options,sent,notices,inserted,refreshed,queries,imageURL:c.window.YingXuCapture.imageURL};
}
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
test('capture stays busy while link, insert and refresh await and duplicate results cannot insert twice',async()=>{
 const link=deferred(),insertion=deferred(),refresh=deferred(),insertEntered=deferred(),refreshEntered=deferred();let links=0,inserts=0;
 const s=setup({api:()=>{links++;return link.promise;},insert:()=>{inserts++;insertEntered.resolve();return insertion.promise;},refresh:()=>{refreshEntered.resolve();return refresh.promise;}});
 await s.ui.handle({action:'capture-context-request',requestId:'delayed'});
 const result={action:'capture-result',requestId:'delayed',item:{id:image,project_id:project}};
 const first=s.ui.handle(result);assert.equal(s.ui.isBusy(),true);assert.equal(inserts,0);
 link.resolve({markdown:'![截图](a.png)'});await insertEntered.promise;
 assert.equal(inserts,1);assert.equal(s.ui.isBusy(),true);
 insertion.resolve(true);await refreshEntered.promise;assert.equal(s.ui.isBusy(),true);
 const duplicate=s.ui.handle(result);assert.equal(links,1);assert.equal(s.ui.isBusy(),true);
 refresh.resolve();await Promise.all([first,duplicate]);assert.equal(s.ui.isBusy(),false);assert.equal(inserts,1);
});
test('overlapping result processing remains busy until every refresh finishes',async()=>{
 const gates=[deferred(),deferred()];let calls=0;const s=setup({refresh:()=>gates[calls++].promise});
 const result=id=>({action:'capture-result',requestId:id,item:{id:image,project_id:project}});
 const first=s.ui.handle(result('old')),second=s.ui.handle(result('later'));assert.equal(s.ui.isBusy(),true);
 gates[0].resolve();await first;assert.equal(s.ui.isBusy(),true);
 gates[1].resolve();await second;assert.equal(s.ui.isBusy(),false);assert.equal(s.inserted.length,0);
});
test('failed refresh releases processing state after its rejection',async()=>{
 const gate=deferred(),s=setup({refresh:()=>gate.promise});const done=s.ui.handle({action:'capture-result',requestId:'failed',item:{id:image,project_id:project}});
 assert.equal(s.ui.isBusy(),true);gate.reject(new Error('合成刷新失败'));await assert.rejects(done,/合成刷新失败/);assert.equal(s.ui.isBusy(),false);
});
test('local image resolver rejects network, unsafe protocols, absolute paths and SVG',()=>{const s=setup();for(const url of ['https://example.test/a.png','//example.test/a.png','%2f%2fexample.test/a.png','file:///C:/a.png','../a.svg','../a.png?x=1','..\\a.png','data:image/png,x'])assert.equal(s.imageURL(note,url),null);assert.match(s.imageURL(note,'../截图%20a.png'),/^\/api\/markdown-assets\/image\?note=/);assert.equal(s.imageURL('bad','a.png'),null);});
test('capture context is locked and result inserts only in its project',async()=>{const s=setup();await s.ui.handle({action:'capture-context-request',requestId:'one'});assert.equal(s.sent[0][1].projectId,project);assert.equal(s.ui.isBusy(),true);await s.ui.handle({action:'capture-result',requestId:'one',item:{id:image,project_id:project},clipboardCopied:true});assert.equal(s.inserted.length,1);assert.equal(s.refreshed[0],project);assert.equal(s.ui.isBusy(),false);assert.match(s.notices[0][0],/插入笔记草稿/);});
test('late or unmatched results never insert into a later selected note',async()=>{const s=setup();await s.ui.handle({action:'capture-context-request',requestId:'first'});await s.ui.handle({action:'capture-context-request',requestId:'second'});await s.ui.handle({action:'capture-result',requestId:'first',item:{id:image,project_id:project},clipboardCopied:true});assert.equal(s.inserted.length,0);assert.equal(s.ui.isBusy(),true);await s.ui.handle({action:'capture-result',requestId:'second',cancelled:true});assert.equal(s.ui.isBusy(),false);});
test('cross-project result saves attachment without inserting',async()=>{const s=setup();await s.ui.handle({action:'capture-context-request',requestId:'x'});await s.ui.handle({action:'capture-result',requestId:'x',item:{id:image,project_id:'d'.repeat(32)},clipboardCopied:true});assert.equal(s.queries.length,0);assert.equal(s.inserted.length,0);});
test('clipboard and attachment failures are reported separately without fake insertion',async()=>{const s=setup();await s.ui.handle({action:'capture-context-request',requestId:'x'});await s.ui.handle({action:'capture-result',requestId:'x',item:null,clipboardCopied:true,saveError:'合成写入失败'});assert.equal(s.inserted.length,0);assert.ok(s.notices.some(n=>n[0].includes('图片已复制')));assert.ok(s.notices.some(n=>n[0].includes('合成写入失败')));});
test('a cancelled crop has no insertion, refresh or success message',async()=>{const s=setup();await s.ui.handle({action:'capture-context-request',requestId:'x'});await s.ui.handle({action:'capture-result',requestId:'x',cancelled:true});assert.equal(s.notices.length,0);assert.equal(s.refreshed.length,0);});
function appSetup(){const nodes=new Map(),ctx=vm.createContext({console,setTimeout,clearTimeout,document:{querySelector:k=>{if(!nodes.has(k))nodes.set(k,{value:'',open:false});return nodes.get(k);}},window:{},localStorage:{getItem:()=>null,setItem(){}}});vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'')+'\nglobalThis.app={state,captureTarget,insertCapture,inlineMarkdown,markdownImageURL};',ctx);return ctx.app;}
test('changed or closed note does not receive a late screenshot',async()=>{const a=appSetup(),calls=[];const t={key:'file:'+note,id:note,source:'file',item:{kind:'markdown',project_id:project},content:{editable:true},draft:'原文',mode:'live',markdownEditor:{isComposing:()=>false,getSelection:()=>({from:2,to:2}),insertText:(...args)=>{calls.push(args);return true;}}};Object.assign(a.state,{projectId:project,activeKey:t.key,tabs:[t]});const target=a.captureTarget();t.draft='用户又改了';assert.equal(await a.insertCapture(target,'![图](a.png)'),false);t.draft=target.draft;assert.equal(await a.insertCapture(target,'![图](a.png)'),true);assert.equal(calls[0][0],'\n![图](a.png)\n');a.state.tabs=[];assert.equal(await a.insertCapture(target,'![图](a.png)'),false);});
test('preview escapes labels and leaves image syntax inside code untouched',()=>{const a=appSetup();assert.match(a.inlineMarkdown('![<img>](../a.png)',()=>'/api/markdown-assets/image?note=x&path=a'),/alt="&lt;img&gt;"/);assert.doesNotMatch(a.inlineMarkdown('`![x](a.png)`',()=>'/image'),/<img/);assert.doesNotMatch(a.inlineMarkdown('![x](https://example.test/a.png)'),/<img/);});
test('switching to preview while screenshot uploads preserves the note without hidden insertion',async()=>{
 const a=appSetup(),calls=[];const t={key:'file:'+note,id:note,source:'file',item:{kind:'markdown',project_id:project},content:{editable:true},draft:'原有第一行\n正文',mode:'live',markdownEditor:{isComposing:()=>false,getSelection:()=>({from:9,to:9}),insertText:(...args)=>{calls.push(args);return true;}}};
 Object.assign(a.state,{projectId:project,activeKey:t.key,tabs:[t]});const target=a.captureTarget();t.mode='preview';
 assert.equal(await a.insertCapture(target,'![截图](a.png)'),false);assert.equal(calls.length,0);assert.equal(t.draft,'原有第一行\n正文');
});
test('capturing with the entire note selected appends an image without replacing selected Markdown',async()=>{
 const a=appSetup(),calls=[],original='# 已有标题\r\n原有正文';const t={key:'file:'+note,id:note,source:'file',item:{kind:'markdown',project_id:project},content:{editable:true},draft:original,mode:'live'};
 t.markdownEditor={isComposing:()=>false,getSelection:()=>({from:0,to:original.length}),insertText:(text,from,to)=>{calls.push({text,from,to});t.draft=t.draft.slice(0,from)+text+t.draft.slice(to);return true;}};
 Object.assign(a.state,{projectId:project,activeKey:t.key,tabs:[t]});const target=a.captureTarget();
 assert.equal(await a.insertCapture(target,'![截图](a.png)'),true);assert.equal(calls.length,1);assert.equal(calls[0].from,original.length);assert.equal(calls[0].to,original.length);assert.equal(t.draft,original+'\r\n![截图](a.png)\r\n');
});
