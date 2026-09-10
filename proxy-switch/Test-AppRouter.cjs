 'use strict';
const assert=require('node:assert/strict');const vm=require('node:vm');const r=require('./AppRouter.cjs');
let checks=0;function check(test,message){assert.ok(test,message);checks++;}function throws(fn){assert.throws(fn);checks++;}
const sha256=value=>require('node:crypto').createHash('sha256').update(value).digest('hex');
r.assertExpectedStateHash(sha256('<missing>'),null);checks++;
r.assertExpectedStateHash(sha256('{"entries":[]}'),'\uFEFF{"entries":[]}');checks++;
throws(()=>r.assertExpectedStateHash(sha256('<missing>'),''));
throws(()=>r.assertExpectedStateHash('','{"entries":[]}'));
const options={Version:3,Profiles:[{Id:'engine',Name:'Office',Protocol:'http',Host:'127.0.0.1',Port:7890,CorePath:'C:\\Apps\\core.exe'},
{Id:'custom',Name:'Custom name',Protocol:'http',Host:'192.0.2.1',Port:8080},{Id:'socks',Name:'SOCKS',Protocol:'socks5',Host:'127.0.0.1',Port:1080}],Routing:{Adapter:'clash-verge',ProfileId:'engine'}};
const base={mode:'rule',dns:{enable:true},secret:'test-only-value',proxies:[{name:'original',type:'http',server:'example.org',port:80}],
'proxy-groups':[{name:'primary',type:'select',proxies:['original']}],rules:['DOMAIN,example.org,DIRECT','MATCH,primary']};
const entries=[{path:'C:\\Apps\\例子.exe',route:'socks'},{path:'C:\\Apps\\browser.exe',route:'Direct'}];
const config=r.makeConfig(base,entries,'custom',options,'primary',{present:false});
check(config.proxies.find(p=>p.name===r.routeName('socks')).type==='socks5','SOCKS proxy emitted');
check(config.proxies.find(p=>p.name===r.routeName('custom')).server==='192.0.2.1','Custom HTTP host preserved');
check(config.rules[0]==='PROCESS-PATH,'+entries[0].path+','+r.routeName('socks'),'Program exception has highest priority');
check(config.rules[2]==='MATCH,'+r.routeName('custom'),'Unified fallback precedes original rules');
check(config['find-process-mode']==='always','Process identification enabled for exceptions');
check(base.rules.length===2&&base.proxies.length===1,'Base input untouched');
assert.deepEqual(config.dns,base.dns);checks++;
assert.deepEqual(r.makeConfig(config,entries,'custom',options,'primary',{present:false}),config);checks++;
const unified=r.makeConfig(config,[],'engine',options,'primary',{present:false});
check(!unified.rules.some(x=>x.startsWith('PROCESS-PATH'))&&unified.rules[0]==='MATCH,'+r.routeName('engine'),'Unified action removes all saved exceptions');
check(unified['proxy-groups'].find(g=>g.name===r.routeName('engine')).proxies[0]==='primary','Engine routes to original node group without proxy loop');
assert.deepEqual(r.makeConfig(unified,[],null,options,'primary',{present:false}),base);checks++;
const original='function main(c) { c.custom=123; return c; }\r\n';
const script=r.makeScript(original,entries,'custom',options,'primary',{present:false});
check(r.stripScript(script)===original,'Script cleanup restores original bytes');
check(r.makeScript(script,entries,'custom',options,'primary',{present:false})===script,'Script rewrite is idempotent');
check(r.makeScript(script,[],null,options,'primary',{present:false})===original,'Empty routing removes persistent extension');
const context=vm.createContext({});new vm.Script(script).runInContext(context);const emitted=context.main(structuredClone(base));
check(emitted.custom===123,'Existing user script retained');
check(JSON.stringify(emitted.rules)===JSON.stringify(config.rules),'Persistent script matches runtime rules');
const engineScript=r.makeScript(original,[],'engine',options,'primary',{present:false});const engineVm=vm.createContext({});new vm.Script(engineScript).runInContext(engineVm);
const another=structuredClone(base);another['proxy-groups'][0].name='new-profile';
check(engineVm.main(another)['proxy-groups'].find(g=>g.name===r.routeName('engine')).proxies[0]==='new-profile','Profile switches retain managed default');
check(r.routeOfChains([r.routeName('socks')],options)==='socks','Custom route recognized');
check(r.routeOfChains(['DIRECT'],options)==='Direct','Direct connection recognized');
check(r.routeOfChains(['REJECT'],options)==='Blocked','Blocked connection recognized');
check(r.ruleMatches({type:'ProcessPath',payload:entries[0].path.toUpperCase(),proxy:r.routeName('socks')},entries[0]),'Case-insensitive Windows paths');
throws(()=>r.normalizeEntry('relative.exe','Direct',options));throws(()=>r.normalizeEntry('C:\\bad,rule.exe','Direct',options));throws(()=>r.normalizeEntry('C:\\a.exe','deleted',options));
throws(()=>r.makeConfig(base,[{path:options.Profiles[0].CorePath,route:'custom'}],null,options,'primary',{}));
throws(()=>r.makeSpec([entries[0],entries[0]],null,options,'',null));
const renamed=structuredClone(options);renamed.Profiles[1].Name='New name';check(r.fingerprint(entries,'custom',options)===r.fingerprint(entries,'custom',renamed),'Renaming does not invalidate route identity');
renamed.Profiles[1].Port=9090;check(r.fingerprint(entries,'custom',options)!==r.fingerprint(entries,'custom',renamed),'Changed endpoint must reload before claiming loaded');
const clean={Version:3,Profiles:[],Routing:{Adapter:'none',ProfileId:''}};check(r.normalizeOptions(clean).Profiles.length===0,'Fresh empty install accepted');
const fixedOptions=structuredClone(options);fixedOptions.Routing.UnifiedMode='gateway';fixedOptions.Profiles[1].CorePath='C:\\Apps\\upstream.exe';
const fixed=r.makeConfig(base,entries,'custom',fixedOptions,'primary',{present:false});
check(fixed.rules[0]==='PROCESS-PATH,C:\\Apps\\core.exe,'+r.routeName('Direct')&&fixed.rules[1]==='PROCESS-PATH,C:\\Apps\\upstream.exe,'+r.routeName('Direct'),'Proxy kernels bypass the selected upstream to prevent a loop');
const sample=[
 {id:'old',start:'2026-09-09',metadata:{processPath:entries[0].path},chains:[r.routeName('custom')]},
 {id:'target',start:'2026-09-09',metadata:{processPath:entries[0].path},chains:[r.routeName('socks')]},
 {id:'other',start:'2026-09-09',metadata:{processPath:entries[1].path},chains:[r.routeName('custom')]},
 {id:'unidentified',start:'2026-09-09',metadata:{},chains:[r.routeName('custom')]}
];
const reconnect=r.selectReconnectConnections(sample,entries[0].path.toUpperCase(),'socks',options);
check(reconnect.length===1&&reconnect[0].id==='old','Reconnect only selects old-route connections of the exact executable, never other apps, current route or unidentified connections');
throws(()=>r.makeSpec([{path:'C:\\Apps\\temporary\\..\\core.exe',route:'custom'}],null,options,'',null));
throws(()=>r.makeSpec([{path:'C:\\Apps\\same.exe',route:'custom'},{path:'C:/Apps/other/../same.exe',route:'socks'}],null,options,'',null));
const identity={Version:1,Kind:'Package',PackageFamilyName:'Fixture_123',PackageVerified:true,Exists:true,untrusted:'discard'};
assert.deepEqual(r.normalizeIdentity(identity),{Version:1,Kind:'Package',PackageFamilyName:'Fixture_123',Exists:true,PackageVerified:true});checks++;
check(r.fingerprint(entries,'custom',options)===r.fingerprint(entries.map(e=>({...e,identity})),'custom',options),'Saving application identity does not alter the active route fingerprint');
// Exercise status through a real isolated named-pipe HTTP server, including independent API failures.
async function statusEvidence(){
 const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),http=require('node:http');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'FlowSwitch-RoutingEvidence-')),pipe='\\\\.\\pipe\\ProxySwitch-Test-'+path.basename(root);
 const previous={};for(const key of ['PROXY_SWITCH_DATA_DIR','PROXY_SWITCH_TEST_ENGINE_DIR','PROXY_SWITCH_TEST_PIPE','PROXY_SWITCH_PROFILES'])previous[key]=process.env[key];
 Object.assign(process.env,{PROXY_SWITCH_DATA_DIR:root,PROXY_SWITCH_TEST_ENGINE_DIR:root,PROXY_SWITCH_TEST_PIPE:pipe,PROXY_SWITCH_PROFILES:JSON.stringify(options)});
 const liveRules=entries.map(e=>({type:'ProcessPath',payload:e.path,proxy:r.routeName(e.route)})).concat({type:'Match',proxy:r.routeName('custom')});
 fs.writeFileSync(path.join(root,'app-rules.json'),JSON.stringify({version:2,installed:true,entries,defaultRoute:'custom',fingerprint:r.fingerprint(entries,'custom',options)}));
 let failure='',malformed='',shadowed=false;
 const server=http.createServer((req,res)=>{
  if(req.url===failure){res.writeHead(503);res.end('{}');return;}
  const values={'/configs':{'mixed-port':7890,mode:'rule'},'/rules':{rules:shadowed?[{type:'Match',proxy:'DIRECT'},...liveRules]:liveRules},'/connections':{connections:[{id:'fixture',start:'2026-09-11T00:00:00Z',metadata:{processPath:entries[0].path,sourcePort:'42000',sourceIP:'127.0.0.1',destinationIP:'192.0.2.2',destinationPort:'443'},chains:[r.routeName('socks')]}]}};
  res.setHeader('Content-Type','application/json');res.end(JSON.stringify(req.url===malformed?{}:values[req.url]||{}));
 });
 try{
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(pipe,resolve);});
  delete require.cache[require.resolve('./AppRouter.cjs')];const router=require('./AppRouter.cjs');
  const lockFile=path.join(root,'app-rules.lock');fs.writeFileSync(lockFile,JSON.stringify({pid:process.pid,startTicks:'1',token:'reused-pid'}));
  await router.withMutationLock(async()=>{
   check(JSON.parse(fs.readFileSync(lockFile)).startTicks!=='1','Clash rule mutation reclaims stale lock identity even when the PID was reused');
   await assert.rejects(()=>router.withMutationLock(async()=>{}),/正在更新/);checks++;
  });
  check(!fs.existsSync(lockFile),'Completed rule mutation releases only its own token');
  const departed=require('node:child_process').spawnSync(process.execPath,['-e',''],{windowsHide:true,stdio:'ignore'});
  assert.equal(departed.status,0);fs.writeFileSync(lockFile,JSON.stringify({pid:departed.pid,startTicks:'1',token:'departed-writer'}));
  await router.withMutationLock(async()=>{});check(!fs.existsSync(lockFile),'A departed writer lock is reclaimed before the next Clash rule mutation');
  const unknownOwner=JSON.stringify({pid:process.pid,startTicks:'1',token:'query-unavailable'});fs.writeFileSync(lockFile,unknownOwner);
  const realSystemRoot=process.env.SystemRoot;
  try{
   process.env.SystemRoot=path.join(root,'missing-system');delete require.cache[require.resolve('./IndependentRouter.cjs')];
   await assert.rejects(()=>router.withMutationLock(async()=>{}),/核对.*身份/);checks++;
   check(fs.readFileSync(lockFile,'utf8')===unknownOwner,'Unavailable identity query never deletes an uncertain lock owner');
  }finally{process.env.SystemRoot=realSystemRoot;delete require.cache[require.resolve('./IndependentRouter.cjs')];fs.unlinkSync(lockFile);}
  const beforeState=fs.readFileSync(path.join(root,'app-rules.json'),'utf8');
  await assert.rejects(()=>router.transaction(entries,'custom',sha256('stale-preview')),/规则已在预览后改变/);checks++;
  await assert.rejects(()=>router.transaction(entries,'custom',sha256(beforeState),sha256('stale-settings')),/代理设置已在预览后改变/);checks++;
  check(fs.readFileSync(path.join(root,'app-rules.json'),'utf8')===beforeState,'External state invalidates engine repair before any configuration write');
  let state=await router.status();check(state.available&&state.rulesAvailable&&state.connectionsAvailable&&state.entries[0].loaded,'Controller, rules and connections have independent positive evidence');
  check(state.connections[0].sourceAddress==='127.0.0.1'&&state.connections[0].destinationPort===443,'Connection endpoint evidence survives the controller adapter');
  failure='/connections';state=await router.status();check(state.available&&state.rulesAvailable&&state.entries[0].loaded&&!state.connectionsAvailable&&!!state.connectionError,'Connection API failure does not erase loaded rules or claim observed zero connections');
  failure='/rules';state=await router.status();check(state.available&&!state.rulesAvailable&&state.entries[0].loaded===null&&state.entries[0].loadState==='unknown'&&state.connectionsAvailable&&state.connections.length===1,'Rule API failure preserves observed traffic and marks load evidence unknown');
  failure='';malformed='/connections';state=await router.status();check(!state.connectionsAvailable&&state.entries[0].loaded,'Malformed connection payload is unknown, never an empty successful observation');
  malformed='';shadowed=true;state=await router.status();check(state.rulesAvailable&&state.entries.every(e=>e.loaded===false)&&state.defaultLoaded===false,'Rules shadowed by an earlier MATCH must not be reported loaded');
  shadowed=false;failure='/configs';state=await router.status();check(!state.available&&!state.rulesAvailable&&!state.connectionsAvailable&&state.entries[0].loaded===null,'Unavailable controller leaves status unknown rather than declaring rules unloaded');
  const emptyState=JSON.stringify({version:2,installed:false,entries:[],defaultRoute:null});fs.writeFileSync(path.join(root,'app-rules.json'),'\uFEFF'+emptyState);
  const noChange=await router.transaction([],null,sha256(emptyState));check(noChange.stateHash===sha256(emptyState),'Successful engine no-op returns the exact UTF8 state identity without a BOM');
 }finally{
  await new Promise(resolve=>server.close(resolve));
  for(const [key,value] of Object.entries(previous)){if(value===undefined)delete process.env[key];else process.env[key]=value;}
  delete require.cache[require.resolve('./AppRouter.cjs')];
 }
}
async function independentEvidence(){
 const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),http=require('node:http'),net=require('node:net');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'FlowSwitch-IndependentEvidence-')),previous=process.env.PROXY_SWITCH_DATA_DIR;
 process.env.PROXY_SWITCH_DATA_DIR=root;delete require.cache[require.resolve('./IndependentRouter.cjs')];const router=require('./IndependentRouter.cjs');
 const entrance=net.createServer(socket=>socket.end());let server;
 try{
  await new Promise(resolve=>entrance.listen(0,'127.0.0.1',resolve));
  const o=structuredClone(options);o.Routing.Adapter='standalone';o.Profiles[0].Port=entrance.address().port;
  fs.writeFileSync(path.join(root,'config.json'),JSON.stringify(o));
  fs.writeFileSync(path.join(root,'app-rules.json'),JSON.stringify({version:2,installed:true,entries,defaultRoute:'custom'}));
  const beforeState=fs.readFileSync(path.join(root,'app-rules.json'),'utf8');
  await assert.rejects(()=>router.main({action:'replace',entries,defaultRoute:'custom',expectedStateHash:sha256('stale-preview')}),/规则已在预览后改变/);checks++;
  await assert.rejects(()=>router.main({action:'replace',entries,defaultRoute:'custom',expectedStateHash:sha256(beforeState),expectedSettingsHash:sha256('stale-settings')}),/代理设置已在预览后改变/);checks++;
  check(fs.readFileSync(path.join(root,'app-rules.json'),'utf8')===beforeState&&!fs.existsSync(router.CONFIG),'Independent repair checks preview state inside its lock before writing config');
  const liveRules=entries.map(e=>({type:'ProcessPath',payload:e.path,proxy:r.routeName(e.route)})).concat({type:'Match',proxy:r.routeName('custom')});
  let failure='',shadowed=false;
  server=http.createServer((req,res)=>{
   if(req.url===failure||(req.method==='DELETE'&&failure==='DELETE')){res.writeHead(503);res.end('{}');return;}
   const values={'/configs':{'mixed-port':o.Profiles[0].Port,mode:'rule'},'/rules':{rules:shadowed?[{type:'Match',proxy:'DIRECT'},...liveRules]:liveRules},'/connections':{connections:[{id:'fixture-old',start:'2026-09-11T00:00:00Z',metadata:{processPath:entries[0].path,sourcePort:'42000'},chains:['FS-Up-custom']}]},'/proxies':{proxies:{[r.routeName('custom')]:{now:'FS-Up-custom'},[r.routeName('socks')]:{now:'FS-Up-socks'}}}};
   res.end(JSON.stringify(values[req.url]||{}));
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(router.PIPE,resolve);});
  let state=await router.status();check(state.available&&state.entries[0].loaded&&state.connectionsAvailable,'Independent adapter verifies its isolated listener and controller');
  failure='/connections';state=await router.status();check(state.available&&state.entries[0].loaded&&!state.connectionsAvailable,'Independent connection read failure preserves known loaded rules');
  failure='/rules';state=await router.status();check(state.available&&state.entries[0].loaded===null&&state.connectionsAvailable&&state.connections.length===1,'Independent rule read failure preserves connection evidence');
  failure='/proxies';state=await router.status();check(state.available&&state.defaultLoaded&&!state.proxiesAvailable&&state.effectiveDefaultRoute==='Unknown','Independent selector read failure does not invent a usable exit');
  failure='';shadowed=true;state=await router.status();check(!state.entries[0].loaded,'Independent program rule behind MATCH is not loaded');
  await assert.rejects(()=>router.main({action:'reconnect-plan',path:entries[0].path}),/未验证/);checks++;
  shadowed=false;await assert.rejects(()=>router.main({action:'reconnect-plan',path:o.Profiles[0].CorePath}),/代理/);checks++;
  const plan=await router.main({action:'reconnect-plan',path:entries[0].path});failure='DELETE';
  const result=await router.main({action:'reconnect',plan});check(result.ok===false&&result.closed===0&&result.failed===1,'Independent DELETE failure is reported without claiming success');
 }finally{
  if(server)await new Promise(resolve=>server.close(resolve));await new Promise(resolve=>entrance.close(resolve));
  if(previous===undefined)delete process.env.PROXY_SWITCH_DATA_DIR;else process.env.PROXY_SWITCH_DATA_DIR=previous;
  delete require.cache[require.resolve('./IndependentRouter.cjs')];
 }
}
statusEvidence().then(independentEvidence).then(()=>console.log('PASS: '+checks+' routing assertions; no real network writes.')).catch(error=>{console.error(error.stack);process.exitCode=1;});
