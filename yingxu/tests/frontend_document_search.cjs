'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {test}=require('node:test'),{execFile}=require('node:child_process'),{promisify}=require('node:util'),{pathToFileURL}=require('node:url');
const {findMatches,MAX_MATCHES,MAX_CHARACTERS}=require('../frontend/document-search.js');
const {render}=require('../frontend/docx-preview.js');
test('literal Chinese and punctuation search preserves original UTF16 offsets',()=>{
 const r=findMatches([{id:'one',text:'😀雨夜\r\n雨夜 [a+b]'}],'雨夜');assert.deepEqual(r.matches.map(m=>[m.segmentId,m.from,m.to]),[['one',2,4],['one',6,8]]);assert.equal(findMatches([{text:'[a+b]'}],'[a+b]').matches.length,1);
});
test('case-insensitive matching does not shift Unicode source offsets',()=>{
 const text='İıſKABC abc';const r=findMatches([{text}],'abc');assert.deepEqual(r.matches.map(m=>text.slice(m.from,m.to)),['ABC','abc']);assert.deepEqual(r.matches.map(m=>m.from),[4,8]);
});
test('segments remain independently addressable including all Word pages',()=>{
 const segments=Array.from({length:5000},(_,i)=>({id:'p'+i,text:i===4999?'最后命中':'原段落'}));const r=findMatches(segments,'命中');assert.deepEqual(r.matches,[{segmentId:'p4999',segmentIndex:4999,from:2,to:4}]);
});
test('current draft text is used without touching stale runs or mutating segments',()=>{
 const segments=[{id:'p',text:'当前草稿',runs:[{text:'原始正文'}]}],before=JSON.stringify(segments);assert.equal(findMatches(segments,'草稿').matches.length,1);assert.equal(findMatches(segments,'原始').matches.length,0);assert.equal(JSON.stringify(segments),before);
});
test('empty and missing queries have zero results',()=>{for(const q of ['',null,'不存在'])assert.equal(findMatches([{text:'正文'}],q).matches.length,0);assert.equal(findMatches([], '正文').matches.length,0);});
test('many matches and excessive documents are bounded and explicitly marked',()=>{
 const many=findMatches([{text:'a'.repeat(MAX_MATCHES+10)}],'a');assert.equal(many.matches.length,MAX_MATCHES);assert.equal(many.limited,true);
 const large=findMatches([{text:'x'.repeat(MAX_CHARACTERS)},{text:'outside'}],'outside');assert.equal(large.scanned,MAX_CHARACTERS);assert.equal(large.limited,true);assert.equal(large.matches.length,0);
});
test('Word preview renders only forty paragraphs and keeps later-page drafts',()=>{
 const p=Array.from({length:5000},(_,i)=>({id:'p'+i,text:'paragraph-'+i}));p[4999].text='最后未保存草稿';const first=render({},p),last=render({},p,{page:124});assert.equal((first.match(/data-docx-preview-index/g)||[]).length,40);assert.ok(!first.includes('paragraph-40<'));assert.ok(last.includes('最后未保存草稿'));assert.ok(!last.includes('paragraph-0<'));
});
test('large tables do not mount all rows or empty columns when showing one slice',()=>{
 const p=Array.from({length:3000},(_,i)=>({id:'p'+i,text:'t'+i})),blocks=[{kind:'table',rows:[p.map(v=>({blocks:[{kind:'paragraph',id:v.id}]}))]}];const html=render({blocks},p,{page:30});assert.equal((html.match(/data-docx-preview-index/g)||[]).length,40);assert.ok((html.match(/<td /g)||[]).length<=42);assert.ok(html.includes('t1200'));assert.ok(!html.includes('>t2000<'));
});
test('real Chromium search navigates drafts across Word pages, highlights and closes without edits',async t=>{
 const browser=[process.env.YINGXU_TEST_BROWSER,'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(p=>p&&fs.existsSync(p));if(!browser){t.skip('Existing Chromium required; no download');return;}
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'yingxu-document-search-'));t.after(()=>{const root=path.resolve(temporary);assert.ok(root.startsWith(path.resolve(os.tmpdir())+path.sep)&&path.basename(root).startsWith('yingxu-document-search-'));fs.rmSync(root,{recursive:true,force:true,maxRetries:10,retryDelay:100});});
 for(const file of ['document-search.js','document-search.css','docx-editor.js','docx-editor.css','docx-preview.js'])fs.copyFileSync(path.join(__dirname,'../frontend',file),path.join(temporary,file));
 fs.writeFileSync(path.join(temporary,'runner.js'),`(async()=>{
 const checks=[],check=(name,ok)=>checks.push({name,ok}),tick=()=>new Promise(r=>setTimeout(r,140)),parent=document.querySelector('#editor');
 const paragraphs=Array.from({length:5000},(_,i)=>({id:'p'+i,text:'普通段落 '+i}));paragraphs[0].text='草稿雨夜';paragraphs[42].text='跨页雨夜';paragraphs[4999].text='结尾雨夜';let key='doc',writes=0;
 const editor=YingXuDocxEditor.mount({parent,paragraphs,editable:true,onChange:()=>writes++});
 const search=YingXuDocumentSearch.install({parent:document.querySelector('#search'),getDocument:()=>({key,segments:paragraphs}),onReveal:(m,opts)=>editor.revealMatch(m,opts),onClear:()=>editor.clearSearch()});
 search.open('雨夜');await tick();check('finds all current draft paragraphs across pages',search.getState().count===3&&search.getState().active===0);check('first match highlighted',!!parent.querySelector('.docx-search-current'));
 search.next();await tick();const second=parent.querySelector('[data-docx-index="42"]');check('next navigates cross-page and selects the exact text',editor.getPage()===1&&second.selectionStart===2&&second.selectionEnd===4&&parent.querySelectorAll('textarea').length===40);
 search.previous();search.previous();await tick();check('previous wraps to final paragraph',editor.getPage()===124&&!!parent.querySelector('[data-docx-index="4999"]'));
 const input=search.element.querySelector('input');input.value='不存在';input.dispatchEvent(new Event('input',{bubbles:true}));await tick();check('zero results clear highlight and disable navigation',search.getState().count===0&&!parent.querySelector('.docx-search-current')&&search.element.querySelector('[data-document-next]').disabled);
 editor.goTo(0);const field=parent.querySelector('[data-docx-index="0"]');field.value='修改后的鹤鸣';field.dispatchEvent(new Event('input',{bubbles:true}));input.value='鹤鸣';input.dispatchEvent(new Event('input',{bubbles:true}));await tick();check('edited draft becomes searchable without saving',search.getState().count===1&&paragraphs[0].text==='修改后的鹤鸣'&&writes===1);
 input.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));input.value='雨夜';input.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true}));await tick();check('IME input does not jump before composition commits',search.getState().count===1);input.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));await tick();check('IME committed query searches normally',search.getState().count===2);
 input.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));check('Escape closes and clears highlights',!search.isOpen()&&!parent.querySelector('.docx-search-current'));
 search.open('雨夜');key='other';search.refresh();await tick();check('changing document key cancels old document search',!search.isOpen());search.destroy();editor.destroy();
 const before=JSON.stringify(paragraphs);const preview=YingXuDocx.mount({parent,content:{},paragraphs});check('preview mounts at most forty paragraphs',parent.querySelectorAll('[data-docx-preview-index]').length===40);preview.revealMatch({segmentIndex:4999,from:2,to:4});check('preview jumps to final page without creating editable controls',preview.getPage()===124&&!!parent.querySelector('[data-docx-preview-index="4999"]')&&!parent.querySelector('textarea'));check('preview match is highlighted',!!parent.querySelector('.docx-search-current')&&(!CSS.highlights||CSS.highlights.has('yingxu-document-match')));preview.clearSearch();check('clearing preview removes highlight',!parent.querySelector('.docx-search-current'));preview.destroy();check('search and preview never mutate content',JSON.stringify(paragraphs)===before&&writes===1);
 document.querySelector('#result').textContent=JSON.stringify(checks);
 })().catch(error=>document.querySelector('#result').textContent=JSON.stringify({error:String(error),stack:error.stack}));`);
 fs.writeFileSync(path.join(temporary,'fixture.html'),'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="document-search.css"><link rel="stylesheet" href="docx-editor.css"><div id="search"></div><div id="editor" style="height:500px;overflow:auto"></div><pre id="result"></pre><script src="document-search.js"></script><script src="docx-editor.js"></script><script src="docx-preview.js"></script><script src="runner.js"></script>');
 const {stdout}=await promisify(execFile)(browser,['--headless','--disable-gpu','--no-first-run','--disable-background-networking',`--user-data-dir=${path.join(temporary,'profile')}`,'--virtual-time-budget=7000','--dump-dom',pathToFileURL(path.join(temporary,'fixture.html')).href],{windowsHide:true,timeout:30000,maxBuffer:2*1024*1024});
 const match=stdout.match(/<pre id="result">([^<]+)<\/pre>/);assert.ok(match,stdout.slice(-1500));const result=JSON.parse(match[1].replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'));assert.ok(Array.isArray(result),JSON.stringify(result));assert.equal(result.length,15);for(const row of result)assert.equal(row.ok,true,row.name);
});
