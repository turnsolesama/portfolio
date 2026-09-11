 'use strict';
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');
const yaml = require('./vendor/js-yaml');
const ROOT = __dirname;
const DATA = process.env.PROXY_SWITCH_DATA_DIR || path.join(process.env.USERPROFILE || require('node:os').homedir(), '.proxyswitch');
const TEST_ENGINE = process.env.PROXY_SWITCH_TEST_ENGINE_DIR;
const TEST_PIPE = process.env.PROXY_SWITCH_TEST_PIPE;
if((TEST_ENGINE||TEST_PIPE)&&(!TEST_ENGINE||!path.isAbsolute(TEST_ENGINE)||!TEST_PIPE?.startsWith('\\\\.\\pipe\\ProxySwitch-Test-')))throw new Error('Isolated test engine requires a dedicated directory and test pipe.');
const CLASH = TEST_ENGINE || path.join(process.env.APPDATA, 'io.github.clash-verge-rev.clash-verge-rev');
const RUNTIME = path.join(CLASH, 'clash-verge.yaml');
const SCRIPT = path.join(CLASH, 'profiles', 'Script.js');
const STATE = path.join(DATA, 'app-rules.json');
const BEGIN = '// >>> ProxySwitch application routing >>>';
const END = '// <<< ProxySwitch application routing <<<';
const PREFIX = 'PSW-App-';
const read = p => fs.existsSync(p) ? fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, '') : null;
const hash = s => crypto.createHash('sha256').update(s || '').digest('hex');
const stateHash = (current=read(STATE)) => hash(current===null?'<missing>':current.replace(/^\uFEFF/,''));
function assertExpectedStateHash(expected,current=read(STATE)){
  if(expected===undefined||expected===null)return;
  const actual=stateHash(current);
  if(typeof expected!=='string'||!/^[a-f0-9]{64}$/i.test(expected)||actual!==expected.toLowerCase())throw new Error('程序规则已在预览后改变，请刷新并重新预览修复。');
}
function assertExpectedSettingsHash(expected,current=read(path.join(DATA,'config.json'))){
  try{assertExpectedStateHash(expected,current);}catch{throw new Error('代理设置已在预览后改变，请刷新并重新预览修复。');}
}
const samePath = (a,b) => typeof a==='string' && typeof b==='string' && !!a && !!b && path.win32.normalize(a).toLowerCase() === path.win32.normalize(b).toLowerCase();
const ownedName = value => typeof value === 'string' && value.startsWith(PREFIX);
const ownedRule = rule => typeof rule === 'string' && ownedName(rule.split(',').at(-1));
function normalizeOptions(options) {
  if (options.Version !== 3) {
    const profiles = ['Clash','Upnet'].filter(id=>options[id]).map(id=>({Id:id,Name:options[id].Name,Protocol:'http',Host:'127.0.0.1',Port:options[id].Port,CorePath:options[id].CorePath,AppPath:options[id].AppPath,AutoPort:id==='Clash'&&options[id].AutoPort!==false}));
    options={Version:3,Profiles:profiles,Routing:{Adapter:options.Clash?'clash-verge':'none',ProfileId:options.Clash?'Clash':''}};
  }
  if(!Array.isArray(options.Profiles)||!options.Routing||!['none','clash-verge','standalone'].includes(options.Routing.Adapter)) throw new Error('代理列表格式无效。');
  const ids=new Set(),endpoints=new Set();
  for(const p of options.Profiles){
    if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$/.test(p.Id)||['direct','follow','other','unset','blocked','unknown'].includes(p.Id.toLowerCase())||ids.has(p.Id.toLowerCase()))throw new Error('代理标识无效或重复。');
    ids.add(p.Id.toLowerCase());
    if(!['http','socks5'].includes(p.Protocol)||!Number.isInteger(p.Port)||p.Port<1||p.Port>65535||typeof p.Host!=='string'||!p.Host||/[%\s,@/\\"\x00-\x1f]/.test(p.Host))throw new Error('代理地址、协议或端口无效。');
    const endpoint=(['localhost','127.0.0.1','::1'].includes(p.Host)?'loopback':p.Host.toLowerCase())+':'+p.Port;
    if(endpoints.has(endpoint))throw new Error('代理入口重复。');endpoints.add(endpoint);
  }
  if(['clash-verge','standalone'].includes(options.Routing.Adapter)){
    const gateway=options.Profiles.find(p=>p.Id===options.Routing.ProfileId);
    if(!gateway||gateway.Protocol!=='http'||!['127.0.0.1','localhost','::1'].includes(gateway.Host)||!gateway.CorePath)throw new Error('分流引擎必须为本地 HTTP 入口，并配置内核路径。');
  }
  return options;
}
function readOptions() {
  const options=normalizeOptions(JSON.parse(process.env.PROXY_SWITCH_PROFILES || read(path.join(DATA,'config.json')) || read(path.join(ROOT,'config.defaults.json'))));
  const gateway=options.Profiles.find(p=>p.Id===options.Routing.ProfileId);
  if(gateway?.AutoPort){const m=/^verge_mixed_port:\s*(\d+)\s*$/m.exec(read(path.join(CLASH,'verge.yaml'))||'');if(m)gateway.Port=Number(m[1]);}
  return normalizeOptions(options);
}
function routeName(id){return id==='Direct'?PREFIX+'Direct':PREFIX+'route-'+id;}
function validRoute(route,options,follow=false){return route==='Direct'||(follow&&route==='Follow')||options.Profiles.some(p=>p.Id===route);}
function normalizeEntry(executable,route,options=readOptions()){
  if(!validRoute(route,options,true))throw new Error('所选代理不在列表中。');
  if(typeof executable!=='string'||!path.win32.isAbsolute(executable)||/[,\r\n\x00]/.test(executable)||!/\.exe$/i.test(executable))throw new Error('请选择完整 EXE 路径，路径不能含逗号或换行。');
  return {path:path.win32.normalize(executable),route};
}
function normalizeIdentity(identity){
  if(!identity||identity.Version!==1||!['Package','File','Path'].includes(identity.Kind))return undefined;
  const result={Version:1,Kind:identity.Kind};
  for(const key of ['Path','CanonicalPath','FileId','PathStatus','PackageFamilyName','PackageFullName','RelativeExecutable'])if(typeof identity[key]==='string'&&identity[key].length<=32768)result[key]=identity[key];
  for(const key of ['Exists','PackageVerified'])if(typeof identity[key]==='boolean')result[key]=identity[key];
  return result;
}
function normalizeSavedEntry(entry,options){
  const result=normalizeEntry(entry.path,entry.route,options),identity=normalizeIdentity(entry.identity);
  if(identity)result.identity=identity;
  return result;
}
function readState(options=readOptions()){
  const raw=read(STATE);if(!raw)return {version:2,entries:[],defaultRoute:null,installed:false};
  const state=JSON.parse(raw);
  if((state.programIngresses?.length||state.siteRules?.length)&&options.Routing.Adapter!=='standalone')throw new Error('独立程序入口和网站规则仍存在，不能使用外部分流适配器覆盖它们。请恢复独立入口配置。');
  if(![1,2,3].includes(state.version)||!Array.isArray(state.entries))throw new Error('程序规则文件格式错误。');
  const entries=state.entries.map(e=>normalizeSavedEntry(e,options));
  for(const e of entries)if(e.route==='Follow')throw new Error('程序规则文件含无效默认项。');
  if(state.defaultRoute&&!validRoute(state.defaultRoute,options))throw new Error('统一线路已不在代理列表中。');
  return {...state,entries,defaultRoute:state.defaultRoute||null};
}
function atomicWrite(p,content){
  fs.mkdirSync(path.dirname(p),{recursive:true});const temp=p+'.'+crypto.randomUUID()+'.tmp';
  fs.writeFileSync(temp,content,{encoding:'utf8',mode:0o600});fs.renameSync(temp,p);
}
function api(method, endpoint, value) {
  return new Promise((resolve, reject) => {
    const body = value === undefined ? '' : JSON.stringify(value);
    const req = http.request({ socketPath: TEST_PIPE || '\\\\.\\pipe\\verge-mihomo', path: endpoint, method,
      headers: { Host: 'localhost', Connection: 'close', 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } }, res => {
      const chunks = []; let size = 0;
      res.on('data', chunk => { size += chunk.length; if (size > 8 * 1024 * 1024) req.destroy(new Error('响应过大')); else chunks.push(chunk); });
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) return reject(new Error('Clash 控制接口返回 HTTP ' + res.statusCode));
        try { const s = Buffer.concat(chunks).toString('utf8'); resolve(s ? JSON.parse(s) : null); }
        catch { reject(new Error('Clash 控制接口响应格式异常')); }
      });
    });
    req.setTimeout(5000, () => req.destroy(new Error('Clash 控制接口超时')));
    req.on('error', () => reject(new Error('无法访问 Clash 本地控制接口，请检查 Clash 是否运行。')));
    req.end(body);
  });
}

// This pure function is also embedded in Verge's persistent script. Keep it self-contained.
function applyRouting(config,spec){
  var owned=function(n){return typeof n==='string'&&n.indexOf('PSW-App-')===0;};
  var name=function(id){return id==='Direct'?'PSW-App-Direct':'PSW-App-route-'+id;};
  config.proxies=(config.proxies||[]).filter(function(p){return !owned(p.name);});
  config['proxy-groups']=(config['proxy-groups']||[]).filter(function(p){return !owned(p.name);});
  config.rules=(config.rules||[]).filter(function(r){return !owned(r.split(',').pop());});
  if(!spec.entries.length&&!spec.defaultRoute){
    if(spec.originalFind&&spec.originalFind.present)config['find-process-mode']=spec.originalFind.value;else delete config['find-process-mode'];
    return config;
  }
  var used={};spec.entries.forEach(function(e){used[e.route]=true;});if(spec.defaultRoute)used[spec.defaultRoute]=true;
  var guards=spec.guardPaths||[];
  if(used.Direct||guards.length)config.proxies.push({name:name('Direct'),type:'direct'});
  spec.profiles.forEach(function(p){
    if(!used[p.Id])return;
    if(p.Id===spec.gateway){
      var primary=spec.primary;
      if(!config['proxy-groups'].some(function(g){return g.name===primary;})){
        var first=config['proxy-groups'].filter(function(g){return g.type==='select'&&g.name!=='GLOBAL';})[0];
        if(!first)throw new Error('ProxySwitch: no primary proxy group');primary=first.name;
      }
      config['proxy-groups'].push({name:name(p.Id),type:'select',proxies:[primary]});
    }else{config.proxies.push({name:name(p.Id),type:p.Protocol,server:p.Host,port:p.Port});}
  });
  var rules=guards.map(function(p){return 'PROCESS-PATH,'+p+','+name('Direct');}).concat(spec.entries.map(function(e){return 'PROCESS-PATH,'+e.path+','+name(e.route);}));
  if(spec.defaultRoute)rules.push('MATCH,'+name(spec.defaultRoute));
  config.rules=rules.concat(config.rules);
  if(spec.entries.length||guards.length)config['find-process-mode']='always';
  else if(spec.originalFind&&spec.originalFind.present)config['find-process-mode']=spec.originalFind.value;else delete config['find-process-mode'];
  return config;
}
function makeSpec(entries,defaultRoute,options,primary,originalFind){
  entries=entries.map(e=>normalizeEntry(e.path,e.route,options));
  const seen=new Set();
  for(const e of entries){
    normalizeEntry(e.path,e.route,options);
    if(e.route==='Follow'||seen.has(e.path.toLowerCase()))throw new Error('程序规则重复或无效。');
    if(options.Profiles.some(p=>[p.CorePath,p.AppPath].some(x=>x&&samePath(x,e.path))))throw new Error('不能给代理程序自身分流，以免形成回路。');
    seen.add(e.path.toLowerCase());
  }
  if(defaultRoute&&!validRoute(defaultRoute,options))throw new Error('统一线路无效。');
  const used=new Set(entries.map(e=>e.route));if(defaultRoute)used.add(defaultRoute);
  const guardPaths=options.Routing.UnifiedMode==='gateway'?options.Profiles.flatMap(p=>[p.CorePath,p.AppPath]).filter(Boolean).map(p=>normalizeEntry(p,'Direct',options).path).filter((p,i,all)=>all.findIndex(other=>samePath(p,other))===i):[];
  for(const p of guardPaths)normalizeEntry(p,'Direct',options);
  return {entries,defaultRoute:defaultRoute||null,primary,originalFind,gateway:options.Routing.ProfileId,guardPaths,
    profiles:options.Profiles.filter(p=>used.has(p.Id)).map(p=>({Id:p.Id,Protocol:p.Protocol,Host:p.Host,Port:p.Port}))};
}
function makeConfig(base,entries,defaultRoute,options,primary,originalFind){return applyRouting(structuredClone(base),makeSpec(entries,defaultRoute,options,primary,originalFind));}
function stripScript(source){
  const start=source.indexOf(BEGIN);if(start<0)return source;
  const end=source.indexOf(END,start);if(end<0||source.indexOf(BEGIN,start+BEGIN.length)>=0)throw new Error('已有分流脚本标记异常。');
  return source.slice(0,start).replace(/\n\n$/,'')+source.slice(end+END.length).replace(/^\r?\n/,'');
}
function makeScript(source,entries,defaultRoute,options,primary,originalFind){
  const base=stripScript(source);if(!entries.length&&!defaultRoute)return base;
  if(!/function\s+main\s*\(/.test(base))throw new Error('全局脚本入口无法安全扩展，已保留原文件。');
  const spec=makeSpec(entries,defaultRoute,options,primary,originalFind);
  const result=base+'\n\n'+BEGIN+'\nvar __pswOriginalMain = main;\nmain = function(config, profileName) {\nconfig = __pswOriginalMain(config, profileName);\nreturn ('+applyRouting.toString()+')(config, '+JSON.stringify(spec)+');\n};\n'+END+'\n';
  new vm.Script(result);return result;
}
function routeOfChains(chains,options=readOptions()){
  for(const item of chains.slice().reverse()){
    if(item===routeName('Direct'))return 'Direct';
    const found=options.Profiles.find(p=>item===routeName(p.Id));if(found)return found.Id;
    if(item==='PSW-App-Upnet'&&options.Profiles.some(p=>p.Id==='Upnet'))return 'Upnet';
  }
  if(chains.includes('DIRECT'))return 'Direct';if(chains.includes('REJECT')||chains.includes('REJECT-DROP'))return 'Blocked';
  return chains.length?(options.Routing.ProfileId||'Unknown'):'Unknown';
}
function ruleMatches(rule,entry){return rule.type==='ProcessPath'&&samePath(rule.payload,entry.path)&&rule.proxy===routeName(entry.route);}
function verifyRoutingRules(rules,entries,defaultRoute,guardPaths=[]){
  if(!Array.isArray(rules))return false;
  const expected=guardPaths.map(p=>({path:p,route:'Direct'})).concat(entries);
  if(!expected.every((entry,index)=>rules[index]&&ruleMatches(rules[index],entry)))return false;
  if(defaultRoute&&(rules[expected.length]?.type!=='Match'||rules[expected.length]?.proxy!==routeName(defaultRoute)))return false;
  return rules.filter(rule=>ownedName(rule?.proxy)).length===expected.length+(defaultRoute?1:0);
}
function ruleSnapshot(value){
  if(!Array.isArray(value?.rules))throw new Error('内核规则响应无效。');
  return JSON.stringify(value.rules.map(rule=>({type:rule.type,payload:rule.payload||'',proxy:rule.proxy})));
}
function fingerprint(entries,defaultRoute,options){return hash(JSON.stringify(makeSpec(entries,defaultRoute,options,'',null)));}
async function status(){
  const options=readOptions(),state=readState(options);
  try{
    if(options.Routing.Adapter==='none')throw new Error('尚未设置程序分流引擎。HTTP 统一切换与直连仍可使用。');
    const config=await api('GET','/configs');
    const current=state.fingerprint===fingerprint(state.entries,state.defaultRoute,options);
    const gateway=options.Profiles.find(p=>p.Id===options.Routing.ProfileId);
    if(!config||(Number(config['mixed-port'])!==gateway.Port&&Number(config.port)!==gateway.Port))throw new Error('所选引擎端口与控制接口不一致，未接管该入口。');
    const [connectionRead,ruleRead]=await Promise.allSettled([api('GET','/connections'),api('GET','/rules')]);
    const observedConnections=connectionRead.status==='fulfilled'?require('./RoutePolicy.cjs').connectionRows(connectionRead.value):null;
    const connectionsAvailable=observedConnections!==null;
    const rulesAvailable=ruleRead.status==='fulfilled'&&Array.isArray(ruleRead.value?.rules);
    const guards=state.entries.length||state.defaultRoute?makeSpec(state.entries,state.defaultRoute,options,'',null).guardPaths:[];
    const loaded=rulesAvailable?current&&config.mode==='rule'&&verifyRoutingRules(ruleRead.value.rules,state.entries,state.defaultRoute,guards):null;
    return {available:true,rulesAvailable,connectionsAvailable,ruleError:rulesAvailable?null:'无法核对内核规则，当前载入状态未知。',connectionError:connectionsAvailable?null:'无法读取内核连接，当前连接状态未知。',
      mode:config.mode,tunEnabled:!!config.tun?.enable,defaultRoute:state.defaultRoute,defaultLoaded:rulesAvailable?(!state.defaultRoute||loaded):null,
      entries:state.entries.map(e=>({...e,loaded,loadState:loaded===null?'unknown':loaded?'loaded':'not-loaded'})),
      connections:(observedConnections||[]).map(c=>({id:c.id,start:c.start,path:c.metadata?.processPath||'',sourcePort:Number(c.metadata?.sourcePort),sourceAddress:c.metadata?.sourceIP||'',destinationAddress:c.metadata?.destinationIP||'',destinationPort:Number(c.metadata?.destinationPort),network:c.metadata?.network||'',inbound:c.metadata?.type||'',route:routeOfChains(c.chains||[],options),managed:ownedName(c.chains?.at(-1)),rule:c.rule||''}))};
  }catch(e){return {available:false,rulesAvailable:false,connectionsAvailable:false,error:e.message,defaultRoute:state.defaultRoute,defaultLoaded:null,entries:state.entries.map(e=>({...e,loaded:null,loadState:'unknown'})),connections:[]};}
}
async function transaction(entries,defaultRoute=null,expectedStateHash,expectedSettingsHash){
  const initialState=read(STATE);assertExpectedStateHash(expectedStateHash,initialState);
  assertExpectedSettingsHash(expectedSettingsHash);
  const options=readOptions(),state=readState(options);
  entries=entries.map(e=>normalizeSavedEntry(e,options));
  makeSpec(entries,defaultRoute,options,'',null);
  if(!entries.length&&!defaultRoute&&!state.installed){return {ok:true,message:'没有需要撤回的分流规则。',entries:[],stateHash:stateHash(initialState)};}
  if(options.Routing.Adapter!=='clash-verge')throw new Error('请先配置受支持的程序分流引擎。');
  const gateway=options.Profiles.find(p=>p.Id===options.Routing.ProfileId);
  const settingsFile=path.join(DATA,'config.json');
  const before={runtime:read(RUNTIME),script:read(SCRIPT),state:read(STATE),settings:read(settingsFile)};
  assertExpectedStateHash(expectedStateHash,before.state);
  assertExpectedSettingsHash(expectedSettingsHash,before.settings);
  if(!before.runtime||before.script===null)throw new Error('未找到分流引擎的运行配置与全局脚本。');
  const base=yaml.load(before.runtime),core=await api('GET','/configs'),previousRules=ruleSnapshot(await api('GET','/rules'));
  if(Number(core['mixed-port'])!==gateway.Port&&Number(core.port)!==gateway.Port)throw new Error('所选引擎端口与控制接口不一致，保留原配置。');
  if(core.mode!=='rule')throw new Error('请先将分流引擎切回规则模式。');
  if(!state.installed&&((base.proxies||[]).some(p=>ownedName(p.name))||(base['proxy-groups']||[]).some(p=>ownedName(p.name))||(base.rules||[]).some(ownedRule)))throw new Error('检测到未归属本工具的路由名称，已停止更改。');
  const groups=(base['proxy-groups']||[]).filter(p=>!ownedName(p.name));
  const primary=groups.find(p=>p.name===state.primary)?.name||groups.find(p=>p.type==='select'&&p.name!=='GLOBAL')?.name;
  const originalFind=state.installed?state.originalFind:{present:Object.hasOwn(base,'find-process-mode'),value:base['find-process-mode']};
  const config=makeConfig(base,entries,defaultRoute,options,primary,originalFind);
  const output=yaml.dump(config,{lineWidth:-1,noRefs:true}),script=makeScript(before.script,entries,defaultRoute,options,primary,originalFind);
  const next={version:2,installed:entries.length>0||!!defaultRoute,entries,defaultRoute,primary,originalFind,fingerprint:fingerprint(entries,defaultRoute,options),changedAt:new Date().toISOString()};
  const stash=path.join(CLASH,'proxy-switch-backups',new Date().toISOString().replace(/[:.]/g,'-')+'-'+crypto.randomUUID().slice(0,6));
  fs.mkdirSync(stash,{recursive:true});
  for(const [name,content] of [['runtime.yaml',before.runtime],['Script.js',before.script],['state.json',before.state||JSON.stringify({version:2,entries:[],defaultRoute:null,installed:false})]])fs.writeFileSync(path.join(stash,name),content,{mode:0o600});
  const candidate=path.join(stash,'candidate.yaml');fs.writeFileSync(candidate,output,{mode:0o600});
  const check=spawnSync(gateway.CorePath,['-t','-d',CLASH,'-f',candidate],{windowsHide:true,timeout:15000,encoding:'utf8'});
  if(check.status!==0)throw new Error('分流内核未通过候选配置检查，保留原配置。');
  if(hash(read(RUNTIME))!==hash(before.runtime)||hash(read(SCRIPT))!==hash(before.script)||hash(read(STATE))!==hash(before.state)||hash(read(settingsFile))!==hash(before.settings))throw new Error('验证期间配置被其他程序改动，请重试。');
  const written={};
  try{
    for(const [key,file,value] of [['runtime',RUNTIME,output],['script',SCRIPT,script],['state',STATE,JSON.stringify(next,null,2)]]){atomicWrite(file,value);written[key]=value;}
    await api('PUT','/configs?force=true',{path:RUNTIME});
    const actual=await api('GET','/rules');
    const guards=(entries.length||defaultRoute)?makeSpec(entries,defaultRoute,options,primary,originalFind).guardPaths:[];
    if(!verifyRoutingRules(actual?.rules,entries,defaultRoute,guards))throw new Error('规则重载核对失败。');
    if([['runtime',RUNTIME],['script',SCRIPT],['state',STATE]].some(([key,file])=>hash(read(file))!==hash(written[key]))||hash(read(settingsFile))!==hash(before.settings))throw new Error('核对期间配置被其他程序更改。');
    return {ok:true,message:'线路规则已保存并载入，新连接生效。',entries,defaultRoute,stateHash:stateHash(written.state)};
  }catch(e){
    if([['runtime',RUNTIME],['script',SCRIPT],['state',STATE]].some(([key,file])=>hash(read(file))!==hash(Object.hasOwn(written,key)?written[key]:before[key]))||hash(read(settingsFile))!==hash(before.settings))throw new Error('规则应用未完成，检测到其他程序修改了配置，已保留外部更改。请检查分流引擎目录中的 proxy-switch-backups 备份。');
    try{atomicWrite(RUNTIME,before.runtime);atomicWrite(SCRIPT,before.script);atomicWrite(STATE,before.state||JSON.stringify({version:2,entries:[],installed:false}));await api('PUT','/configs?force=true',{path:RUNTIME});if(ruleSnapshot(await api('GET','/rules'))!==previousRules)throw new Error('回滚规则核对失败。');}
    catch{throw new Error('应用失败且回滚未完成，请检查分流引擎目录中的 proxy-switch-backups 备份。');}
    throw new Error('规则应用失败，已恢复修改前配置。');
  }
}
function stableJson(value){if(Array.isArray(value))return '['+value.map(stableJson).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stableJson(value[k])).join(',')+'}';return JSON.stringify(value);}
function planOfflineDetach(runtime,script,state,options){
  if(options.Routing.Adapter!=='clash-verge'||!state.installed)throw Error('没有可核验归属的外部分流安装记录，未静态移除第三方配置。');
  const entries=state.entries||[],defaultRoute=state.defaultRoute||null;
  if(state.fingerprint!==fingerprint(entries,defaultRoute,options))throw Error('外部分流保存指纹与当前设置不一致，无法安全静态分离。请保留备份并核对旧引擎。');
  const begins=script.split(BEGIN).length-1,ends=script.split(END).length-1;
  let nextScript=script;
  if(begins||ends){
    if(begins!==1||ends!==1||script.indexOf(END)<script.indexOf(BEGIN))throw Error('外部分流脚本标记异常，未移除未知内容。');
    const base=stripScript(script),expected=makeScript(base,entries,defaultRoute,options,state.primary,state.originalFind);
    if(expected!==script)throw Error('外部分流托管脚本已改变，无法核验其归属，未覆盖外部修改。');
    nextScript=base;new vm.Script(nextScript);
  }else if(script.includes(PREFIX)){throw Error('外部脚本包含无法归属的分流名称，未自动移除。');}
  const base=yaml.load(runtime);
  if(!base||typeof base!=='object'||Array.isArray(base))throw Error('外部运行配置格式无效，未进行静态分离。');
  for(const field of ['proxies','proxy-groups','rules'])if(base[field]!==undefined&&!Array.isArray(base[field]))throw Error('外部运行配置列表格式无效，未进行静态分离。');
  const clean=structuredClone(base);
  clean.proxies=(base.proxies||[]).filter(x=>!ownedName(x?.name));
  clean['proxy-groups']=(base['proxy-groups']||[]).filter(x=>!ownedName(x?.name));
  clean.rules=(base.rules||[]).filter(x=>!ownedRule(x));
  if(clean['proxy-groups'].some(g=>(g.proxies||[]).some(ownedName))||clean.rules.some(rule=>typeof rule==='string'&&rule.includes(PREFIX)))throw Error('外部自定义规则仍引用本工具出口，无法安全静态分离。');
  const actualOwned={proxies:(base.proxies||[]).filter(x=>ownedName(x?.name)),groups:(base['proxy-groups']||[]).filter(x=>ownedName(x?.name)),rules:(base.rules||[]).filter(ownedRule)};
  const hasOwned=Object.values(actualOwned).some(x=>x.length);
  let nextRuntime=runtime;
  if(hasOwned){
    const generated=makeConfig(clean,entries,defaultRoute,options,state.primary,state.originalFind);
    const expectedOwned={proxies:generated.proxies.filter(x=>ownedName(x?.name)),groups:generated['proxy-groups'].filter(x=>ownedName(x?.name)),rules:generated.rules.filter(ownedRule)};
    if(stableJson(actualOwned)!==stableJson(expectedOwned))throw Error('外部运行配置中的分流对象与保存记录不符，未删除未知规则或节点。');
    const spec=makeSpec(entries,defaultRoute,options,state.primary,state.originalFind);
    if((entries.length||spec.guardPaths.length)&&base['find-process-mode']==='always'){
      if(state.originalFind?.present)clean['find-process-mode']=state.originalFind.value;else delete clean['find-process-mode'];
    }
    nextRuntime=yaml.dump(clean,{lineWidth:-1,noRefs:true});
    if(stableJson(yaml.load(nextRuntime))!==stableJson(clean))throw Error('静态分离候选无法保持原配置语义，未写入。');
  }
  return {runtime:nextRuntime,script:nextScript,state:JSON.stringify({version:2,installed:false,entries:[],defaultRoute:null,offlineDetachedAt:new Date().toISOString()},null,2)};
}
function runPrivatePowerShell(command){
  const binary=path.join(process.env.SystemRoot||process.env.WINDIR||'C:\\Windows','System32','WindowsPowerShell','v1.0','powershell.exe');
  const env={...process.env};for(const key of Object.keys(env))if(key.toLowerCase()==='psmodulepath')delete env[key];
  const result=spawnSync(binary,['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand',Buffer.from(command,'utf16le').toString('base64')],{windowsHide:true,timeout:45000,encoding:'utf8',maxBuffer:16384,env});
  try{const parsed=JSON.parse(result.stdout.trim());if(result.status===0&&parsed?.ok)return parsed;}catch{}
  throw Error('本机文件或离线状态核验未完成，未确认静态分离；请保留本机备份并重试。');
}
async function assertExternalOffline(options){
  let reachable=false;try{await api('GET','/configs');reachable=true;}catch{}
  if(reachable)throw Error('外部分流控制接口仍在线，请使用正常撤回；未静态改写运行中的引擎。');
  const gateway=options.Profiles.find(p=>p.Id===options.Routing.ProfileId);
  const payload=Buffer.from(JSON.stringify({inventory:path.join(ROOT,'ProcessInventory.ps1'),core:gateway.CorePath,port:gateway.Port})).toString('base64');
  const result=runPrivatePowerShell(`$ErrorActionPreference='Stop';try{$q=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${payload}'))|ConvertFrom-Json;. $q.inventory;$ps=@(Get-ProcessInventory);$name=[IO.Path]::GetFileNameWithoutExtension($q.core);$suspect=@($ps|Where-Object {$_.Path -ieq $q.core -or (-not $_.Path -and $_.ProcessName -ieq $name)});$tcp=@();try{$tcp=@(Get-NetTCPConnection -ErrorAction Stop)}catch{if($_.FullyQualifiedErrorId -notlike 'CmdletizationQuery_NotFound*'){throw}};@{ok=$true;offline=($suspect.Count -eq 0 -and @($tcp|Where-Object {[string]$_.State -eq 'Listen' -and [int]$_.LocalPort -eq [int]$q.port}).Count -eq 0)}|ConvertTo-Json -Compress}catch{@{ok=$false}|ConvertTo-Json -Compress;exit 1}`);
  if(!result.offline)throw Error('旧代理内核仍运行、身份未知或入口仍监听，未静态分离。请先正常退出旧代理客户端。');
}
function captureDetachFiles(){
  const files={runtime:RUNTIME,script:SCRIPT,state:STATE,settings:path.join(DATA,'config.json')},values={};
  for(const [key,file] of Object.entries(files)){
    const stat=fs.lstatSync(file);if(!stat.isFile()||stat.isSymbolicLink()||stat.size>16*1024*1024)throw Error('静态分离所需文件缺失、为链接或过大，未改写外部配置。');
    const root=fs.realpathSync(key==='runtime'||key==='script'?CLASH:DATA),actual=fs.realpathSync(file);
    if(!actual.toLowerCase().startsWith((root+path.sep).toLowerCase()))throw Error('静态分离文件不在已配置目录内，未跟随外部链接。');
    values[key]=fs.readFileSync(file);
  }
  return {files,values};
}
function exclusiveDetachExchange(requestFile){
  const encoded=Buffer.from(requestFile).toString('base64');
  return runPrivatePowerShell(`$ErrorActionPreference='Stop';$handles=@();$written=@();try{
$request=Get-Content -LiteralPath ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${encoded}'))) -Raw -Encoding UTF8|ConvertFrom-Json
foreach($item in @($request.guard)+@($request.changes)){
 $access=[IO.FileAccess]::Read;if($item.PSObject.Properties['content']){$access=[IO.FileAccess]::ReadWrite}
 $file=[IO.File]::Open($item.path,[IO.FileMode]::Open,$access,[IO.FileShare]::None);$record=[pscustomobject]@{file=$file;before=$null;after=$null};$handles+=@($record)
 if($file.Length -gt 16777216){throw 'size'};$bytes=New-Object byte[] ([int]$file.Length);$offset=0;while($offset -lt $bytes.Length){$count=$file.Read($bytes,$offset,$bytes.Length-$offset);if($count -eq 0){throw 'read'};$offset+=$count};$record.before=$bytes
 $sha=[Security.Cryptography.SHA256]::Create();try{$hash=[BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()};if($hash -cne $item.expected){throw 'changed'}
 if($item.PSObject.Properties['content']){$record.after=[Convert]::FromBase64String($item.content)}
}
foreach($record in $handles){if($null -ne $record.after){$written+=@($record);$record.file.Position=0;$record.file.Write($record.after,0,$record.after.Length);$record.file.SetLength($record.after.Length);$record.file.Flush($true)}}
@{ok=$true}|ConvertTo-Json -Compress
}catch{$restored=$true;for($i=$written.Count-1;$i -ge 0;$i--){try{$r=$written[$i];$r.file.Position=0;$r.file.Write($r.before,0,$r.before.Length);$r.file.SetLength($r.before.Length);$r.file.Flush($true)}catch{$restored=$false}};@{ok=$false;restored=$restored}|ConvertTo-Json -Compress;exit 1}finally{foreach($r in $handles){$r.file.Dispose()}}`);
}
function detachPaths(id){
  if(!/^[a-f0-9]{32}$/.test(id))throw Error('离线分离备份标识无效。');
  return {manifest:path.join(DATA,'offline-detach-backups',id+'.json'),store:path.join(CLASH,'proxy-switch-backups','offline-detach-'+id)};
}
async function detachOffline(input,deps={}){
  if(Object.keys(deps).length&&!TEST_ENGINE)throw Error('测试替身只能用于隔离引擎目录。');
  if(!input.expectedStateHash||!input.expectedSettingsHash)throw Error('离线分离需要当前规则与设置的精确校验。');
  const options=readOptions();if(options.Routing.Adapter!=='clash-verge')throw Error('离线分离只适用于外部 Clash 分流。');
  const before=captureDetachFiles();assertExpectedStateHash(input.expectedStateHash,before.values.state.toString('utf8'));assertExpectedSettingsHash(input.expectedSettingsHash,before.values.settings.toString('utf8'));
  const state=readState(options);
  const planned=planOfflineDetach(before.values.runtime.toString('utf8').replace(/^\uFEFF/,''),before.values.script.toString('utf8').replace(/^\uFEFF/,''),state,options);
  await (deps.offline||assertExternalOffline)(options);
  const id=crypto.randomUUID().replace(/-/g,''),locations=detachPaths(id),manifest={version:1,id,phase:'prepared',createdAt:new Date().toISOString(),before:{},after:{},settingsHash:hash(before.values.settings)};
  fs.mkdirSync(locations.store,{recursive:true});fs.mkdirSync(path.dirname(locations.manifest),{recursive:true});
  const next={};for(const key of ['runtime','script','state']){
    const beforeText=before.values[key].toString('utf8'),preservedBom=key!=='state'&&beforeText.startsWith('\uFEFF')?'\uFEFF':'';
    next[key]=planned[key]===beforeText.replace(/^\uFEFF/,'')?before.values[key]:Buffer.from(preservedBom+planned[key]);
    manifest.before[key]=hash(before.values[key]);manifest.after[key]=hash(next[key]);fs.writeFileSync(path.join(locations.store,key+'.before'),before.values[key],{mode:0o600,flag:'wx'});
  }
  fs.writeFileSync(locations.manifest,JSON.stringify(manifest,null,2),{mode:0o600,flag:'wx'});
  const request={guard:[{path:before.files.settings,expected:hash(before.values.settings)}],changes:['runtime','script','state'].map(key=>({path:before.files[key],expected:manifest.before[key],content:next[key].toString('base64')}))};
  const requestFile=path.join(locations.store,'detach-request.json');fs.writeFileSync(requestFile,JSON.stringify(request),{mode:0o600,flag:'wx'});
  try{await (deps.offline||assertExternalOffline)(options);(deps.exchange||exclusiveDetachExchange)(requestFile);manifest.phase='detached';atomicWrite(locations.manifest,JSON.stringify(manifest,null,2));}
  catch{throw Error('外部分流静态分离未完成；原文件若被其他程序修改将予以保留。请核对本机备份：'+locations.manifest);}
  return {ok:true,detached:true,backup:locations.manifest,stateHash:stateHash(next.state.toString('utf8')),stateText:next.state.toString('utf8'),afterFileHashes:manifest.after,pendingExternalCleanup:false,Message:'已离线撤下可核验的外部分流托管段与规则；未启动、重载或结束第三方程序。'};
}
async function restoreOfflineDetach(input,deps={}){
  if(Object.keys(deps).length&&!TEST_ENGINE)throw Error('测试替身只能用于隔离引擎目录。');
  const id=typeof input.backup==='string'?path.basename(input.backup,'.json'):'';const locations=detachPaths(id);
  if(path.resolve(input.backup)!==path.resolve(locations.manifest))throw Error('只接受当前数据目录中的离线分离备份。');
  for(const file of [path.dirname(locations.manifest),locations.manifest,path.dirname(locations.store),locations.store]){const stat=fs.lstatSync(file);if(stat.isSymbolicLink())throw Error('离线分离备份路径为链接，未恢复。');}
  const manifest=JSON.parse(fs.readFileSync(locations.manifest,'utf8'));
  if(manifest.version!==1||manifest.id!==id||!['detached','prepared','restored'].includes(manifest.phase))throw Error('离线分离备份格式无效。');
  const current=captureDetachFiles();assertExpectedSettingsHash(input.expectedSettingsHash,current.values.settings.toString('utf8'));
  if(!input.expectedSettingsHash||hash(current.values.settings)!==manifest.settingsHash)throw Error('设置已改变，不能按旧离线备份恢复外部分流。');
  const options=readOptions();if(options.Routing.Adapter!=='clash-verge')throw Error('请先恢复原外部适配器设置，再恢复离线分离备份。');
  const originals={};for(const key of ['runtime','script','state']){
    const file=path.join(locations.store,key+'.before');if(fs.lstatSync(file).isSymbolicLink())throw Error('备份内容为链接，未恢复。');originals[key]=fs.readFileSync(file);
    if(hash(originals[key])!==manifest.before[key]||hash(current.values[key])!==(manifest.phase==='restored'?manifest.before[key]:manifest.after[key]))throw Error('外部文件已改变或备份不完整，保留最新内容；离线分离回滚未完成。');
  }
  if(manifest.phase==='restored')return {ok:true,restored:true,stateHash:stateHash(originals.state.toString('utf8')),backup:locations.manifest};
  await (deps.offline||assertExternalOffline)(options);
  const request={guard:[{path:current.files.settings,expected:manifest.settingsHash}],changes:['runtime','script','state'].map(key=>({path:current.files[key],expected:manifest.after[key],content:originals[key].toString('base64')}))};
  const requestFile=path.join(locations.store,'restore-'+crypto.randomUUID()+'.json');fs.writeFileSync(requestFile,JSON.stringify(request),{mode:0o600,flag:'wx'});
  (deps.exchange||exclusiveDetachExchange)(requestFile);manifest.phase='restored';atomicWrite(locations.manifest,JSON.stringify(manifest,null,2));
  return {ok:true,restored:true,stateHash:stateHash(originals.state.toString('utf8')),backup:locations.manifest,Message:'已恢复仍归本次离线分离的原文件字节，未启动或重载第三方引擎。'};
}
function selectReconnectConnections(connections, executable, wanted, options){
  return connections.filter(c=>samePath(c.metadata?.processPath,executable)&&typeof c.id==='string'&&/^[a-zA-Z0-9-]{1,100}$/.test(c.id)&&c.start&&routeOfChains(c.chains||[],options)!==wanted)
    .map(c=>({id:c.id,start:c.start,route:routeOfChains(c.chains||[],options)}));
}
async function reconnectPlan(executable){
  const options=readOptions(),state=readState(options),entry=normalizeEntry(executable,'Follow',options);
  if(options.Profiles.some(p=>[p.CorePath,p.AppPath].some(x=>x&&samePath(x,entry.path))))throw new Error('不能重连代理引擎或上游代理自身的连接。');
  const live=await status(),rule=live.entries.find(e=>samePath(e.path,entry.path));
  const wanted=rule?.route||state.defaultRoute;
  if(!live.available||!wanted||(rule?!rule.loaded:!live.defaultLoaded))throw new Error('目标规则尚未载入，不能重连。请先完成线路设置。');
  const connections=(await api('GET','/connections')).connections||[];
  return {path:entry.path,wanted,fingerprint:state.fingerprint,createdAt:Date.now(),connections:selectReconnectConnections(connections,entry.path,wanted,options)};
}
async function reconnect(plan){
  if(!plan||!Array.isArray(plan.connections)||plan.connections.length>1024||!Number.isFinite(plan.createdAt)||Date.now()-plan.createdAt>60000||plan.createdAt>Date.now()+1000)throw new Error('重连预览已失效，请重新查看。');
  const current=await reconnectPlan(plan.path);
  if(current.fingerprint!==plan.fingerprint||current.wanted!==plan.wanted)throw new Error('线路已改变，请重新查看重连预览。');
  const targets=current.connections.filter(c=>plan.connections.some(p=>p.id===c.id&&p.start===c.start&&p.route===c.route));
  let closed=0,failed=0;
  for(const c of targets){try{await api('DELETE','/connections/'+encodeURIComponent(c.id));closed++;}catch{failed++;}}
  return {ok:failed===0,closed,failed,Message:`已关闭 ${closed} 条所选程序的旧线路连接${failed?`，${failed} 条未完成`:''}。应用是否自动重连取决于应用自身；新连接请查看实际出口。其他程序和已经使用目标线路的连接未处理。`};
}
async function main(){
  let raw='';for await(const chunk of process.stdin)raw+=chunk;const input=JSON.parse(raw.replace(/^\uFEFF/,''));
  if(readOptions().Routing.Adapter==='standalone')return require('./IndependentRouter.cjs').main(input);
  if(input.programIngresses?.length||input.siteRules?.length)throw new Error('程序固定入口和网站规则需要流向独立入口，外部分流适配器不支持。');
  if(input.action==='status')return status();
  if(input.action==='detach-offline')return withMutationLock(()=>detachOffline(input));
  if(input.action==='restore-offline-detach')return withMutationLock(()=>restoreOfflineDetach(input));
  if(input.action==='reconnect-plan')return reconnectPlan(input.path);
  if(input.action==='reconnect')return withMutationLock(()=>reconnect(input.plan));
  if(input.action==='replace')return withMutationLock(()=>transaction(input.entries,input.defaultRoute||null,input.expectedStateHash,input.expectedSettingsHash));
  if(input.action==='sync')return withMutationLock(()=>{const state=readState();return transaction(state.entries,state.defaultRoute);});
  if(input.action==='set')return withMutationLock(()=>{
    const options=readOptions(),entry=normalizeEntry(input.path,input.route,options),state=readState(options);
    const identity=normalizeIdentity(input.identity||state.entries.find(e=>samePath(e.path,entry.path))?.identity);if(identity)entry.identity=identity;
    if(options.Profiles.some(p=>[p.CorePath,p.AppPath].some(x=>x&&samePath(x,entry.path))))throw new Error('不能给代理程序自身分流，以免形成回路。');
    if(entry.route!=='Follow'&&!fs.existsSync(entry.path))throw new Error('程序路径已失效。');
    const entries=state.entries.filter(e=>!samePath(e.path,entry.path));if(entry.route!=='Follow')entries.push(entry);
    return transaction(entries,state.defaultRoute);
  });
  throw new Error('未知路由操作。');
}
async function withMutationLock(action) {
  fs.mkdirSync(DATA, {recursive: true});
  const lockPath = path.join(DATA, 'app-rules.lock'),locking=require('./IndependentRouter.cjs');
  const owner=await locking.claimLock(lockPath);
  try { return await action(); }
  finally { locking.releaseLock(lockPath,owner); }
}

if(require.main===module)main().then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{
  const message=['YAMLException','SyntaxError'].includes(error.name)?'配置格式校验失败，未应用更改。':error.message;
  process.stdout.write(JSON.stringify({ok:false,error:message}));process.exitCode=1;
});
module.exports={api,normalizeOptions,normalizeEntry,normalizeIdentity,assertExpectedStateHash,assertExpectedSettingsHash,stateHash,routeName,makeConfig,makeScript,stripScript,ownedRule,routeOfChains,ruleMatches,verifyRoutingRules,status,fingerprint,makeSpec,selectReconnectConnections,reconnectPlan,reconnect,transaction,withMutationLock,planOfflineDetach,detachOffline,restoreOfflineDetach,assertExternalOffline,exclusiveDetachExchange};
