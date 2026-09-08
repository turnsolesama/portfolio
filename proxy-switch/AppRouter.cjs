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
const samePath = (a,b) => String(a).toLowerCase() === String(b).toLowerCase();
const ownedName = value => typeof value === 'string' && value.startsWith(PREFIX);
const ownedRule = rule => typeof rule === 'string' && ownedName(rule.split(',').at(-1));
function normalizeOptions(options) {
  if (options.Version !== 3) {
    const profiles = ['Clash','Upnet'].filter(id=>options[id]).map(id=>({Id:id,Name:options[id].Name,Protocol:'http',Host:'127.0.0.1',Port:options[id].Port,CorePath:options[id].CorePath,AppPath:options[id].AppPath,AutoPort:id==='Clash'&&options[id].AutoPort!==false}));
    options={Version:3,Profiles:profiles,Routing:{Adapter:options.Clash?'clash-verge':'none',ProfileId:options.Clash?'Clash':''}};
  }
  if(!Array.isArray(options.Profiles)||!options.Routing||!['none','clash-verge'].includes(options.Routing.Adapter)) throw new Error('代理列表格式无效。');
  const ids=new Set(),endpoints=new Set();
  for(const p of options.Profiles){
    if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$/.test(p.Id)||['direct','follow','other','unset','blocked','unknown'].includes(p.Id.toLowerCase())||ids.has(p.Id.toLowerCase()))throw new Error('代理标识无效或重复。');
    ids.add(p.Id.toLowerCase());
    if(!['http','socks5'].includes(p.Protocol)||!Number.isInteger(p.Port)||p.Port<1||p.Port>65535||typeof p.Host!=='string'||!p.Host||/[%\s,@/\\"\x00-\x1f]/.test(p.Host))throw new Error('代理地址、协议或端口无效。');
    const endpoint=(['localhost','127.0.0.1','::1'].includes(p.Host)?'loopback':p.Host.toLowerCase())+':'+p.Port;
    if(endpoints.has(endpoint))throw new Error('代理入口重复。');endpoints.add(endpoint);
  }
  if(options.Routing.Adapter==='clash-verge'){
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
function readState(options=readOptions()){
  const raw=read(STATE);if(!raw)return {version:2,entries:[],defaultRoute:null,installed:false};
  const state=JSON.parse(raw);
  if(![1,2].includes(state.version)||!Array.isArray(state.entries))throw new Error('程序规则文件格式错误。');
  for(const e of state.entries){normalizeEntry(e.path,e.route,options);if(e.route==='Follow')throw new Error('程序规则文件含无效默认项。');}
  if(state.defaultRoute&&!validRoute(state.defaultRoute,options))throw new Error('统一线路已不在代理列表中。');
  return {...state,defaultRoute:state.defaultRoute||null};
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
  if(used.Direct)config.proxies.push({name:name('Direct'),type:'direct'});
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
  var rules=spec.entries.map(function(e){return 'PROCESS-PATH,'+e.path+','+name(e.route);});
  if(spec.defaultRoute)rules.push('MATCH,'+name(spec.defaultRoute));
  config.rules=rules.concat(config.rules);
  if(spec.entries.length)config['find-process-mode']='always';
  else if(spec.originalFind&&spec.originalFind.present)config['find-process-mode']=spec.originalFind.value;else delete config['find-process-mode'];
  return config;
}
function makeSpec(entries,defaultRoute,options,primary,originalFind){
  const seen=new Set();
  for(const e of entries){
    normalizeEntry(e.path,e.route,options);
    if(e.route==='Follow'||seen.has(e.path.toLowerCase()))throw new Error('程序规则重复或无效。');
    if(options.Profiles.some(p=>[p.CorePath,p.AppPath].some(x=>x&&samePath(x,e.path))))throw new Error('不能给代理程序自身分流，以免形成回路。');
    seen.add(e.path.toLowerCase());
  }
  if(defaultRoute&&!validRoute(defaultRoute,options))throw new Error('统一线路无效。');
  const used=new Set(entries.map(e=>e.route));if(defaultRoute)used.add(defaultRoute);
  return {entries,defaultRoute:defaultRoute||null,primary,originalFind,gateway:options.Routing.ProfileId,
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
function fingerprint(entries,defaultRoute,options){return hash(JSON.stringify(makeSpec(entries,defaultRoute,options,'',null)));}
async function status(){
  const options=readOptions(),state=readState(options);
  try{
    if(options.Routing.Adapter==='none')throw new Error('尚未设置程序分流引擎。HTTP 统一切换与直连仍可使用。');
    const [config,connections,rules]=await Promise.all([api('GET','/configs'),api('GET','/connections'),api('GET','/rules')]);
    const current=state.fingerprint===fingerprint(state.entries,state.defaultRoute,options);
    return {available:true,mode:config.mode,defaultRoute:state.defaultRoute,defaultLoaded:!state.defaultRoute||(current&&config.mode==='rule'&&rules.rules.some(r=>r.type==='Match'&&r.proxy===routeName(state.defaultRoute))),
      entries:state.entries.map(e=>({...e,loaded:current&&config.mode==='rule'&&rules.rules.some(r=>ruleMatches(r,e))})),
      connections:(connections.connections||[]).map(c=>({path:c.metadata?.processPath||'',sourcePort:Number(c.metadata?.sourcePort),route:routeOfChains(c.chains||[],options),managed:ownedName(c.chains?.at(-1)),rule:c.rule||''}))};
  }catch(e){return {available:false,error:e.message,defaultRoute:state.defaultRoute,defaultLoaded:false,entries:state.entries.map(e=>({...e,loaded:false})),connections:[]};}
}
async function transaction(entries,defaultRoute=null){
  const options=readOptions(),state=readState(options);
  makeSpec(entries,defaultRoute,options,'',null);
  if(!entries.length&&!defaultRoute&&!state.installed){return {ok:true,message:'没有需要撤回的分流规则。',entries:[]};}
  if(options.Routing.Adapter!=='clash-verge')throw new Error('请先配置受支持的程序分流引擎。');
  const gateway=options.Profiles.find(p=>p.Id===options.Routing.ProfileId);
  const before={runtime:read(RUNTIME),script:read(SCRIPT),state:read(STATE)};
  if(!before.runtime||before.script===null)throw new Error('未找到分流引擎的运行配置与全局脚本。');
  const base=yaml.load(before.runtime),core=await api('GET','/configs');
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
  if(hash(read(RUNTIME))!==hash(before.runtime)||hash(read(SCRIPT))!==hash(before.script)||hash(read(STATE))!==hash(before.state))throw new Error('验证期间配置被其他程序改动，请重试。');
  try{
    atomicWrite(RUNTIME,output);atomicWrite(SCRIPT,script);atomicWrite(STATE,JSON.stringify(next,null,2));
    await api('PUT','/configs?force=true',{path:RUNTIME});
    const actual=await api('GET','/rules');
    const expected=entries.length+(defaultRoute?1:0);
    if(!entries.every(e=>actual.rules.some(r=>ruleMatches(r,e)))||actual.rules.filter(r=>ownedName(r.proxy)).length!==expected|| (defaultRoute&&!actual.rules.some(r=>r.type==='Match'&&r.proxy===routeName(defaultRoute))))throw new Error('规则重载核对失败。');
    return {ok:true,message:'线路规则已保存并载入，新连接生效。',entries,defaultRoute};
  }catch(e){
    try{atomicWrite(RUNTIME,before.runtime);atomicWrite(SCRIPT,before.script);atomicWrite(STATE,before.state||JSON.stringify({version:2,entries:[],installed:false}));await api('PUT','/configs?force=true',{path:RUNTIME});}
    catch{throw new Error('应用失败且回滚未完成，请检查分流引擎目录中的 proxy-switch-backups 备份。');}
    throw new Error('规则应用失败，已恢复修改前配置。');
  }
}
async function main(){
  let raw='';for await(const chunk of process.stdin)raw+=chunk;const input=JSON.parse(raw.replace(/^\uFEFF/,''));
  if(input.action==='status')return status();
  if(input.action==='replace')return withMutationLock(()=>transaction(input.entries,input.defaultRoute||null));
  if(input.action==='sync')return withMutationLock(()=>{const state=readState();return transaction(state.entries,state.defaultRoute);});
  if(input.action==='set')return withMutationLock(()=>{
    const options=readOptions(),entry=normalizeEntry(input.path,input.route,options),state=readState(options);
    if(options.Profiles.some(p=>[p.CorePath,p.AppPath].some(x=>x&&samePath(x,entry.path))))throw new Error('不能给代理程序自身分流，以免形成回路。');
    if(entry.route!=='Follow'&&!fs.existsSync(entry.path))throw new Error('程序路径已失效。');
    const entries=state.entries.filter(e=>!samePath(e.path,entry.path));if(entry.route!=='Follow')entries.push(entry);
    return transaction(entries,state.defaultRoute);
  });
  throw new Error('未知路由操作。');
}
async function withMutationLock(action) {
  fs.mkdirSync(DATA, {recursive: true});
  const lockPath = path.join(DATA, 'app-rules.lock');
  const token = JSON.stringify({ pid: process.pid, id: crypto.randomUUID() });
  let fd;
  for (let attempt = 0; attempt < 2; attempt++) {
    try { fd = fs.openSync(lockPath, 'wx', 0o600); break; }
    catch (error) {
      if (error.code !== 'EEXIST') throw new Error('无法创建程序规则操作锁。');
      let old, text;
      try { text = read(lockPath); old = JSON.parse(text); } catch { throw new Error('程序规则操作锁异常，请稍后检查。'); }
      let alive = true;
      try { process.kill(old.pid, 0); } catch (e) { if (e.code === 'ESRCH') alive = false; }
      if (alive) throw new Error('另一个程序规则操作尚未完成，请稍候。');
      if (read(lockPath) === text) fs.unlinkSync(lockPath);
    }
  }
  if (fd === undefined) throw new Error('无法取得程序规则操作锁，请稍后重试。');
  fs.writeFileSync(fd, token); fs.closeSync(fd);
  try { return await action(); }
  finally { if (read(lockPath) === token) fs.unlinkSync(lockPath); }
}

if(require.main===module)main().then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{
  const message=['YAMLException','SyntaxError'].includes(error.name)?'配置格式校验失败，未应用更改。':error.message;
  process.stdout.write(JSON.stringify({ok:false,error:message}));process.exitCode=1;
});
module.exports={api,normalizeOptions,normalizeEntry,routeName,makeConfig,makeScript,stripScript,ownedRule,routeOfChains,ruleMatches,status,fingerprint,makeSpec};
