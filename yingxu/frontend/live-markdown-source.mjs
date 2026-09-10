/* Offline CodeMirror live preview. Markdown source is the only document model. */
import {Annotation,Compartment,EditorSelection,EditorState,Facet,StateEffect,Text} from '@codemirror/state';
import {Decoration,EditorView,ViewPlugin,WidgetType,keymap,drawSelection,highlightActiveLine} from '@codemirror/view';
import {defaultKeymap,history,historyKeymap,indentWithTab,isolateHistory} from '@codemirror/commands';
import {syntaxTree,indentOnInput} from '@codemirror/language';
import {markdown,markdownKeymap} from '@codemirror/lang-markdown';
import {GFM} from '@lezer/markdown';

const MAX_LENGTH = 500000;
const liveMode = Facet.define({combine:values => values[0] || 'live'});
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

function frontmatterEnd(state) {
  if (!/^\uFEFF?---\s*$/.test(state.doc.line(1).text)) return -1;
  for (let number = 2; number <= state.doc.lines; number++) {
    const line = state.doc.line(number);
    if (/^(?:---|\.\.\.)\s*$/.test(line.text)) return line.to;
  }
  return state.doc.length;
}

const untouched = new Set(['FencedCode','CodeBlock','HTMLBlock','CommentBlock','ProcessingInstructionBlock',
  'Table','Image','Link','Autolink','LinkReference','HTMLTag','Comment','ProcessingInstruction','SetextHeading1','SetextHeading2']);
const inlineClasses = {StrongEmphasis:'yx-md-strong',Emphasis:'yx-md-emphasis',Strikethrough:'yx-md-strike',InlineCode:'yx-md-code'};
const hiddenMarks = new Set(['HeaderMark','EmphasisMark','StrikethroughMark','CodeMark','QuoteMark','ListMark','TaskMarker']);

function previewDecorations(state,visibleRanges = [{from:0,to:state.doc.length}],hasFocus = true) {
  if (state.facet(liveMode) !== 'live' || state.doc.length > MAX_LENGTH) return Decoration.none;
  const decorations = [], lineClasses = new Set(), marked = new Set(), yamlEnd = frontmatterEnd(state);
  const visible = (from,to) => visibleRanges.some(range => range.from <= to && range.to >= from);
  const touched = node => hasFocus && state.selection.ranges.some(range => range.from <= node.to && range.to >= node.from);
  const lineStyle = (position,style) => {
    const from = state.doc.lineAt(position).from, key = `${from}:${style}`;
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
    if (node.name === 'ListItem') active = touched(node);
    const heading = /^ATXHeading([1-6])$/.exec(node.name);
    if (heading) lineStyle(node.from,`yx-md-heading yx-md-heading-${heading[1]}`);
    if (node.name === 'Blockquote') {
      const first = state.doc.lineAt(node.from).number, last = state.doc.lineAt(node.to).number;
      for (let number = first; number <= last; number++) lineStyle(state.doc.line(number).from,'yx-md-quote-line');
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
  const wrapper = {bold:'**',italic:'*'}[command];
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
  const prefix = {heading2:'## ',bullet:'- ',quote:'> '}[command];
  if (!prefix) return null;
  const numbers = new Set();
  for (const range of state.selection.ranges) {
    const first = state.doc.lineAt(range.from).number;
    const end = range.to > range.from && state.doc.lineAt(range.to).from === range.to ? range.to-1 : range.to;
    for (let number = first; number <= state.doc.lineAt(end).number; number++) numbers.add(number);
  }
  const lines = [...numbers].sort((a,b)=>a-b).map(number => state.doc.line(number));
  const remove = lines.every(line => line.text.startsWith(prefix));
  const edits = lines.flatMap(line => {
    if (!remove && line.text.startsWith(prefix)) return [];
    const oldHeading = command === 'heading2' ? /^#{1,6}\s+/.exec(line.text)?.[0] || '' : '';
    return [{from:line.from,to:line.from+(remove ? prefix.length : oldHeading.length),insert:remove ? '' : prefix}];
  });
  const changes = state.changes(edits);
  return {changes,selection:state.selection.map(changes,1),scrollIntoView:true,userEvent:'input.format',annotations:isolateHistory.of('full')};
}

function formatCommand(command) {
  return view => {
    if (view.composing || view.compositionStarted || view.plugin(previewPlugin)?.frozen) return true;
    const spec = formatSpec(view.state,command);
    if (!spec) return false;
    view.dispatch(spec); return true;
  };
}

function buildEditorState(value,mode,label,onChange) {
  const source = sourceText(value), modeSlot = new Compartment(), lineSlot = new Compartment();
  const state = EditorState.create({doc:source.text,extensions:[
    lineSlot.of(EditorState.lineSeparator.of(source.separator)), modeSlot.of(liveMode.of(mode)),
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

export const create = ({parent,value = '',mode = 'live',label = 'Markdown 实时编辑',onChange} = {}) => {
  if (!parent || !['live','source'].includes(mode)) throw new Error('Markdown 编辑器的挂载位置或模式无效。');
  const config = buildEditorState(value,mode,label,onChange);
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
    focus() { alive(); view.focus(); },
    destroy() { if (!destroyed) { destroyed = true; view.destroy(); } },
    isComposing:composing,
    format(command) { alive(); if (composing()) return false; const spec = formatSpec(view.state,command); if (!spec) return false; view.dispatch(spec); view.focus(); return true; }
  };
};

if (typeof window !== 'undefined') window.YingXuMarkdown = {create,supports};
