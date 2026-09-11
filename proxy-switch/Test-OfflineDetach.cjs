'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto'),http=require('node:http'),net=require('node:net');
const yaml=require('./vendor/js-yaml');
const qa=fs.mkdtempSync(path.join(os.tmpdir(),'FlowSwitch-OfflineDetach-')),data=path.join(qa,'data'),engine=path.join(qa,'engine'),pipe='\\\\.\\pipe\\ProxySwitch-Test-'+crypto.randomUUID();
fs.mkdirSync(data);fs.mkdirSync(path.join(engine,'profiles'),{recursive:true});
Object.assign(process.env,{PROXY_SWITCH_DATA_DIR:data,PROXY_SWITCH_TEST_ENGINE_DIR:engine,PROXY_SWITCH_TEST_PIPE:pipe});
const r=require('./AppRouter.cjs');let checks=0;
function check(value,message){assert.ok(value,message);checks++;}
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const files={runtime:path.join(engine,'clash-verge.yaml'),script:path.join(engine,'profiles','Script.js'),state:path.join(data,'app-rules.json'),settings:path.join(data,'config.json')};
const options={Version:3,Profiles:[{Id:'clash',Name:'Clash fixture',Protocol:'http',Host:'127.0.0.1',Port:29988,CorePath:path.join(qa,'missing-unique-fixture-core.exe')},{Id:'b',Name:'B',Protocol:'http',Host:'127.0.0.1',Port:29989}],Routing:{Adapter:'clash-verge',ProfileId:'clash',UnifiedMode:'gateway'}};
const entries=[{path:'C:\\Fixture\\ChatGPT.exe',route:'clash'}],originalScript='function main(config) { config.userField = "preserved"; return config; }\r\n';
const base={mode:'rule','mixed-port':options.Profiles[0].Port,secret:'PRIVATE_FIXTURE_SECRET_DO_NOT_EMIT',dns:{enable:true,nameserver:['1.1.1.1']},proxies:[{name:'SubscriptionNode',type:'http',server:'proxy.example.invalid',port:8080,username:'fixture-user',password:'PRIVATE_FIXTURE_PASSWORD'}],'proxy-groups':[{name:'Primary',type:'select',proxies:['SubscriptionNode']}],rules:['DOMAIN,example.com,DIRECT','MATCH,Primary']};
function reset(){
 const state={version:2,installed:true,entries,defaultRoute:'b',primary:'Primary',originalFind:{present:false},fingerprint:r.fingerprint(entries,'b',options)};
 const runtime=r.makeConfig(base,entries,'b',options,'Primary',state.originalFind),script=r.makeScript(originalScript,entries,'b',options,'Primary',state.originalFind);
 fs.writeFileSync(files.runtime,'\uFEFF'+yaml.dump(runtime,{lineWidth:-1,noRefs:true}));fs.writeFileSync(files.script,'\uFEFF'+script);fs.writeFileSync(files.state,'\uFEFF'+JSON.stringify(state,null,2));fs.writeFileSync(files.settings,'\uFEFF'+JSON.stringify(options,null,2));
 process.env.PROXY_SWITCH_PROFILES=JSON.stringify(options);
 return {state,runtime,script,bytes:Object.fromEntries(Object.entries(files).map(([key,file])=>[key,fs.readFileSync(file)]))};
}
function request(){return {expectedStateHash:r.stateHash(fs.readFileSync(files.state,'utf8')),expectedSettingsHash:r.stateHash(fs.readFileSync(files.settings,'utf8'))};}
function unchanged(before,message){check(Object.entries(before).every(([key,value])=>fs.readFileSync(files[key]).equals(value)),message);}
const testOffline={offline:async()=>{}};
async function rejects(action,pattern){await assert.rejects(action,pattern);checks++;}
async function freePort(){const server=net.createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const port=server.address().port;await new Promise(resolve=>server.close(resolve));return port;}
(async()=>{
 options.Profiles[0].Port=await freePort();base['mixed-port']=options.Profiles[0].Port;
 let start=reset(),plan=r.planOfflineDetach(yaml.dump(start.runtime),start.script,start.state,options);
 check(plan.script===originalScript,'Only the byte-verifiable managed Script.js suffix is removed');
 assert.deepEqual(yaml.load(plan.runtime),base);checks++;
 check(!JSON.parse(plan.state).installed&&JSON.parse(plan.state).entries.length===0,'Detached FlowSwitch state releases installed external rules');
 const runtimeExternal=structuredClone(start.runtime);runtimeExternal['find-process-mode']='off';runtimeExternal['external-custom']={preserve:true};
 const detachedExternal=yaml.load(r.planOfflineDetach(yaml.dump(runtimeExternal),start.script,start.state,options).runtime);
 check(detachedExternal['find-process-mode']==='off'&&detachedExternal['external-custom'].preserve,'Independent process-mode and other external changes are retained');
 assert.throws(()=>r.planOfflineDetach(yaml.dump(start.runtime),start.script.replace('var __pswOriginalMain','var __userChangedOriginalMain'),start.state,options),/已改变/);checks++;
 const collision=structuredClone(start.runtime);collision.proxies.push({name:'PSW-App-unknown-owner',type:'direct'});
 assert.throws(()=>r.planOfflineDetach(yaml.dump(collision),start.script,start.state,options),/不符/);checks++;
 const references=structuredClone(start.runtime);references['proxy-groups'].push({name:'UserReference',type:'select',proxies:['PSW-App-route-b']});
 assert.throws(()=>r.planOfflineDetach(yaml.dump(references),start.script,start.state,options),/引用/);checks++;
 assert.throws(()=>r.planOfflineDetach(yaml.dump(start.runtime),start.script+'\n// >>> ProxySwitch application routing >>>',start.state,options),/标记异常/);checks++;
 assert.throws(()=>r.planOfflineDetach(yaml.dump(start.runtime),start.script,{...start.state,fingerprint:'bad'},options),/指纹/);checks++;
 await rejects(()=>r.detachOffline({}),/精确校验/);unchanged(start.bytes,'Missing CAS expectations cannot modify external files');
 await rejects(()=>r.detachOffline({...request(),expectedStateHash:sha('stale')},testOffline),/预览后改变/);unchanged(start.bytes,'A stale state expectation does not change files');
 await rejects(()=>r.detachOffline({...request(),expectedSettingsHash:sha('stale')},testOffline),/设置已在预览后改变/);unchanged(start.bytes,'A stale settings expectation does not change files');
 const server=http.createServer((req,res)=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify({'mixed-port':options.Profiles[0].Port,mode:'rule'}));});
 await new Promise(resolve=>server.listen(pipe,resolve));
 try{await rejects(()=>r.detachOffline(request()),/仍在线/);unchanged(start.bytes,'A live named-pipe controller prevents offline detachment without reload');}finally{await new Promise(resolve=>server.close(resolve));}
 const occupied=net.createServer();await new Promise(resolve=>occupied.listen(options.Profiles[0].Port,'127.0.0.1',resolve));
 try{await rejects(()=>r.assertExternalOffline(options),/仍运行|仍监听/);checks++;}finally{await new Promise(resolve=>occupied.close(resolve));}
 await r.assertExternalOffline(options);checks++;
 const running=structuredClone(options);running.Profiles[0].CorePath=process.execPath;
 await rejects(()=>r.assertExternalOffline(running),/仍运行/);
 const oldSystemRoot=process.env.SystemRoot;process.env.SystemRoot=path.join(qa,'unavailable-system-query');
 try{await rejects(()=>r.assertExternalOffline(options),/离线状态核验未完成/);unchanged(start.bytes,'Unavailable limited-query helper cannot be treated as an offline core');}finally{if(oldSystemRoot===undefined)delete process.env.SystemRoot;else process.env.SystemRoot=oldSystemRoot;}
 start=reset();const detached=await r.withMutationLock(()=>r.detachOffline(request()));
 check(detached.detached&&detached.stateHash===r.stateHash(fs.readFileSync(files.state,'utf8')),'Real isolated offline detach uses the exclusive Windows file transaction and returns its state hash');
 check(fs.readFileSync(files.script,'utf8')==='\uFEFF'+originalScript,'Managed script removal preserves original BOM and CRLF content');
 assert.deepEqual(yaml.load(fs.readFileSync(files.runtime,'utf8')),base);checks++;
 check(fs.readFileSync(files.settings).equals(start.bytes.settings),'Offline detach never changes the profile/settings file');
 const manifest=JSON.parse(fs.readFileSync(detached.backup,'utf8'));
 check(!fs.readFileSync(detached.backup,'utf8').includes('PRIVATE_FIXTURE'),'The data-directory receipt contains hashes and no copied proxy credentials');
 check(fs.readFileSync(path.join(engine,'proxy-switch-backups','offline-detach-'+manifest.id,'runtime.before')).equals(start.bytes.runtime),'The original credential-bearing runtime is backed up only in the engine private backup directory');
 check(detached.stateText===fs.readFileSync(files.state,'utf8'),'Exact detached-state text is available to the enclosing migration rollback');
 await r.withMutationLock(()=>r.restoreOfflineDetach({backup:detached.backup,expectedSettingsHash:request().expectedSettingsHash}));unchanged(start.bytes,'Paired offline restore recovers exact original bytes including BOM');
 const repeated=await r.restoreOfflineDetach({backup:detached.backup,expectedSettingsHash:request().expectedSettingsHash},testOffline);check(repeated.restored,'A fully restored receipt is safely idempotent');
 await rejects(()=>r.restoreOfflineDetach({backup:path.join(qa,path.basename(detached.backup)),expectedSettingsHash:request().expectedSettingsHash},testOffline),/只接受/);
 start=reset();const externalDetach=await r.detachOffline(request(),testOffline);fs.appendFileSync(files.script,'\n// user later edit');const externalBytes=fs.readFileSync(files.script);
 await rejects(()=>r.restoreOfflineDetach({backup:externalDetach.backup,expectedSettingsHash:request().expectedSettingsHash},testOffline),/外部文件已改变/);check(fs.readFileSync(files.script).equals(externalBytes),'Restore preserves script edits made by another actor after detachment');
 start=reset();let reads=0;const race={offline:async()=>{if(++reads===2)fs.appendFileSync(files.script,'\n// edit between preview and write');}};
 await rejects(()=>r.detachOffline(request(),race),/静态分离未完成/);check(fs.readFileSync(files.runtime).equals(start.bytes.runtime)&&fs.readFileSync(files.state).equals(start.bytes.state)&&fs.readFileSync(files.script,'utf8').includes('edit between'),'Exclusive multi-file CAS detects a raced script and leaves the other files unchanged');
 start=reset();const rollback=await r.detachOffline(request(),testOffline);fs.appendFileSync(files.settings,' ');const settingsBytes=fs.readFileSync(files.settings);
 await rejects(()=>r.restoreOfflineDetach({backup:rollback.backup,expectedSettingsHash:request().expectedSettingsHash},testOffline),/设置已改变/);check(fs.readFileSync(files.settings).equals(settingsBytes),'Changed settings block restoration even when the caller supplies a fresh hash');
 console.log('PASS: '+checks+' offline external detachment checks; isolated named pipe, listener, real exclusive Windows file handles, and private fixture backups only.');
})().catch(error=>{console.error(error.message);process.exitCode=1;});
