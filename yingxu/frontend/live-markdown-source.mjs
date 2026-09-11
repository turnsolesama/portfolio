/* Offline CodeMirror live preview. Markdown source is the only document model. */
import {Annotation,Compartment,EditorSelection,EditorState,Facet,StateEffect,Text} from '@codemirror/state';
import {Decoration,EditorView,ViewPlugin,WidgetType,keymap,drawSelection,highlightActiveLine} from '@codemirror/view';
import {defaultKeymap,history,historyKeymap,indentWithTab,isolateHistory,undo,redo} from '@codemirror/commands';
import {syntaxTree,indentOnInput} from '@codemirror/language';
import {markdown,markdownKeymap} from '@codemirror/lang-markdown';
import {GFM} from '@lezer/markdown';

const MAX_LENGTH = 500000;
const liveMode = Facet.define({combine:values => values[0] || 'live'});
const localImageResolver = Facet.define({combine:values => values[0] || null});
const documentLinkHandler = Facet.define({combine:values => values[0] || null});
const repaint = StateEffect.define();
const replacement = Annotation.define();

function newlineKind(value) {
  const kinds = new Set(value.match(/\r\n|\r|\n/g) || []);
  return kinds.size > 1 ? null : kinds.values().next().value || '\n';
}

export const supports = value => typeof value === 'string' && value.length <= MAX_LENGTH && newlineKind(value) !== null;

function sourceText(value) {
  if (!supports(value)) throw new Error('此文档含混合换行或超过实时编辑大小限制，请使用源码编辑。');
  const separator = newlineKind(value);
  return {separator,text:Text.of(value.split(separator))};
}

class SymbolWidget extends WidgetType {
  constructor(text,kind) { super(); this.text = text; this.kind = kind; }
  eq(other) { return this.text === other.text && this.kind === other.kind; }
  toDOM(view) {
    const span = view.dom.ownerDocument.createElement('span');
    span.className = `yx-md-symbol yx-md-${this.kind}`;
    span.textContent = this.text;
    span.setAttribute('aria-hidden','true');
    return span;
  }
  ignoreEvent() { return false; }
}

class LocalImageWidget extends WidgetType {
  constructor(src,alt) { super(); this.src = src; this.alt = alt; }
  eq(other) { return this.src === other.src && this.alt === other.alt; }
  get estimatedHeight() { return 220; }
  toDOM(view) {
    const doc = view.dom.ownerDocument,span = doc.createElement('span'),img = doc.createElement('img');
    span.className = 'yx-md-image'; span.contentEditable = 'false'; span.tabIndex = 0;
    span.setAttribute('role','button'); span.setAttribute('aria-label',`编辑图片 Markdown：${this.alt || '图片'}`);
    img.alt = this.alt; img.loading = 'lazy'; img.decoding = 'async'; img.referrerPolicy = 'no-referrer';
    const measure = () => { if (view.dom.isConnected) view.requestMeasure(); };
    img.addEventListener('load',measure);
    img.addEventListener('error',() => { img.hidden = true; span.classList.add('yx-md-image-error'); span.appendChild(doc.createTextNode(`图片暂不可用${this.alt ? ' · '+this.alt : ''}`)); measure(); },{once:true});
    const edit = event => {
      if (event.type === 'keydown' && !['Enter',' '].includes(event.key)) return;
      if (event.type === 'mousedown' && event.button !== 0) return;
      event.preventDefault();
      if (view.composing || view.compositionStarted || view.plugin(previewPlugin)?.frozen) return;
      const position = view.posAtDOM(span);
      view.dispatch({selection:{anchor:Math.min(position+1,view.state.doc.length)}}); view.focus();
    };
    span.addEventListener('mousedown',edit); span.addEventListener('keydown',edit);
    span.appendChild(img); img.src = this.src;
    return span;
  }
  ignoreEvent(event) { return ['mousedown','keydown','load','error'].includes(event.type); }
}

function imageWidget(state,node) {
  const resolve = state.facet(localImageResolver);
  if (!resolve || state.doc.lineAt(node.from).number !== state.doc.lineAt(node.to).number) return null;
  let destination,altEnd;
  for (let child = node.firstChild; child; child = child.nextSibling) {
    if (child.name === 'URL') destination = state.doc.sliceString(child.from,child.to);
    if (child.name === 'LinkMark' && state.doc.sliceString(child.from,child.to) === ']' && altEnd === undefined) altEnd = child.from;
  }
  if (!destination || altEnd === undefined) return null;
  const unescape = text => text.replace(/\\([!"#$%&'()*+,\-./:;<=>?@[\]\\^_`{|}~])/g,'$1');
  const url = unescape(destination.startsWith('<') && destination.endsWith('>') ? destination.slice(1,-1) : destination);
  let decoded;
  try { decoded = decodeURIComponent(url); } catch { return null; }
  if (!url || /[\x00-\x20\x7f]/.test(url.replace(/ /g,'')) || /^(?:[a-z][a-z0-9+.-]*:|[\\/]|[?#])/i.test(decoded.trim()) || /[\x00-\x1f\x7f\\]/.test(decoded)) return null;
  const alt = unescape(state.doc.sliceString(node.from+2,altEnd));
  let src;
  try { src = resolve(url,alt); } catch { return null; }
  // Only origin-relative routes returned by the host are permitted. No remote,
  // protocol-relative, data/blob/file URLs or browser navigation are inferred.
  if (typeof src !== 'string' || !src.startsWith('/') || /^\/[\\/]/.test(src) || /[\x00-\x20\x7f\\]/.test(src)) return null;
  return new LocalImageWidget(src,alt);
}

class DocumentLinkWidget extends WidgetType {
  constructor(url,label,local){super();this.url=url;this.label=label;this.local=local;}
  eq(other){return this.url===other.url&&this.label===other.label&&this.local===other.local;}
  toDOM(view){
    const doc=view.dom.ownerDocument,anchor=doc.createElement('a');anchor.className='yx-md-document-link';anchor.textContent=this.label;anchor.contentEditable='false';anchor.href=this.local?'#yx-file':this.url;anchor.style.color='var(--accent,#4f715c)';anchor.style.textDecoration='underline';
    if(!this.local){anchor.target='_blank';anchor.rel='noopener noreferrer';}
    anchor.title=this.local?'在映序中打开项目文件':this.url;
    const blocked=()=>view.composing||view.compositionStarted||view.plugin(previewPlugin)?.frozen;
    anchor.addEventListener('mousedown',event=>{if(event.button===0)event.preventDefault();});
    anchor.addEventListener('click',event=>{
      if(blocked()){event.preventDefault();return;}
      if(!this.local)return;
      event.preventDefault();event.stopPropagation();const callback=view.state.facet(documentLinkHandler);if(!callback)return;
      try{Promise.resolve(callback(this.url)).catch(()=>{anchor.title='链接暂时无法打开，请重试。';});}catch{anchor.title='链接暂时无法打开，请重试。';}
    });
    anchor.addEventListener('keydown',event=>{if(this.local&&['Enter',' '].includes(event.key)){event.preventDefault();anchor.click();}});
    return anchor;
  }
  ignoreEvent(event){return ['mousedown','click','keydown'].includes(event.type);}
}
function linkWidget(state,node){
  if(state.doc.lineAt(node.from).number!==state.doc.lineAt(node.to).number)return null;
  let destination,labelEnd;
  for(let child=node.firstChild;child;child=child.nextSibling){if(child.name==='URL')destination=state.doc.sliceString(child.from,child.to);if(child.name==='LinkMark'&&state.doc.sliceString(child.from,child.to)===']'&&labelEnd===undefined)labelEnd=child.from;}
  if(!destination||labelEnd===undefined)return null;
  const unescape=text=>text.replace(/\\([!"#$%&'()*+,\-./:;<=>?@[\]\\^_`{|}~])/g,'$1');
  const raw=unescape(destination.startsWith('<')&&destination.endsWith('>')?destination.slice(1,-1):destination),url=raw.replace(/ /g,'%20');
  let decoded;try{decoded=decodeURIComponent(url);}catch{return null;}
  if(!url||url.length>4096||/[\x00-\x1f\x7f\\]/.test(decoded)||decoded!==decoded.trim())return null;
  const label=unescape(state.doc.sliceString(node.from+1,labelEnd));
  if(/^https?:\/\//i.test(url))return new DocumentLinkWidget(url,label,false);
  if(!state.facet(documentLinkHandler)||/^(?:[a-z][a-z0-9+.-]*:|[\/\\]|[?#])/i.test(decoded)||url.includes('?'))return null;
  const fragment=url.split('#');if(fragment.length>2||fragment[1]&&!/^yx-item=[a-f0-9]{32}$/.test(fragment[1]))return null;
  return new DocumentLinkWidget(url,label,true);
}

// CodeMirror Text objects are immutable: selection/viewport changes reuse this
// key, while any document edit creates a new one. Weak keys retain no old docs.
const frontmatterCache = new WeakMap();
function frontmatterEnd(state) {
  const doc = state.doc;
  if (frontmatterCache.has(doc)) return frontmatterCache.get(doc);
  let end = -1;
  if (/^\uFEFF?---\s*$/.test(doc.line(1).text)) {
    end = doc.length;
    for (let number = 2; number <= doc.lines; number++) {
      const line = doc.line(number);
      if (/^(?:---|\.\.\.)\s*$/.test(line.text)) { end = line.to; break; }
    }
  }
  frontmatterCache.set(doc,end);
  return end;
}

const untouched = new Set(['FencedCode','CodeBlock','HTMLBlock','CommentBlock','ProcessingInstructionBlock',
  'Table','Autolink','LinkReference','HTMLTag','Comment','ProcessingInstruction','SetextHeading1','SetextHeading2']);
const inlineClasses = {StrongEmphasis:'yx-md-strong',Emphasis:'yx-md-emphasis',Strikethrough:'yx-md-strike',InlineCode:'yx-md-code'};
const hiddenMarks = new Set(['HeaderMark','EmphasisMark','StrikethroughMark','CodeMark','QuoteMark','ListMark','TaskMarker']);

function previewDecorations(state,visibleRanges = [{from:0,to:state.doc.length}],hasFocus = true) {
  if (state.facet(liveMode) !== 'live' || state.doc.length > MAX_LENGTH) return Decoration.none;
  const decorations = [], lineClasses = new Set(), marked = new Set(), yamlEnd = frontmatterEnd(state);
  const visible = (from,to) => visibleRanges.some(range => range.from <= to && range.to >= from);
  const touched = node => hasFocus && state.selection.ranges.some(range => range.from <= node.to && range.to >= node.from);
  const lineStyle = (position,style) => {
    const line = state.doc.lineAt(position);
    if (!visible(line.from,line.to)) return;
    const from = line.from, key = `${from}:${style}`;
    if (!lineClasses.has(key)) { lineClasses.add(key); decorations.push(Decoration.line({class:style}).range(from)); }
  };
  const marker = (node,active) => {
    const original = state.doc.sliceString(node.from,node.to);
    if (!original || original.includes('\n')) return;
    if (active) { decorations.push(Decoration.mark({class:'yx-md-source-mark'}).range(node.from,node.to)); return; }
    let to = node.to, widget;
    if (['HeaderMark','QuoteMark','ListMark'].includes(node.name) && state.doc.sliceString(to,to+1) === ' ') to++;
    if (node.name === 'ListMark') {
      const rest = state.doc.sliceString(node.to,state.doc.lineAt(node.to).to);
      if (!/^\s+\[[ xX]\]/.test(rest)) widget = new SymbolWidget(/^\d/.test(original) ? original : '•','bullet');
    } else if (node.name === 'TaskMarker') widget = new SymbolWidget(/x/i.test(original) ? '☑' : '☐','task');
    // View-plugin replacements are always confined to a single physical line.
    if (state.doc.lineAt(node.from).number !== state.doc.lineAt(to).number) return;
    const key = `${node.from}:${to}`;
    if (!marked.has(key)) { marked.add(key); decorations.push(Decoration.replace({widget,inclusive:false}).range(node.from,to)); }
  };
  const visit = (node,active) => {
    if (!visible(node.from,node.to) || node.from <= yamlEnd || untouched.has(node.name)) return;
    if(node.name==='Link'){
      if(!touched(state.doc.lineAt(node.from))){const widget=linkWidget(state,node);if(widget)decorations.push(Decoration.replace({widget,inclusive:false}).range(node.from,node.to));}
      return;
    }
    if (node.name === 'Image') {
      if (!touched(node)) { const widget = imageWidget(state,node); if (widget) decorations.push(Decoration.replace({widget,inclusive:false}).range(node.from,node.to)); }
      return;
    }
    if (node.name === 'ListItem') active = touched(node);
    const heading = /^ATXHeading([1-6])$/.exec(node.name);
    if (heading) lineStyle(node.from,`yx-md-heading yx-md-heading-${heading[1]}`);
    if (node.name === 'Blockquote') {
      for (const range of visibleRanges) {
        const from = Math.max(node.from,range.from),to = Math.min(node.to,range.to);
        if (from > to) continue;
        const first = state.doc.lineAt(from).number,last = state.doc.lineAt(to).number;
        for (let number = first; number <= last; number++) lineStyle(state.doc.line(number).from,'yx-md-quote-line');
      }
    }
    if (node.name === 'ListItem') lineStyle(node.from,'yx-md-list-line');
    if (inlineClasses[node.name] && node.to > node.from) decorations.push(Decoration.mark({class:inlineClasses[node.name]}).range(node.from,node.to));
    if (hiddenMarks.has(node.name)) marker(node,active);
    for (let child = node.firstChild; child; child = child.nextSibling) visit(child,active);
  };
  for (let block = syntaxTree(state).topNode.firstChild; block; block = block.nextSibling) {
    if (!visible(block.from,block.to)) continue;
    visit(block,touched(block));
  }
  return Decoration.set(decorations,true);
}

class LivePreviewPlugin {
  constructor(view) {
    this.view = view; this.frozen = false; this.ended = false; this.timer = null;
    this.decorations = previewDecorations(view.state,view.visibleRanges,view.hasFocus);
  }
  update(update) {
    if (this.frozen || update.view.compositionStarted || update.view.composing) {
      if (update.docChanged) this.decorations = this.decorations.map(update.changes);
      return;
    }
    if (update.docChanged || update.selectionSet || update.viewportChanged || update.focusChanged ||
        update.startState.facet(liveMode) !== update.state.facet(liveMode) ||
        syntaxTree(update.startState) !== syntaxTree(update.state) ||
        update.transactions.some(transaction => transaction.effects.some(effect => effect.is(repaint)))) {
      this.decorations = previewDecorations(update.state,update.view.visibleRanges,update.view.hasFocus);
    }
  }
  finishComposition() {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      if (this.ended) return;
      if (this.view.composing || this.view.compositionStarted) { this.finishComposition(); return; }
      this.frozen = false;
      this.view.dispatch({effects:repaint.of(null)});
    },25);
  }
  destroy() { this.ended = true; clearTimeout(this.timer); }
}
const previewPlugin = ViewPlugin.fromClass(LivePreviewPlugin, {
  decorations:plugin => plugin.decorations,
  eventHandlers:{
    compositionstart() { this.frozen = true; clearTimeout(this.timer); return false; },
    compositionend() { this.finishComposition(); return false; }
  }
});

function formatSpec(state,command) {
  const wrapper = {bold:'**',italic:'*',strike:'~~'}[command];
  if (wrapper) {
    const change = state.changeByRange(range => {
      const selected = state.doc.sliceString(range.from,range.to);
      const exactItalic = wrapper !== '*' || (!selected.startsWith('**') && !selected.endsWith('**'));
      if (selected.length >= wrapper.length*2 && selected.startsWith(wrapper) && selected.endsWith(wrapper) && exactItalic) {
        const text = selected.slice(wrapper.length,-wrapper.length);
        return {changes:{from:range.from,to:range.to,insert:Text.of(text.split('\n'))},range:EditorSelection.range(range.from,range.from+text.length)};
      }
      const outsideItalic = wrapper !== '*' || (state.doc.sliceString(Math.max(0,range.from-2),range.from) !== '**' && state.doc.sliceString(range.to,range.to+2) !== '**');
      if (range.from >= wrapper.length && state.doc.sliceString(range.from-wrapper.length,range.from) === wrapper && state.doc.sliceString(range.to,range.to+wrapper.length) === wrapper && outsideItalic) {
        return {changes:[{from:range.from-wrapper.length,to:range.from},{from:range.to,to:range.to+wrapper.length}],range:EditorSelection.range(range.from-wrapper.length,range.to-wrapper.length)};
      }
      const text = selected || '文字';
      return {changes:{from:range.from,to:range.to,insert:Text.of((wrapper+text+wrapper).split('\n'))},range:EditorSelection.range(range.from+wrapper.length,range.from+wrapper.length+text.length)};
    });
    return {...change,scrollIntoView:true,userEvent:'input.format',annotations:isolateHistory.of('full')};
  }
  if (command === 'link') {
    const change = state.changeByRange(range => {
      const label = state.doc.sliceString(range.from,range.to) || '链接文字';
      const insert = '['+label+'](https://)';
      return {changes:{from:range.from,to:range.to,insert:Text.of(insert.split('\n'))},range:EditorSelection.range(range.from+label.length+3,range.from+insert.length-1)};
    });
    return {...change,scrollIntoView:true,userEvent:'input.format',annotations:isolateHistory.of('full')};
  }
  const heading = /^heading([1-6])$/.exec(command);
  const prefix = heading ? '#'.repeat(Number(heading[1]))+' ' : {bullet:'- ',quote:'> ',ordered:'1. ',task:'- [ ] ',paragraph:''}[command];
  if (prefix === undefined && !['rule','codeblock'].includes(command)) return null;
  const numbers = new Set();
  for (const range of state.selection.ranges) {
    const first = state.doc.lineAt(range.from).number;
    const end = range.to > range.from && state.doc.lineAt(range.to).from === range.to ? range.to-1 : range.to;
    for (let number = first; number <= state.doc.lineAt(end).number; number++) numbers.add(number);
  }
  const lines = [...numbers].sort((a,b)=>a-b).map(number => state.doc.line(number));
  const edits = [];
  if (command === 'rule' || command === 'codeblock') {
    const groups = [];
    for (const line of lines) {
      const group = groups.at(-1);
      if (group && group.at(-1).number+1 === line.number) group.push(line); else groups.push([line]);
    }
    for (const group of groups) {
      const from = group[0].from,to = group.at(-1).to;
      if (command === 'rule') { edits.push({from:to,insert:Text.of(['','','---',''])}); continue; }
      const text = state.doc.sliceString(from,to), longest = Math.max(2,...(text.match(/`+/g) || []).map(value => value.length));
      const fence = '`'.repeat(longest+1);
      edits.push({from,insert:Text.of([fence,''])},{from:to,insert:Text.of(['',fence])});
    }
  } else {
    const list = ['bullet','ordered','task'].includes(command);
    const pattern = heading || command === 'paragraph' ? /^#{1,6}\s+/ : list ? /^(?:[-+*]|\d+[.)])\s+(?:\[[ xX]\]\s+)?/ : /^>\s?/;
    const hasStyle = text => heading ? text.startsWith(prefix) : command === 'paragraph' ? false : command === 'ordered' ? /^\d+[.)]\s+/.test(text) : command === 'task' ? /^[-+*]\s+\[[ xX]\]\s+/.test(text) : command === 'bullet' ? /^[-+*]\s+(?!\[[ xX]\]\s)/.test(text) : /^>\s?/.test(text);
    const remove = lines.every(line => hasStyle(line.text));
    lines.forEach((line,index) => {
      if (!remove && hasStyle(line.text) && command !== 'ordered') return;
      const old = pattern.exec(line.text)?.[0] || '';
      const insert = remove || command === 'paragraph' ? '' : command === 'ordered' ? `${index+1}. ` : prefix;
      if (old !== insert) edits.push({from:line.from,to:line.from+old.length,insert});
    });
  }
  const changes = state.changes(edits);
  return {changes,selection:state.selection.map(changes,1),scrollIntoView:true,userEvent:'input.format',annotations:isolateHistory.of('full')};
}

function formatCommand(command) {
  return view => {
    if (view.composing || view.compositionStarted || view.plugin(previewPlugin)?.frozen) return true;
    if (command === 'undo' || command === 'redo') return (command === 'undo' ? undo : redo)(view);
    const spec = formatSpec(view.state,command);
    if (!spec) return false;
    view.dispatch(spec); return true;
  };
}

function buildEditorState(value,mode,label,onChange,imageResolver,onLink) {
  const source = sourceText(value), modeSlot = new Compartment(), lineSlot = new Compartment();
  const state = EditorState.create({doc:source.text,extensions:[
    lineSlot.of(EditorState.lineSeparator.of(source.separator)), modeSlot.of(liveMode.of(mode)),localImageResolver.of(typeof imageResolver === 'function' ? imageResolver : null),documentLinkHandler.of(typeof onLink === 'function' ? onLink : null),
    EditorState.allowMultipleSelections.of(true), history(), drawSelection(), highlightActiveLine(), indentOnInput(),
    markdown({extensions:GFM,addKeymap:false,completeHTMLTags:false}),
    keymap.of([{key:'Mod-b',run:formatCommand('bold'),preventDefault:true},{key:'Mod-i',run:formatCommand('italic'),preventDefault:true},...markdownKeymap,...defaultKeymap,...historyKeymap,indentWithTab]),
    EditorView.clipboardInputFilter.of((text,state) => text.replace(/\r\n|\r|\n/g,state.lineBreak)),
    EditorView.lineWrapping, EditorView.contentAttributes.of({'aria-label':label,spellcheck:'false'}),
    EditorView.editorAttributes.compute([liveMode],state => ({class:'yx-markdown-editor'+(state.facet(liveMode) === 'source' ? ' yx-markdown-source' : '')})),
    previewPlugin,
    EditorView.updateListener.of(update => {
      if (update.docChanged && onChange) onChange(update.state.sliceDoc(),{origin:update.transactions.some(transaction => transaction.annotation(replacement)) ? 'setValue' : 'input'});
    })
  ]});
  return {state,modeSlot,lineSlot};
}

function sourceSelection(state) {
  const range = state.selection.main;
  return {from:state.sliceDoc(0,range.from).length,to:state.sliceDoc(0,range.to).length};
}

function insertionSpec(state,text,from,to) {
  if (typeof text !== 'string') throw new TypeError('插入内容必须是 Markdown 文本。');
  const current = state.sliceDoc(),selection = sourceSelection(state),implicit = from === undefined;
  from = implicit ? selection.from : from; to = to === undefined ? (implicit ? selection.to : from) : to;
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to < from || to > current.length) throw new RangeError('插入位置已失效。');
  for (const offset of [from,to]) if (current[offset-1] === '\r' && current[offset] === '\n') throw new RangeError('插入位置不能位于换行符中间。');
  const insert = text.replace(/\r\n|\r|\n/g,state.lineBreak);
  if (current.length-(to-from)+insert.length > MAX_LENGTH) throw new RangeError('文稿超过实时编辑大小限制，请使用源码编辑。');
  const position = offset => current.slice(0,offset).replace(/\r\n|\r/g,'\n').length;
  const start = position(from),end = position(to),doc = Text.of(insert.split(state.lineBreak));
  return {changes:{from:start,to:end,insert:doc},selection:{anchor:start+doc.length},scrollIntoView:true,userEvent:'input.insert',annotations:isolateHistory.of('full')};
}

export const create = ({parent,value = '',mode = 'live',label = 'Markdown 实时编辑',onChange,imageResolver,onLink} = {}) => {
  if (!parent || !['live','source'].includes(mode)) throw new Error('Markdown 编辑器的挂载位置或模式无效。');
  const config = buildEditorState(value,mode,label,onChange,imageResolver,onLink);
  const view = new EditorView({state:config.state,parent});
  let destroyed = false;
  const alive = () => { if (destroyed) throw new Error('Markdown 编辑器已关闭。'); };
  const composing = () => !destroyed && !!(view.composing || view.compositionStarted || view.plugin(previewPlugin)?.frozen);
  return {
    mount(target) { alive(); if (!target) throw new Error('缺少编辑器挂载位置。'); if (view.dom.parentNode !== target) target.appendChild(view.dom); view.requestMeasure(); },
    setMode(next) { alive(); if (!['live','source'].includes(next)) throw new Error('Markdown 模式无效。'); if (next !== view.state.facet(liveMode)) { if (composing()) throw new Error('正在输入中文，请完成输入后再切换模式。'); view.dispatch({effects:config.modeSlot.reconfigure(liveMode.of(next))}); } },
    setValue(next) {
      alive(); if (next === view.state.sliceDoc()) return;
      if (composing()) throw new Error('正在输入中文，请完成输入后再替换文稿。');
      const source = sourceText(next);
      view.dispatch({changes:{from:0,to:view.state.doc.length,insert:source.text},effects:config.lineSlot.reconfigure(EditorState.lineSeparator.of(source.separator)),annotations:[replacement.of(true),isolateHistory.of('full')],selection:{anchor:Math.min(view.state.selection.main.head,source.text.length)}});
    },
    getValue() { alive(); return view.state.sliceDoc(); },
    getSelection() { alive(); return sourceSelection(view.state); },
    revealMatch({from,to,focus=false}) {
      alive(); if (composing()) return false;
      const raw=view.state.sliceDoc();
      if (!Number.isInteger(from)||!Number.isInteger(to)||from<0||to<from||to>raw.length) return false;
      const position=offset=>raw.slice(0,offset).replace(/\r\n|\r/g,'\n').length;
      const start=position(from),end=position(to);
      view.dispatch({selection:{anchor:start,head:end},effects:EditorView.scrollIntoView(start,{y:'center'})});
      if(focus)view.focus(); return true;
    },
    insertText(text,from,to) { alive(); if (composing()) return false; view.dispatch(insertionSpec(view.state,text,from,to)); view.focus(); return true; },
    focus() { alive(); view.focus(); },
    destroy() { if (!destroyed) { destroyed = true; view.destroy(); } },
    isComposing:composing,
    format(command) { alive(); if (composing()) return false; const changed = formatCommand(command)(view); view.focus(); return changed; }
  };
};

if (typeof window !== 'undefined') window.YingXuMarkdown = {create,supports};
