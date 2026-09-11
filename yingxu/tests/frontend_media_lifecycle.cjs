'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm');
const {test}=require('node:test'),{execFile}=require('node:child_process'),{promisify}=require('node:util'),{pathToFileURL}=require('node:url');
const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');

function cleanupFixture(temporary) {
  const resolved=path.resolve(temporary);
  assert.ok(resolved.startsWith(path.resolve(os.tmpdir())+path.sep)&&path.basename(resolved).startsWith('yingxu-media-lifecycle-'));
  fs.rmSync(resolved,{recursive:true,force:true,maxRetries:10,retryDelay:100});
}
test('release pauses both media kinds and removes direct/nested sources even if one pause or load fails',()=>{
  const events=[];
  const media=[0,1].map(index=>({
    pause(){events.push(`pause${index}`);if(index===0)throw Error('synthetic');},
    removeAttribute(name){events.push(`remove${index}:${name}`);},
    querySelectorAll(){return [{removeAttribute:name=>events.push(`source${index}:${name}`)}];},
    load(){events.push(`load${index}`);if(index===0)throw Error('synthetic');}
  }));
  const context=vm.createContext({window:{},document:{querySelectorAll:()=>media},localStorage:{getItem:()=>null},setTimeout,clearTimeout});
  vm.runInContext(source+';stopPreviewMedia(true);',context);
  assert.deepEqual(events,['pause0','remove0:autoplay','remove0:src','source0:src','load0','pause1','remove1:autoplay','remove1:src','source1:src','load1']);
});
test('hide-only pause does not reload or clear sources and unknown native messages do not affect playback',async()=>{
  let pauses=0;
  const context=vm.createContext({window:{},document:{querySelectorAll:()=>[{pause(){pauses++;}}]},localStorage:{getItem:()=>null},setTimeout,clearTimeout});
  vm.runInContext(source+';globalThis.message=handleDesktopMessage;',context);
  await context.message({action:'unrelated'});assert.equal(pauses,0);
  await context.message({action:'pause-media'});assert.equal(pauses,1);
});

test('real Chromium releases closed/switched media and pauses native/page visibility transitions',async t=>{
  const browser=[process.env.YINGXU_TEST_BROWSER,'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(p=>p&&fs.existsSync(p));
  if(!browser){t.skip('Requires an existing Chromium browser; does not download');return;}
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'yingxu-media-lifecycle-'));
  t.after(()=>cleanupFixture(temporary));
  // A 30-second silent PCM fixture exercises actual media decode/play/pause.
  // Muting and silence ensure the test never makes sound on the user's desktop.
  const samples=8000*30,wav=Buffer.alloc(44+samples*2);
  wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(8000,24);wav.writeUInt32LE(16000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(samples*2,40);
  fs.writeFileSync(path.join(temporary,'silent.wav'),wav);
  fs.writeFileSync(path.join(temporary,'app.js'),source);
  const runner=`
  (async()=>{
    const results=[],check=(name,ok)=>{results.push({name,ok});if(!ok)throw new Error(name);};
    const tick=()=>new Promise(resolve=>setTimeout(resolve,50));
    const makeTab=(id,kind='audio')=>({key:'external:'+id,id,source:'external',item:{id,name:'合成媒体',kind,size:480044,media_url:'silent.wav'},mode:'preview',dirty:false,detailReady:true});
    const play=async node=>{node.muted=true;await node.play();check('synthetic media actually starts',!node.paused&&node.readyState>=2);};
    let persisted=0;persistDrafts=()=>{persisted++;};wireEvents();
    const tab=makeTab('first');state.tabs=[tab];state.activeKey=tab.key;renderWorkspace();
    let media=$('#editorContent audio');await play(media);media.currentTime=2;
    await handleDesktopMessage({action:'pause-media'});
    check('native tray-hide message pauses but retains source and time',media.paused&&media.getAttribute('src')==='silent.wav'&&media.currentTime>=2);
    await play(media);window.dispatchEvent(new Event('pagehide'));
    check('pagehide pauses and persists drafts without releasing source',media.paused&&media.hasAttribute('src')&&persisted>0);
    await play(media);Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));
    check('hidden visibility pauses current media',media.paused&&media.hasAttribute('src'));
    Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));
    check('becoming visible does not automatically resume playback',media.paused);
    await play(media);document.dispatchEvent(new Event('visibilitychange'));
    check('visible visibility event does not interrupt active playback',!media.paused);
    await closeTab(tab.key);await tick();
    check('closing final tab pauses and releases detached media',media.paused&&!media.hasAttribute('src')&&media.readyState===0&&media.networkState===0);
    check('closing final tab clears editor and hides workspace',!$('#editorContent').childElementCount&&$('#editor').hidden&&state.tabs.length===0);
    const videoTab=makeTab('video','video');state.tabs=[videoTab];state.activeKey=videoTab.key;renderWorkspace();
    const oldVideo=$('#editorContent video');let videoPauses=0;
    const nativeVideoPause=oldVideo.pause.bind(oldVideo);oldVideo.pause=()=>{videoPauses++;nativeVideoPause();};
    check('video fixture uses actual media element and source',oldVideo instanceof HTMLVideoElement&&oldVideo.getAttribute('src')==='silent.wav');
    const next=makeTab('next');state.tabs.push(next);state.activeKey=next.key;renderWorkspace();await tick();
    check('switching tab pauses and releases old video element',videoPauses===1&&oldVideo.paused&&!oldVideo.hasAttribute('src')&&oldVideo.readyState===0&&oldVideo.networkState===0);
    media=$('#editorContent audio');await play(media);next.loading=true;renderEditorBody(next);await tick();
    check('loading a replacement clears old audio',media.paused&&!media.hasAttribute('src')&&media.readyState===0&&!!$('#editorContent .editor-loading'));
    $('#editorContent').innerHTML='<audio autoplay><source src="silent.wav" type="audio/wav"></audio>';
    media=$('#editorContent audio');stopPreviewMedia(true);await tick();
    check('nested source and autoplay are released',media.paused&&!media.hasAttribute('autoplay')&&!media.querySelector('source').hasAttribute('src')&&media.readyState===0);
    stopPreviewMedia(true);check('repeated cleanup remains safe',media.paused);
    document.querySelector('#result').textContent=JSON.stringify(results);
  })().catch(error=>document.querySelector('#result').textContent=JSON.stringify({error:String(error),stack:error.stack}));`;
  fs.writeFileSync(path.join(temporary,'runner.js'),runner);
  const html=fs.readFileSync(path.join(__dirname,'../frontend/index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace(/<link\b[^>]*>/g,'').replace('</body>','<pre id="result"></pre><script src="app.js"></script><script src="runner.js"></script></body>');
  fs.writeFileSync(path.join(temporary,'fixture.html'),html);
  const {stdout}=await promisify(execFile)(browser,['--headless','--disable-gpu','--no-first-run','--disable-background-networking','--autoplay-policy=no-user-gesture-required','--mute-audio',`--user-data-dir=${path.join(temporary,'profile')}`,'--virtual-time-budget=15000','--dump-dom',pathToFileURL(path.join(temporary,'fixture.html')).href],{windowsHide:true,timeout:45000,maxBuffer:2*1024*1024});
  const match=stdout.match(/<pre id="result">([^<]+)<\/pre>/);assert.ok(match,stdout.slice(-2000));
  const result=JSON.parse(match[1].replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'));
  assert.ok(Array.isArray(result),JSON.stringify(result));assert.equal(result.length,17);for(const row of result)assert.equal(row.ok,true,row.name);
});
