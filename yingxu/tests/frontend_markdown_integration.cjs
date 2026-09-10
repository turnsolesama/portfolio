'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {test}=require('node:test');
function setup() {
  const nodes=new Map(),calls=[],created=[];
  const context=vm.createContext({setTimeout,clearTimeout,console,localStorage:{setItem:()=>{},getItem:()=>null},window:{YingXuMarkdown:{supports:value=>value.length<=500000&&!/\r\n.*(?<!\r)\n/s.test(value),create:options=>{const item={options,value:options.value,destroyed:false,setValue(value){this.value=value;options.onChange(value,{origin:'setValue'});},setMode(mode){this.mode=mode;},mount(parent){this.parent=parent;},destroy(){this.destroyed=true;},isComposing(){return !!this.composing;}};created.push(item);return item;}}},document:{querySelector:key=>{if(!nodes.has(key))nodes.set(key,{innerHTML:'',addEventListener(){},querySelector(){return null;},classList:{toggle(){}}});return nodes.get(key);},querySelectorAll:()=>[]}});
  const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8').replace(/boot\(\);\s*$/,'');
  vm.runInContext(source+`\nrenderTabs=()=>{};renderEditorToolbar=()=>{};renderEditorStatus=()=>{};renderInspector=()=>{};updatePreview=()=>{};toast=()=>{};report=()=>{};refreshProjects=async()=>{};loadItems=()=>{};globalThis.app={state,preserveTextNewlines,editableMarkdown,canUseMarkdownEditor,mountMarkdownEditor,discardUnusedMarkdownEditors,markdownInputReady,saveTab,prepareTabs,persistDrafts,draftStateLabel,markdown,markdownDocumentHeading,markdownToolbarHtml,renderEditorBody,applyMarkdownFormat};`,context);
  return {...context.app,context,nodes,calls,created};
}
function tab(value='# 标题\n\n正文\n') {return {key:'file:1',id:'1',source:'file',item:{kind:'markdown',name:'笔记'},content:{editable:true,etag:'old'},draft:value,mode:'live',dirty:false};}

test('textarea edits retain untouched mixed endings and exact no-op content',()=>{const {preserveTextNewlines:keep}=setup();const mixed='甲\r\n乙\n丙\r丁\r\n';assert.equal(keep(mixed,'甲\n乙\n丙\n丁\n'),mixed);assert.equal(keep(mixed,'甲\n乙改\n丙\n丁\n'),'甲\r\n乙改\n丙\r丁\r\n');assert.equal(keep(mixed,'甲乙\n丙\n丁\n'),'甲乙\n丙\r丁\r\n');});
test('textarea inserts honor CRLF/CR/LF and retain emoji and trailing newlines',()=>{const {preserveTextNewlines:keep}=setup();for(const sep of ['\n','\r','\r\n']){const before=['😀第一行','第二行','',''].join(sep);assert.equal(keep(before,'😀第一行\n插入\n第二行\n\n\n'),['😀第一行','插入','第二行','','',''].join(sep));assert.equal(keep(before,'😀第一行修改\n第二行\n\n'),['😀第一行修改','第二行','',''].join(sep));}});
test('readonly external files and external skills never receive a writable editor',()=>{const s=setup();for(const value of [{...tab(),source:'external'}, {...tab(),source:'skill',item:{kind:'skill'},content:{editable:false}}, {...tab(),item:{kind:'text'}}])assert.equal(s.canUseMarkdownEditor(value),false);assert.equal(s.canUseMarkdownEditor(tab()),true);});
test('mode changes and tab remounts reuse editor state while equal replacement stays clean',()=>{const s=setup(),t=tab();s.state.tabs=[t];s.state.activeKey=t.key;s.mountMarkdownEditor(t,{});const editor=t.markdownEditor;t.mode='edit';s.mountMarkdownEditor(t,{});assert.equal(t.markdownEditor,editor);assert.equal(s.created.length,1);assert.equal(t.dirty,false);editor.options.onChange('修改',{origin:'input'});assert.equal(t.draft,'修改');assert.equal(t.dirty,true);clearTimeout(vm.runInContext('draftTimer',s.context));});
test('only removed tabs destroy their editor and dispose exactly once',()=>{const s=setup(),t=tab(),other={...tab(),key:'file:2'};s.state.tabs=[t,other];s.mountMarkdownEditor(t,{});s.mountMarkdownEditor(other,{});const first=t.markdownEditor,second=other.markdownEditor;s.state.tabs=[other];s.discardUnusedMarkdownEditors();assert.equal(first.destroyed,true);assert.equal(second.destroyed,false);s.discardUnusedMarkdownEditors();assert.equal(other.markdownEditor,second);});
test('composition blocks saves before a request can start',async()=>{const s=setup(),t=tab();t.dirty=true;t.markdownEditor={isComposing:()=>true};vm.runInContext('api=async()=>{throw new Error("must not call");}',s.context);assert.equal(s.markdownInputReady(t),false);assert.equal(await s.saveTab(t),false);assert.equal(t.dirty,true);});
test('an edit arriving during save remains dirty and its newer text is retained',async()=>{const s=setup(),t=tab();s.state.tabs=[t];t.dirty=true;s.context.target=t;vm.runInContext(`api=async(url,options)=>{if(options){target.draft='新编辑';return {etag:'new',content:options.body.content};}return target.item;};`,s.context);assert.equal(await s.saveTab(t),false);assert.equal(t.draft,'新编辑');assert.equal(t.content.etag,'new');assert.equal(t.dirty,true);clearTimeout(vm.runInContext('draftTimer',s.context));});
test('a new composition during an in-flight save cannot approve close or exit',async()=>{const s=setup(),t=tab();s.state.tabs=[t];t.dirty=true;let composing=false;t.markdownEditor={isComposing:()=>composing};s.context.target=t;s.context.startComposition=()=>{composing=true;};vm.runInContext(`api=async(url,options)=>{if(options){startComposition();return {etag:'new',content:options.body.content};}return target.item;};`,s.context);assert.equal(await s.saveTab(t),false);assert.equal(composing,true);clearTimeout(vm.runInContext('draftTimer',s.context));});
test('exit preparation rechecks a previously handled tab after another save',async()=>{const s=setup(),a=tab(),b={...tab(),id:'2',key:'file:2',dirty:true};s.state.tabs=[a,b];s.context.first=a;vm.runInContext(`guardProperties=async()=>true;choose=async()=> 'save';saveTab=async tab=>{tab.dirty=false;first.dirty=true;return true;};`,s.context);assert.equal(await s.prepareTabs([a,b]),false);assert.equal(a.dirty,true);});
test('draft storage failures and oversized drafts never claim to be persisted',()=>{const s=setup(),t=tab();s.state.tabs=[t];t.dirty=true;s.persistDrafts(true);assert.equal(t.draftStorage,'saved');vm.runInContext('localStorage.setItem=()=>{throw Error("quota");}',s.context);s.persistDrafts(true);assert.equal(t.draftStorage,'memory');assert.match(s.draftStateLabel(t),/仅在当前窗口/);vm.runInContext('localStorage.setItem=()=>{}',s.context);t.draft='字'.repeat(600000);s.persistDrafts(true);assert.equal(t.draftStorage,'memory');});
test('reading preview handles CR-only lines and escapes embedded HTML',()=>{const s=setup();assert.match(s.markdown('# 标题\r\r<script>alert(1)</script>'),/<h1>标题<\/h1>/);assert.doesNotMatch(s.markdown('<script>alert(1)</script>'),/<script>/);});
test('filename heading is outside the editable document in every view and never changes its first line',()=>{
  const s=setup(),original='# 原有第一行\r\n\r\n正文\r\n',t=tab(original);t.item.path='C:\\合成项目\\文件名称.md';s.state.tabs=[t];s.state.activeKey=t.key;
  for(const mode of ['live','edit','split','preview']) {
    t.mode=mode;s.renderEditorBody(t);const markup=s.nodes.get('#editorContent').innerHTML;
    assert.match(markup,/<header class="document-heading" contenteditable="false"><h1[^>]*>文件名称<\/h1><\/header>/);
    assert.ok(markup.indexOf('</header>')<markup.indexOf('class="text-workspace'));
    assert.equal(t.draft,original);assert.equal(t.dirty,false);
    if(mode!=='preview')assert.equal(t.markdownEditor.value,original);
  }
});
test('displayed filenames escape markup and editable SKILL uses its name without changing YAML',()=>{
  const s=setup(),t={...tab('---\nname: 规范\n---\n正文'),source:'skill',item:{kind:'skill',name:'规范 <script>',path:'C:\\合成\\SKILL.md'}};
  const heading=s.markdownDocumentHeading(t);assert.match(heading,/规范 &lt;script&gt;/);assert.doesNotMatch(heading,/<script>/);assert.equal(t.draft,'---\nname: 规范\n---\n正文');
});
test('extended toolbar is available to writable source/live/split only and offers all heading levels',()=>{
  const s=setup(),t=tab();for(const mode of ['live','edit','split']) {
    t.mode=mode;const markup=s.markdownToolbarHtml(t);
    for(const command of ['undo','redo','bold','italic','strike','bullet','ordered','task','quote','link','rule','codeblock'])assert.ok(markup.includes(`data-markdown-format="${command}"`));
    for(let level=1;level<=6;level++)assert.ok(markup.includes(`value="heading${level}"`));
  }
  assert.equal(s.markdownToolbarHtml({...t,mode:'preview'}),'');
  assert.equal(s.markdownToolbarHtml({...t,content:{editable:false}}),'');
  assert.equal(s.markdownToolbarHtml({...t,source:'external'}),'');
});
test('toolbar dispatch shares the editor model and rejects preview, readonly and composing edits',()=>{
  const s=setup(),t=tab(),commands=[];t.markdownEditor={format:command=>{commands.push(command);return true;},isComposing:()=>false};s.state.tabs=[t];s.state.activeKey=t.key;
  assert.equal(s.applyMarkdownFormat('undo'),true);t.mode='preview';assert.equal(s.applyMarkdownFormat('bold'),false);
  t.mode='live';t.content.editable=false;assert.equal(s.applyMarkdownFormat('bold'),false);
  t.content.editable=true;t.markdownEditor.isComposing=()=>true;assert.equal(s.applyMarkdownFormat('bold'),false);
  assert.deepEqual(commands,['undo']);
});
