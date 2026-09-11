'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {test}=require('node:test'),{execFile}=require('node:child_process'),{promisify}=require('node:util'),{pathToFileURL}=require('node:url');
test('real Chromium reports image size, follows fit resize, and disconnects observers',async t=>{
  // The fixed WebView2 runtime requires an embedding host; it is not an Edge CLI.
  const browser=[process.env.YINGXU_TEST_BROWSER,'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(p=>p&&fs.existsSync(p));
  if(!browser){t.skip('Requires an existing Chromium browser; does not download');return;}
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'yingxu-image-zoom-'));
  t.after(()=>{const resolved=path.resolve(temporary);assert.ok(resolved.startsWith(path.resolve(os.tmpdir())+path.sep)&&path.basename(resolved).startsWith('yingxu-image-zoom-'));fs.rmSync(resolved,{recursive:true,force:true,maxRetries:10,retryDelay:100});});
  const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
  const runner=`
    (async()=>{
      const results=[],check=(name,ok)=>results.push({name,ok}),tick=()=>new Promise(r=>setTimeout(r,80));
      const tab={key:'zoom-fixture',item:{id:'fixture',kind:'image',name:'合成图片'},source:'file'};
      state.tabs=[tab];state.activeKey=tab.key;
      const img=document.querySelector('#mainImage');
      await img.decode();trackImageZoom(tab,img);updateImageZoomLabel(img);
      const label=()=>document.querySelector('#imageZoomPercent').textContent;
      check('fit uses rendered width and natural dimensions',label()==='图片 50%');
      changeImageZoom('zoom-in');check('plus starts at current fit percentage',label()==='图片 63%');
      changeImageZoom('zoom-out');check('minus reverses plus',label()==='图片 50%');
      for(let i=0;i<20;i++)changeImageZoom('zoom-in');check('upper limit reports 400%',label()==='图片 400%');
      for(let i=0;i<30;i++)changeImageZoom('zoom-out');check('lower limit reports 25%',label()==='图片 25%');
      changeImageZoom('zoom-fit');check('fit returns to actual 50%',label()==='图片 50%'&&!img.classList.contains('zoomed'));
      document.querySelector('.media-stage').style.width='250px';await tick();updateImageZoomLabel(img);check('narrow fit reports 25%',label()==='图片 25%');
      document.querySelector('.media-stage').style.height='50px';await tick();updateImageZoomLabel(img);check('height constraint accounts for object fit',label()==='图片 10%');
      stopImageZoomTracking();check('observer is released',imageZoomObserver===null);
      const before=label();state.activeKey='different';img.dispatchEvent(new Event('load'));check('stale image cannot update another tab',label()===before);
      img.removeAttribute('src');await tick();updateImageZoomLabel(img);check('unloaded image does not invent 100%',label()==='图片 —');
      document.querySelector('#result').textContent=JSON.stringify(results);
    })().catch(error=>document.querySelector('#result').textContent=JSON.stringify({error:String(error),stack:error.stack}));`;
  fs.writeFileSync(path.join(temporary,'app.js'),source);
  fs.writeFileSync(path.join(temporary,'runner.js'),runner);
  const svg=encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="500"><rect width="1000" height="500" fill="green"/></svg>');
  fs.writeFileSync(path.join(temporary,'fixture.html'),`<!doctype html><meta charset="utf-8"><style>.media-stage{display:flex;align-items:center;justify-content:center;width:500px;height:300px;overflow:auto}.media-stage>img{max-width:100%;max-height:100%;object-fit:contain;flex:none}.media-stage>img.zoomed{max-width:none;max-height:none}</style><span id="imageZoomPercent"></span><div class="media-stage"><img id="mainImage" src="data:image/svg+xml,${svg}"></div><pre id="result"></pre><script src="app.js"></script><script src="runner.js"></script>`);
  const {stdout}=await promisify(execFile)(browser,['--headless','--disable-gpu','--no-first-run','--disable-background-networking',`--user-data-dir=${path.join(temporary,'profile')}`,'--virtual-time-budget=3000','--dump-dom',pathToFileURL(path.join(temporary,'fixture.html')).href],{windowsHide:true,timeout:30000,maxBuffer:2*1024*1024});
  const match=stdout.match(/<pre id="result">([^<]+)<\/pre>/);assert.ok(match,stdout.slice(-1500));
  const result=JSON.parse(match[1].replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'));
  assert.ok(Array.isArray(result),JSON.stringify(result));assert.equal(result.length,11);for(const row of result)assert.equal(row.ok,true,row.name);
});
