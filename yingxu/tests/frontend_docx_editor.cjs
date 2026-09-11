'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const{test}=require('node:test'),{execFile}=require('node:child_process'),{promisify}=require('node:util'),{pathToFileURL}=require('node:url');
test('Word bounded editor keeps page drafts, protects composition and limits layout work in real Chromium',async t=>{
 const browser=[process.env.YINGXU_TEST_BROWSER,'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(p=>p&&fs.existsSync(p));if(!browser){t.skip('Existing Chromium required; no download');return;}
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'yingxu-docx-editor-'));t.after(()=>{const root=path.resolve(temporary);assert.ok(root.startsWith(path.resolve(os.tmpdir())+path.sep)&&path.basename(root).startsWith('yingxu-docx-editor-'));fs.rmSync(root,{recursive:true,force:true,maxRetries:10,retryDelay:100});});
 for(const file of ['docx-editor.js','docx-editor.css','styles.css'])fs.copyFileSync(path.join(__dirname,'../frontend',file),path.join(temporary,file));
 fs.writeFileSync(path.join(temporary,'runner.js'),`(async()=>{
 const results=[],check=(name,ok)=>results.push({name,ok}),tick=()=>new Promise(r=>setTimeout(r,60));
 const paragraphs=Array.from({length:5000},(_,i)=>({id:'p'+i,text:'原段落 '+i,editable:true}));paragraphs[1]={id:'p1',text:'只读表格',editable:false,readonly_reason:'表格只读'};paragraphs[2].text='</textarea><img src=x onerror=alert(1)>';
 let changes=0,blocked=0;const parent=document.querySelector('#mount');const editor=YingXuDocxEditor.mount({parent,paragraphs,editable:true,onChange:()=>changes++,onBlocked:()=>blocked++});
 const field=n=>parent.querySelector('[data-docx-index="'+n+'"]');
 check('initial DOM has exactly forty controls',parent.querySelectorAll('textarea').length===40);
 check('malicious paragraph stays textarea text',field(2).value===paragraphs[2].text&&!parent.querySelector('img'));
 field(0).value='第一页草稿';field(0).dispatchEvent(new Event('input',{bubbles:true}));await tick();check('first-page input updates original paragraph',paragraphs[0].text==='第一页草稿'&&changes===1);
 field(1).value='不得修改';field(1).dispatchEvent(new Event('input',{bubbles:true}));check('readonly paragraph ignores injected input',paragraphs[1].text==='只读表格'&&changes===1);
 parent.querySelector('[data-docx-next]').click();check('next page keeps bounded controls and absolute number',parent.querySelectorAll('textarea').length===40&&!!field(40)&&field(40).getAttribute('aria-label')==='第 41 段');
 field(40).value='第二页草稿';field(40).dispatchEvent(new Event('input',{bubbles:true}));parent.querySelector('[data-docx-prev]').click();check('round-trip page keeps unsaved edits across all pages',field(0).value==='第一页草稿'&&paragraphs[40].text==='第二页草稿');
 field(0).dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));field(0).value='中文输入中';field(0).dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true}));
 check('composition disables navigation and blocks programmatic page switch',editor.isComposing()&&parent.querySelector('[data-docx-next]').disabled&&editor.goTo(2)===false&&blocked===1&&!!field(0));
 field(0).dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));check('composition commits draft and restores navigation',!editor.isComposing()&&!parent.querySelector('[data-docx-next]').disabled&&paragraphs[0].text==='中文输入中');
 parent.querySelector('[data-docx-page-input]').value='125';parent.querySelector('[data-docx-go]').click();check('jump to final page renders final original paragraph',!!field(4999)&&editor.getPage()===124&&parent.querySelector('[data-docx-next]').disabled);
 editor.goTo(9999);check('out of range page clamps',editor.getPage()===124&&parent.querySelectorAll('textarea').length===40);
 const before=changes,old=field(4999);old.value='pending';old.dispatchEvent(new Event('input',{bubbles:true}));editor.destroy();old.value='destroyed';old.dispatchEvent(new Event('input',{bubbles:true}));await tick();check('destroy removes listeners and queued resize',paragraphs[4999].text==='pending'&&changes===before+1);
 const short=YingXuDocxEditor.mount({parent,paragraphs:paragraphs.slice(0,41),editable:true,page:1});check('restored page index renders only remainder',short.getPage()===1&&parent.querySelectorAll('textarea').length===1&&!!field(40));short.destroy();
 const empty=YingXuDocxEditor.mount({parent,paragraphs:[],editable:true});check('empty document has no control and no enabled page navigation',parent.querySelectorAll('textarea').length===0&&parent.querySelector('[data-docx-prev]').disabled&&parent.querySelector('[data-docx-next]').disabled);empty.destroy();
 document.querySelector('#result').textContent=JSON.stringify(results);
 })().catch(error=>document.querySelector('#result').textContent=JSON.stringify({error:String(error),stack:error.stack}));`);
 fs.writeFileSync(path.join(temporary,'fixture.html'),'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="docx-editor.css"><style>body{display:block}.docx-editor{width:750px;height:800px}</style><div class="docx-editor"><div id="mount"></div></div><pre id="result"></pre><script src="docx-editor.js"></script><script src="runner.js"></script>');
 const{stdout}=await promisify(execFile)(browser,['--headless','--disable-gpu','--no-first-run','--disable-background-networking',`--user-data-dir=${path.join(temporary,'profile')}`,'--virtual-time-budget=4000','--dump-dom',pathToFileURL(path.join(temporary,'fixture.html')).href],{windowsHide:true,timeout:30000,maxBuffer:2*1024*1024});
 const match=stdout.match(/<pre id="result">([^<]+)<\/pre>/);assert.ok(match,stdout.slice(-1500));const result=JSON.parse(match[1].replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'));assert.ok(Array.isArray(result),JSON.stringify(result));assert.equal(result.length,13);for(const row of result)assert.equal(row.ok,true,row.name);
});
