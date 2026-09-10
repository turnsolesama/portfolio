'use strict';
const fs=require('fs'),path=require('path'),os=require('os'),http=require('http'),net=require('net'),assert=require('assert/strict');
const {spawn,spawnSync}=require('child_process');
const sourceCore=process.argv[2];if(!sourceCore||!path.isAbsolute(sourceCore)||!fs.existsSync(sourceCore))throw Error('Pass an installed mihomo executable');
const data=fs.mkdtempSync(path.join(os.tmpdir(),'FlowSwitch-Independent-'));process.env.PROXY_SWITCH_DATA_DIR=data;
// An isolated image name keeps a running production UI from discovering test ports.
const core=path.join(data,'FlowSwitch-TestEngine.exe');fs.copyFileSync(sourceCore,core);
const r=require('./IndependentRouter.cjs');let checks=0;const children=[],servers=[],sockets=[];
const delay=ms=>new Promise(x=>setTimeout(x,ms));
async function until(fn,label,ms=30000){const end=Date.now()+ms;while(Date.now()<end){try{if(await fn()){checks++;console.log('PASS: '+label);return;}}catch{}await delay(150);}throw Error('Timed out: '+label);}
async function upstream(marker,port=0){const record={broken:false,tunnelBroken:false,delay:0,server:null,port:0,sockets:new Set()};const server=http.createServer((req,res)=>{res.writeHead(record.broken?502:200);res.end(marker)});record.server=server;
server.on('connect',(req,s)=>{if(record.tunnelBroken){s.end('HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n');return;}s.write('HTTP/1.1 200 Connection Established\r\n\r\n');s.once('data',()=>{const code=record.broken?'502 Bad Gateway':'200 OK';setTimeout(()=>s.end('HTTP/1.1 '+code+'\r\nContent-Length: 1\r\nConnection: close\r\n\r\n'+marker),record.delay);});});
server.on('connection',s=>{sockets.push(s);record.sockets.add(s);s.on('close',()=>record.sockets.delete(s));});servers.push(server);await new Promise(x=>server.listen(port,'127.0.0.1',x));record.port=server.address().port;return record;}
async function stopUpstream(x){for(const s of x.sockets)s.destroy();await new Promise(done=>x.server.close(done));}
function request(port,url){return new Promise((resolve,reject)=>{const req=http.get({host:'127.0.0.1',port,path:url,headers:{Host:new URL(url).host},timeout:2000},res=>{let b='';res.on('data',c=>b+=c);res.on('end',()=>res.statusCode===200?resolve(b):reject(Error('HTTP '+res.statusCode)));});req.on('error',reject);req.on('timeout',()=>req.destroy(Error('timeout')));});}
async function main(){
 const a=await upstream('A'),b=await upstream('B'),direct=await upstream('D');const reservation=net.createServer();await new Promise(x=>reservation.listen(0,'127.0.0.1',x));const port=reservation.address().port;await new Promise(x=>reservation.close(x));
 const url='http://127.0.0.1:'+direct.port+'/health';process.env.PROXY_SWITCH_TEST_HEALTH_URL=url;
 const o={Version:3,Profiles:[{Id:'gateway',Name:'own',Protocol:'http',Host:'127.0.0.1',Port:port,CorePath:core},{Id:'a',Name:'A',Protocol:'http',Host:'127.0.0.1',Port:a.port},{Id:'b',Name:'B',Protocol:'http',Host:'127.0.0.1',Port:b.port}],Routing:{Adapter:'standalone',ProfileId:'gateway',UnifiedMode:'gateway',Failover:{Enabled:true,Order:['a','b'],AllowDirect:false}}};
 fs.writeFileSync(path.join(data,'config.json'),JSON.stringify(o));fs.writeFileSync(path.join(data,'app-rules.json'),JSON.stringify({version:2,installed:true,entries:[],defaultRoute:'a'}));
 await r.start();await until(async()=>await request(port,url)==='A','initial A');
 const original=JSON.parse(fs.readFileSync(path.join(r.ROOT,'process.json'))).core;
 await stopUpstream(a);await until(async()=>await request(port,url)==='B','A exited: automatic B');
 assert.equal((await r.status()).effectiveDefaultRoute,'b');checks++;
 const recovered=await upstream('A',a.port);await delay(5500);assert.equal(await request(port,url),'B');checks++;
 await r.replace([],'a');await delay(3000);assert.equal(await request(port,url),'B');checks++;
 await r.replace([{path:'C:\\FlowSwitch-Test-Unrelated.exe',route:'Direct'}],'a');await delay(3000);assert.equal(await request(port,url),'B');checks++;
 recovered.delay=2500;const slow=await r.healthCheck('a',o);assert.equal(slow.healthy,true);checks++;recovered.delay=0;
 recovered.tunnelBroken=true;assert.equal(await request(a.port,url),'A');assert.equal((await r.healthCheck('a',o)).healthy,false);checks++;recovered.tunnelBroken=false;
 // A listening but broken proxy must not be called healthy.
 b.broken=true;await until(async()=>await request(port,url)==='A','HTTP failure despite open port: automatic A');
 await stopUpstream(recovered);await until(async()=>(await r.status()).effectiveDefaultRoute==='Blocked','all unavailable blocks');
 await assert.rejects(request(port,url));checks++;
 b.broken=false;await until(async()=>await request(port,url)==='B','backup recovery');
 await r.replace([],'Direct');assert.equal(await request(port,url),'D');checks++;
 const cs=`using System;using System.IO;using System.Net.Sockets;using System.Text;using System.Threading;class Client{static void Main(string[] a){var u=new Uri(a[1]);for(;;){try{using(var tcp=new TcpClient("127.0.0.1",int.Parse(a[0]))){tcp.ReceiveTimeout=2000;var stream=tcp.GetStream();var reader=new StreamReader(stream);var bytes=Encoding.ASCII.GetBytes("CONNECT "+u.Host+":"+u.Port+" HTTP/1.1\\r\\nHost: "+u.Host+":"+u.Port+"\\r\\n\\r\\n");stream.Write(bytes,0,bytes.Length);string line;while((line=reader.ReadLine())!=null&&line.Length>0){}bytes=Encoding.ASCII.GetBytes("GET /probe HTTP/1.1\\r\\nHost: "+u.Host+":"+u.Port+"\\r\\nConnection: close\\r\\n\\r\\n");stream.Write(bytes,0,bytes.Length);line=reader.ReadLine();if(line!=null&&line.Contains("200")){while((line=reader.ReadLine())!=null&&line.Length>0){}var content=reader.ReadToEnd();if(content.Contains("A"))content="A";else if(content.Contains("B"))content="B";else if(content.Contains("D"))content="D";File.AppendAllText(a[2],content+"\\n");}}}catch{}Thread.Sleep(250);}}}`;
 const csPath=path.join(data,'client.cs'),exe=path.join(data,'First.exe'),exe2=path.join(data,'Second.exe');fs.writeFileSync(csPath,cs);
 const compiled=spawnSync(path.join(process.env.SystemRoot,'Microsoft.NET/Framework64/v4.0.30319/csc.exe'),['/nologo','/target:winexe','/out:'+exe,csPath],{windowsHide:true,encoding:'utf8'});assert.equal(compiled.status,0,compiled.stdout+compiled.stderr);fs.copyFileSync(exe,exe2);
 const one=path.join(data,'one.txt'),two=path.join(data,'two.txt'),last=p=>fs.existsSync(p)?fs.readFileSync(p,'utf8').trim().split('\n').at(-1):'';
 await r.replace([{path:exe,route:'b'}],'Direct');for(const [e,f] of [[exe,one],[exe2,two]])children.push(spawn(e,[String(port),url,f],{windowsHide:true,stdio:'ignore'}));
 await until(()=>last(one)==='B'&&last(two)==='D','per-program B while other direct');
 const freshA=await upstream('A',a.port);b.broken=true;await until(()=>last(one)==='A'&&last(two)==='D','per-program fallback preserves other direct');
 assert.equal(JSON.parse(fs.readFileSync(path.join(r.ROOT,'process.json'))).core,original);checks++;
 const c=await r.api('GET','/configs');assert.equal(c['mixed-port'],port);assert.equal(c.tun.enable,false);checks++;
 const events=JSON.parse(fs.readFileSync(path.join(r.ROOT,'failover-events.json')));assert.ok(events.some(e=>e.from==='a'&&e.to==='b'&&e.reason==='listener-closed'));assert.ok(events.every(e=>!JSON.stringify(e).includes(url)));checks++;
 await r.main({action:'stop'});await until(()=>!fs.existsSync(path.join(r.ROOT,'supervisor.lock')),'supervisor stopped for quick restart');
 await r.start();assert.equal((await r.status()).entries.find(e=>e.path===exe).effectiveRoute,'a');checks++;
 await until(()=>last(one)==='A'&&last(two)==='D','restart retains verified per-program backup');
 console.log('PASS: '+checks+' independent real-core checks, upstream exit, alive-but-broken, fallback recovery, all-failed block, direct, per-program isolation, stable core and port. '+data);
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;}).finally(async()=>{for(const c of children)c.kill();fs.mkdirSync(r.ROOT,{recursive:true});fs.writeFileSync(path.join(r.ROOT,'stop'),'stop');for(const s of sockets)s.destroy();for(const s of servers)if(s.listening)s.close();await delay(3000);});
