'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync(path.join(__dirname,'../frontend/global-search.js'),'utf8');
const escapeHtml = value => String(value).replace(/[&<>"']/g,char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const flush = async () => { for (let i=0;i<8;i++) await Promise.resolve(); };
function deferred() { let resolve,reject; const promise = new Promise((yes,no) => { resolve=yes; reject=no; }); return {promise,resolve,reject}; }
const item = (id='one',overrides={}) => ({type:'item',id,name:`结果 ${id}`,project_id:'project',project_name:'测试项目',snippet:'测试正文',...overrides});
const response = (results=[item()],extra={}) => ({results,total:results.length,total_exact:true,has_more:false,...extra});

function harness(responder = async () => response(),options = {}) {
  let clock = 0, nextTimer = 1, allowed = true;
  const timers = new Map(), closeEvents = [], calls = [], opened = [], toasts = [];
  const document = {activeElement:null};
  class Element {
    constructor(tag='div',parent=null) { this.tag=tag; this.parentNode=parent; this.children=[]; this.attributes={}; this.dataset={}; this.listeners={}; this.value=''; this.textContent=''; this.hidden=false; this.disabled=false; this.open=false; this.isConnected=true; this._html=''; this.nodes=new Map(); this.classes=new Set(); this.classList={toggle:(name,on)=>on?this.classes.add(name):this.classes.delete(name)}; }
    set innerHTML(value) { this._html=value; if(this===results) {this.children=[]; for(const match of value.matchAll(/data-search-result="(\d+)"/g)){const row=new Element('button',this); row.setAttribute('data-search-result',match[1]);row.dataset.searchResult=match[1];this.children.push(row);}} }
    get innerHTML() { return this._html; }
    appendChild(child) { this.children.push(child); child.parentNode=this; return child; }
    setAttribute(name,value) {this.attributes[name]=String(value);}
    removeAttribute(name) {delete this.attributes[name];}
    hasAttribute(name) {return name in this.attributes;}
    addEventListener(name,fn,options={}) {(this.listeners[name] ||= []).push({fn,once:!!options.once});}
    emit(name,event={}) {event.target ||= this;event.preventDefault ||= ()=>{event.prevented=true;};event.stopPropagation ||= ()=>{event.stopped=true;};for(const listener of [...(this.listeners[name]||[])]){if(listener.once)this.listeners[name]=this.listeners[name].filter(value=>value!==listener);listener.fn(event);}return event;}
    querySelector(selector) { if(!this.nodes.has(selector)){const isButton=selector.includes('prev')||selector.includes('next')||selector.includes('close');const node=new Element(isButton?'button':selector.includes('Input')?'input':'div',this);const data=/^\[([^\]]+)\]$/.exec(selector);if(data)node.setAttribute(data[1],'');this.nodes.set(selector,node);}return this.nodes.get(selector); }
    querySelectorAll() {return this.children;}
    contains(target) {for(let node=target;node;node=node.parentNode)if(node===this)return true;return false;}
    closest(selector) {return selector==='button'&&this.tag==='button'?this:null;}
    focus() {document.activeElement=this;this.focusCount=(this.focusCount||0)+1;}
    select() {this.selectedText=true;}
    scrollIntoView() {this.scrolled=true;}
    showModal() {this.open=true;}
    close() {if(this.open){this.open=false;closeEvents.push(()=>this.emit('close'));}}
  }
  let dialog,results;
  document.body = new Element('body');
  document.createElement = tag => {const node=new Element(tag);if(tag==='dialog')dialog=node;return node;};
  const prior = new Element('textarea'); prior.focus();
  const context = vm.createContext({document,window:{},AbortController,setTimeout:(fn,delay=0)=>{const id=nextTimer++;timers.set(id,{fn,at:clock+delay});return id;},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source,context);
  let navigation = async result => {opened.push(result);};
  const app = context.window.YingXuGlobalSearch.install({api:(url,options)=>{calls.push({url,options});return responder(url,options);},openResult:result=>navigation(result),escapeHtml,toast:(...args)=>toasts.push(args),canOpen:()=>allowed,categoryLabel:options.categoryLabel});
  results=dialog.querySelector('#globalSearchResults');
  const input=dialog.querySelector('#globalSearchInput'),status=dialog.querySelector('#globalSearchStatus'),notice=dialog.querySelector('[data-search-notice]');
  const previous=dialog.querySelector('[data-search-prev]'),next=dialog.querySelector('[data-search-next]');
  async function tick(ms=250) {clock+=ms;for(const [id,timer] of [...timers])if(timer.at<=clock){timers.delete(id);timer.fn();}await flush();}
  function type(value) {input.value=value;input.emit('input');}
  function key(key,target=input,extra={}) {return dialog.emit('keydown',{target,key,...extra});}
  function click(target) {dialog.emit('click',{target});}
  async function closeEvent() {while(closeEvents.length)closeEvents.shift()();await flush();}
  return {app,dialog,input,results,status,notice,previous,next,prior,calls,opened,toasts,tick,type,key,click,closeEvent,document,
    allow:value=>{allowed=value;},navigate:fn=>{navigation=fn;}};
}

test('native independent dialog respects the open guard and idle scope needs no request',()=>{
  const h=harness();h.allow(false);assert.equal(h.app.open(),false);assert.equal(h.document.activeElement,h.prior);
  h.allow(true);assert.equal(h.app.open(),true);assert.equal(h.app.isOpen(),true);assert.equal(h.document.activeElement,h.input);
  assert.equal(h.calls.length,0);assert.match(h.dialog.innerHTML,/未保存修改不参与，外部文件修改后需同步项目/);assert.doesNotMatch(h.dialog.innerHTML,/appDialog/);
  assert.match(h.dialog.innerHTML,/maxlength="200"/);
  assert.equal(h.app.open(),true);assert.equal(h.input.selectedText,true);
});
test('input is debounced for 250ms and only q plus fixed paging parameters are sent',async()=>{
  const h=harness();h.app.open();h.type('旧');await h.tick(200);h.type(' 中文 & "关键词" ');await h.tick(249);assert.equal(h.calls.length,0);await h.tick(1);
  assert.equal(h.calls.length,1);const url=new URL(h.calls[0].url,'http://localhost');assert.equal(url.searchParams.get('q'),'中文 & "关键词"');assert.equal(url.searchParams.get('limit'),'20');assert.equal(url.searchParams.get('offset'),'0');assert.equal([...url.searchParams.keys()].length,3);
});
test('editing q invalidates an older response even before the next debounce fires',async()=>{
  const waiting=deferred(),h=harness(()=>waiting.promise);h.app.open();h.type('旧');await h.tick();h.type('新');assert.equal(h.calls[0].options.signal.aborted,true);
  waiting.resolve(response([item('old')]));await flush();assert.equal(h.results.innerHTML,'');assert.match(h.status.textContent,/输入完成/);
});
test('older success and error cannot overwrite a newer query result',async()=>{
  const old=deferred(),newer=deferred();let count=0;const h=harness(()=>++count===1?old.promise:newer.promise);h.app.open();h.type('old');await h.tick();h.type('new');await h.tick();newer.resolve(response([item('new')]));await flush();old.reject(Error('old failure'));await flush();assert.match(h.results.innerHTML,/结果 new/);assert.doesNotMatch(h.status.textContent,/failure/);
});
test('closing invalidates responses and restores prior focus only after native close',async()=>{
  const waiting=deferred(),h=harness(()=>waiting.promise);h.app.open();h.type('query');await h.tick();h.key('Escape');assert.equal(h.dialog.open,false);assert.equal(h.app.isOpen(),true);assert.equal(h.app.open(),false);
  waiting.resolve(response([item('late')]));await flush();assert.equal(h.results.innerHTML,'');await h.closeEvent();assert.equal(h.app.isOpen(),false);assert.equal(h.document.activeElement,h.prior);
  h.app.open();assert.equal(h.input.value,'');assert.equal(h.results.innerHTML,'');
});
test('native cancel closes without navigating and returns keyboard focus',async()=>{
  const h=harness();h.app.open();const event=h.dialog.emit('cancel');assert.equal(event.prevented,true);await h.closeEvent();assert.equal(h.document.activeElement,h.prior);assert.equal(h.opened.length,0);
});
test('keyboard selection opens exactly one result after the queued close event',async()=>{
  const h=harness(async()=>response([item('a'),item('b')]));h.app.open();h.type('q');await h.tick();h.key('ArrowDown');assert.equal(h.input.attributes['aria-activedescendant'],'globalSearchResult1');assert.equal(h.results.children[1].scrolled,true);
  h.key('ArrowUp');h.key('ArrowDown');h.key('Enter');h.key('Enter');assert.equal(h.opened.length,0);assert.equal(h.dialog.open,false);await h.closeEvent();assert.equal(h.opened.length,1);assert.equal(h.opened[0].id,'b');assert.equal(h.app.isOpen(),false);
});
test('result clicks wait for closing and failed navigation is reported without editing data',async()=>{
  const h=harness();h.navigate(async()=>{assert.equal(h.app.isOpen(),false);throw Error('文件已移除');});h.app.open();h.type('q');await h.tick();h.click(h.results.children[0]);assert.equal(h.toasts.length,0);await h.closeEvent();assert.equal(h.toasts[0][0],'文件已移除');assert.equal(h.toasts[0][1],'error');assert.equal(h.calls.length,1);
});
test('results, cross-project origin, snippets and warnings cannot inject HTML',async()=>{
  const evil='<img src=x onerror=alert(1)>',h=harness(async()=>response([item('x',{name:evil,project_name:evil,category:evil,snippet:evil})],{truncated:true,total_exact:false,warnings:[evil]}));h.app.open();h.type('q');await h.tick();
  assert.doesNotMatch(h.results.innerHTML,/<img/);assert.equal((h.results.innerHTML.match(/&lt;img/g)||[]).length,4);assert.match(h.status.textContent,/部分结果/);assert.equal(h.notice.hidden,false);assert.match(h.notice.textContent,/<img/);assert.equal(h.notice.innerHTML,'');
  assert.match(h.status.textContent,/^已找到 1 条 · 部分结果$/);
});
test('category names use the host label callback and remain escaped',async()=>{
  const h=harness(async()=>response([item('x',{category:'characters'})]),{categoryLabel:()=> '角色 <自定义>'});h.app.open();h.type('q');await h.tick();assert.match(h.results.innerHTML,/角色 &lt;自定义&gt;/);assert.doesNotMatch(h.results.innerHTML,/characters/);
});
test('pagination uses 20-item offsets and changing q returns to page one',async()=>{
  const h=harness(async url=>{const offset=Number(new URL(url,'http://local').searchParams.get('offset'));return response(Array.from({length:offset?3:20},(_,i)=>item(String(offset+i))),{total:23,has_more:offset===0});});h.app.open();h.type('q');await h.tick();assert.equal(h.previous.disabled,true);assert.equal(h.next.disabled,false);h.click(h.next);await flush();assert.match(h.calls[1].url,/offset=20$/);assert.equal(h.previous.disabled,false);assert.equal(h.next.disabled,true);h.click(h.previous);await flush();assert.match(h.calls[2].url,/offset=0$/);h.type('other');await h.tick();assert.match(h.calls[3].url,/q=other&limit=20&offset=0$/);
});
test('loading, failure and empty results are explicit and Enter retries a failed request',async()=>{
  const waiting=deferred();let count=0;const h=harness(()=>++count===1?waiting.promise:Promise.resolve(response([])));h.app.open();h.type('q');await h.tick();assert.match(h.status.textContent,/正在搜索/);assert.equal(h.results.attributes['aria-busy'],'true');h.key('Enter');assert.equal(h.calls.length,1);waiting.reject(Error('网络暂不可用'));await flush();assert.match(h.status.textContent,/网络暂不可用/);h.key('Enter');await flush();assert.equal(h.calls.length,2);assert.match(h.status.textContent,/没有找到/);assert.equal(h.next.disabled,true);
});
test('IME does not search or activate candidates until composition has ended',async()=>{
  const h=harness();h.app.open();h.input.emit('compositionstart');h.type('zhong');await h.tick(500);h.key('Enter',h.input,{isComposing:true});h.key('Escape',h.input,{isComposing:true});assert.equal(h.calls.length,0);assert.equal(h.dialog.open,true);h.input.value='中文';h.input.emit('compositionend');await h.tick(249);assert.equal(h.calls.length,0);await h.tick(1);assert.equal(h.calls.length,1);assert.match(h.calls[0].url,/q=%E4%B8%AD%E6%96%87/);
});
test('another modal guard can prevent activation without closing search',async()=>{
  const h=harness();h.app.open();h.type('q');await h.tick();h.allow(false);h.key('Enter');assert.equal(h.dialog.open,true);assert.equal(h.opened.length,0);
});
test('rendering caps each page at 20 entries and rejects unsupported result types',async()=>{
  const h=harness(async()=>response([item('bad',{type:'unknown'}),...Array.from({length:40},(_,i)=>item(String(i)))]));h.app.open();h.type('q');await h.tick();assert.equal(h.results.children.length,19);assert.doesNotMatch(h.results.innerHTML,/结果 bad/);
});
test('a closed and reopened dialog ignores a previous sessions response',async()=>{
  const old=deferred(),h=harness(()=>old.promise);h.app.open();h.type('q');await h.tick();h.key('Escape');await h.closeEvent();h.app.open();old.resolve(response([item('old')]));await flush();assert.equal(h.results.innerHTML,'');assert.match(h.status.textContent,/输入关键词/);
});
