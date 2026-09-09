'use strict';
// Real isolated mihomo, two local upstreams and two compiled client executables.
// Never uses the user's controller, subscription, Windows proxy or TUN.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),net=require('node:net'),http=require('node:http');
const {spawn,spawnSync}=require('node:child_process');
const assert=require('node:assert/strict');
const core=process.argv[2];
if(!core||!path.isAbsolute(core)||!fs.existsSync(core))throw new Error('Pass the absolute path of an already installed mihomo executable. No download is performed.');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'ProxySwitch-Gateway-'));
const pipe='\\\\.\\pipe\\ProxySwitch-Test-'+path.basename(root);
process.env.PROXY_SWITCH_DATA_DIR=path.join(root,'data');process.env.PROXY_SWITCH_TEST_ENGINE_DIR=root;process.env.PROXY_SWITCH_TEST_PIPE=pipe;
fs.mkdirSync(path.join(root,'profiles'));fs.mkdirSync(process.env.PROXY_SWITCH_DATA_DIR);
const r=require('./AppRouter.cjs'),yaml=require('./vendor/js-yaml');
const children=[],servers=[],sockets=new Set();let checks=0;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,label,timeout=12000){const start=Date.now();while(Date.now()-start<timeout){try{if(await fn()){checks++;return;}}catch{}await delay(100);}throw new Error('Timed out: '+label);}
async function listen(server){servers.push(server);server.on('connection',s=>{sockets.add(s);s.on('close',()=>sockets.delete(s));s.on('error',()=>{});});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));return server.address().port;}
async function upstream(marker){const server=http.createServer();server.on('connect',(req,s)=>{s.write('HTTP/1.1 200 Connection Established\r\n\r\n');setTimeout(()=>{if(!s.destroyed)s.write(marker+'\n');},100);});return listen(server);}
async function socksUpstream(){return listen(net.createServer(s=>{let stage=0,buffer=Buffer.alloc(0);s.on('data',chunk=>{buffer=Buffer.concat([buffer,chunk]);if(stage===0&&buffer.length>=2&&buffer.length>=2+buffer[1]){buffer=buffer.subarray(2+buffer[1]);stage=1;s.write(Buffer.from([5,0]));}if(stage===1&&buffer.length>=10){stage=2;s.write(Buffer.from([5,0,0,1,127,0,0,1,0,0]));setTimeout(()=>{if(!s.destroyed)s.write('SOCKS\n');},100);}});}));}
async function main(){
 const portA=await upstream('A'),portB=await upstream('B'),portSocks=await socksUpstream();
 const directPort=await listen(net.createServer(s=>s.write('DIRECT\n')));
 const reservation=net.createServer();await new Promise(resolve=>reservation.listen(0,'127.0.0.1',resolve));const gatewayPort=reservation.address().port;await new Promise(resolve=>reservation.close(resolve));
 const options={Version:3,Profiles:[{Id:'engine',Name:'Fixture engine',Protocol:'http',Host:'127.0.0.1',Port:gatewayPort,CorePath:core},{Id:'a',Name:'A',Protocol:'http',Host:'127.0.0.1',Port:portA},{Id:'b',Name:'B',Protocol:'http',Host:'127.0.0.1',Port:portB}],Routing:{Adapter:'clash-verge',ProfileId:'engine',UnifiedMode:'gateway'}};
 process.env.PROXY_SWITCH_PROFILES=JSON.stringify(options);
 options.Profiles.push({Id:'socks',Name:'SOCKS',Protocol:'socks5',Host:'127.0.0.1',Port:portSocks});process.env.PROXY_SWITCH_PROFILES=JSON.stringify(options);
 fs.writeFileSync(path.join(root,'clash-verge.yaml'),yaml.dump({'mixed-port':gatewayPort,'external-controller-pipe':pipe,'allow-lan':false,'bind-address':'127.0.0.1',mode:'rule',ipv6:false,'log-level':'silent',dns:{enable:false},tun:{enable:false},proxies:[{name:'origin',type:'http',server:'127.0.0.1',port:portA}],'proxy-groups':[{name:'primary',type:'select',proxies:['origin']}],rules:['MATCH,primary']}));
 fs.writeFileSync(path.join(root,'profiles','Script.js'),'function main(c){return c;}\n');
 const cs=`using System;using System.IO;using System.Net.Sockets;using System.Threading;
 public class Client{public static void Main(string[] a){while(true){try{using(var tcp=new TcpClient("127.0.0.1",int.Parse(a[0]))){var stream=tcp.GetStream();var bytes=System.Text.Encoding.ASCII.GetBytes("CONNECT 127.0.0.1:"+a[1]+" HTTP/1.1\\r\\nHost: 127.0.0.1:"+a[1]+"\\r\\n\\r\\nprobe");stream.Write(bytes,0,bytes.Length);var reader=new StreamReader(stream);string line;while((line=reader.ReadLine())!=null&&line.Length>0){}line=reader.ReadLine();if(line!=null)File.AppendAllText(a[2],line+"\\n");while(reader.Read()!=-1){}}}catch{}Thread.Sleep(150);}}}`;
 const csPath=path.join(root,'Client.cs'),exe1=path.join(root,'First.exe'),exe2=path.join(root,'Second.exe');fs.writeFileSync(csPath,cs);
 const csc=path.join(process.env.SystemRoot,'Microsoft.NET','Framework64','v4.0.30319','csc.exe');
 const compile=spawnSync(csc,['/nologo','/target:winexe','/out:'+exe1,csPath],{windowsHide:true,encoding:'utf8'});assert.equal(compile.status,0,compile.stdout+compile.stderr);fs.copyFileSync(exe1,exe2);
 const kernel=spawn(core,['-d',root,'-f',path.join(root,'clash-verge.yaml')],{windowsHide:true,stdio:'ignore'});children.push(kernel);
 await until(async()=>{await r.api('GET','/version');return true;},'isolated controller');
 await r.transaction([],'a');
 const file1=path.join(root,'first.txt'),file2=path.join(root,'second.txt');
 const values=p=>fs.existsSync(p)?fs.readFileSync(p,'utf8').trim().split(/\r?\n/):[];
 for(const [exe,file] of [[exe1,file1],[exe2,file2]])children.push(spawn(exe,[String(gatewayPort),String(directPort),file],{windowsHide:true,stdio:'ignore'}));
 await until(()=>values(file1)[0]==='A'&&values(file2)[0]==='A','both clients use initial A');
 const ids=children.slice(1).map(c=>c.pid);
 const started=Date.now();await r.transaction([{path:exe1,route:'b'}],'a');
 await until(async()=>{const s=await r.status();return s.entries[0].loaded;},'per-process rule loaded');
 const plan=await r.reconnectPlan(exe1);assert.equal(plan.connections.length,1);checks++;
 const changed=await r.reconnect(plan);assert.equal(changed.closed,1);checks++;
 await until(()=>values(file1).at(-1)==='B','same first process reconnects through B');
 assert.equal(values(file2).length,1);assert.equal(values(file2)[0],'A');checks++;
 assert.deepEqual(children.slice(1).map(c=>c.pid),ids);checks++;
 const repeat=await r.reconnect(plan);assert.equal(repeat.closed,0);checks++;
 const snapshot=await r.reconnectPlan(exe2);
 await r.transaction([],'b');
 await assert.rejects(()=>r.reconnect(snapshot),/线路已改变/);checks++;
 const secondPlan=await r.reconnectPlan(exe2);assert.equal(secondPlan.connections.length,1);checks++;
 await r.reconnect(secondPlan);await until(()=>values(file2).at(-1)==='B','unified B replaces per-process exceptions');
 await r.transaction([],'socks');await r.reconnect(await r.reconnectPlan(exe1));await until(()=>values(file1).at(-1)==='SOCKS','SOCKS5 exit through unchanged gateway');
 await r.transaction([],'Direct');
 await r.reconnect(await r.reconnectPlan(exe1));await until(()=>values(file1).at(-1)==='DIRECT','direct exit through unchanged gateway');
 const conf=await r.api('GET','/configs');assert.equal(conf['mixed-port'],gatewayPort);assert.equal(conf.tun?.enable,false);checks++;
 await assert.rejects(async()=>r.reconnect({...await r.reconnectPlan(exe1),createdAt:Date.now()-61000}),/失效/);checks++;
 const badOptions=structuredClone(options);badOptions.Profiles[0].Port=directPort;process.env.PROXY_SWITCH_PROFILES=JSON.stringify(badOptions);
 assert.equal((await r.status()).available,false);checks++;process.env.PROXY_SWITCH_PROFILES=JSON.stringify(options);
 fs.writeFileSync(path.join(root,'result.json'),JSON.stringify({checks,elapsedMilliseconds:Date.now()-started,first:values(file1),second:values(file2),samePIDs:true,gatewayPortUnchanged:true,tunEnabled:false},null,2));
 console.log('PASS: '+checks+' real gateway checks; same running clients A -> B -> DIRECT, other app preserved, old snapshot rejected. Evidence: '+root);
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;}).finally(async()=>{
 for(const child of children.reverse()){if(child.exitCode===null)child.kill();}
 for(const s of sockets)s.destroy();
 await Promise.all(servers.map(server=>new Promise(resolve=>server.close(resolve))));
});
