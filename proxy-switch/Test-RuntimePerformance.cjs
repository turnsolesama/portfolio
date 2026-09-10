'use strict';
const fs=require('fs'),path=require('path'),os=require('os'),http=require('http'),net=require('net');
const {spawn}=require('child_process');const {performance}=require('perf_hooks');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function worker(app,core){
 const data=fs.mkdtempSync(path.join(os.tmpdir(),'FlowSwitch-Perf-'));process.env.PROXY_SWITCH_DATA_DIR=data;
 const owned=path.join(data,'BenchmarkEngine.exe');fs.copyFileSync(core,owned);
 const body=Buffer.alloc(256*1024,42),tiny=Buffer.alloc(1024,42);
 const server=http.createServer((req,res)=>{const b=req.url.includes('latency')?tiny:body;res.writeHead(200,{'Content-Length':b.length});res.end(b);});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const upstream=server.address().port;
 const reserve=net.createServer();await new Promise(r=>reserve.listen(0,'127.0.0.1',r));const port=reserve.address().port;await new Promise(r=>reserve.close(r));
 const settings={Version:3,Profiles:[{Id:'gateway',Name:'Gateway',Protocol:'http',Host:'127.0.0.1',Port:port,CorePath:owned},{Id:'upstream',Name:'Fixture',Protocol:'http',Host:'127.0.0.1',Port:upstream}],Routing:{Adapter:'standalone',ProfileId:'gateway',UnifiedMode:'gateway',Failover:{Enabled:true,Order:['upstream'],AllowDirect:false}}};
 fs.writeFileSync(path.join(data,'config.json'),JSON.stringify(settings));fs.writeFileSync(path.join(data,'app-rules.json'),JSON.stringify({version:2,entries:[],defaultRoute:'Direct',installed:true}));
 const router=require(path.join(app,'IndependentRouter.cjs'));const agent=new http.Agent({keepAlive:true,maxSockets:8});
 const request=route=>new Promise((resolve,reject)=>{const q=http.get({host:'127.0.0.1',port,path:'http://127.0.0.1:'+upstream+route,headers:{Host:'127.0.0.1:'+upstream},agent,timeout:5000},r=>{let bytes=0;r.on('data',b=>bytes+=b.length);r.on('end',()=>r.statusCode===200?resolve(bytes):reject(Error('HTTP '+r.statusCode)));});q.on('error',reject);q.on('timeout',()=>q.destroy(Error('timeout')));});
 try{const begin=performance.now();await router.start();const readyMs=performance.now()-begin;for(let i=0;i<20;i++)await request('/latency');const latencies=[],rates=[];
 for(let round=0;round<5;round++){for(let i=0;i<40;i++){const t=performance.now();await request('/latency');latencies.push(performance.now()-t);}const t=performance.now();let next=0,bytes=0;await Promise.all(Array.from({length:8},async()=>{while(next++<128)bytes+=await request('/bulk');}));rates.push(bytes/1048576/((performance.now()-t)/1000));}
 return {readyMs,latencies,rates};
 }finally{agent.destroy();await router.main({action:'stop'});for(let i=0;i<40;i++){const available=(await router.status()).available;if(!available)break;await delay(100);}server.closeAllConnections();await new Promise(r=>server.close(r));}
}
const median=a=>{a=[...a].sort((x,y)=>x-y);return a[Math.floor(a.length/2)];};
const percentile=(a,p)=>{a=[...a].sort((x,y)=>x-y);return a[Math.floor((a.length-1)*p)];};
async function child(node,app,core){return new Promise((resolve,reject)=>{const env={...process.env};delete env.NODE_OPTIONS;delete env.NODE_PATH;const p=spawn(node,[__filename,'--worker',app,core],{windowsHide:true,env,stdio:['ignore','pipe','pipe']});let out='',err='';p.stdout.on('data',b=>out+=b);p.stderr.on('data',b=>err+=b);p.on('error',reject);p.on('exit',code=>{if(code)return reject(Error(err||out));try{resolve(JSON.parse(out));}catch(e){reject(e);}});});}
async function main(){const [baseApp,baseNode,baseCore,newApp,newNode,newCore,output]=process.argv.slice(2);if(!output)throw Error('Arguments: baseline-app baseline-node baseline-core candidate-app candidate-node candidate-core output.json');const results={baseline:[],candidate:[]};
 for(let round=0;round<3;round++){for(const kind of (round%2?['candidate','baseline']:['baseline','candidate'])){results[kind].push(await child(kind==='baseline'?baseNode:newNode,kind==='baseline'?baseApp:newApp,kind==='baseline'?baseCore:newCore));process.stdout.write('Completed '+kind+' round '+(round+1)+'\n');}}
 const summarize=r=>({coreReadyMedianMs:median(r.map(x=>x.readyMs)),latencyMedianMs:median(r.flatMap(x=>x.latencies)),latencyP95Ms:percentile(r.flatMap(x=>x.latencies),.95),throughputMedianMiBps:median(r.flatMap(x=>x.rates))});
 const report={scope:'Same host, alternating runs; loopback HTTP, 8 concurrent streams, 256 KiB payload; 600 latency samples and 15 throughput batches per version. Not a real Internet speed or all-hardware guarantee.',baseline:summarize(results.baseline),candidate:summarize(results.candidate)};
 report.throughputRatio=report.candidate.throughputMedianMiBps/report.baseline.throughputMedianMiBps;
 fs.writeFileSync(output,JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
}
if(process.argv[2]==='--worker')worker(process.argv[3],process.argv[4]).then(x=>console.log(JSON.stringify(x))).catch(e=>{console.error(e);process.exitCode=1;});else main().catch(e=>{console.error(e);process.exitCode=1;});
