'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const {test} = require('node:test');
const root = path.resolve(__dirname,'..');
const dependencies = path.join(root,'tools/markdown-editor/node_modules');
if (!fs.existsSync(path.join(dependencies,'esbuild'))) {
  test('live Markdown development checks require the locked offline build dependencies',{skip:true},()=>{});
} else {
  const esbuild = require(path.join(dependencies,'esbuild'));
  const source = fs.readFileSync(path.join(root,'frontend/live-markdown-source.mjs'),'utf8');
  const bundled = esbuild.buildSync({stdin:{contents:source+'\nexport {buildEditorState,previewDecorations,frontmatterEnd,formatSpec,formatCommand,liveMode,EditorSelection,EditorState,EditorView,Text,markdownKeymap,LivePreviewPlugin,keymap,LocalImageWidget,sourceSelection,insertionSpec};\nexport {ensureSyntaxTree} from "@codemirror/language";\nexport {undo,redo} from "@codemirror/commands";',resolveDir:path.join(root,'frontend'),loader:'js'},nodePaths:[dependencies],bundle:true,write:false,platform:'node',format:'cjs'});
  const loaded = new Module(path.join(root,'work-live-markdown-check.cjs'),module);
  loaded.filename = path.join(root,'work-live-markdown-check.cjs');
  loaded._compile(bundled.outputFiles[0].text,loaded.filename);
  const api = loaded.exports;
  function state(value,mode='live') { return api.buildEditorState(value,mode,'测试').state; }
  function decs(value) { const result=[];api.previewDecorations(value).between(0,value.doc.length,(from,to,dec)=>result.push({from,to,spec:dec.spec}));return result; }
  const replacements = value => decs(value).filter(dec=>dec.from < dec.to && !dec.spec.class);

  test('long continuous quotes add line decorations only inside separate visible ranges',()=>{
    const s=state('> **引用正文**\n'.repeat(5000));assert.ok(api.ensureSyntaxTree(s,s.doc.length,10000));
    const ranges=[{from:s.doc.line(120).from+3,to:s.doc.line(125).to},{from:s.doc.line(3100).from,to:s.doc.line(3102).to}];
    const quotes=[];api.previewDecorations(s,ranges,false).between(0,s.doc.length,(from,to,dec)=>{if(dec.spec.class==='yx-md-quote-line')quotes.push(s.doc.lineAt(from).number);});
    assert.deepEqual(quotes,[120,121,122,123,124,125,3100,3101,3102]);assert.equal(s.sliceDoc(),'> **引用正文**\n'.repeat(5000));
  });
  test('overlapping viewports do not duplicate quote line decorations and CRLF remains unchanged',()=>{
    const original='> 甲\r\n> 乙\r\n> 丙\r\n末尾',s=state(original);const ranges=[{from:0,to:s.doc.line(2).to},{from:s.doc.line(2).from,to:s.doc.line(3).to}];
    const positions=[];api.previewDecorations(s,ranges,false).between(0,s.doc.length,(from,to,dec)=>{if(dec.spec.class==='yx-md-quote-line')positions.push(from);});
    assert.equal(positions.length,3);assert.equal(new Set(positions).size,3);assert.equal(s.sliceDoc(),original);
  });
  test('frontmatter cache reuses immutable document identity across selection and viewport states',()=>{
    const original=state('---\n'+'title: 测试\n'.repeat(1000));let reads=0;
    const doc={length:original.doc.length,lines:original.doc.lines,line:n=>{reads++;return original.doc.line(n);}};
    assert.equal(api.frontmatterEnd({doc}),doc.length);const scanned=reads;assert.equal(scanned,doc.lines);
    for(let i=0;i<20;i++)assert.equal(api.frontmatterEnd({doc}),doc.length);assert.equal(reads,scanned);
    assert.equal(original.update({selection:{anchor:10}}).state.doc,original.doc);
  });
  test('editing an unclosed YAML document invalidates cached end and exposes only the new Markdown body',()=>{
    const original=state('---\ntitle: 测试\n');assert.equal(api.frontmatterEnd(original),original.doc.length);
    const closed=original.update({changes:{from:original.doc.length,insert:'---\n\n**正文**'}}).state;
    assert.notEqual(closed.doc,original.doc);assert.equal(api.frontmatterEnd(closed),closed.doc.line(3).to);
    assert.ok(api.ensureSyntaxTree(closed,closed.doc.length,10000));
    const styled=[];api.previewDecorations(closed,undefined,false).between(0,closed.doc.length,(from,to,dec)=>{if(dec.spec.class==='yx-md-strong')styled.push(closed.doc.sliceString(from,to));});assert.deepEqual(styled,['**正文**']);
    const plain=closed.update({changes:{from:0,to:3,insert:'标题'}}).state;assert.equal(api.frontmatterEnd(plain),-1);assert.equal(api.frontmatterEnd(original),original.doc.length);
  });

  test('line endings, trailing whitespace, Unicode and final newline roundtrip exactly',()=>{
    for (const separator of ['\n','\r\n','\r']) {
      const value=['# 中文标题','字形 😀 与 e\u0301  ','','末尾',''].join(separator);
      assert.equal(api.supports(value),true);
      assert.equal(state(value).sliceDoc(),value);
    }
    assert.equal(state('').sliceDoc(),'');
  });
  test('mixed newlines and oversized documents decline without transforming source',()=>{
    for (const value of ['a\r\nb\nc','a\rb\nc','a\r\nb\rc','文'.repeat(500001)]) assert.equal(api.supports(value),false);
    assert.equal(api.supports('文'.repeat(500000)),true);
    assert.equal(api.supports(null),false);
  });
  test('live decorations style Markdown and hide only single-line inactive syntax',()=>{
    const value='# 标题\n\n**加粗**与*斜体*、~~删除~~和`code`\n\n- [x] 完成\n- 普通\n\n> 引用\n\n最后';
    const original=state(value), s=original.update({selection:{anchor:original.doc.length}}).state;
    const decorated=decs(s), classes=decorated.map(dec=>dec.spec.class||'').join(' ');
    for(const name of ['yx-md-heading-1','yx-md-strong','yx-md-emphasis','yx-md-strike','yx-md-code','yx-md-quote-line']) assert.match(classes,new RegExp(name));
    assert.ok(replacements(s).length>=8);
    assert.ok(decorated.some(dec=>dec.spec.widget?.text==='☑'));
    for (const dec of replacements(s)) assert.equal(s.doc.lineAt(dec.from).number,s.doc.lineAt(dec.to).number);
    assert.equal(s.sliceDoc(),value);
  });
  test('every touched block exposes syntax for multiple selections',()=>{
    const original=state('# 标题\n\n**正文**\n\n末尾');
    const selection=api.EditorSelection.create([api.EditorSelection.cursor(3),api.EditorSelection.range(8,10)]);
    const selected=original.update({selection}).state;
    assert.equal(replacements(selected).length,0);
    assert.ok(decs(selected).some(dec=>dec.spec.class==='yx-md-source-mark'));
  });
  test('source mode contains no preview replacements',()=>{
    assert.equal(decs(state('# 标题\n\n**加粗**','source')).length,0);
  });
  test('YAML, tables, fenced code, images and HTML remain unmodified source',()=>{
    const value='---\ntitle: **yaml**\n---\n\n| **列** | 值 |\n| --- | --- |\n| a | b |\n\n```md\n# **code**\n```\n\n![**图片**](https://example.invalid/a.png)\n\n<div>**html**</div>\n\n末尾';
    const original=state(value),s=original.update({selection:{anchor:original.doc.length}}).state;
    assert.equal(replacements(s).length,0);
    assert.equal(s.sliceDoc(),value);
    assert.equal(decs(s).filter(dec=>dec.spec.class==='yx-md-strong').length,0);
  });
  test('multiline bold formatting and undo retain each supported newline kind',()=>{
    for(const separator of ['\n','\r\n','\r']) {
      let s=state('甲'+separator+'乙');
      s=s.update({selection:{anchor:0,head:s.doc.length}}).state;
      s=s.update(api.formatSpec(s,'bold')).state;
      assert.equal(s.sliceDoc(),'**甲'+separator+'乙**');
      assert.equal(api.undo({get state(){return s;},dispatch(transaction){s=transaction.state;}}),true);
      assert.equal(s.sliceDoc(),'甲'+separator+'乙');
      assert.equal(api.redo({get state(){return s;},dispatch(transaction){s=transaction.state;}}),true);
      assert.equal(s.sliceDoc(),'**甲'+separator+'乙**');
    }
  });
  test('mode changes preserve document, selection and undo history',()=>{
    const config=api.buildEditorState('原稿\r\n末尾','live','测试');
    let s=config.state.update({selection:{anchor:0,head:2}}).state;
    s=s.update(api.formatSpec(s,'italic')).state;
    const selected=s.selection.main, value=s.sliceDoc();
    s=s.update({effects:config.modeSlot.reconfigure(api.liveMode.of('source'))}).state;
    assert.equal(s.sliceDoc(),value);assert.equal(s.selection.main.from,selected.from);assert.equal(s.selection.main.to,selected.to);
    api.undo({get state(){return s;},dispatch(transaction){s=transaction.state;}});
    assert.equal(s.sliceDoc(),'原稿\r\n末尾');
  });
  test('block formatting respects selected lines, can toggle and preserves trailing newline',()=>{
    let s=state('第一行\r\n第二行\r\n');
    s=s.update({selection:{anchor:0,head:s.doc.line(2).from}}).state;
    s=s.update(api.formatSpec(s,'heading2')).state;
    assert.equal(s.sliceDoc(),'## 第一行\r\n第二行\r\n');
    s=s.update(api.formatSpec(s,'heading2')).state;
    assert.equal(s.sliceDoc(),'第一行\r\n第二行\r\n');
    assert.equal(api.formatSpec(s,'unsupported'),null);
  });
  test('block formatting deduplicates lines touched by multiple cursors',()=>{
    let s=state('第一行\n第二行');
    s=s.update({selection:api.EditorSelection.create([api.EditorSelection.cursor(1),api.EditorSelection.cursor(2),api.EditorSelection.cursor(5)])}).state;
    s=s.update(api.formatSpec(s,'bullet')).state;
    assert.equal(s.sliceDoc(),'- 第一行\n- 第二行');
  });
  test('pasted and dropped text follows the document newline convention',()=>{
    for(const separator of ['\r\n','\r','\n']) {
      let s=state('原稿'+separator+'');
      const pasted=s.facet(api.EditorView.clipboardInputFilter).reduce((value,filter)=>filter(value,s),'甲\n乙\r\n丙\r丁');
      s=s.update({changes:{from:s.doc.length,insert:pasted}}).state;
      assert.equal(s.sliceDoc(),'原稿'+separator+['甲','乙','丙','丁'].join(separator));
      assert.equal(api.supports(s.sliceDoc()),true);
    }
  });
  test('italic formatting within bold text preserves the existing bold markers',()=>{
    let s=state('**文字**');s=s.update({selection:{anchor:2,head:4}}).state;
    s=s.update(api.formatSpec(s,'italic')).state;assert.equal(s.sliceDoc(),'***文字***');
  });
  test('mixed prefixed lines are not accidentally nested by a block command',()=>{
    let s=state('- 已有列表\n新行');s=s.update({selection:{anchor:0,head:s.doc.length}}).state;
    s=s.update(api.formatSpec(s,'bullet')).state;assert.equal(s.sliceDoc(),'- 已有列表\n- 新行');
  });
  test('composition start freezes decorations before the first IME document change',()=>{
    const start=state('光标\n\n**中文**'),view={state:start,visibleRanges:[{from:0,to:start.doc.length}],composing:false,compositionStarted:true};
    const plugin=new api.LivePreviewPlugin(view),before=plugin.decorations;
    const transaction=start.update({selection:{anchor:start.doc.length}});view.state=transaction.state;
    plugin.update({view,state:view.state,startState:start,docChanged:false,selectionSet:true,transactions:[transaction]});
    assert.equal(plugin.decorations,before);
    view.compositionStarted=false;
    plugin.update({view,state:view.state,startState:start,docChanged:false,selectionSet:true,transactions:[transaction]});
    assert.notEqual(plugin.decorations,before);
    plugin.destroy();
  });
  test('deferred composition repaint is cancelled when its editor is destroyed',async()=>{
    const initial=state('输入'),calls=[];
    const view={state:initial,visibleRanges:[{from:0,to:initial.doc.length}],composing:false,compositionStarted:false,dispatch:spec=>calls.push(spec)};
    const plugin=new api.LivePreviewPlugin(view);plugin.frozen=true;plugin.finishComposition();plugin.destroy();
    await new Promise(resolve=>setTimeout(resolve,40));assert.equal(calls.length,0);
  });
  test('unfocused editor shows rendered markers even for the retained cursor block',()=>{
    const s=state('# 标题'),all=[];
    api.previewDecorations(s,[{from:0,to:s.doc.length}],false).between(0,s.doc.length,(from,to,value)=>all.push({from,to,spec:value.spec}));
    assert.ok(all.some(dec=>dec.from===0 && dec.to===2 && !dec.spec.class));
    assert.equal(replacements(s).length,0);
  });
  test('editing one list item does not expose the other items source markers',()=>{
    let s=state('- 第一项\n- 第二项\n- 第三项');s=s.update({selection:{anchor:3}}).state;
    const hidden=replacements(s);assert.equal(hidden.length,2);
    assert.ok(hidden.every(dec=>dec.from>=s.doc.line(2).from));
  });
  test('Ctrl B and Ctrl I format before default commands and leave Ctrl F unbound',()=>{
    for(const [key,expected] of [['Mod-b','**文字**'],['Mod-i','*文字*']]) {
      let s=state('文字');s=s.update({selection:{anchor:0,head:2}}).state;
      const bindings=s.facet(api.keymap).flat(),binding=bindings.find(value=>value.key===key);
      const view={get state(){return s;},composing:false,compositionStarted:false,plugin:()=>null,dispatch(spec){s=s.update(spec).state;}};
      assert.equal(binding.run(view),true);assert.equal(s.sliceDoc(),expected);
      assert.ok(!bindings.some(value=>value.key==='Mod-f' || value.key==='Ctrl-f'));
    }
  });
  test('format keyboard commands do not change a composing document',()=>{
    const s=state('拼音'),binding=s.facet(api.keymap).flat().find(value=>value.key==='Mod-b');let changed=false;
    assert.equal(binding.run({state:s,composing:true,dispatch(){changed=true;}}),true);assert.equal(changed,false);
  });
  test('editor classes are managed attributes that survive input and track mode reconfiguration',()=>{
    const config=api.buildEditorState('正文','live','测试');let s=config.state;
    const classes=()=>s.facet(api.EditorView.editorAttributes).map(value=>value.class||'').join(' ');
    assert.match(classes(),/\byx-markdown-editor\b/);assert.doesNotMatch(classes(),/\byx-markdown-source\b/);
    s=s.update({changes:{from:2,insert:'输入'}}).state;
    assert.match(classes(),/\byx-markdown-editor\b/);
    s=s.update({effects:config.modeSlot.reconfigure(api.liveMode.of('source'))}).state;
    assert.match(classes(),/\byx-markdown-editor\b/);assert.match(classes(),/\byx-markdown-source\b/);
    s=s.update({changes:{from:0,insert:'继续'}}).state;
    assert.match(classes(),/\byx-markdown-source\b/);
    s=s.update({effects:config.modeSlot.reconfigure(api.liveMode.of('live'))}).state;
    assert.match(classes(),/\byx-markdown-editor\b/);assert.doesNotMatch(classes(),/\byx-markdown-source\b/);
  });
  test('heading levels replace heading markers and paragraph removes only heading syntax',()=>{
    let s=state('## 已有标题\n正文');
    for(const level of [1,3,6,2]) {s=s.update(api.formatSpec(s,'heading'+level)).state;assert.equal(s.doc.line(1).text,'#'.repeat(level)+' 已有标题');}
    s=s.update(api.formatSpec(s,'paragraph')).state;
    assert.equal(s.sliceDoc(),'已有标题\n正文');
    s=s.update(api.formatSpec(s,'paragraph')).state;assert.equal(s.sliceDoc(),'已有标题\n正文');
  });
  test('new commands preserve newline style and each action can be undone as one step',()=>{
    for(const separator of ['\n','\r\n','\r'])for(const command of ['strike','ordered','task','link','rule','codeblock']) {
      const original=['第一行','第二行',''].join(separator);let s=state(original);
      s=s.update({selection:{anchor:0,head:s.doc.line(2).to}}).state;
      const changed=s.update(api.formatSpec(s,command)).state;assert.notEqual(changed.sliceDoc(),original,command);s=changed;
      assert.equal(api.supports(s.sliceDoc()),true,command);
      assert.equal(api.undo({get state(){return s;},dispatch(transaction){s=transaction.state;}}),true,command);
      assert.equal(s.sliceDoc(),original,command);
    }
  });
  test('numbered and task lists replace existing list markers without deleting the item text',()=>{
    let s=state('- 第一项\n- [x] 已完成\n第三项');s=s.update({selection:{anchor:0,head:s.doc.length}}).state;
    s=s.update(api.formatSpec(s,'ordered')).state;assert.equal(s.sliceDoc(),'1. 第一项\n2. 已完成\n3. 第三项');
    s=s.update(api.formatSpec(s,'task')).state;assert.equal(s.sliceDoc(),'- [ ] 第一项\n- [ ] 已完成\n- [ ] 第三项');
    s=s.update(api.formatSpec(s,'task')).state;assert.equal(s.sliceDoc(),'第一项\n已完成\n第三项');
  });
  test('code blocks choose a safe fence and rules preserve the selected text',()=>{
    let s=state('首行标题\n```js\nalert(1)\n```\n尾行');s=s.update({selection:{anchor:s.doc.line(2).from,head:s.doc.line(4).to}}).state;
    s=s.update(api.formatSpec(s,'codeblock')).state;assert.equal(s.sliceDoc(),'首行标题\n````\n```js\nalert(1)\n```\n````\n尾行');
    let rule=state('原句\n下一句');rule=rule.update({selection:{anchor:0,head:2}}).state;rule=rule.update(api.formatSpec(rule,'rule')).state;
    assert.equal(rule.sliceDoc(),'原句\n\n---\n\n下一句');
    const empty=state('').update(api.formatSpec(state(''),'codeblock')).state;assert.equal(empty.sliceDoc(),'```\n\n```');
  });
  test('link insertion keeps its label and selects the editable URL',()=>{
    let s=state('链接名称');s=s.update({selection:{anchor:0,head:4}}).state;s=s.update(api.formatSpec(s,'link')).state;
    assert.equal(s.sliceDoc(),'[链接名称](https://)');assert.equal(s.sliceDoc(s.selection.main.from,s.selection.main.to),'https://');
  });
  test('toolbar undo and redo share keyboard history and are blocked during composition',()=>{
    let s=state('原稿');s=s.update({selection:{anchor:0,head:2}}).state;
    const view={get state(){return s;},composing:false,compositionStarted:false,plugin:()=>null,dispatch(spec){s=spec.state||s.update(spec).state;}};
    api.formatCommand('strike')(view);assert.equal(s.sliceDoc(),'~~原稿~~');
    assert.equal(api.formatCommand('undo')(view),true);assert.equal(s.sliceDoc(),'原稿');
    assert.equal(api.formatCommand('redo')(view),true);assert.equal(s.sliceDoc(),'~~原稿~~');
    view.composing=true;api.formatCommand('undo')(view);assert.equal(s.sliceDoc(),'~~原稿~~');
  });
  test('Ctrl A selects the unchanged Markdown document including its original first line',()=>{
    const original='# 文稿原有标题\n\n正文';let s=state(original);
    const selectAll=s.facet(api.keymap).flat().find(binding=>binding.key==='Mod-a');assert.ok(selectAll);
    selectAll.run({get state(){return s;},dispatch(spec){s=s.update(spec).state;}});
    assert.equal(s.selection.main.from,0);assert.equal(s.selection.main.to,original.length);
    assert.equal(s.sliceDoc(s.selection.main.from,s.selection.main.to),original);
  });
  const imageDecs = s => decs(s).filter(dec=>dec.spec.widget instanceof api.LocalImageWidget);
  function imageState(value,resolver,mode='live') {
    const s=api.buildEditorState(value,mode,'图片测试',null,resolver).state;
    return s.update({selection:{anchor:s.doc.length}}).state;
  }
  test('local inline images use only the host resolver while Markdown remains unchanged',()=>{
    const calls=[],text='前文\n\n![截图](<assets/屏幕 1.png>)\n\n末尾',s=imageState(text,(url,alt)=>{calls.push({url,alt});return '/api/markdown-assets/image?note=1&path=assets%2Fscreen.png';});
    const images=imageDecs(s);assert.equal(images.length,1);assert.deepEqual(calls,[{url:'assets/屏幕 1.png',alt:'截图'}]);
    assert.equal(images[0].spec.widget.alt,'截图');assert.equal(s.sliceDoc(),text);
    assert.equal(s.doc.lineAt(images[0].from).number,s.doc.lineAt(images[0].to).number);
  });
  test('default editor never loads images and active image selection exposes original syntax',()=>{
    const text='![说明](assets/a.png)\n\n末尾';assert.equal(imageDecs(imageState(text)).length,0);
    let s=imageState(text,()=>'/api/markdown-assets/image?note=1&path=a.png');assert.equal(imageDecs(s).length,1);
    s=s.update({selection:{anchor:4}}).state;assert.equal(imageDecs(s).length,0);assert.equal(s.sliceDoc(),text);
    assert.equal(imageDecs(imageState(text,()=>'/api/markdown-assets/image','source')).length,0);
  });
  test('external absolute encoded protocols and control-bearing image destinations do not reach resolver',()=>{
    for(const url of ['https://example.invalid/a.png','//host/a.png','/private/a.png','file:///C:/a.png','data:image/png;base64,AAA','blob:test','C:/private/a.png','%68ttps%3A%2F%2Fexample.invalid/a.png','%2Fprivate.png','assets/%00a.png','assets/%5Ca.png']) {
      let called=false;const s=imageState(`![x](${url})\n\n末尾`,()=>{called=true;return '/api/image';});assert.equal(imageDecs(s).length,0,url);assert.equal(called,false,url);
    }
  });
  test('resolver failure null and non-origin routes preserve source without image loading',()=>{
    for(const result of [null,undefined,'https://foreign.invalid/a.png','//foreign.invalid/a.png','file:///a.png','data:image/png;base64,AAA','/\\foreign/a.png','/api/image\n']) {
      assert.equal(imageDecs(imageState('![x](assets/a.png)\n\n末尾',()=>result)).length,0);
    }
    assert.equal(imageDecs(imageState('![x](assets/a.png)\n\n末尾',()=>{throw Error('missing asset');})).length,0);
  });
  test('reference multiline code table and YAML images stay source even with a resolver',()=>{
    for(const text of ['![x][ref]\n\n[ref]: assets/a.png\n\n末尾','![多行\n说明](assets/a.png)\n\n末尾','```md\n![x](assets/a.png)\n```\n\n末尾','---\npicture: ![x](assets/a.png)\n---\n\n末尾','| 图片 |\n| --- |\n| ![x](assets/a.png) |\n\n末尾']) {
      const s=imageState(text,()=>'/api/image');assert.equal(imageDecs(s).length,0,text);assert.equal(s.sliceDoc(),text);
    }
  });
  test('inline image URL escapes and alt text are data rather than HTML',()=>{
    const calls=[],s=imageState('![<script>](assets/a\\(1\\).png "title")\n\n末尾',(url,alt)=>{calls.push({url,alt});return '/api/image';});
    assert.equal(imageDecs(s).length,1);assert.deepEqual(calls,[{url:'assets/a(1).png',alt:'<script>'}]);
  });
  test('image widget is lazy and keyboard-accessible and opens its own source without rewriting',()=>{
    const elements=[];
    const doc={createElement(tag){const value={tag,children:[],attributes:{},events:{},classList:{add(){}},setAttribute(k,v){this.attributes[k]=v;},appendChild(v){this.children.push(v);},addEventListener(k,v){this.events[k]=v;}};elements.push(value);return value;},createTextNode:text=>({textContent:text})};
    let focused=false,selected=null,measures=0;const original=state('![图](a.png)');
    const view={dom:{ownerDocument:doc,isConnected:true},state:original,plugin:()=>null,posAtDOM:()=>0,dispatch:spec=>{selected=spec.selection.anchor;},focus:()=>{focused=true;},requestMeasure:()=>{measures++;}};
    const span=new api.LocalImageWidget('/api/image','<img onerror=bad>').toDOM(view),img=span.children[0];
    assert.equal(img.loading,'lazy');assert.equal(img.decoding,'async');assert.equal(img.referrerPolicy,'no-referrer');assert.equal(img.alt,'<img onerror=bad>');assert.equal(img.src,'/api/image');
    assert.equal(span.contentEditable,'false');assert.equal(span.tabIndex,0);span.events.keydown({type:'keydown',key:'Enter',preventDefault(){}});assert.equal(selected,1);assert.equal(focused,true);assert.equal(original.sliceDoc(),'![图](a.png)');
    selected=null;view.composing=true;span.events.mousedown({type:'mousedown',button:0,preventDefault(){}});assert.equal(selected,null);
    img.events.load();assert.equal(measures,1);img.events.error();assert.equal(img.hidden,true);assert.match(span.children[1].textContent,/图片暂不可用/);
  });
  test('composition freezes image decorations',()=>{
    const s=imageState('![图](a.png)\n\n末尾',()=>'/api/image');const view={state:s,visibleRanges:[{from:0,to:s.doc.length}],hasFocus:true,composing:true};
    const plugin=new api.LivePreviewPlugin(view),initial=plugin.decorations,transaction=s.update({selection:{anchor:3}});view.state=transaction.state;
    plugin.update({view,state:view.state,startState:s,docChanged:false,selectionSet:true,transactions:[transaction]});assert.equal(plugin.decorations,initial);plugin.destroy();
  });
  test('source offset insertion normalizes incoming newlines and undo preserves original bytes',()=>{
    for(const separator of ['\n','\r\n','\r']) {
      const original='\ufeff第一行'+separator+'替换我'+separator+'末尾';let s=state(original);const from=original.indexOf('替换我'),to=from+3;
      s=s.update(api.insertionSpec(s,'![截图](assets/a.png)\n新行',from,to)).state;
      assert.equal(s.sliceDoc(),'\ufeff第一行'+separator+'![截图](assets/a.png)'+separator+'新行'+separator+'末尾');
      const selection=api.sourceSelection(s);assert.equal(selection.from,selection.to);assert.equal(selection.from,s.sliceDoc().indexOf(separator+'末尾'));
      assert.equal(api.undo({get state(){return s;},dispatch(transaction){s=transaction.state;}}),true);assert.equal(s.sliceDoc(),original);
    }
  });
  test('getSelection offsets count CRLF source bytes correctly and default insertion replaces that range',()=>{
    let s=state('甲\r\n选中\r\n乙');s=s.update({selection:{anchor:s.doc.line(2).from,head:s.doc.line(2).to}}).state;
    assert.deepEqual(api.sourceSelection(s),{from:3,to:5});s=s.update(api.insertionSpec(s,'图片')).state;assert.equal(s.sliceDoc(),'甲\r\n图片\r\n乙');
    s=s.update(api.insertionSpec(s,'前缀',3)).state;assert.equal(s.sliceDoc(),'甲\r\n前缀图片\r\n乙');
  });
  test('invalid stale or half-newline offsets and oversized insertion leave document intact',()=>{
    const s=state('甲\r\n乙'),before=s.sliceDoc();
    for(const [from,to] of [[-1,0],[0,100],[3,1],[2,2],[1.5,2]])assert.throws(()=>api.insertionSpec(s,'图',from,to),RangeError);
    assert.throws(()=>api.insertionSpec(s,null),TypeError);assert.throws(()=>api.insertionSpec(s,'x'.repeat(500001)),RangeError);assert.equal(s.sliceDoc(),before);
  });
}
