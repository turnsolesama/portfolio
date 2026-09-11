'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {test}=require('node:test'),{execFile}=require('node:child_process'),{promisify}=require('node:util'),{pathToFileURL}=require('node:url');
const {render}=require('../frontend/docx-preview.js');
const p=(id,text,extra={})=>({id,text,...extra});
const paragraph=id=>({kind:'paragraph',id});
const cell=(id,extra={})=>({colspan:1,vmerge:'',blocks:[paragraph(id)],...extra});

test('text, image descriptions, and unsupported block messages are escaped',()=>{
  const malicious='<img src=x onerror=alert(1)>';
  const html=render({blocks:[paragraph('p'),{kind:'unsupported',text:malicious}]},[p('p',malicious,{images:[{src:'https://example.invalid/a.png',reason:malicious,alt:'" onerror="bad'}]})]);
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(html.includes('&quot; onerror=&quot;bad'));
});
test('run formatting is restricted to known safe CSS values',()=>{
  const html=render({},[p('p','安全',{alignment:'right;position:fixed',heading_level:2,runs:[{text:'安全',bold:true,italic:true,underline:true,color:'#996633',font_size:18}]})]);
  assert.ok(html.includes('<h2'));
  assert.ok(html.includes('text-align:left'));
  assert.ok(html.includes('font-weight:700;font-style:italic;text-decoration:underline;color:#996633;font-size:18pt'));
  const rejected=render({},[p('p','x',{runs:[{text:'x',color:'red;background:url(http://bad)',font_size:10000}]})]);
  assert.ok(!rejected.includes('background'));
  assert.ok(!rejected.includes('font-size'));
});
test('image source allowlist blocks links, SVG, quoted payloads and data HTML',()=>{
  for(const src of ['https://invalid.example/a.png','file:///C:/secret.png','javascript:alert(1)','data:image/svg+xml;base64,PHN2Zz4=','data:text/html;base64,eA==','data:image/png;base64,eA==" onerror="bad']){
    assert.ok(!render({},[p('p','',{images:[{src}]})]).includes('<img'),src);
  }
  assert.ok(render({},[p('p','',{images:[{src:'data:image/png;base64,eA==',alt:'合成'}]})]).includes('<img'));
});
test('preview follows current edited text rather than old formatted runs',()=>{
  const html=render({blocks:[paragraph('p')]},[p('p','新文字',{runs:[{text:'旧文字',bold:true}]})]);
  assert.ok(html.includes('新文字'));assert.ok(!html.includes('旧文字'));
});
test('table horizontal and vertical merges retain remaining cells',()=>{
  const blocks=[{kind:'table',rows:[[cell('a',{colspan:2,vmerge:'restart'}),cell('b')],[cell('empty',{colspan:2,vmerge:'continue'}),cell('c')]]}];
  const html=render({blocks},[p('a','A'),p('b','B'),p('c','C'),p('empty','')]);
  assert.ok(html.includes('colspan="2" rowspan="2"'));
  assert.equal((html.match(/<td /g)||[]).length,3);
  assert.ok(html.includes('>C</span>'));
});
test('orphan vertical continuation does not silently discard content',()=>{
  const html=render({blocks:[{kind:'table',rows:[[cell('a',{vmerge:'continue'})],[cell('b',{vmerge:'continue'})]]}]},[p('a','A'),p('b','B')]);
  assert.ok(html.includes('>A</span>'));assert.ok(html.includes('>B</span>'));
});
test('nested tables, empty paragraphs and unsupported blocks remain explicit',()=>{
  const inner={kind:'table',rows:[[cell('p')]]};
  const html=render({blocks:[{kind:'table',rows:[[{blocks:[inner],colspan:1}]]},{kind:'unsupported',text:'浮动图形'}]},[p('p','')]);
  assert.equal((html.match(/<table /g)||[]).length,2);assert.ok(html.includes('class="docx-preview-paragraph"'));assert.ok(html.includes('浮动图形'));
  let deep=paragraph('p');for(let i=0;i<20;i++)deep={kind:'table',rows:[[{blocks:[deep]}]]};
  assert.ok(render({blocks:[deep]},[p('p','')]).includes('表格嵌套较深'));
});
test('real Chromium confines wide tables and embedded images in narrow preview',async t=>{
  const browser=[process.env.YINGXU_TEST_BROWSER,'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(value=>value&&fs.existsSync(value));
  if(!browser){t.skip('Requires existing Chromium; no download');return;}
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'yingxu-docx-preview-'));
  t.after(()=>{const resolved=path.resolve(temporary);assert.ok(resolved.startsWith(path.resolve(os.tmpdir())+path.sep)&&path.basename(resolved).startsWith('yingxu-docx-preview-'));fs.rmSync(resolved,{recursive:true,force:true,maxRetries:10,retryDelay:100});});
  fs.copyFileSync(path.join(__dirname,'../frontend/docx-preview.js'),path.join(temporary,'preview.js'));
  fs.copyFileSync(path.join(__dirname,'../frontend/styles.css'),path.join(temporary,'styles.css'));
  const runner=`(async()=>{
    const checks=[],check=(name,ok)=>checks.push({name,ok});
    const canvas=document.createElement('canvas');canvas.width=2400;canvas.height=800;canvas.getContext('2d').fillRect(0,0,2400,800);
    const paragraphs=[{id:'title',text:'合成标题',heading_level:1},{id:'image',text:'',images:[{src:canvas.toDataURL('image/png'),alt:'合成图片'}]}];
    const row=[];for(let i=0;i<12;i++){paragraphs.push({id:'c'+i,text:'栏目'+i+' '+('abcdefgh'.repeat(10))});row.push({colspan:1,blocks:[{kind:'paragraph',id:'c'+i}]});}
    document.getElementById('fixture').innerHTML=YingXuDocx.render({blocks:[{kind:'paragraph',id:'title'},{kind:'paragraph',id:'image'},{kind:'table',rows:[row]}]},paragraphs);
    const img=document.querySelector('.docx-image');await img.decode();
    const article=document.querySelector('.docx-preview'),table=document.querySelector('.docx-table-wrap');
    check('heading semantics',!!article.querySelector('h1'));
    check('decoded embedded image',img.naturalWidth===2400);
    check('image fits narrow preview',img.getBoundingClientRect().width<=article.clientWidth);
    check('wide table has own scroll',table.scrollWidth>table.clientWidth&&getComputedStyle(table).overflowX==='auto');
    check('article does not overflow outer viewport',article.scrollWidth<=article.clientWidth+1);
    check('all table cells retained',table.querySelectorAll('td').length===12);
    document.getElementById('result').textContent=JSON.stringify(checks);
  })().catch(error=>document.getElementById('result').textContent=JSON.stringify({error:String(error),stack:error.stack}));`;
  fs.writeFileSync(path.join(temporary,'runner.js'),runner);
  fs.writeFileSync(path.join(temporary,'fixture.html'),'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="styles.css"><style>body{display:block;overflow:auto}#fixture{width:340px;height:auto}</style><div id="fixture"></div><pre id="result"></pre><script src="preview.js"></script><script src="runner.js"></script>');
  const {stdout}=await promisify(execFile)(browser,['--headless','--disable-gpu','--no-first-run','--disable-background-networking',`--user-data-dir=${path.join(temporary,'profile')}`,'--virtual-time-budget=3000','--dump-dom',pathToFileURL(path.join(temporary,'fixture.html')).href],{windowsHide:true,timeout:30000,maxBuffer:2*1024*1024});
  const match=stdout.match(/<pre id="result">([^<]+)<\/pre>/);assert.ok(match,stdout.slice(-1500));
  const results=JSON.parse(match[1].replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'));
  assert.ok(Array.isArray(results),JSON.stringify(results));assert.equal(results.length,6);for(const row of results)assert.equal(row.ok,true,row.name);
});
