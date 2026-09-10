'use strict';
const fs=require('fs'),path=require('path'),os=require('os'),http=require('http'),net=require('net'),assert=require('assert/strict');
const {spawnSync}=require('child_process');
const supplied=process.argv[2];if(!supplied||!path.isAbsolute(supplied)||!fs.existsSync(supplied))throw Error('Pass an installed test core source');
const data=fs.mkdtempSync(path.join(os.tmpdir(),'FlowSwitch-Lifecycle-'));process.env.PROXY_SWITCH_DATA_DIR=data;
const core=path.join(data,'FlowSwitch-TestEngine.exe');fs.copyFileSync(supplied,core);
const r=require('./IndependentRouter.cjs');let checks=0;const sockets=new Set(),servers=[];
const delay=ms=>new Promise(x=>setTimeout(x,ms));
function check(v,label){assert.ok(v,label);checks++;console.log('PASS: '+label);}
async function until(fn,label,timeout=22000){const end=Date.now()+timeout;while(Date.now()<end){try{if(await fn()){check(true,label);return;}}catch{}await delay(100);}throw Error('Timed out: '+label);}
const get=p=>JSON.parse(fs.readFileSync(path.join(r.ROOT,p),'utf8'));
async function server(marker){const s=http.createServer((q,res)=>res.end(marker));s.on('connect',(q,c)=>{c.write('HTTP/1.1 200 Connection Established\r\n\r\n');c.once('data',()=>c.end('HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\n'+marker));});s.on('connection',c=>{sockets.add(c);c.on('close',()=>sockets.delete(c));});await new Promise(done=>s.listen(0,'127.0.0.1',done));servers.push(s);return s;}
function request(port,url){return new Promise((resolve,reject)=>{const q=http.get({host:'127.0.0.1',port,path:url,headers:{Host:new URL(url).host},timeout:1500},s=>{let b='';s.on('data',x=>b+=x);s.on('end',()=>s.statusCode===200?resolve(b):reject(Error('http')));});q.on('error',reject);q.on('timeout',()=>q.destroy(Error('timeout')));});}
async function stop(){fs.mkdirSync(r.ROOT,{recursive:true});await r.main({action:'stop'});await until(()=>!fs.existsSync(path.join(r.ROOT,'supervisor.lock')),'supervisor exits on explicit stop',16000);}
async function main(){
 const a=await server('A'),b=await server('B');const reserver=net.createServer();await new Promise(done=>reserver.listen(0,'127.0.0.1',done));const port=reserver.address().port;await new Promise(done=>reserver.close(done));
 const url='http://127.0.0.1:'+b.address().port+'/fixture';process.env.PROXY_SWITCH_TEST_HEALTH_URL=url;
 const o={Version:3,Profiles:[{Id:'gateway',Name:'entry',Protocol:'http',Host:'127.0.0.1',Port:port,CorePath:core},{Id:'a',Name:'A',Protocol:'http',Host:'127.0.0.1',Port:a.address().port},{Id:'b',Name:'B',Protocol:'http',Host:'127.0.0.1',Port:b.address().port}],Routing:{Adapter:'standalone',ProfileId:'gateway',UnifiedMode:'gateway',Failover:{Enabled:true,Order:['a','b'],AllowDirect:false}}};
 fs.writeFileSync(path.join(data,'config.json'),JSON.stringify(o));fs.writeFileSync(path.join(data,'app-rules.json'),JSON.stringify({version:2,installed:true,entries:[],defaultRoute:'a'}));
 await assert.rejects(request(port,url));check(true,'application before service sees closed entry, not authentication failure');
 fs.mkdirSync(r.ROOT,{recursive:true});fs.writeFileSync(path.join(r.ROOT,'supervisor.lock'),JSON.stringify({pid:process.pid,startTicks:'1',token:'reused-pid-fixture'}));
 fs.writeFileSync(path.join(r.ROOT,'stop'),'prior-session-stop');
 await r.start();await until(async()=>await request(port,url)==='A','initial entry forwards');
 check(get('process.json').supervisor!==process.pid,'stale singleton with a reused PID cannot block a fresh supervisor');
 check(get('process.json').coreStartTicks===await r.processStartTicks(get('process.json').core),'core journal records exact operating-system process creation ticks');
 const firstSupervisor=get('process.json').supervisor;
 await r.main({action:'stop'});await r.start();await delay(2500);
 check((await r.status()).available&&get('process.json').supervisor!==firstSupervisor,'immediate start waits for pending stop and creates a new supervised entry');
 fs.writeFileSync(path.join(r.ROOT,'mutation.lock'),JSON.stringify({pid:process.pid,startTicks:'1',token:'abandoned-update-fixture'}));
 for(const c of sockets)c.destroy();await new Promise(done=>a.close(done));
 await until(async()=>await request(port,url)==='B','upstream outage switches to B');
 await until(()=>!fs.existsSync(path.join(r.ROOT,'mutation.lock')),'automatic failover reclaims an abandoned rule mutation lock');
 await until(()=>get('health.json').policies.a?.current==='b','backup is journaled');
 const supervisor=get('process.json').supervisor;
 for(let attempt=1;attempt<=3;attempt++){
  const previous=get('process.json').core;process.kill(previous);
  await until(()=>{const life=get('lifecycle-state.json');return life.phase==='ready'&&life.attempt===attempt&&life.core!==previous;},'real core crash recovers attempt '+attempt);
  check(get('process.json').supervisor===supervisor,'supervisor identity survives restart '+attempt);
  check(await request(port,url)==='B','cached entry reconnects through retained B '+attempt);
 }
 const stateBefore=fs.readFileSync(path.join(data,'app-rules.json'),'utf8').replace(/^\uFEFF/,'');
 const digest=text=>require('node:crypto').createHash('sha256').update(text).digest('hex');
 const replaced=await r.main({action:'replace',entries:[{path:'C:\\FlowSwitch-Unrelated-Test.exe',route:'Direct'}],defaultRoute:'a',expectedStateHash:digest(stateBefore)});check(await request(port,url)==='B','unrelated rule reload retains active backup');
 check(replaced.stateHash===digest(fs.readFileSync(path.join(data,'app-rules.json'),'utf8').replace(/^\uFEFF/,'')),'successful independent repair returns the exact state hash for guarded compensation');
 const shared=await r.replace([{path:'C:\\FlowSwitch-Old-Version.exe',route:'a'}],'a',replaced.stateHash);
 check(await request(port,url)==='B','adding a program to the active default policy preserves the shared backup');
 const migrated=await r.replace([{path:'C:\\FlowSwitch-New-Version.exe',route:'a'}],'a',shared.stateHash);
 check(await request(port,url)==='B'&&/^[a-f0-9]{64}$/.test(migrated.stateHash),'repairing a versioned program path preserves the actual shared exit');
 process.kill(get('process.json').core);await until(()=>get('lifecycle-state.json').phase==='failed'&&get('lifecycle-state.json').reason==='restart-limit','fourth crash reaches finite restart limit');
 await until(()=>!fs.existsSync(path.join(r.ROOT,'supervisor.lock')),'failed supervisor exits for watchdog restoration');
 await delay(3500);check(get('lifecycle-state.json').attempt===3,'no unbounded restart after exhaustion');
 const events=fs.readFileSync(path.join(r.ROOT,'lifecycle-core.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
 check(events.filter(e=>e.event==='restart-attempt').map(e=>e.delayMs).join(',')==='1000,2000,4000','backoff is 1, 2, 4 seconds');
 check(events.some(e=>e.event==='core-exit'&&Number.isInteger(e.exitCode)),'actual core exit code logged');
 await stop();
 const occupied=net.createServer(c=>c.destroy());await new Promise(done=>occupied.listen(port,'127.0.0.1',done));servers.push(occupied);
 await assert.rejects(r.start(),/占用/);check(true,'occupied entry rejected without adopting foreign listener');check(!(await r.status()).available,'open TCP port alone never reports managed core healthy');await new Promise(done=>occupied.close(done));
 await r.start();const cancelledCore=get('process.json').core;process.kill(cancelledCore);
 await until(()=>get('lifecycle-state.json').phase==='restarting','core enters recovery before user stop');
 await stop();await delay(1500);
 check(get('lifecycle-state.json').phase==='stopped'&&get('process.json').core===cancelledCore,'user stop during recovery cancels the delayed restart');
 const cs=path.join(data,'Bad.cs'),bad=path.join(data,'Bad-TestCore.exe');fs.writeFileSync(cs,'using System;class Bad{static int Main(){Console.Error.WriteLine("token=TEST_SECRET https://private.invalid/login C:\\\\private");return 9;}}');
 const build=spawnSync(path.join(process.env.SystemRoot,'Microsoft.NET/Framework64/v4.0.30319/csc.exe'),['/nologo','/target:exe','/out:'+bad,cs],{windowsHide:true,encoding:'utf8'});assert.equal(build.status,0,build.stdout+build.stderr);
 o.Profiles[0].CorePath=bad;fs.writeFileSync(path.join(data,'config.json'),JSON.stringify(o));await assert.rejects(r.start(),/启动失败/);check(true,'non-ready core startup fails without applying Windows settings');
 await until(()=>!fs.existsSync(path.join(r.ROOT,'supervisor.lock')),'failed startup leaves no supervisor');
 const logs=fs.readFileSync(path.join(r.ROOT,'lifecycle-core.jsonl'),'utf8');check(logs.includes('"exitCode":9'),'failed startup exit code retained');check(!/TEST_SECRET|private\.invalid|C:\\private|\/fixture/.test(logs),'raw core output, credentials and URLs excluded');
 for(let i=0;i<4000;i++)r.lifecycleEvent('rotation-test',{reason:'bounded'});
 check(fs.statSync(path.join(r.ROOT,'lifecycle-core.jsonl')).size<263000&&fs.statSync(path.join(r.ROOT,'lifecycle-core.jsonl.1')).size<263000,'lifecycle logs have bounded rotation');
 check(!fs.existsSync(path.join(data,'gateway-session.json')),'tests never create a real Windows proxy session');
 console.log('PASS: '+checks+' lifecycle real-core checks. Isolated data: '+data);
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;}).finally(async()=>{try{await stop();}catch{}for(const c of sockets)c.destroy();for(const s of servers)if(s.listening)s.close();});
