const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('frontend/macos.js','utf8');
function load(search) {
  const sent=[], events={}, styles=[];
  const window={addEventListener:(name,fn)=>events[name]=fn};
  const context={window,location:{search},URLSearchParams,console,state:{bootstrap:{token:'local'}} ,
    document:{createElement:()=>({}),head:{appendChild:style=>styles.push(style)}}};
  vm.createContext(context);vm.runInContext(source,context);
  return {context,window,sent,events,styles};
}
const win=load('');assert.equal(win.window.chrome,undefined);assert.equal(win.styles.length,0);
const mac=load('?desktop=macos');assert.equal(mac.window.yingxuMac,true);
mac.window.chrome.webview.postMessage({action:'desktop-ready'});
mac.window.pywebview={api:{post_message:(message,token)=>{mac.sent.push({message,token});return Promise.resolve(true);}}};
mac.events.pywebviewready();assert.equal(mac.sent.length,1);assert.equal(mac.sent[0].token,'local');
mac.window.chrome.webview.postMessage({action:'drag-files',ids:['arbitrary']});assert.equal(mac.sent.length,1);
mac.window.chrome.webview.postMessage({action:'exit-response',requestId:'x',allow:false});assert.equal(mac.sent[1].message.allow,false);
let received;mac.window.chrome.webview.addEventListener('message',event=>received=event.data);
mac.window.yingxuMacReceive({action:'prepare-exit'});assert.equal(received.action,'prepare-exit');
assert.match(mac.styles[0].textContent,/capture-screen/);
assert.match(mac.styles[0].textContent,/data-drag-file/);
console.log('macOS bridge: Windows isolation, queued readiness, unsupported action rejection, close routing and hidden controls passed');
