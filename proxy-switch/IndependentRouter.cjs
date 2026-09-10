'use strict';
// FlowSwitch owns this core and its loopback controller. No subscriptions are copied.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),http=require('node:http'),net=require('node:net');
const {spawn,spawnSync,execFile}=require('node:child_process');
const systemCurl=path.join(process.env.SystemRoot||'C:\\Windows','System32','curl.exe');
const yaml=require('./vendor/js-yaml');
const DATA=process.env.PROXY_SWITCH_DATA_DIR||path.join(process.env.USERPROFILE,'.proxyswitch');
const ROOT=path.join(DATA,'gateway'),STATE=path.join(DATA,'app-rules.json'),CONFIG=path.join(ROOT,'runtime.yaml');
const PIPE='\\\\.\\pipe\\FlowSwitch-'+crypto.createHash('sha256').update(path.resolve(DATA).toLowerCase()).digest('hex').slice(0,20);
const read=p=>fs.existsSync(p)?fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''):null;
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
 const seen=new Set(),guard=o.Profiles.flatMap(p=>[p.CorePath,p.AppPath]).filter(Boolean).map(p=>p.toLowerCase());
 for(const e of entries){require('./AppRouter.cjs').normalizeEntry(e.path,e.route,o);if(e.route==='Follow'||seen.has(e.path.toLowerCase())||guard.includes(e.path.toLowerCase()))throw Error('无效或重复的程序规则');seen.add(e.path.toLowerCase());candidates(e.route,o);}
 if(defaultRoute)candidates(defaultRoute,o);
}
function makeConfig(o,s,selections={}){validate(s.entries,s.defaultRoute,o);const entrance=o.Profiles.find(p=>p.Id===o.Routing.ProfileId);if(!entrance)throw Error('缺少独立入口');
 const used=[...new Set([...s.entries.map(e=>e.route),s.defaultRoute].filter(Boolean))];
 const proxies=o.Profiles.filter(p=>p.Id!==entrance.Id).map(p=>({name:upstream(p.Id),type:p.Protocol,server:p.Host,port:p.Port}));
 proxies.push({name:group('Direct'),type:'direct'});
 const groups=used.filter(id=>id!=='Direct').map(id=>{const list=[...candidates(id,o).map(x=>x==='Direct'?group(x):upstream(x)),'REJECT'];const selected=selections[group(id)];return {name:group(id),type:'select',proxies:list.includes(selected)?[selected,...list.filter(x=>x!==selected)]:list};});
 return {'mixed-port':entrance.Port,'bind-address':'127.0.0.1','allow-lan':false,'external-controller-pipe':PIPE,mode:'rule',ipv6:false,'log-level':'silent','find-process-mode':'always',profile:{'store-selected':false},dns:{enable:false},tun:{enable:false},proxies,'proxy-groups':groups,rules:[...s.entries.map(e=>'PROCESS-PATH,'+e.path+','+group(e.route)),'MATCH,'+(s.defaultRoute?group(s.defaultRoute):'REJECT')]};
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
 const reset=new Set(next.entries.filter(e=>!old.entries.some(x=>x.path.toLowerCase()===e.path.toLowerCase()&&x.route===e.route)).map(e=>e.route));
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
async function lock(action){fs.mkdirSync(ROOT,{recursive:true});const file=path.join(ROOT,'mutation.lock');let fd;for(let i=0;i<2;i++){try{fd=fs.openSync(file,'wx');break;}catch(e){if(e.code!=='EEXIST')throw e;const old=json(file,{});try{process.kill(old.pid,0);throw Error('独立内核正在更新，请稍后重试');}catch(err){if(err.code!=='ESRCH')throw err;fs.unlinkSync(file);}}}if(fd===undefined)throw Error('操作锁不可用');fs.writeFileSync(fd,JSON.stringify({pid:process.pid}));fs.closeSync(fd);try{return await action();}finally{fs.unlinkSync(file);}}
async function replace(entries,defaultRoute){return lock(async()=>{
 const o=options(),old=state(),before=read(CONFIG),next={version:2,installed:!!defaultRoute||entries.length>0,entries,defaultRoute:defaultRoute||null,changedAt:new Date().toISOString()};
 const liveProxies=(await api('GET','/proxies')).proxies;
 const selections=retainedSelections(o,old,next,liveProxies);
 const rollbackConfig=before===null?null:yaml.load(before);
 for(const g of rollbackConfig?.['proxy-groups']||[]){const selected=liveProxies[g.name]?.now;if(g.proxies.includes(selected))g.proxies=[selected,...g.proxies.filter(x=>x!==selected)];}
 const rollback=rollbackConfig===null?null:yaml.dump(rollbackConfig,{lineWidth:-1,noRefs:true});
 const output=yaml.dump(makeConfig(o,next,selections),{lineWidth:-1,noRefs:true});const candidate=path.join(ROOT,'candidate-'+crypto.randomUUID()+'.yaml');write(candidate,output);
 const check=spawnSync(o.Profiles.find(p=>p.Id===o.Routing.ProfileId).CorePath,['-t','-d',ROOT,'-f',candidate],{windowsHide:true,timeout:15000,stdio:'ignore'});
 if(check.status!==0){fs.unlinkSync(candidate);throw Error('独立内核配置验证失败');}
 try{write(CONFIG,output);await api('PUT','/configs?force=true',{path:CONFIG});
  const live=await api('GET','/rules');const expected=next.entries.map(e=>({type:'ProcessPath',payload:e.path,proxy:group(e.route)}));expected.push({type:'Match',proxy:next.defaultRoute?group(next.defaultRoute):'REJECT'});
  if(!expected.every(e=>live.rules.some(r=>r.type===e.type&&r.proxy===e.proxy&&(!e.payload||r.payload.toLowerCase()===e.payload.toLowerCase()))))throw Error('独立规则实读不一致');
  write(STATE,next);write(path.join(ROOT,'generation.json'),{generation:crypto.randomUUID()});
  return {ok:true,Message:'独立入口规则已载入；上游失效后按备用顺序接替。',entries,defaultRoute};
 }catch(e){if(before!==null){write(CONFIG,rollback);try{await api('PUT','/configs?force=true',{path:CONFIG});}catch{throw Error('独立内核回滚失败，退出恢复保护将清除失效入口');}}write(STATE,old);throw e;}finally{fs.unlinkSync(candidate);}
});}
async function status(){const o=options(),s=state();try{
 const [c,r,con,g]=await Promise.all([api('GET','/configs'),api('GET','/rules'),api('GET','/connections'),api('GET','/proxies')]);const gateway=o.Profiles.find(p=>p.Id===o.Routing.ProfileId);
 if(c['mixed-port']!==gateway.Port||c.mode!=='rule')throw Error('独立入口配置不一致');
 const effective=id=>id==='Direct'?'Direct':actualRoute([g.proxies[group(id)]?.now],o);
 return {available:true,mode:c.mode,tunEnabled:false,independent:true,defaultRoute:s.defaultRoute,effectiveDefaultRoute:s.defaultRoute?effective(s.defaultRoute):'Blocked',defaultLoaded:!!s.defaultRoute&&r.rules.some(x=>x.type==='Match'&&x.proxy===group(s.defaultRoute)),
  entries:s.entries.map(e=>({...e,effectiveRoute:effective(e.route),loaded:r.rules.some(x=>x.type==='ProcessPath'&&x.payload.toLowerCase()===e.path.toLowerCase()&&x.proxy===group(e.route))})),
  connections:(con.connections||[]).map(x=>({path:x.metadata?.processPath||'',sourcePort:Number(x.metadata?.sourcePort),network:x.metadata?.network||'',inbound:x.metadata?.type||'',route:actualRoute(x.chains||[],o),managed:true})),failover:{...json(path.join(ROOT,'health.json'),{}),events:json(path.join(ROOT,'failover-events.json'),[])}};
 }catch(e){return {available:false,error:'独立分流内核未就绪：'+e.message,defaultRoute:s.defaultRoute,defaultLoaded:false,entries:s.entries.map(e=>({...e,loaded:false})),connections:[]};}}
async function start(){try{if((await status()).available)return {ok:true};}catch{}
 const o=options();fs.mkdirSync(ROOT,{recursive:true});const s=state();write(CONFIG,yaml.dump(makeConfig(o,s,resumeSelections(o,s,json(path.join(ROOT,'health.json'),{}))),{lineWidth:-1}));
 const entrance=o.Profiles.find(p=>p.Id===o.Routing.ProfileId);if(await listening(entrance.Host,entrance.Port))throw Error('独立入口端口已被其他程序占用');
 const stopped=path.join(ROOT,'stop');if(fs.existsSync(stopped))fs.unlinkSync(stopped);
 const env={...process.env};delete env.PROXY_SWITCH_PROFILES;
 const node=path.join(ROOT,'runtime','node.exe');const child=spawn(fs.existsSync(node)?node:process.execPath,[__filename,'--serve'],{windowsHide:true,detached:true,stdio:'ignore',env});child.unref();
 for(let i=0;i<60;i++){await new Promise(r=>setTimeout(r,100));try{if((await status()).available)return {ok:true};}catch{}}
 throw Error('独立内核启动失败，原系统设置保持不变');
}
async function serve(){fs.mkdirSync(ROOT,{recursive:true});const singleton=path.join(ROOT,'supervisor.lock');
 try{const fd=fs.openSync(singleton,'wx');fs.writeFileSync(fd,JSON.stringify({pid:process.pid}));fs.closeSync(fd);}catch(e){if(e.code!=='EEXIST')throw e;const old=json(singleton,{});try{process.kill(old.pid,0);return;}catch(e){if(e.code!=='ESRCH')throw e;fs.unlinkSync(singleton);return serve();}}
 const o=options(),core=o.Profiles.find(p=>p.Id===o.Routing.ProfileId).CorePath;
 const env={...process.env};for(const key of Object.keys(env))if(/^(http|https|all)_proxy$/i.test(key))delete env[key];
 const child=spawn(core,['-d',ROOT,'-f',CONFIG],{windowsHide:true,stdio:'ignore',env});let exited=false;child.on('exit',()=>exited=true);child.on('error',()=>exited=true);
 write(path.join(ROOT,'process.json'),{supervisor:process.pid,core:child.pid,started:new Date().toISOString()});let policies={},generation='';
 try{while(!fs.existsSync(path.join(ROOT,'stop'))&&!exited){
  const o=options(),s=state(),gen=read(path.join(ROOT,'generation.json'))||s.changedAt||'';
  if(gen!==generation){policies={};generation=gen;}
  const ids=[...new Set([...s.entries.map(e=>e.route),s.defaultRoute].filter(id=>id&&id!=='Direct'))];
  const needed=[...new Set(ids.flatMap(id=>candidates(id,o)).filter(id=>id!=='Direct'))];const health={},details={};
  await Promise.all(needed.map(async id=>{details[id]=await healthCheck(id,o);health[id]=details[id].healthy;}));
  if(fs.existsSync(path.join(ROOT,'mutation.lock'))||generation!==(read(path.join(ROOT,'generation.json'))||state().changedAt||'')){await new Promise(r=>setTimeout(r,250));continue;}
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
  await new Promise(r=>setTimeout(r,policy(o).IntervalMs));
 }}finally{if(!exited)child.kill();if(fs.existsSync(singleton))fs.unlinkSync(singleton);}
}
async function reconnectPlan(executable){const o=options(),s=state(),live=await status();require('./AppRouter.cjs').normalizeEntry(executable,'Follow',o);const rule=live.entries.find(e=>e.path.toLowerCase()===executable.toLowerCase());const wanted=rule?rule.effectiveRoute:live.effectiveDefaultRoute;
 if(!live.available||!live.defaultLoaded||wanted==='Blocked'||wanted==='Unknown')throw Error('当前没有已验证的可用出口');
 const all=(await api('GET','/connections')).connections||[];
 return {path:executable,wanted,createdAt:Date.now(),fingerprint:JSON.stringify(s),connections:all.filter(c=>c.metadata?.processPath?.toLowerCase()===executable.toLowerCase()&&actualRoute(c.chains||[],o)!==wanted).map(c=>({id:c.id,start:c.start,route:actualRoute(c.chains||[],o)}))};
}
async function main(input){if(input.action==='status')return status();if(input.action==='start')return start();if(input.action==='stop'){write(path.join(ROOT,'stop'),'stop');return {ok:true};}
 if(input.action==='replace')return replace(input.entries,input.defaultRoute);if(input.action==='sync'){const s=state();return replace(s.entries,s.defaultRoute);}
 if(input.action==='reconnect-plan')return reconnectPlan(input.path);
 if(input.action==='reconnect'){const p=input.plan;if(!p||!Array.isArray(p.connections)||p.connections.length>1024||!Number.isFinite(p.createdAt)||Date.now()-p.createdAt>60000||p.createdAt>Date.now())throw Error('重连预览已失效');const now=await reconnectPlan(p.path);if(now.wanted!==p.wanted||now.fingerprint!==p.fingerprint)throw Error('线路已改变，请重新预览');let closed=0;for(const c of now.connections.filter(c=>p.connections.some(x=>x.id===c.id&&x.start===c.start&&x.route===c.route))){if(/^[a-zA-Z0-9-]{1,100}$/.test(c.id)){await api('DELETE','/connections/'+encodeURIComponent(c.id));closed++;}}return {ok:true,closed,Message:'已关闭 '+closed+' 条预览确认的旧连接。'};}
 throw Error('独立内核不支持此操作');
}
if(require.main===module&&process.argv.includes('--serve'))serve().catch(()=>{process.exitCode=1;});
module.exports={main,api,makeConfig,actualRoute,decide,policy,candidates,healthCheck,retainedSelections,resumeSelections,status,replace,start,ROOT,PIPE,CONFIG};
