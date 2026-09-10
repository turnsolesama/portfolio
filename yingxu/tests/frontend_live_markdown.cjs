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
  const bundled = esbuild.buildSync({stdin:{contents:source+'\nexport {buildEditorState,previewDecorations,formatSpec,liveMode,EditorSelection,EditorState,EditorView,Text,markdownKeymap,LivePreviewPlugin,keymap};\nexport {undo,redo} from "@codemirror/commands";',resolveDir:path.join(root,'frontend'),loader:'js'},nodePaths:[dependencies],bundle:true,write:false,platform:'node',format:'cjs'});
  const loaded = new Module(path.join(root,'work-live-markdown-check.cjs'),module);
  loaded.filename = path.join(root,'work-live-markdown-check.cjs');
  loaded._compile(bundled.outputFiles[0].text,loaded.filename);
  const api = loaded.exports;
  function state(value,mode='live') { return api.buildEditorState(value,mode,'测试').state; }
  function decs(value) { const result=[];api.previewDecorations(value).between(0,value.doc.length,(from,to,dec)=>result.push({from,to,spec:dec.spec}));return result; }
  const replacements = value => decs(value).filter(dec=>dec.from < dec.to && !dec.spec.class);

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
}
