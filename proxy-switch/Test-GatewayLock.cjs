'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const r=require('./IndependentRouter.cjs');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const childMode=process.argv[2];
async function contender(){
 const file=process.argv[3],gate=file+'.critical';
 const end=Date.now()+20000;let owner;
 while(Date.now()<end){try{owner=await r.claimLock(file);break;}catch{await delay(50);}}
 assert.ok(owner,'contender eventually acquires');
 const fd=fs.openSync(gate,'wx');
 try{await delay(150);assert.equal(JSON.parse(fs.readFileSync(file,'utf8')).token,owner.token,'ownership cannot be stolen');}
 finally{fs.closeSync(fd);fs.unlinkSync(gate);await r.releaseLock(file,owner);}
}
async function main(){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'FlowSwitch-Locks-')),file=path.join(root,'mutation.lock');let checks=0;
 const check=(v,label)=>{assert.ok(v,label);checks++;console.log('PASS: '+label);};
 const selfTicks=await r.processStartTicks(process.pid);
 for(const content of ['', '{"pid":', 'null', JSON.stringify({pid:process.pid,startTicks:'1',token:'stale'})]){
  fs.writeFileSync(file,content);const owner=await r.claimLock(file);
  check(JSON.parse(fs.readFileSync(file,'utf8')).token===owner.token,'abandoned empty, truncated, null or reused-PID lock recovers');await r.releaseLock(file,owner);
 }
 for(const owner of [{pid:process.pid,startTicks:selfTicks,token:'active'},{pid:process.pid,token:'legacy'}]){
  const content=JSON.stringify(owner);fs.writeFileSync(file,content);await assert.rejects(r.claimLock(file),/正在更新/);
  check(fs.readFileSync(file,'utf8')===content,'live current or legacy owner remains untouched');fs.unlinkSync(file);
 }
 // Emulate an old writer suspended immediately after exclusive creation.
 const held=fs.openSync(file,'wx');
 try{await assert.rejects(r.claimLock(file),/正在更新/);check(fs.statSync(file).size===0,'open empty legacy writer is never reclaimed');}
 finally{fs.closeSync(held);}
 const recovered=await r.claimLock(file);check(JSON.parse(fs.readFileSync(file)).token===recovered.token,'closed interrupted writer can recover');
 await r.releaseLock(file,{token:'wrong'});check(fs.existsSync(file),'unrelated release cannot remove the owner');await r.releaseLock(file,recovered);
 for(const content of ['',JSON.stringify({pid:process.pid,startTicks:'1',token:'stale'})]){
  fs.writeFileSync(file,content);
  await Promise.all(Array.from({length:8},()=>new Promise((resolve,reject)=>{
   const child=spawn(process.execPath,[__filename,'contender',file],{windowsHide:true,stdio:['ignore','pipe','pipe']});let output='';
   child.stdout.on('data',x=>output+=x);child.stderr.on('data',x=>output+=x);child.on('error',reject);child.on('exit',code=>code===0?resolve():reject(Error('Contender failed: '+output)));
  })));
  check(!fs.existsSync(file)&&!fs.existsSync(file+'.critical'),'eight concurrent recoverers serialize without stealing a new owner');
 }
 console.log('PASS: '+checks+' real Windows lock recovery checks; isolated files and child processes only.');
}
(childMode==='contender'?contender():main()).catch(e=>{console.error(e.stack);process.exitCode=1;});
