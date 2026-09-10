'use strict';
// FlowSwitch owns this core and its loopback controller. No subscriptions are copied.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),http=require('node:http'),net=require('node:net');
const {spawn,spawnSync,execFile}=require('node:child_process');
const systemCurl=path.join(process.env.SystemRoot||'C:\\Windows','System32','curl.exe');
const systemPowerShell=path.join(process.env.SystemRoot||'C:\\Windows','System32','WindowsPowerShell','v1.0','powershell.exe');
const yaml=require('./vendor/js-yaml');
const DATA=process.env.PROXY_SWITCH_DATA_DIR||path.join(process.env.USERPROFILE,'.proxyswitch');
const ROOT=path.join(DATA,'gateway'),STATE=path.join(DATA,'app-rules.json'),CONFIG=path.join(ROOT,'runtime.yaml');
const PIPE='\\\\.\\pipe\\FlowSwitch-'+crypto.createHash('sha256').update(path.resolve(DATA).toLowerCase()).digest('hex').slice(0,20);
const read=p=>{try{return fs.readFileSync(p,'utf8').replace(/^\uFEFF/,'');}catch(e){if(e.code==='ENOENT')return null;throw e;}};
const json=(p,fallback)=>{const s=read(p);return s===null?fallback:JSON.parse(s);};
function write(p,value){fs.mkdirSync(path.dirname(p),{recursive:true});const t=p+'.'+crypto.randomUUID()+'.tmp';fs.writeFileSync(t,typeof value==='string'?value:JSON.stringify(value,null,2));fs.renameSync(t,p);}
const options=()=>require('./AppRouter.cjs').normalizeOptions(json(path.join(DATA,'config.json'),{}));
const state=()=>json(STATE,{version:2,installed:false,entries:[],defaultRoute:null});
const group=id=>id==='Direct'?'PSW-App-Direct':'PSW-App-route-'+id;
const upstream=id=>'FS-Up-'+id;
function api(method,endpoint,value){return new Promise((resolve,reject)=>{
 const body=value===undefined?'':JSON.stringify(value);
 const req=http.request({socketPath:PIPE,path:endpoint,method,headers:{'Content-Type':'application/json','Content-Length':Buffer.byteLength(body)}},res=>{
  let text='';res.on('data',c=>{text+=c;if(text.length>8*1024*1024)req.destroy(Error('Controller response too large'));});
  res.on('end',()=>{if(res.statusCode<200||res.statusCode>=300)return reject(Error('Controller HTTP '+res.statusCode));try{resolve(text?JSON.parse(text):null);}catch(e){reject(e);}});
 });req.setTimeout(5000,()=>req.destroy(Error('Controller timeout')));req.on('error',reject);req.end(body);
});}
function policy(o){const raw=o.Routing.Failover||{};const ids=o.Profiles.filter(p=>p.Id!==o.Routing.ProfileId).map(p=>p.Id);
 const order=[...new Set([...(raw.Order||[]),...ids])].filter(id=>ids.includes(id));
 return {Enabled:raw.Enabled!==false,Order:order,AllowDirect:raw.AllowDirect===true,Failures:3,IntervalMs:2000,CooldownMs:30000};
}
function candidates(preferred,o){const p=policy(o);if(preferred==='Direct')return ['Direct'];if(!p.Order.includes(preferred))throw Error('目标不是可用上游');return [...new Set([preferred,...(p.Enabled?p.Order:[]),...(p.Enabled&&p.AllowDirect?['Direct']:[])])];}
function validate(entries,defaultRoute,o){
 const seen=new Set(),guard=o.Profiles.flatMap(p=>[p.CorePath,p.AppPath]).filter(Boolean).map(p=>path.win32.normalize(p).toLowerCase());
 for(const raw of entries){const e=require('./AppRouter.cjs').normalizeEntry(raw.path,raw.route,o);if(e.route==='Follow'||seen.has(e.path.toLowerCase())||guard.includes(e.path.toLowerCase()))throw Error('无效或重复的程序规则');seen.add(e.path.toLowerCase());candidates(e.route,o);}
 if(defaultRoute)candidates(defaultRoute,o);
}
function makeConfig(o,s,selections={}){validate(s.entries,s.defaultRoute,o);const entrance=o.Profiles.find(p=>p.Id===o.Routing.ProfileId);if(!entrance)throw Error('缺少独立入口');
 const used=[...new Set([...s.entries.map(e=>e.route),s.defaultRoute].filter(Boolean))];
 const proxies=o.Profiles.filter(p=>p.Id!==entrance.Id).map(p=>({name:upstream(p.Id),type:p.Protocol,server:p.Host,port:p.Port}));
 proxies.push({name:group('Direct'),type:'direct'});
 const groups=used.filter(id=>id!=='Direct').map(id=>{const list=[...candidates(id,o).map(x=>x==='Direct'?group(x):upstream(x)),'REJECT'];const selected=selections[group(id)];return {name:group(id),type:'select',proxies:list.includes(selected)?[selected,...list.filter(x=>x!==selected)]:list};});
 return {'mixed-port':entrance.Port,'bind-address':'127.0.0.1','allow-lan':false,'external-controller-pipe':PIPE,mode:'rule',ipv6:false,'log-level':'warning','find-process-mode':'always',profile:{'store-selected':false},dns:{enable:false},tun:{enable:false},proxies,'proxy-groups':groups,rules:[...s.entries.map(e=>'PROCESS-PATH,'+path.win32.normalize(e.path)+','+group(e.route)),'MATCH,'+(s.defaultRoute?group(s.defaultRoute):'REJECT')]};
}
function actualRoute(chains,o){for(const c of chains){const p=o.Profiles.find(p=>c===upstream(p.Id));if(p)return p.Id;if(c===group('Direct')||c==='DIRECT')return 'Direct';if(c==='REJECT'||c==='REJECT-DROP')return 'Blocked';}return 'Unknown';}
function decide(previous,list,health,now,settings,details={}){
 const old=previous||{current:list[0],failures:0,changed:0};const okay=id=>id==='Direct'||health[id]===true;
 // Keep a recovered backup until it fails; recovery never forces another reconnect.
 if(okay(old.current))return {...old,failures:0};
 // An unavailable tester/controller is not evidence that the user's proxy failed.
 if(old.current!=='Blocked'&&health[old.current]!==false)return {...old,failures:0};
 const failures=old.failures+1;
 const offline=details[old.current]?.reason==='listener-closed';
 const next=list.find(okay)||'Blocked';
 if((!offline||next==='Blocked')&&failures<settings.Failures&&old.current!=='Blocked')return {...old,failures};
 if(next==='Blocked'&&list.some(id=>id!=='Direct'&&health[id]!==false))return {...old,failures};
 if(!offline&&next!==old.current&&old.current!=='Blocked'&&now-old.changed<settings.CooldownMs&&failures<settings.Failures+1)return {...old,failures};
 return {current:next,failures:0,changed:next===old.current?old.changed:now};
}
async function healthCheck(id,o){const p=o.Profiles.find(p=>p.Id===id);if(!p)return {healthy:null,reason:'profile-missing'};
 if(['127.0.0.1','localhost','::1'].includes(p.Host)&&!await listening(p.Host,p.Port)){
  await new Promise(r=>setTimeout(r,200));
  if(!await listening(p.Host,p.Port))return {healthy:false,reason:'listener-closed'};
 }
 const urls=process.env.PROXY_SWITCH_TEST_HEALTH_URL?[process.env.PROXY_SWITCH_TEST_HEALTH_URL]:['https://www.gstatic.com/generate_204','https://www.msftconnecttest.com/connecttest.txt'];
 const host=p.Host.includes(':')?'['+p.Host+']':p.Host;
 const endpoint=(p.Protocol==='socks5'?'socks5h':'http')+'://'+host+':'+p.Port;
 const r=await Promise.all(urls.map(url=>new Promise(resolve=>{
  // CONNECT also checks HTTP proxy tunnel support, as used by the owned core.
  execFile(fs.existsSync(systemCurl)?systemCurl:'curl.exe',['--silent','--output','NUL','--write-out','%{http_code}','--connect-timeout','3','--max-time','6','--noproxy','','--proxy',endpoint,...(p.Protocol==='http'?['--proxytunnel']:[]),url],{windowsHide:true,timeout:7000,maxBuffer:1024},(error,out)=>resolve({healthy:!error&&/^(200|204)$/.test(out.trim()),unavailable:!!error&&typeof error.code!=='number',timeout:error?.code===28}));
 })));
 if(r.some(x=>x.healthy))return {healthy:true,reason:'probe-ok'};
 if(r.some(x=>x.unavailable))return {healthy:null,reason:'probe-unavailable'};
 return {healthy:false,reason:r.every(x=>x.timeout)?'probe-timeout':'probe-failed'};
}
function retainedSelections(o,old,next,proxies){
 // A group is shared by every program choosing the same policy. Adding a
 // program or repairing its EXE path must not reset everybody's active backup.
 const reset=new Set();
 if(next.defaultRoute!==old.defaultRoute)reset.add(next.defaultRoute);
 return Object.fromEntries([...new Set([...next.entries.map(e=>e.route),next.defaultRoute])].filter(id=>id&&id!=='Direct'&&!reset.has(id)).map(id=>[group(id),proxies[group(id)]?.now]));
}
function resumeSelections(o,s,health,now=Date.now()){
 const updated=Date.parse(health.updated);const changed=Date.parse(s.changedAt||0);
 if(!Number.isFinite(updated)||now-updated>120000||updated>now||!Number.isFinite(changed)||changed>updated)return {};
 const result={};for(const id of [...new Set([...s.entries.map(e=>e.route),s.defaultRoute])].filter(id=>id&&id!=='Direct')){
  const current=health.policies?.[id]?.current;
  if(candidates(id,o).includes(current)&&(current==='Direct'||health.health?.[current]===true))result[group(id)]=current==='Direct'?group(current):upstream(current);
 }return result;
}
function recordEvent(event){const file=path.join(ROOT,'failover-events.json');const events=json(file,[]);events.push({id:crypto.randomUUID(),at:new Date().toISOString(),...event});write(file,events.slice(-100));}
function listening(host,port){return new Promise(resolve=>{const s=net.connect({host,port});let done=false;const end=b=>{if(!done){done=true;s.destroy();resolve(b);}};s.setTimeout(400,()=>end(false));s.on('connect',()=>end(true));s.on('error',()=>end(false));});}
function processStartTicks(pid){return new Promise(resolve=>{
 if(!Number.isSafeInteger(pid)||pid<=0)return resolve(null);
 execFile(systemPowerShell,['-NoProfile','-NonInteractive','-Command',"$ErrorActionPreference='Stop';$p=[Diagnostics.Process]::GetProcessById("+pid+");try{$p.StartTime.ToUniversalTime().Ticks.ToString()}finally{$p.Dispose()}"],{windowsHide:true,timeout:3000,maxBuffer:1024},(error,out)=>resolve(!error&&/^\d+$/.test(out.trim())?out.trim():null));
});}
let selfStart;
async function ownStartTicks(){return selfStart||(selfStart=await processStartTicks(process.pid));}
async function lockOwnerAlive(owner){
 if(!Number.isSafeInteger(owner.pid)||owner.pid<=0)return false;
 try{process.kill(owner.pid,0);}catch(e){if(e.code==='ESRCH')return false;throw e;}
 if(owner.startTicks){const actual=await processStartTicks(owner.pid);if(actual)return actual===owner.startTicks;}
 return true; // Missing legacy identity or unavailable OS query is not proof of death.
}
async function claimLock(file){
 const startTicks=await ownStartTicks();if(!startTicks)throw Error('无法核对独立内核进程身份');
 const token=crypto.randomUUID(),owner={pid:process.pid,startTicks,token};
 for(let i=0;i<3;i++){
  try{const fd=fs.openSync(file,'wx');try{fs.writeFileSync(fd,JSON.stringify(owner));}finally{fs.closeSync(fd);}return owner;}
  catch(e){if(e.code!=='EEXIST')throw e;
   const prior=read(file);let old;try{old=JSON.parse(prior);}catch{throw Error('独立内核正在更新，请稍后重试');}
   if(await lockOwnerAlive(old))throw Error('独立内核正在更新，请稍后重试');
   if(read(file)===prior)fs.unlinkSync(file);
  }
 }
 throw Error('操作锁不可用');
}
function releaseLock(file,owner){try{if(json(file,{}).token===owner.token)fs.unlinkSync(file);}catch{}}
async function lock(action,name='mutation.lock'){fs.mkdirSync(ROOT,{recursive:true});const file=path.join(ROOT,name),owner=await claimLock(file);try{return await action();}finally{releaseLock(file,owner);}}
async function replace(entries,defaultRoute,expectedStateHash,expectedSettingsHash){return lock(async()=>{
 const o=options(),old=state(),before=read(CONFIG),beforeState=read(STATE),settingsPath=path.join(DATA,'config.json'),beforeSettings=read(settingsPath),router=require('./AppRouter.cjs');
 router.assertExpectedStateHash(expectedStateHash,beforeState);
 router.assertExpectedSettingsHash(expectedSettingsHash,beforeSettings);
 entries=entries.map(e=>{const normalized=router.normalizeEntry(e.path,e.route,o),identity=router.normalizeIdentity(e.identity);if(identity)normalized.identity=identity;return normalized;});
 const next={version:2,installed:!!defaultRoute||entries.length>0,entries,defaultRoute:defaultRoute||null,changedAt:new Date().toISOString()};
 const liveProxies=(await api('GET','/proxies')).proxies;
 const previousRules=ruleSnapshot((await api('GET','/rules')).rules);
 const selections=retainedSelections(o,old,next,liveProxies);
 const rollbackConfig=before===null?null:yaml.load(before);
 for(const g of rollbackConfig?.['proxy-groups']||[]){const selected=liveProxies[g.name]?.now;if(g.proxies.includes(selected))g.proxies=[selected,...g.proxies.filter(x=>x!==selected)];}
 const rollback=rollbackConfig===null?null:yaml.dump(rollbackConfig,{lineWidth:-1,noRefs:true});
 const output=yaml.dump(makeConfig(o,next,selections),{lineWidth:-1,noRefs:true});const candidate=path.join(ROOT,'candidate-'+crypto.randomUUID()+'.yaml');write(candidate,output);
 const check=spawnSync(o.Profiles.find(p=>p.Id===o.Routing.ProfileId).CorePath,['-t','-d',ROOT,'-f',candidate],{windowsHide:true,timeout:15000,stdio:'ignore'});
 if(check.status!==0){fs.unlinkSync(candidate);throw Error('独立内核配置验证失败');}
 let wroteConfig=false,wroteState=false;const nextState=JSON.stringify(next,null,2);
 try{
  if(read(CONFIG)!==before||read(STATE)!==beforeState||read(settingsPath)!==beforeSettings)throw Error('配置验证期间发生外部更改');
  write(CONFIG,output);wroteConfig=true;await api('PUT','/configs?force=true',{path:CONFIG});
  const live=await api('GET','/rules');if(!rulesMatch(next,live.rules))throw Error('独立规则实读或顺序不一致');
  if(read(CONFIG)!==output||read(STATE)!==beforeState||read(settingsPath)!==beforeSettings)throw Error('配置核对期间发生外部更改');
  write(STATE,nextState);wroteState=true;write(path.join(ROOT,'generation.json'),{generation:crypto.randomUUID()});
  return {ok:true,Message:'独立入口规则已载入；上游失效后按备用顺序接替。',entries,defaultRoute,stateHash:router.stateHash(nextState)};
 }catch(e){
  if(read(CONFIG)!==(wroteConfig?output:before)||read(STATE)!==(wroteState?nextState:beforeState)||read(settingsPath)!==beforeSettings)throw Error('规则应用未完成，检测到其他程序修改配置；已保留外部更改，请刷新并检查独立入口状态');
  if(!wroteConfig)throw e;
  try{if(before===null)throw Error('missing-rollback');write(CONFIG,rollback);await api('PUT','/configs?force=true',{path:CONFIG});if(ruleSnapshot((await api('GET','/rules')).rules)!==previousRules)throw Error('rollback-unverified');write(STATE,beforeState===null?old:beforeState);write(path.join(ROOT,'generation.json'),{generation:crypto.randomUUID()});}
  catch{throw Error('独立内核回滚尚未通过验证，请检查入口状态并通过托盘停止服务恢复设置');}
  throw Error('独立规则应用失败，已恢复修改前配置与实际规则');
 }finally{fs.unlinkSync(candidate);}
});}
function ruleSnapshot(rules){return JSON.stringify((rules||[]).map(r=>({type:r.type,payload:r.payload||'',proxy:r.proxy})));}
function rulesMatch(s,rules){
 const expected=[...s.entries.map(e=>({type:'ProcessPath',payload:e.path,proxy:group(e.route)})),{type:'Match',proxy:s.defaultRoute?group(s.defaultRoute):'REJECT'}];
 return Array.isArray(rules)&&rules.length===expected.length&&expected.every((e,i)=>rules[i].type===e.type&&rules[i].proxy===e.proxy&&(!e.payload||String(rules[i].payload||'').toLowerCase()===e.payload.toLowerCase()));
}
async function status(){const o=options(),s=state();try{
 const result=await Promise.allSettled([api('GET','/configs'),api('GET','/rules'),api('GET','/connections'),api('GET','/proxies')]);
 const [configResult,rulesResult,connectionResult,proxyResult]=result,c=configResult.value,g=proxyResult.value,gateway=o.Profiles.find(p=>p.Id===o.Routing.ProfileId);
 if(configResult.status!=='fulfilled'||!gateway||c['mixed-port']!==gateway.Port||c.mode!=='rule'||!await listening(gateway.Host,gateway.Port))throw Error('独立入口配置或控制接口未验证');
 const rulesAvailable=rulesResult.status==='fulfilled'&&Array.isArray(rulesResult.value?.rules),connectionsAvailable=connectionResult.status==='fulfilled'&&Array.isArray(connectionResult.value?.connections),proxiesAvailable=proxyResult.status==='fulfilled'&&!!g?.proxies;
 const loaded=rulesAvailable?rulesMatch(s,rulesResult.value.rules):null;
 const effective=id=>id==='Direct'?'Direct':proxiesAvailable?actualRoute([g.proxies[group(id)]?.now],o):'Unknown';
 return {available:true,mode:c.mode,tunEnabled:!!c.tun?.enable,independent:true,rulesAvailable,connectionsAvailable,proxiesAvailable,ruleError:rulesAvailable?'':'独立规则读取失败，生效状态未知',connectionError:connectionsAvailable?'':'独立连接读取失败，连接状态未知',proxyError:proxiesAvailable?'':'独立出口读取失败，出口状态未知',defaultRoute:s.defaultRoute,effectiveDefaultRoute:s.defaultRoute?effective(s.defaultRoute):'Blocked',defaultLoaded:rulesAvailable?!!s.defaultRoute&&loaded:null,
  entries:s.entries.map(e=>({...e,effectiveRoute:effective(e.route),loaded,loadState:loaded===null?'unknown':loaded?'loaded':'not-loaded'})),
  connections:(connectionsAvailable?connectionResult.value.connections:[]).map(x=>({id:x.id,start:x.start,path:x.metadata?.processPath||'',sourcePort:Number(x.metadata?.sourcePort),sourceAddress:x.metadata?.sourceIP||'',destinationAddress:x.metadata?.destinationIP||'',destinationPort:Number(x.metadata?.destinationPort),network:x.metadata?.network||'',inbound:x.metadata?.type||'',route:actualRoute(x.chains||[],o),managed:true})),failover:{...json(path.join(ROOT,'health.json'),{}),events:json(path.join(ROOT,'failover-events.json'),[])}};
 }catch(e){return {available:false,error:'独立分流内核未就绪：'+e.message,rulesAvailable:false,connectionsAvailable:false,proxiesAvailable:false,ruleError:'内核未就绪，规则状态未知',connectionError:'内核未就绪，连接状态未知',defaultRoute:s.defaultRoute,defaultLoaded:null,entries:s.entries.map(e=>({...e,loaded:null,loadState:'unknown'})),connections:[]};}}

const LIFECYCLE=path.join(ROOT,'lifecycle-state.json');
function lifecycleEvent(event,fields={}) {
 try {
  fs.mkdirSync(ROOT,{recursive:true});const file=path.join(ROOT,'lifecycle-core.jsonl');
  if(fs.existsSync(file)&&fs.statSync(file).size>262144){fs.rmSync(file+'.1',{force:true});fs.renameSync(file,file+'.1');}
  const row={at:new Date().toISOString(),event,pid:process.pid};
  for(const k of ['core','attempt','exitCode','delayMs'])if(Number.isFinite(fields[k]))row[k]=fields[k];
  for(const k of ['reason','signal'])if(typeof fields[k]==='string'&&/^[a-zA-Z0-9_-]{1,64}$/.test(fields[k]))row[k]=fields[k];
  fs.appendFileSync(file,JSON.stringify(row)+'\n');
 }catch{} // A full disk must not stop a working proxy.
}
function nextRestart(attempts,now=Date.now()) {
 const recent=attempts.filter(t=>now-t<300000);
 return {allowed:recent.length<3,attempt:recent.length+1,delayMs:1000*2**recent.length,recent};
}
async function waitForCore(child,entrance,stopping,timeout=6000) {
 const end=Date.now()+timeout;
 while(Date.now()<end&&!stopping()){
  if(child.exitCode!==null||child.signalCode||!child.pid)return false;
  try {const config=await api('GET','/configs');
   if(child.exitCode===null&&!child.signalCode&&config['mixed-port']===entrance.Port&&config.mode==='rule'&&await listening(entrance.Host,entrance.Port))return true;
  }catch{}
  await new Promise(r=>setTimeout(r,100));
 }
 return false;
}

async function start(){return lock(async()=>{
 const stopped=path.join(ROOT,'stop'),singleton=path.join(ROOT,'supervisor.lock');
 // A still-listening old child may already have a stop request. Do not report
 // that retiring process as a successfully restarted service.
 if(fs.existsSync(stopped)){
  const end=Date.now()+14000;
  while(fs.existsSync(singleton)&&Date.now()<end){
   if(!await lockOwnerAlive(json(singleton,{})))break;await new Promise(r=>setTimeout(r,100));
  }
  if(fs.existsSync(singleton)&&await lockOwnerAlive(json(singleton,{})))throw Error('上一次代理服务尚未停止，请稍后重试');
 }
 try{const live=await status(),life=json(LIFECYCLE,{}),owned=json(path.join(ROOT,'process.json'),{});
  if(!fs.existsSync(stopped)&&live.available&&life.phase==='ready'&&life.supervisor===owned.supervisor&&owned.supervisorStartTicks&&await processStartTicks(owned.supervisor)===owned.supervisorStartTicks)return {ok:true};
 }catch{}
 const o=options();fs.mkdirSync(ROOT,{recursive:true});lifecycleEvent('start-request');const s=state();write(CONFIG,yaml.dump(makeConfig(o,s,resumeSelections(o,s,json(path.join(ROOT,'health.json'),{}))),{lineWidth:-1}));
 const entrance=o.Profiles.find(p=>p.Id===o.Routing.ProfileId);if(await listening(entrance.Host,entrance.Port)){lifecycleEvent('start-rejected',{reason:'port-occupied'});throw Error('独立入口端口已被其他程序占用；未接管该端口，未更改 Windows 代理');}
 if(fs.existsSync(stopped))fs.unlinkSync(stopped);
 const env={...process.env};delete env.PROXY_SWITCH_PROFILES;
 const node=path.join(ROOT,'runtime','node.exe');const child=spawn(fs.existsSync(node)?node:process.execPath,[__filename,'--serve'],{windowsHide:true,detached:true,stdio:'ignore',env});child.unref();
 const readyDeadline=Date.now()+10000;
 while(Date.now()<readyDeadline){await new Promise(r=>setTimeout(r,100));if(fs.existsSync(stopped))throw Error('启动已取消，代理服务正在停止');try{const life=json(LIFECYCLE,{});if(life.supervisor===child.pid&&life.phase==='failed')break;if((await status()).available&&life.supervisor===child.pid&&life.phase==='ready')return {ok:true};}catch{}}
 write(path.join(ROOT,'stop'),'startup-timeout');lifecycleEvent('start-failed',{reason:'readiness-timeout'});
 throw Error('独立内核启动失败，原系统设置保持不变');
},'start.lock');}
async function serve(){fs.mkdirSync(ROOT,{recursive:true});const singleton=path.join(ROOT,'supervisor.lock');
 let ownership;try{ownership=await claimLock(singleton);}catch{return;}
 const o=options(),entrance=o.Profiles.find(p=>p.Id===o.Routing.ProfileId),core=entrance.CorePath;
 const env={...process.env};for(const key of Object.keys(env))if(/^(http|https|all)_proxy$/i.test(key))delete env[key];
 let child=null,exited=true,policies={},generation='',attempts=[],unreadySince=0;
 const stopped=()=>fs.existsSync(path.join(ROOT,'stop'));
 let life={phase:'starting',supervisor:process.pid,core:null,attempt:0,reason:'startup',startedAt:new Date().toISOString()};
 const publish=()=>{try{write(LIFECYCLE,{...life,updatedAt:new Date().toISOString()});}catch{}};
 const setPhase=(phase,reason)=>{life.phase=phase;life.reason=reason;publish();};
 const heartbeat=setInterval(publish,1000);publish();
 const pause=async ms=>{const end=Date.now()+ms;while(Date.now()<end&&!stopped())await new Promise(r=>setTimeout(r,Math.min(100,end-Date.now())));};
 async function spawnCore(){
  if(stopped())return false;
  // A listener without our live controller is not a healthy FlowSwitch instance.
  if(await listening(entrance.Host,entrance.Port)){setPhase('failed','port-occupied');lifecycleEvent('start-rejected',{reason:'port-occupied'});return false;}
  child=spawn(core,['-d',ROOT,'-f',CONFIG],{windowsHide:true,stdio:['ignore','pipe','pipe'],env});exited=false;
  const spawned=child;
  child.on('exit',(code,signal)=>{if(child===spawned)exited=true;lifecycleEvent('core-exit',{core:spawned.pid,exitCode:code,signal:signal||'none',reason:stopped()?'requested-stop':'unexpected-exit'});});
  child.on('error',()=>{if(child===spawned)exited=true;lifecycleEvent('core-spawn-failed',{reason:'spawn-error'});});
  // Drain both streams, but never retain raw core output: it can contain URLs or credentials.
  let warningReported=false;
  for(const stream of [child.stdout,child.stderr])stream.on('data',chunk=>{if(!warningReported){warningReported=true;lifecycleEvent('core-output',{reason:/bind|address already in use|Only one usage/i.test(chunk.toString().slice(0,4096))?'listener-bind-failed':'output-observed'});}});
  life.core=child.pid||null;const started=new Date().toISOString(),coreStartTicks=await processStartTicks(child.pid);
  write(path.join(ROOT,'process.json'),{supervisor:process.pid,supervisorStartTicks:ownership.startTicks,core:child.pid||null,coreStartTicks,started});
  lifecycleEvent('core-start',{core:child.pid,attempt:life.attempt});
  const ready=!!coreStartTicks&&await waitForCore(child,entrance,()=>stopped()||exited);
  if(!ready){lifecycleEvent('readiness-failed',{reason:exited?'core-exited':'listener-or-controller-timeout'});if(!exited){child.kill();await Promise.race([new Promise(r=>child.once('exit',r)),new Promise(r=>setTimeout(r,2000))]);if(!exited)throw Error('内核停止未确认');}return false;}
  setPhase('ready','listener-and-controller-ready');lifecycleEvent('entry-ready',{core:child.pid,attempt:life.attempt});unreadySince=0;return true;
 }
 try{
  if(!await spawnCore()){setPhase('failed','initial-start-failed');return;}
  while(!stopped()){
   if(exited){
    const retry=nextRestart(attempts);if(!retry.allowed){setPhase('failed','restart-limit');lifecycleEvent('restart-exhausted',{reason:'restart-limit'});break;}
    attempts=retry.recent;attempts.push(Date.now());life.attempt=retry.attempt;
    setPhase('restarting','unexpected-core-exit');lifecycleEvent('restart-attempt',{attempt:retry.attempt,delayMs:retry.delayMs});await pause(retry.delayMs);
    if(stopped())break;
    // Last verified selection survives a crash, as it does an unrelated rules reload.
    const currentOptions=options(),saved=state();
    write(CONFIG,yaml.dump(makeConfig(currentOptions,saved,resumeSelections(currentOptions,saved,json(path.join(ROOT,'health.json'),{}))),{lineWidth:-1}));
    if(!await spawnCore()){if(life.reason==='port-occupied')break;setPhase('restarting','readiness-failed');continue;}
    policies={};generation='';
   }
   try{const c=await api('GET','/configs');if(c['mixed-port']!==entrance.Port||c.mode!=='rule'||!await listening(entrance.Host,entrance.Port))throw Error('not-ready');unreadySince=0;}
   catch{if(!unreadySince)unreadySince=Date.now();setPhase('degraded','listener-or-controller-unavailable');if(Date.now()-unreadySince>=10000){lifecycleEvent('core-unresponsive',{reason:'readiness-lost'});if(!exited)child.kill();}await pause(500);continue;}
   setPhase('ready','listener-and-controller-ready');
  const o=options(),s=state(),gen=read(path.join(ROOT,'generation.json'))||s.changedAt||'';
  if(gen!==generation){policies={};generation=gen;}
  const ids=[...new Set([...s.entries.map(e=>e.route),s.defaultRoute].filter(id=>id&&id!=='Direct'))];
  const needed=[...new Set(ids.flatMap(id=>candidates(id,o)).filter(id=>id!=='Direct'))];const health={},details={};
  await Promise.all(needed.map(async id=>{details[id]=await healthCheck(id,o);health[id]=details[id].healthy;}));
  // An abandoned writer lock must reach claimLock so its process identity can
  // be checked and reclaimed; file existence alone can freeze failover forever.
  if(generation!==(read(path.join(ROOT,'generation.json'))||state().changedAt||'')){await new Promise(r=>setTimeout(r,250));continue;}
  try{await lock(async()=>{
  if(generation!==(read(path.join(ROOT,'generation.json'))||state().changedAt||''))return;
  for(const id of ids){
   try{const current=await api('GET','/proxies/'+encodeURIComponent(group(id)));const actual=actualRoute([current.now],o);const prior=policies[id]?.current===actual?policies[id]:{current:actual==='Unknown'?id:actual,failures:0,changed:0};
    const next=decide(prior,candidates(id,o),health,Date.now(),policy(o),details);const wanted=next.current==='Blocked'?'REJECT':next.current==='Direct'?group('Direct'):upstream(next.current);
    if(current.now!==wanted){await api('PUT','/proxies/'+encodeURIComponent(group(id)),{name:wanted});const verified=await api('GET','/proxies/'+encodeURIComponent(group(id)));if(verified.now!==wanted)throw Error('selection-not-applied');recordEvent({policy:id,from:prior.current,to:next.current,reason:details[prior.current]?.reason||'route-recovered'});}
    policies[id]=next;
   }catch{details[id]={...details[id],selectionError:true};}
  }
  write(path.join(ROOT,'health.json'),{updated:new Date().toISOString(),health,details,policies});
  });}catch{}

   await pause(policy(o).IntervalMs);
  }
 }catch{setPhase('failed','supervisor-error');lifecycleEvent('supervisor-failed',{reason:'supervisor-error'});}
 finally{
  if(child&&!exited){child.kill();await Promise.race([new Promise(r=>child.once('exit',r)),new Promise(r=>setTimeout(r,2000))]);}
  clearInterval(heartbeat);if(stopped())setPhase('stopped','requested-stop');else if(life.phase!=='failed')setPhase('failed','supervisor-ended');
  lifecycleEvent('supervisor-stop',{reason:life.reason});releaseLock(singleton,ownership);
 }
}
async function reconnectPlan(executable){const o=options(),s=state();executable=require('./AppRouter.cjs').normalizeEntry(executable,'Follow',o).path;
 if(o.Profiles.some(p=>[p.CorePath,p.AppPath].filter(Boolean).some(x=>path.win32.normalize(x).toLowerCase()===executable.toLowerCase())))throw Error('代理内核和客户端不能按程序重连');
 const live=await status(),rule=live.entries.find(e=>e.path.toLowerCase()===executable.toLowerCase());const wanted=rule?rule.effectiveRoute:live.effectiveDefaultRoute;
 if(!live.available||!live.rulesAvailable||!live.defaultLoaded||(rule&&rule.loaded!==true)||wanted==='Blocked'||wanted==='Unknown')throw Error('当前规则或出口未验证，无法预览重连');
 const all=(await api('GET','/connections')).connections||[];
 return {path:executable,wanted,createdAt:Date.now(),fingerprint:JSON.stringify(s),connections:all.filter(c=>c.metadata?.processPath?.toLowerCase()===executable.toLowerCase()&&actualRoute(c.chains||[],o)!==wanted).map(c=>({id:c.id,start:c.start,route:actualRoute(c.chains||[],o)}))};
}
async function main(input){if(input.action==='status')return status();if(input.action==='start')return start();if(input.action==='stop'){lifecycleEvent('stop-request',{reason:'explicit-stop'});write(path.join(ROOT,'stop'),'stop');return {ok:true};}
 if(input.action==='replace')return replace(input.entries,input.defaultRoute,input.expectedStateHash,input.expectedSettingsHash);if(input.action==='sync'){const s=state();return replace(s.entries,s.defaultRoute);}
 if(input.action==='reconnect-plan')return reconnectPlan(input.path);
 if(input.action==='reconnect')return lock(async()=>{const p=input.plan;if(!p||!Array.isArray(p.connections)||p.connections.length>1024||!Number.isFinite(p.createdAt)||Date.now()-p.createdAt>60000||p.createdAt>Date.now())throw Error('重连预览已失效');const now=await reconnectPlan(p.path);if(now.wanted!==p.wanted||now.fingerprint!==p.fingerprint)throw Error('线路已改变，请重新预览');let closed=0,failed=0;for(const c of now.connections.filter(c=>p.connections.some(x=>x.id===c.id&&x.start===c.start&&x.route===c.route))){if(/^[a-zA-Z0-9-]{1,100}$/.test(c.id)){try{await api('DELETE','/connections/'+encodeURIComponent(c.id));closed++;}catch{failed++;}}}return {ok:failed===0,closed,failed,Message:'已关闭 '+closed+' 条预览确认的旧连接。'+(failed?' '+failed+' 条未能关闭；请刷新状态后重新预览。':'')};});
 throw Error('独立内核不支持此操作');
}
if(require.main===module&&process.argv.includes('--serve'))serve().catch(()=>{process.exitCode=1;});
module.exports={main,api,makeConfig,actualRoute,decide,policy,candidates,healthCheck,retainedSelections,resumeSelections,status,replace,start,nextRestart,lifecycleEvent,rulesMatch,processStartTicks,claimLock,releaseLock,ROOT,PIPE,CONFIG};
