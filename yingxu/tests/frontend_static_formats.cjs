'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {test}=require('node:test'),{execFile}=require('node:child_process'),{promisify}=require('node:util'),{pathToFileURL}=require('node:url');

test('real browser SVG image and isolated HTML/source views remain read-only',async t=>{
  const browser=[process.env.YINGXU_TEST_BROWSER,'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(p=>p&&fs.existsSync(p));
  if(!browser){t.skip('Existing Chromium required; no download');return;}
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'yingxu-static-preview-'));
  t.after(()=>{const resolved=path.resolve(temporary);assert.ok(resolved.startsWith(path.resolve(os.tmpdir())+path.sep)&&path.basename(resolved).startsWith('yingxu-static-preview-'));fs.rmSync(resolved,{recursive:true,force:true,maxRetries:10,retryDelay:100});});
  const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
  fs.writeFileSync(path.join(temporary,'app.js'),source);
  fs.copyFileSync(path.join(__dirname,'../frontend/html-preview.js'),path.join(temporary,'html-preview.js'));
  const runner=`(async()=>{
    const checks=[],check=(name,ok)=>checks.push({name,ok});window.STATIC_EXECUTED=0;
    const svg='<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="green"/></svg>';
    const tab={key:'static',source:'file',item:{id:'fixture',name:'Vector',kind:'svg'},content:{editable:false,preview_url:'data:image/svg+xml;base64,'+btoa(svg)},mode:'preview',draft:''};
    state.tabs=[tab];state.activeKey=tab.key;renderEditorBody(tab);renderEditorToolbar(tab);
    const image=document.querySelector('#mainImage');await image.decode();
    check('SVG decodes through image element',image.naturalWidth===200&&image.naturalHeight===100);
    check('SVG is not inline DOM or active document',!document.querySelector('#editorContent svg,#editorContent object,#editorContent iframe'));
    check('SVG has zoom and no save',!!document.querySelector('[data-action="zoom-in"]')&&!document.querySelector('#saveContentButton'));
    tab.item.kind='html';tab.item.name='HTML';tab.content={editable:false,content:'<h1>Original source</h1><script>bad()</script>',preview_html:'<h1>Safe title</h1><table><tr><td>Cell</td></tr></table><script>top.STATIC_EXECUTED=1</script>',notice:'Static'};
    renderEditorBody(tab);renderEditorToolbar(tab);
    const frame=document.querySelector('iframe');
    check('HTML iframe grants no sandbox capability',frame.hasAttribute('sandbox')&&frame.getAttribute('sandbox')==='');
    check('HTML has restrictive content policy',frame.srcdoc.includes("default-src 'none'")&&frame.srcdoc.includes("form-action 'none'"));
    await new Promise(resolve=>setTimeout(resolve,150));
    check('Defence in depth prevents script access to host',window.STATIC_EXECUTED===0&&frame.contentDocument===null);
    check('HTML uses explicit preview/source controls',document.querySelector('[aria-label="HTML 视图"]').textContent.includes('查看源码')&&!document.querySelector('#saveContentButton'));
    tab.mode='edit';renderEditorBody(tab);const editor=document.querySelector('#htmlSource');
    check('Source is literal and read-only',editor.readOnly&&editor.value===tab.content.content&&!document.querySelector('#editorContent iframe'));
    check('No document script executes on source display',window.STATIC_EXECUTED===0);
    document.getElementById('result').textContent=JSON.stringify(checks);
  })().catch(error=>document.getElementById('result').textContent=JSON.stringify({error:String(error),stack:error.stack}));`;
  fs.writeFileSync(path.join(temporary,'runner.js'),runner);
  fs.writeFileSync(path.join(temporary,'fixture.html'),'<!doctype html><meta charset="utf-8"><div id="editorToolbar"></div><div id="editorContent"></div><pre id="result"></pre><script src="html-preview.js"></script><script src="app.js"></script><script src="runner.js"></script>');
  const {stdout}=await promisify(execFile)(browser,['--headless','--disable-gpu','--no-first-run','--disable-background-networking',`--user-data-dir=${path.join(temporary,'profile')}`,'--virtual-time-budget=3000','--dump-dom',pathToFileURL(path.join(temporary,'fixture.html')).href],{windowsHide:true,timeout:30000,maxBuffer:3*1024*1024});
  const match=stdout.match(/<pre id="result">([^<]+)<\/pre>/);assert.ok(match,stdout.slice(-1600));
  const rows=JSON.parse(match[1].replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'));
  assert.ok(Array.isArray(rows),JSON.stringify(rows));assert.equal(rows.length,9);for(const row of rows)assert.equal(row.ok,true,row.name);
});
