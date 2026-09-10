import { createNode, createDemo, connect, removeNodes, duplicateNodes, generationPayload, serializeGraph, parseGraph, stableStringify, progressPercent } from './graph.mjs';

const $ = selector => document.querySelector(selector);
const STORAGE_KEY = 'frameweave.canvas.v1';
const JOB_MAP_KEY = 'frameweave.jobs.v1';
const KIND_NAMES = { h3_t2v: 'H3 · 文生视频', h3_i2v: 'H3 · 首尾帧视频', h3_ref: 'H3 · 参考生成视频', sdxl: 'SDXL · 图片生成', krea: 'Krea 2 · 图片生成', api: 'ComfyUI · API 工作流' };
const STATUS_NAMES = { queued: '排队中', running: '生成中', completed: '已完成', failed: '失败', cancelled: '已取消' };
const canvas = $('#canvas');
const world = $('#world');
const nodesLayer = $('#nodes');
const edgesLayer = $('#connections');
let graph = createDemo();
let viewport = { x: 60, y: 160, scale: 0.8 };
let selected = new Set([graph.nodes[1].id]);
let selectedEdge = null;
let history = [];
let future = [];
let csrf = '';
let settings = { backend_url: 'http://127.0.0.1:8188', model_roots: [] };
let engine = { online: false, capabilities: {}, models: {} };
let jobs = [];
let jobNodes = {};
let pointer = null;
let connecting = null;
let tool = 'select';
let spaceDown = false;
let uploadTarget = null;
let workflowTarget = null;
let saveTimer;
let pollBusy = false;
let restored = false;
let submitting = new Set();
let projectTitle = '未命名画布';
const clone = value => JSON.parse(JSON.stringify(value));

function el(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = String(text);
  return element;
}
function button(text, className, action, title) {
  const element = el('button', className, text);
  element.type = 'button';
  if (title) { element.title = title; element.setAttribute('aria-label', title); }
  element.addEventListener('click', event => { event.stopPropagation(); Promise.resolve().then(() => action(event)).catch(reportError); });
  return element;
}
function bind(selector, action) {
  $(selector).addEventListener('click', event => Promise.resolve().then(() => action(event)).catch(reportError));
}
function toast(message, error = false) {
  const messageElement = el('div', `toast${error ? ' error' : ''}`, message);
  $('#toast-region').append(messageElement);
  setTimeout(() => messageElement.remove(), error ? 7000 : 3500);
}
function reportError(error) { toast(error?.message || String(error), true); }
function mediaURL(value) {
  if (typeof value !== 'string' || !value || value.includes('\\')) return '';
  try {
    const url = new URL(value, location.origin);
    return url.origin === location.origin && ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch { return ''; }
}
async function api(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), path === '/api/diagnostics' ? 90000 : 45000);
  try {
    const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-FW-Token': csrf }, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal });
    const result = await response.json().catch(() => ({ error: `服务返回无效数据 (${response.status})` }));
    if (!response.ok) throw new Error(result.error || `请求失败 (${response.status})`);
    return result;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('本地服务响应超时，请检查引擎状态后重试。');
    throw error;
  } finally { clearTimeout(timeout); }
}
function getNode(id) { return graph.nodes.find(node => node.id === id); }
function singleSelected() { return selected.size === 1 ? getNode([...selected][0]) : null; }
function selectedGeneration() { const node = singleSelected(); return node?.type === 'generation' ? node : graph.nodes.find(item => item.type === 'generation'); }
function snapshot() { return JSON.stringify(graph); }
function pushHistory(before) {
  if (before === snapshot()) return;
  history.push(before);
  if (history.length > 80) history.shift();
  future = [];
  save();
  updateHistory();
}
function mutate(action, options = {}) {
  const before = snapshot();
  action();
  pushHistory(before);
  renderNodes();
  if (options.inspector !== false) renderInspector();
}
function save(immediate = false) {
  clearTimeout(saveTimer);
  $('#save-state').textContent = '保存中…';
  const write = () => {
    try {
      localStorage.setItem(STORAGE_KEY, serializeGraph(graph, viewport));
      localStorage.setItem(JOB_MAP_KEY, JSON.stringify(jobNodes));
      $('#save-state').textContent = '已保存到本机';
    } catch { $('#save-state').textContent = '存储已满，请导出'; }
  };
  if (immediate) write(); else saveTimer = setTimeout(write, 500);
}
function undo() {
  if (!history.length) return;
  future.push(snapshot());
  graph = JSON.parse(history.pop());
  selected = new Set([...selected].filter(id => getNode(id)));
  renderAll(); save();
}
function redo() {
  if (!future.length) return;
  history.push(snapshot());
  graph = JSON.parse(future.pop());
  selected = new Set([...selected].filter(id => getNode(id)));
  renderAll(); save();
}
function updateHistory() { $('#undo').disabled = !history.length; $('#redo').disabled = !future.length; }
function viewPoint(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  return { x: (clientX - rect.left - viewport.x) / viewport.scale, y: (clientY - rect.top - viewport.y) / viewport.scale };
}
function applyViewport() {
  world.style.transform = `translate(${viewport.x}px,${viewport.y}px) scale(${viewport.scale})`;
  canvas.style.backgroundSize = `${22 * viewport.scale}px ${22 * viewport.scale}px`;
  canvas.style.backgroundPosition = `${viewport.x}px ${viewport.y}px`;
  $('#zoom-reset').textContent = `${Math.round(viewport.scale * 100)}%`;
  drawMinimap();
}
function zoom(factor, x = canvas.clientWidth / 2, y = canvas.clientHeight / 2) {
  const next = Math.max(.2, Math.min(2, viewport.scale * factor));
  viewport.x = x - (x - viewport.x) / viewport.scale * next;
  viewport.y = y - (y - viewport.y) / viewport.scale * next;
  viewport.scale = next;
  applyViewport(); save();
}
function nodeSize(node) {
  const dom = document.getElementById(`fw-node-${node.id}`);
  return { width: dom?.offsetWidth || (node.type === 'result' ? 338 : node.type === 'generation' ? 304 : 286), height: dom?.offsetHeight || 340 };
}
function bounds() {
  if (!graph.nodes.length) return { minX: 0, minY: 0, maxX: 800, maxY: 500 };
  return graph.nodes.reduce((box, node) => { const size = nodeSize(node); return { minX: Math.min(box.minX, node.x), minY: Math.min(box.minY, node.y), maxX: Math.max(box.maxX, node.x + size.width), maxY: Math.max(box.maxY, node.y + size.height) }; }, { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity });
}
function fitView() {
  const box = bounds();
  const availableWidth = Math.max(100, canvas.clientWidth - 90);
  const availableHeight = Math.max(100, canvas.clientHeight - 240);
  viewport.scale = Math.min(1.1, Math.max(.2, Math.min(availableWidth / (box.maxX - box.minX), availableHeight / (box.maxY - box.minY))));
  viewport.x = (canvas.clientWidth - (box.maxX - box.minX) * viewport.scale) / 2 - box.minX * viewport.scale;
  viewport.y = 132 - box.minY * viewport.scale + Math.max(0, (availableHeight - (box.maxY - box.minY) * viewport.scale) / 3);
  applyViewport(); save();
}
function drawMinimap() {
  const map = $('#minimap');
  const context = map.getContext('2d');
  context.clearRect(0, 0, map.width, map.height);
  const box = bounds();
  const viewBox = { x: -viewport.x / viewport.scale, y: -viewport.y / viewport.scale, width: canvas.clientWidth / viewport.scale, height: canvas.clientHeight / viewport.scale };
  const minX = Math.min(box.minX, viewBox.x), minY = Math.min(box.minY, viewBox.y);
  const maxX = Math.max(box.maxX, viewBox.x + viewBox.width), maxY = Math.max(box.maxY, viewBox.y + viewBox.height);
  const scale = Math.min(270 / Math.max(1, maxX - minX), 125 / Math.max(1, maxY - minY));
  const offsetX = (300 - (maxX - minX) * scale) / 2, offsetY = (185 - (maxY - minY) * scale) / 2;
  context.lineWidth = 1;
  for (const node of graph.nodes) {
    const size = nodeSize(node);
    context.fillStyle = selected.has(node.id) ? '#68baa4' : node.type === 'generation' ? '#345d59' : '#31475d';
    context.fillRect(offsetX + (node.x - minX) * scale, offsetY + (node.y - minY) * scale, size.width * scale, size.height * scale);
  }
  context.strokeStyle = '#86c5b570'; context.fillStyle = '#7dd8ba05';
  const rect = [offsetX + (viewBox.x - minX) * scale, offsetY + (viewBox.y - minY) * scale, viewBox.width * scale, viewBox.height * scale];
  context.fillRect(...rect); context.strokeRect(...rect);
}
function edgePath(a, b) { const spread = Math.max(65, Math.abs(b.x - a.x) * .45); return `M ${a.x} ${a.y} C ${a.x + spread} ${a.y}, ${b.x - spread} ${b.y}, ${b.x} ${b.y}`; }
function svgElement(tag, attributes) { const element = document.createElementNS('http://www.w3.org/2000/svg', tag); Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, String(value))); return element; }
function renderEdges() {
  edgesLayer.replaceChildren();
  for (const edge of graph.edges) {
    const from = getNode(edge.source), to = getNode(edge.target);
    if (!from || !to) continue;
    const a = { x: from.x + nodeSize(from).width, y: from.y + 74.5 }, b = { x: to.x, y: to.y + 74.5 };
    const path = edgePath(a, b);
    const hit = svgElement('path', { d: path, class: 'edge-hit', 'data-edge-id': edge.id });
    hit.addEventListener('click', event => { event.stopPropagation(); selectedEdge = edge.id; selected.clear(); renderSelection(); renderEdges(); renderInspector(); });
    edgesLayer.append(hit, svgElement('path', { d: path, class: `edge-line${selectedEdge === edge.id ? ' edge-selected' : ''}` }));
  }
  if (connecting) {
    const node = getNode(connecting.source);
    if (node) edgesLayer.append(svgElement('path', { d: edgePath({ x: node.x + nodeSize(node).width, y: node.y + 74.5 }, connecting.point), class: 'edge-draft' }));
  }
  drawMinimap();
}
function copyText(value, success = '已复制到剪贴板') {
  if (!value) { toast('还没有可复制的内容'); return Promise.resolve(); }
  return navigator.clipboard.writeText(value).then(() => toast(success)).catch(() => {
    const area = el('textarea'); area.value = value; area.style.position = 'fixed'; area.style.opacity = '0'; document.body.append(area); area.select();
    const done = document.execCommand('copy'); area.remove();
    if (!done) throw new Error('剪贴板不可用，请选中文本后手动复制。');
    toast(success);
  });
}
function outputMedia(output, className, controls = false) {
  const url = mediaURL(output.url);
  if (!url) return el('div', 'media-error', '此媒体地址不可用。请从本地任务重新载入。');
  const media = el(output.type === 'video' ? 'video' : 'img', className);
  media.src = url;
  if (output.type === 'video') { media.controls = controls; media.preload = 'metadata'; media.playsInline = true; }
  else { media.alt = output.filename || '本地生成结果'; media.loading = 'lazy'; }
  media.addEventListener('error', () => { if (media.isConnected) media.replaceWith(el('div', 'media-error', '媒体文件不可用。导入的画布不包含原始媒体，请重新导入素材或检查本地输出。')); }, { once: true });
  if (!controls) media.addEventListener('click', event => { event.stopPropagation(); preview(output); });
  return media;
}
function preview(output) {
  const url = mediaURL(output.url);
  if (!url) throw new Error('只能预览当前本地服务的媒体');
  $('#preview-title').textContent = output.filename || '本地媒体预览';
  $('#preview-content').replaceChildren(outputMedia(output, '', true));
  $('#preview-download').href = url;
  $('#preview-download').download = output.filename || 'frameweave-output';
  $('#preview-dialog').showModal();
}
function port(node, direction) {
  const element = button('', `port ${direction}${connecting?.source === node.id && direction === 'output' ? ' armed' : ''}`, () => {
    if (direction === 'output') {
      connecting = { source: node.id, point: { x: node.x + nodeSize(node).width + 80, y: node.y + 74.5 } };
      canvas.classList.add('connecting');
      $('#canvas-hint').textContent = '点击目标输入端口连接 · Esc 取消';
      renderEdges(); renderSelection();
    } else if (connecting) {
      const source = connecting.source;
      mutate(() => connect(graph, source, node.id));
      cancelConnection(); toast('节点已连接');
    } else toast('先点击来源节点的右侧输出端口');
  }, `${node.data.title} · ${direction === 'input' ? '输入' : '输出'}端口`);
  element.dataset.port = direction;
  return element;
}
function cancelConnection() { connecting = null; canvas.classList.remove('connecting'); $('#canvas-hint').textContent = '滚轮缩放 · 空白拖动 · Shift 框选'; renderEdges(); renderSelection(); }
function renderNodes() {
  nodesLayer.replaceChildren();
  graph.nodes.forEach((node, index) => {
    const card = el('article', `node node-${node.type}${selected.has(node.id) ? ' selected' : ''}`);
    card.id = `fw-node-${node.id}`; card.dataset.nodeId = node.id; card.style.left = `${node.x}px`; card.style.top = `${node.y}px`;
    card.setAttribute('aria-label', `${node.data.title} 节点`);
    const header = el('div', 'node-header');
    header.append(el('span', 'node-badge', { prompt: 'T', reference: '▧', generation: node.data.kind?.startsWith('h3') ? '▷' : '✧', result: '▣' }[node.type]), el('span', 'node-title', node.data.title), el('span', 'node-index', String(index + 1).padStart(2, '0')));
    card.append(header);
    const body = el('div', 'node-body');
    if (node.type === 'prompt') {
      const text = el('textarea', 'node-textarea'); text.value = node.data.text; text.placeholder = '描述画面、主体、镜头与运动…'; text.setAttribute('aria-label', `${node.data.title} 内容`);
      text.addEventListener('change', () => mutate(() => { node.data.text = text.value; }, { inspector: false }));
      body.append(text); card.append(body);
      const footer = el('div', 'node-footer'); footer.append(el('span', '', `${node.data.text.length} 字 · 可连接多个生成节点`), button('复制提示词 ↗', 'node-action', () => copyText(node.data.text))); card.append(footer, port(node, 'output'));
    } else if (node.type === 'generation') {
      const labels = el('div', 'port-label'); labels.append(el('span', '', 'INPUT / 提示词与参考'), el('span', '', 'OUTPUT'));
      body.append(labels, el('span', 'model-chip', node.data.kind.startsWith('h3') ? 'MiniMax H3 · 本地推理' : node.data.kind === 'api' ? 'API 工作流 · 高级' : `${node.data.kind === 'krea' ? 'Krea 2' : 'SDXL'} · 本地推理`));
      const summary = el('div', 'generation-summary');
      const stats = node.data.kind === 'api' ? [['工作流', '已导入 API'], ['节点', Object.keys(node.data.apiPrompt || {}).length], ['执行', '本地引擎'], ['编辑', '原始 JSON']] : [['尺寸', `${node.data.width} × ${node.data.height}`], ['模式', node.data.kind.startsWith('h3') ? `${node.data.seconds}s · ${node.data.fps}fps` : '静态图像'], ['采样步数', node.data.steps], ['种子', node.data.seed]];
      stats.forEach(([name, value]) => { const stat = el('div', 'stat'); stat.append(el('span', '', name), el('strong', '', value)); summary.append(stat); });
      body.append(summary);
      let prompt = ''; try { prompt = generationPayload(graph, node.id).positive; } catch { /* API import has no prompt yet. */ }
      body.append(el('p', 'node-prompt-summary', node.data.kind === 'api' ? '保留原始 ComfyUI API 节点与参数，按完整工作流执行。' : prompt || '连接提示词节点，或在右侧填写画面描述。'));
      const run = button(submitting.has(node.id) ? '正在提交…' : '▷  开始生成', 'button primary run-node', () => runNode(node.id)); run.disabled = submitting.has(node.id); run.dataset.runNode = node.id;
      body.append(run); card.append(body);
      const footer = el('div', 'node-footer');
      const status = el('span', 'node-status', '○ 等待提交'); status.dataset.nodeStatus = node.id;
      footer.append(status, button('检查环境', 'node-action', () => runDiagnostics(node))); card.append(footer, port(node, 'input'), port(node, 'output'));
    } else if (node.type === 'reference') {
      if (node.data.url) body.append(outputMedia({ url: node.data.url, type: node.data.mediaType, filename: node.data.name }, 'reference-media'));
      else { const drop = button('', 'reference-drop', () => chooseReference(node.id)); drop.append(el('span', 'large', '＋'), el('span', '', '选择参考图片'), el('span', 'field-help', 'PNG · JPG · WebP · 最大 20 MiB')); body.append(drop); }
      body.append(el('div', 'reference-name', node.data.name || '参考图保存在本机推理服务中')); card.append(body);
      const footer = el('div', 'node-footer'); footer.append(el('span', '', { start: '首帧参考', end: '尾帧参考', reference: '角色 / 场景参考' }[node.data.role] || '参考素材'), button('更换素材', 'node-action', () => chooseReference(node.id))); card.append(footer, port(node, 'output'));
    } else {
      const outputs = Array.isArray(node.data.outputs) ? node.data.outputs : [];
      if (outputs.length) {
        body.append(outputMedia(outputs[0], outputs[0].type === 'video' ? 'output-video' : 'output-image'));
        const caption = el('div', 'output-caption'); caption.append(el('span', '', outputs[0].type === 'video' ? 'VIDEO · 本地输出' : 'IMAGE · 本地输出'), button('大图预览 ↗', 'node-action', () => preview(outputs[0]))); body.append(caption);
        if (outputs.length > 1) body.append(button(`查看全部 ${outputs.length} 个输出 →`, 'node-action', () => switchTab('jobs')));
      } else {
        const placeholder = el('div', 'output-placeholder'); placeholder.append(el('span', 'empty-icon', '▻'), el('strong', '', '等待第一帧灵感'), el('p', '', '连接生成节点并运行，实际图像与视频将在这里呈现。')); body.append(placeholder);
        const caption = el('div', 'output-caption'); caption.append(el('span', '', 'OUTPUT / 本地媒体'), el('span', '', '未生成')); body.append(caption);
      }
      card.append(body); const footer = el('div', 'node-footer'); footer.append(el('span', '', node.data.jobId ? `任务 ${node.data.jobId.slice(0, 8)}` : '结果会自动保存到本机'), el('span', '', 'IMAGE / VIDEO')); card.append(footer, port(node, 'input'));
    }
    nodesLayer.append(card);
  });
  $('#node-count').textContent = `${graph.nodes.length} 个节点`;
  $('#canvas-empty').hidden = !!graph.nodes.length;
  updateNodeJobStatus();
  requestAnimationFrame(renderEdges);
}
function renderSelection() {
  document.querySelectorAll('.node').forEach(node => node.classList.toggle('selected', selected.has(node.dataset.nodeId)));
  document.querySelectorAll('.port.output').forEach(element => element.classList.toggle('armed', connecting?.source === element.closest('.node').dataset.nodeId));
  drawMinimap();
}
function editNode(id, key, value, refreshInspector = false) { mutate(() => { const node = getNode(id); if (node) node.data[key] = value; }, { inspector: refreshInspector }); }
function field(label, value, onChange, options = {}) {
  const wrapper = el('label', 'field'); wrapper.append(el('span', '', label));
  if (options.help) wrapper.append(el('span', 'field-help', options.help));
  const input = el(options.multiline ? 'textarea' : options.select ? 'select' : 'input');
  input.setAttribute('aria-label', label);
  if (options.select) {
    options.select.forEach(option => { const item = el('option', '', typeof option === 'string' ? option : option.label); item.value = typeof option === 'string' ? option : option.value; input.append(item); });
  } else if (!options.multiline) input.type = options.number ? 'number' : 'text';
  if (options.multiline) input.rows = options.rows || 4;
  if (options.readonly) input.readOnly = true;
  if (options.placeholder) input.placeholder = options.placeholder;
  if (options.min !== undefined) input.min = String(options.min);
  if (options.max !== undefined) input.max = String(options.max);
  if (options.step !== undefined) input.step = String(options.step);
  input.value = value ?? '';
  input.addEventListener('change', () => {
    const next = options.number ? Number(input.value) : input.value;
    if (options.number && (!Number.isFinite(next) || !input.checkValidity())) { toast(`「${label}」参数超出可用范围`, true); input.value = value; return; }
    onChange(next);
  });
  wrapper.append(input); return wrapper;
}
function section(container, label, index) { const heading = el('div', 'section-label'); heading.append(el('span', '', label), el('span', 'section-index', index)); container.append(heading); }
function catalog(key, kind) {
  let values = engine.models?.[key] || (key === 'checkpoint' ? engine.models?.checkpoints : []) || [];
  values = values.map(value => typeof value === 'string' ? value : value?.name).filter(Boolean);
  const lower = value => value.toLowerCase().replaceAll('\\', '/');
  if (kind.startsWith('h3')) {
    if (key === 'dit') return values.filter(value => /h3/i.test(value) && (kind === 'h3_ref' ? /ref/i.test(value) : /fl2v|fl2va|t2v/i.test(value)) && !/lora|turbo_4step|turbo_8step/i.test(value));
    if (key === 'text_encoder') return values.filter(value => /minimax_h3|qwen3vl[_-]?32b|qwen3[_-]vl[_-]?32b/.test(lower(value)));
    if (key === 'vae') return values.filter(value => /minimax_h3.*video|h3.*video.*vae|h3.*vae.*video/.test(lower(value)));
    if (key === 'audio_vae') return values.filter(value => /h3.*audio|audio.*h3/.test(lower(value)));
    if (key === 'lora') return values.filter(value => /h3/.test(lower(value)) && !(kind === 'h3_ref' ? /fl2v/.test(lower(value)) : /ref2v/.test(lower(value))));
  }
  if (kind === 'krea') {
    if (key === 'dit') return values.filter(value => /krea2|krea_2/.test(lower(value)) && !/lora/.test(lower(value)));
    if (key === 'text_encoder') return values.filter(value => /qwen3vl[_-]?4b|qwen3[_-]vl[_-]?4b/.test(lower(value)));
    if (key === 'vae') return values.filter(value => /qwen_image|qwen.*vae/.test(lower(value)));
    if (key === 'lora') return values.filter(value => /krea/.test(lower(value)));
  }
  if (kind === 'sdxl' && key === 'lora') return values.filter(value => /sdxl|pony|illustrious|noob|\bxl\b/.test(lower(value)));
  return values;
}
function modelField(node, label, key) {
  const values = catalog(key, node.data.kind);
  const current = node.data.models?.[key] || '';
  if (current && !values.includes(current)) values.unshift(current);
  return field(label, current, value => mutate(() => { node.data.models = { ...node.data.models, [key]: value }; }, { inspector: false }), { select: [{ value: '', label: key === 'lora' ? '不使用 LoRA' : '自动匹配可用模型' }, ...values.map(value => ({ value, label: key === 'lora' ? `${/turbo|lightning|lcm|hyper|\d[_-]?step/i.test(value) ? '加速' : '风格 / 适配'} · ${value}` : value }))], help: values.length ? `${values.length} 个可选模型` : '连接引擎后读取模型目录' });
}
function renderInspector() {
  const content = $('#inspector-content'); content.replaceChildren();
  if (selectedEdge) {
    const wrap = el('div', 'inspector-empty'); wrap.append(el('span', 'eyebrow', 'CONNECTION'), el('h2', '', '工作流连接'), el('p', '', '连接将提示词、参考素材和生成结果传递给下一个节点。'), button('删除此连接', 'button quiet', () => deleteSelection())); content.append(wrap); return;
  }
  if (selected.size > 1) {
    const wrap = el('div', 'multi-selection'); wrap.append(el('span', 'eyebrow', 'MULTI SELECTION'), el('h2', '', `已选择 ${selected.size} 个节点`), el('p', '', '拖动任一已选节点的标题，可以一起移动。复制时会保留所选节点之间的连接。'));
    const actions = el('div', 'inspector-actions'); actions.append(button('复制所选', 'button quiet', duplicateSelection), button('删除所选', 'button quiet', deleteSelection)); wrap.append(actions); content.append(wrap); return;
  }
  const node = singleSelected();
  if (!node) {
    const wrap = el('div', 'inspector-empty'); wrap.append(el('span', 'eyebrow', 'YOUR CREATIVE SPACE'), el('h2', '', '选择一个节点，开始创作'), el('p', '', '在这里调节模型、镜头与生成参数。每个节点都可以自由连接和复用。'), el('hr', 'divider'), button('检查本地环境', 'button quiet', () => runDiagnostics())); content.append(wrap); return;
  }
  const wrap = el('div', 'inspector-content-wrap');
  wrap.append(el('span', 'eyebrow', { prompt: 'PROMPT DESIGN', reference: 'REFERENCE ASSET', generation: 'GENERATION CONTROL', result: 'OUTPUT PREVIEW' }[node.type]));
  const title = el('div', 'inspector-title-row'); title.append(el('h2', '', node.type === 'generation' ? KIND_NAMES[node.data.kind] : node.data.title)); wrap.append(title);
  wrap.append(el('p', 'inspector-description', { prompt: '写下画面、光线与运动，将文字连接到生成节点。', reference: '角色、场景或首尾帧，让每一次生成有据可循。', generation: '精确设定每一帧，让创作保持可控。', result: '实际输出与任务记录，完整保存在本地。' }[node.type]));
  wrap.append(field('节点名称', node.data.title, value => editNode(node.id, 'title', value || '未命名节点')));
  if (node.type === 'generation') {
    section(wrap, '生成模式', '01 / MODEL');
    wrap.append(field('模型与任务', node.data.kind, kind => mutate(() => {
      node.data.kind = kind; node.data.title = KIND_NAMES[kind]; node.data.models = {};
      if (kind === 'krea') { node.data.steps = 8; node.data.cfg = 1; node.data.width = 1024; node.data.height = 1024; }
      else if (kind === 'sdxl') { node.data.steps = 25; node.data.cfg = 7; node.data.width = 1024; node.data.height = 1024; }
      else if (kind.startsWith('h3')) { node.data.steps = 20; node.data.cfg = 1; node.data.width = 768; node.data.height = 448; }
    }), { select: Object.entries(KIND_NAMES).map(([value, label]) => ({ value, label })) }));
    if (node.data.kind === 'api') {
      wrap.append(el('p', 'model-note', '导入 ComfyUI「Save (API Format)」JSON。工作流完整保留，模型与路径仍需在你的推理引擎中可用。'));
      wrap.append(button(node.data.apiPrompt ? '重新导入 API 工作流' : '导入 API 工作流', 'button quiet', () => { workflowTarget = node.id; $('#workflow-input').click(); }));
      if (node.data.apiPrompt) wrap.append(field('API 工作流 JSON', stableStringify(node.data.apiPrompt), value => { try { const parsed = JSON.parse(value); if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error(); editNode(node.id, 'apiPrompt', parsed); } catch { toast('API 工作流必须是有效 JSON 对象', true); } }, { multiline: true, rows: 10 }));
    } else {
      if (node.data.kind.startsWith('h3')) wrap.append(el('p', 'model-note', 'MiniMax H3 需要兼容扩展与模型。默认 20 步；低步数加速须配合对应 Turbo LoRA。实际帧数与时长由引擎校正。'));
      if (node.data.kind === 'h3_i2v') wrap.append(el('p', 'form-note', '连接首帧参考素材，可再连接一张尾帧。素材属性中选择「首帧」与「尾帧」角色。'));
      if (node.data.kind === 'h3_ref') wrap.append(el('p', 'form-note', '连接角色或场景参考素材以保持一致性。兼容素材类型与上限由当前 H3 扩展校验。'));
      section(wrap, '画面与提示词', '02 / DIRECTION');
      const incomingPrompts = graph.edges.filter(edge => edge.target === node.id && getNode(edge.source)?.type === 'prompt').length;
      wrap.append(field(incomingPrompts ? `补充提示词 · 已连接 ${incomingPrompts} 个文本节点` : '正向提示词', node.data.positive, value => editNode(node.id, 'positive', value), { multiline: true, rows: 4, placeholder: '主体、环境、动作、光线、镜头…' }));
      wrap.append(field('负向提示词', node.data.negative, value => editNode(node.id, 'negative', value), { multiline: true, rows: 2, placeholder: '不希望出现的内容' }));
      wrap.append(button('复制合并后的提示词', 'text-link', () => { const payload = generationPayload(graph, node.id); return copyText(`${payload.positive}${payload.negative ? `\n\n负向提示词：${payload.negative}` : ''}`); }));
      section(wrap, '画幅与时间', '03 / FRAME');
      const ratios = el('div', 'ratio-list');
      [['横屏', 768, 448], ['竖屏', 448, 768], ['1 : 1', 768, 768]].forEach(([label, width, height]) => { const active = Math.abs(node.data.width / node.data.height - width / height) < .01; ratios.append(button(label, `ratio-button${active ? ' active' : ''}`, () => mutate(() => { node.data.width = width; node.data.height = height; }))); });
      wrap.append(ratios);
      const dimensionStep = node.data.kind.startsWith('h3') ? 32 : node.data.kind === 'krea' ? 16 : 8;
      const dimensions = el('div', 'field-grid'); dimensions.append(field('宽度 / px', node.data.width, value => editNode(node.id, 'width', value), { number: true, min: 64, max: 4096, step: dimensionStep }), field('高度 / px', node.data.height, value => editNode(node.id, 'height', value), { number: true, min: 64, max: 4096, step: dimensionStep })); wrap.append(dimensions);
      if (node.data.kind.startsWith('h3')) { const timing = el('div', 'field-grid'); timing.append(field('时长 / s', node.data.seconds, value => editNode(node.id, 'seconds', value), { number: true, min: 1, max: 30, step: .1 }), field('帧率 / fps', 24, () => {}, { number: true, readonly: true, help: 'H3 原生固定 24 fps' })); wrap.append(timing); }
      section(wrap, '采样与可复现性', '04 / SAMPLING');
      const sampling = el('div', 'field-grid'); sampling.append(field('采样步数', node.data.steps, value => editNode(node.id, 'steps', value), { number: true, min: 1, max: 150, step: 1 }), field('引导强度 / CFG', node.data.cfg, value => editNode(node.id, 'cfg', value), { number: true, min: 0, max: 30, step: .1 })); wrap.append(sampling);
      wrap.append(field('随机种子', node.data.seed, value => editNode(node.id, 'seed', value), { number: true, min: 0, max: Number.MAX_SAFE_INTEGER, step: 1 }));
      wrap.append(button('↻  换一个随机种子', 'text-link', () => editNode(node.id, 'seed', crypto.getRandomValues(new Uint32Array(1))[0], true)));
      const schedule = el('div', 'field-grid');
      schedule.append(field('采样器', node.data.sampler || 'euler', value => editNode(node.id, 'sampler', value), { select: ['euler', 'euler_ancestral', 'heun', 'dpmpp_2m', 'dpmpp_2m_sde', 'dpmpp_sde', 'uni_pc', 'ddim'] }), field('调度器', node.data.scheduler || 'simple', value => editNode(node.id, 'scheduler', value), { select: ['simple', 'normal', 'karras', 'exponential', 'sgm_uniform', 'beta'] }));
      wrap.append(schedule, field('去噪强度', node.data.denoise ?? 1, value => editNode(node.id, 'denoise', value), { number: true, min: 0, max: 1, step: .05, readonly: node.data.kind.startsWith('h3'), help: node.data.kind.startsWith('h3') ? 'H3 条件生成固定为 1' : '低于 1 时需要连接参考图' }));
      section(wrap, '模型文件', '05 / LOCAL ASSETS');
      const modelFields = node.data.kind === 'sdxl' ? [['Checkpoint 主模型', 'checkpoint']] : [['DiT 主模型', 'dit'], ['文本编码器', 'text_encoder'], ['图像 / 视频 VAE', 'vae'], ...(node.data.kind.startsWith('h3') ? [['音频 VAE', 'audio_vae']] : [])];
      modelFields.forEach(([label, key]) => wrap.append(modelField(node, label, key)));
      wrap.append(modelField(node, 'LoRA · 风格 / 加速', 'lora'));
      wrap.append(field('LoRA 强度', node.data.lora_strength ?? 1, value => editNode(node.id, 'lora_strength', value), { number: true, min: -2, max: 2, step: .05 }));
    }
    const actions = el('div', 'inspector-actions'); actions.append(button('检查缺失项', 'button quiet', () => runDiagnostics(node)), button('导出执行 JSON', 'button quiet', () => compileNode(node))); wrap.append(actions);
    const run = button(submitting.has(node.id) ? '正在提交…' : '▷  开始生成', 'button primary inspector-run', () => runNode(node.id)); run.disabled = submitting.has(node.id); run.dataset.runNode = node.id; wrap.append(run);
    wrap.append(el('p', 'form-note', '速度与质量取决于后端、模型、显存和参数。生成任务通过本机服务执行，可在队列中查看耗时与取消。'));
  } else if (node.type === 'prompt') {
    wrap.append(field('正向提示词', node.data.text, value => editNode(node.id, 'text', value), { multiline: true, rows: 9 }), field('负向提示词', node.data.negative, value => editNode(node.id, 'negative', value), { multiline: true, rows: 3 }));
    wrap.append(button('复制提示词', 'button primary inspector-run', () => copyText(node.data.text)));
  } else if (node.type === 'reference') {
    if (node.data.url) wrap.append(outputMedia({ url: node.data.url, type: node.data.mediaType, filename: node.data.name }, 'reference-media'));
    wrap.append(field('参考角色', node.data.role, value => editNode(node.id, 'role', value), { select: [{ value: 'reference', label: '角色 / 场景参考' }, { value: 'start', label: '首帧' }, { value: 'end', label: '尾帧' }] }));
    wrap.append(el('p', 'form-note', node.data.name || '还未导入素材。'));
    wrap.append(button('选择本地参考图片', 'button quiet inspector-run', () => chooseReference(node.id)));
    wrap.append(el('p', 'form-note', '素材将发送给已连接的本机推理服务，保存在其输入目录。导出画布只记录引用，不打包原始文件。'));
  } else {
    if (node.data.outputs?.length) node.data.outputs.forEach(output => { wrap.append(outputMedia(output, 'output-image'), button('打开大预览', 'button quiet inspector-run', () => preview(output))); });
    else wrap.append(el('p', 'model-note', '尚无真实生成结果。连接生成节点，检查环境后提交任务。'));
  }
  wrap.append(el('hr', 'divider'));
  const bottom = el('div', 'inspector-actions'); bottom.append(button('复制节点', 'button quiet', duplicateSelection), button('删除节点', 'button quiet', deleteSelection)); wrap.append(bottom);
  content.append(wrap);
}
function renderAll() { renderNodes(); renderInspector(); updateHistory(); applyViewport(); }
function addNode(type, data = {}) {
  const point = viewPoint(canvas.getBoundingClientRect().left + canvas.clientWidth / 2, canvas.getBoundingClientRect().top + canvas.clientHeight / 2);
  const node = createNode(type, point.x - 145, point.y - 115, data);
  mutate(() => { graph.nodes.push(node); selected = new Set([node.id]); selectedEdge = null; });
  return node;
}
function deleteSelection() {
  if (!selected.size && !selectedEdge) return;
  mutate(() => {
    if (selectedEdge) graph.edges = graph.edges.filter(edge => edge.id !== selectedEdge);
    removeNodes(graph, selected); selected.clear(); selectedEdge = null;
  });
  toast('已删除，可使用 Ctrl+Z 撤销');
}
function duplicateSelection() { if (!selected.size) return; mutate(() => { selected = new Set(duplicateNodes(graph, selected)); }); }
function downloadJSON(value, filename) {
  const blob = new Blob([typeof value === 'string' ? value : stableStringify(value)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob); const link = el('a'); link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 10000);
}
function exportProject() { downloadJSON(serializeGraph(graph, viewport), `frameweave-canvas-${new Date().toISOString().slice(0, 10)}.json`); save(true); toast('已导出画布 JSON（不包含模型与原始素材）'); }
async function compileNode(node) {
  const result = await api('/api/compile', generationPayload(graph, node.id));
  downloadJSON(result.prompt, `frameweave-${node.data.kind}-api.json`);
  toast(typeof result.summary === 'string' ? result.summary : '已校验并导出执行工作流 JSON');
}
async function refreshEngine(showToast = false) {
  try {
    engine = await api('/api/status');
    $('#engine-status').classList.toggle('online', !!engine.online); $('#engine-status').classList.toggle('offline', !engine.online);
    $('#engine-label').textContent = engine.online ? '本地引擎已连接' : '本地引擎未连接';
    $('#engine-status').title = engine.online ? `${engine.backend_url || settings.backend_url} · ${engine.devices?.map(item => typeof item === 'string' ? item : item.name).filter(Boolean).join(' / ') || '点击检查环境'}` : '点击查看缺失项与修复提示词';
    if (showToast) toast(engine.online ? '已连接本地推理引擎' : '引擎尚未就绪，可复制环境检查中的修复提示词', !engine.online);
  } catch (error) {
    engine.online = false; $('#engine-status').classList.remove('online'); $('#engine-status').classList.add('offline'); $('#engine-label').textContent = '本地服务不可用';
    if (showToast) throw error;
  }
}
async function runDiagnostics(node = selectedGeneration()) {
  const dialog = $('#diagnostics-dialog'); if (!dialog.open) dialog.showModal();
  $('#diagnostic-summary').textContent = '正在读取本地节点能力、模型与环境…'; $('#diagnostic-list').replaceChildren(); $('#repair-prompt').value = ''; $('#diagnostic-refresh').disabled = true; $('#copy-repair').disabled = true;
  try {
    const result = await api('/api/diagnostics', { kind: node?.data.kind || 'h3_t2v', models: node?.data.models || {} });
    $('#diagnostic-summary').textContent = typeof result.summary === 'string' ? result.summary : '环境检查完成。以下结果来自本地服务。';
    const checks = Array.isArray(result.checks) ? result.checks : [];
    checks.forEach(check => { const row = el('div', `check-row ${['ok', 'missing', 'warning', 'error'].includes(check.status) ? check.status : 'warning'}`); row.append(el('span', 'check-symbol', check.status === 'ok' ? '✓' : check.status === 'warning' ? '!' : '×')); const text = el('div'); text.append(el('div', 'check-name', check.name), el('div', 'check-detail', check.detail)); row.append(text); $('#diagnostic-list').append(row); });
    $('#repair-prompt').value = result.repair_prompt || '未返回修复提示词。请重新检查本地服务。';
    $('#copy-repair').disabled = !result.repair_prompt;
    await refreshEngine();
    if (!$('#properties-panel').contains(document.activeElement)) renderInspector();
  } catch (error) { $('#diagnostic-summary').textContent = error.message; throw error; }
  finally { $('#diagnostic-refresh').disabled = false; }
}
async function runNode(id) {
  if (submitting.has(id)) return;
  const node = getNode(id); if (!node) return;
  const payload = generationPayload(graph, id);
  if (payload.kind !== 'api' && !payload.positive.trim()) throw new Error('先连接提示词节点或填写正向提示词。');
  submitting.add(id); document.querySelectorAll('[data-run-node]').forEach(element => { if (element.dataset.runNode === id) { element.disabled = true; element.textContent = '正在提交…'; } });
  try {
    const job = await api('/api/jobs', payload);
    if (!job.id) throw new Error('服务没有返回任务 ID');
    jobNodes[job.id] = id;
    mutate(() => {
      let targets = graph.edges.filter(edge => edge.source === id).map(edge => getNode(edge.target)).filter(item => item?.type === 'result');
      if (!targets.length) { const result = createNode('result', node.x + 385, node.y, { title: `${node.data.title} · 结果` }); graph.nodes.push(result); connect(graph, id, result.id); targets = [result]; }
      targets.forEach(target => { target.data.jobId = job.id; target.data.outputs = []; });
    });
    jobs.unshift({ ...job, elapsed: job.elapsed || 0, outputs: job.outputs || [] });
    switchTab('jobs'); renderJobs(); save(true);
    toast('任务已提交到本地引擎');
    await pollJobs();
  } finally { submitting.delete(id); document.querySelectorAll('[data-run-node]').forEach(element => { if (element.dataset.runNode === id) { element.disabled = false; element.textContent = '▷  开始生成'; } }); }
}
function duration(seconds) { seconds = Math.max(0, Math.floor(Number(seconds) || 0)); return seconds >= 60 ? `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s` : `${seconds}s`; }
function updateNodeJobStatus() {
  document.querySelectorAll('[data-node-status]').forEach(element => {
    const job = jobs.find(item => jobNodes[item.id] === element.dataset.nodeStatus);
    element.classList.toggle('error', job?.status === 'failed');
    element.textContent = job ? `${job.status === 'completed' ? '✓' : job.status === 'failed' ? '!' : '○'} ${STATUS_NAMES[job.status] || job.status} · ${duration(job.elapsed)}` : '○ 等待提交';
  });
}
function renderJobs() {
  $('#job-count').textContent = String(jobs.filter(job => ['queued', 'running'].includes(job.status)).length);
  const list = $('#jobs-list'); list.replaceChildren();
  if (!jobs.length) { list.append(el('div', 'jobs-empty', '还没有生成任务\n选中生成节点，点击「开始生成」。')); return; }
  jobs.forEach(job => {
    const card = el('article', 'job-card');
    const heading = el('div', 'job-heading'); heading.append(el('span', '', getNode(jobNodes[job.id])?.data.title || `任务 ${job.id.slice(0, 8)}`), el('span', `job-tag ${job.status}`, STATUS_NAMES[job.status] || job.status)); card.append(heading);
    const time = el('div', 'job-time'); time.append(el('span', '', `耗时 ${duration(job.elapsed)}`), el('span', '', job.id.slice(0, 8))); card.append(time);
    const progress = progressPercent(job.progress);
    const track = el('div', 'progress-track'); const bar = el('div', 'progress-bar'); bar.style.width = `${job.status === 'completed' ? 100 : progress ?? 0}%`; track.append(bar); card.append(track);
    if (progress === null && ['queued', 'running'].includes(job.status)) card.append(el('div', 'progress-state', job.status === 'queued' ? '等待引擎执行' : '推理进行中 · 后端暂未提供逐步进度'));
    if (job.error) card.append(el('p', 'job-error', job.error));
    if (job.outputs?.length) {
      const thumbs = el('div', 'job-thumbs'); job.outputs.forEach(output => { const item = button('', '', () => preview(output), `预览 ${output.filename || '输出'}`); const media = outputMedia(output, ''); item.append(media); thumbs.append(item); }); card.append(thumbs);
    }
    if (['queued', 'running'].includes(job.status)) card.append(button('取消任务', 'job-cancel', async () => { await api(`/api/jobs/${encodeURIComponent(job.id)}/cancel`, {}); toast('已发送取消请求'); await pollJobs(); }));
    list.append(card);
  });
  updateNodeJobStatus();
}
async function pollJobs() {
  if (pollBusy || !csrf) return;
  pollBusy = true;
  try {
    const response = await api('/api/jobs');
    const incoming = Array.isArray(response.jobs) ? response.jobs : [];
    let outputsChanged = false;
    jobs = incoming;
    for (const node of graph.nodes.filter(item => item.type === 'result' && item.data.jobId)) {
      const job = jobs.find(item => item.id === node.data.jobId);
      if (job?.status === 'completed' && JSON.stringify(node.data.outputs) !== JSON.stringify(job.outputs || [])) { node.data.outputs = clone(job.outputs || []); outputsChanged = true; }
    }
    renderJobs();
    if (outputsChanged) { renderNodes(); if (singleSelected()?.type === 'result') renderInspector(); save(); }
  } catch { /* Keep the last known task list on a transient disconnect. Status shows connection health. */ }
  finally { pollBusy = false; }
}
function switchTab(tab) {
  const properties = tab === 'properties';
  $('#tab-properties').classList.toggle('active', properties); $('#tab-properties').setAttribute('aria-selected', String(properties));
  $('#tab-jobs').classList.toggle('active', !properties); $('#tab-jobs').setAttribute('aria-selected', String(!properties));
  $('#properties-panel').hidden = !properties; $('#jobs-panel').hidden = properties;
}
function chooseReference(id = null) { uploadTarget = id; $('#reference-input').click(); }
async function uploadFile(file, target) {
  if (!/^image\/(png|jpeg|webp)$/.test(file.type)) throw new Error('参考素材支持 PNG、JPG、WebP 图片。视频输出可在生成后预览。');
  if (file.size > 20 * 1024 * 1024) throw new Error('初版单张参考图上限为 20 MiB，请先缩小图片。');
  toast(`正在导入 ${file.name}…`);
  const data = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('无法读取素材')); reader.readAsDataURL(file); });
  const uploaded = await api('/api/upload', { name: file.name, data });
  if (!uploaded.name || !uploaded.url) throw new Error('上传服务没有返回有效素材引用');
  if (target && getNode(target)) mutate(() => { const node = getNode(target); node.data = { ...node.data, name: uploaded.name, url: uploaded.url, mediaType: file.type.startsWith('video/') ? 'video' : 'image' }; });
  else addNode('reference', { title: file.name.replace(/\.[^.]+$/, '').slice(0, 50), name: uploaded.name, url: uploaded.url, mediaType: file.type.startsWith('video/') ? 'video' : 'image' });
  toast('素材已保存到本地');
}

canvas.addEventListener('wheel', event => {
  if (event.target.closest('textarea,select') && !event.ctrlKey) return;
  event.preventDefault();
  const rect = canvas.getBoundingClientRect(); zoom(Math.exp(-event.deltaY * .0015), event.clientX - rect.left, event.clientY - rect.top);
}, { passive: false });
canvas.addEventListener('pointerdown', event => {
  if (event.button !== 0 && event.button !== 1) return;
  const card = event.target.closest('.node');
  const interactive = event.target.closest('button,input,textarea,select,video,a');
  if (event.target.closest('[data-edge-id],.edge-line')) return;
  if (interactive && event.button !== 1 && !spaceDown) return;
  if (connecting && !card && event.button === 0) { cancelConnection(); return; }
  const point = viewPoint(event.clientX, event.clientY);
  if (spaceDown || event.button === 1 || tool === 'hand' || !card && !event.shiftKey) {
    pointer = { mode: 'pan', x: event.clientX, y: event.clientY, startX: viewport.x, startY: viewport.y, distance: 0 };
    canvas.classList.add('panning');
  } else if (!card && event.shiftKey) {
    const rect = canvas.getBoundingClientRect(); pointer = { mode: 'box', x: event.clientX - rect.left, y: event.clientY - rect.top, previous: new Set(selected) };
    const box = $('#selection-box'); box.hidden = false; box.style.left = `${pointer.x}px`; box.style.top = `${pointer.y}px`; box.style.width = '0'; box.style.height = '0';
  } else if (card) {
    const id = card.dataset.nodeId;
    if (event.shiftKey) { if (selected.has(id)) selected.delete(id); else selected.add(id); }
    else if (!selected.has(id)) selected = new Set([id]);
    selectedEdge = null; renderSelection(); renderInspector(); switchTab('properties');
    if (event.target.closest('.node-header') && selected.has(id)) pointer = { mode: 'drag', start: point, before: snapshot(), positions: graph.nodes.filter(node => selected.has(node.id)).map(node => ({ id: node.id, x: node.x, y: node.y })) };
  }
  if (pointer) { canvas.setPointerCapture(event.pointerId); event.preventDefault(); }
});
canvas.addEventListener('pointermove', event => {
  const point = viewPoint(event.clientX, event.clientY);
  if (connecting) { connecting.point = point; renderEdges(); }
  if (!pointer) return;
  if (pointer.mode === 'pan') {
    viewport.x = pointer.startX + event.clientX - pointer.x; viewport.y = pointer.startY + event.clientY - pointer.y; pointer.distance = Math.abs(event.clientX - pointer.x) + Math.abs(event.clientY - pointer.y); applyViewport();
  } else if (pointer.mode === 'drag') {
    for (const start of pointer.positions) { const node = getNode(start.id); node.x = Math.round(start.x + point.x - pointer.start.x); node.y = Math.round(start.y + point.y - pointer.start.y); const element = document.getElementById(`fw-node-${node.id}`); element.style.left = `${node.x}px`; element.style.top = `${node.y}px`; }
    renderEdges();
  } else {
    const rect = canvas.getBoundingClientRect(); const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const left = Math.min(pointer.x, x), top = Math.min(pointer.y, y), right = Math.max(pointer.x, x), bottom = Math.max(pointer.y, y);
    const box = $('#selection-box'); Object.assign(box.style, { left: `${left}px`, top: `${top}px`, width: `${right - left}px`, height: `${bottom - top}px` });
    selected = new Set(pointer.previous);
    graph.nodes.forEach(node => { const size = nodeSize(node); const nx = node.x * viewport.scale + viewport.x, ny = node.y * viewport.scale + viewport.y; if (nx + size.width * viewport.scale >= left && nx <= right && ny + size.height * viewport.scale >= top && ny <= bottom) selected.add(node.id); });
    selectedEdge = null; renderSelection();
  }
});
function finishPointer(event) {
  if (!pointer) return;
  if (pointer.mode === 'drag') pushHistory(pointer.before);
  if (pointer.mode === 'pan' && pointer.distance < 3 && !event.target.closest('.node') && !spaceDown && tool !== 'hand') { selected.clear(); selectedEdge = null; renderSelection(); renderEdges(); }
  if (pointer.mode === 'pan') save();
  pointer = null; $('#selection-box').hidden = true; canvas.classList.remove('panning'); renderInspector();
  if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
}
canvas.addEventListener('pointerup', finishPointer);
canvas.addEventListener('pointercancel', finishPointer);
canvas.addEventListener('dragover', event => { if (event.dataTransfer?.types.includes('Files')) event.preventDefault(); });
canvas.addEventListener('drop', event => {
  event.preventDefault(); const files = [...event.dataTransfer.files];
  (async () => { for (const file of files) await uploadFile(file, null); })().catch(reportError);
});
document.addEventListener('keydown', event => {
  const editing = event.target.closest('input,textarea,select,[contenteditable=true]');
  if (event.key === 'Escape') { cancelConnection(); return; }
  if (editing || document.querySelector('dialog[open]')) return;
  const command = event.ctrlKey || event.metaKey;
  if (event.code === 'Space') { event.preventDefault(); spaceDown = true; canvas.classList.add('hand'); }
  if (command && event.key.toLowerCase() === 'z') { event.preventDefault(); event.shiftKey ? redo() : undo(); }
  else if (command && event.key.toLowerCase() === 'y') { event.preventDefault(); redo(); }
  else if (command && event.key.toLowerCase() === 'd') { event.preventDefault(); duplicateSelection(); }
  else if (command && event.key.toLowerCase() === 's') { event.preventDefault(); exportProject(); }
  else if (command && event.key.toLowerCase() === 'a') { event.preventDefault(); selected = new Set(graph.nodes.map(node => node.id)); renderSelection(); renderInspector(); }
  else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); deleteSelection(); }
  else if (event.key.toLowerCase() === 'f') { event.preventDefault(); fitView(); }
});
document.addEventListener('keyup', event => { if (event.code === 'Space') { spaceDown = false; canvas.classList.toggle('hand', tool === 'hand'); } });
window.addEventListener('blur', () => { spaceDown = false; canvas.classList.toggle('hand', tool === 'hand'); });
window.addEventListener('beforeunload', () => save(true));
new ResizeObserver(() => { applyViewport(); }).observe(canvas);
document.querySelectorAll('[data-close]').forEach(element => element.addEventListener('click', () => element.closest('dialog').close()));
document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } }));
$('#preview-dialog').addEventListener('close', () => $('#preview-content').replaceChildren());
bind('#tool-select', () => { tool = 'select'; canvas.classList.remove('hand'); $('#tool-select').classList.add('active'); $('#tool-hand').classList.remove('active'); $('#tool-select').setAttribute('aria-pressed', 'true'); $('#tool-hand').setAttribute('aria-pressed', 'false'); });
bind('#tool-hand', () => { tool = 'hand'; canvas.classList.add('hand'); $('#tool-hand').classList.add('active'); $('#tool-select').classList.remove('active'); $('#tool-hand').setAttribute('aria-pressed', 'true'); $('#tool-select').setAttribute('aria-pressed', 'false'); });
bind('#add-prompt', () => addNode('prompt'));
bind('#add-reference', () => chooseReference());
bind('#add-video', () => addNode('generation'));
bind('#add-image', () => addNode('generation', { title: 'SDXL 图片生成', kind: 'sdxl', width: 1024, height: 1024, steps: 25, cfg: 7 }));
bind('#add-result', () => addNode('result'));
bind('#load-demo', () => { mutate(() => { graph = createDemo(); selected = new Set([graph.nodes[1].id]); }); fitView(); });
bind('#undo', undo); bind('#redo', redo); bind('#zoom-in', () => zoom(1.15)); bind('#zoom-out', () => zoom(1 / 1.15)); bind('#zoom-reset', () => zoom(1 / viewport.scale)); bind('#fit-view', fitView); bind('#minimap-button', fitView);
bind('#save-project', exportProject); bind('#open-project', () => $('#project-input').click()); bind('#help-button', () => $('#help-dialog').showModal());
bind('#tab-properties', () => switchTab('properties')); bind('#tab-jobs', () => switchTab('jobs'));
bind('#engine-status', () => runDiagnostics()); bind('#diagnostics-button', () => runDiagnostics()); bind('#diagnostic-refresh', () => runDiagnostics()); bind('#copy-repair', () => copyText($('#repair-prompt').value, '已复制修复提示词，可交给 AI 助手'));
bind('#settings-button', () => { $('#backend-url').value = settings.backend_url; $('#model-roots').value = (settings.model_roots || []).join('\n'); $('#settings-dialog').showModal(); });
$('#settings-form').addEventListener('submit', event => {
  event.preventDefault();
  (async () => {
    const result = await api('/api/settings', { backend_url: $('#backend-url').value.trim(), model_roots: $('#model-roots').value.split('\n').map(line => line.trim()).filter(Boolean) });
    settings = result.settings || { backend_url: $('#backend-url').value.trim(), model_roots: $('#model-roots').value.split('\n').map(line => line.trim()).filter(Boolean) };
    $('#settings-dialog').close(); await refreshEngine(true); renderInspector();
  })().catch(reportError);
});
$('#project-input').addEventListener('change', event => {
  const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
  (async () => {
    if (file.size > 8 * 1024 * 1024) throw new Error('画布 JSON 最大为 8 MiB。');
    const incoming = parseGraph(await file.text());
    mutate(() => { graph = { nodes: incoming.nodes, edges: incoming.edges }; viewport = incoming.viewport; selected.clear(); selectedEdge = null; });
    projectTitle = file.name.replace(/\.json$/i, ''); $('#project-title').textContent = projectTitle; applyViewport(); save(true); toast('画布已导入。原画布可通过撤销恢复。');
  })().catch(reportError);
});
$('#reference-input').addEventListener('change', event => {
  const files = [...(event.target.files || [])]; const target = uploadTarget; event.target.value = ''; uploadTarget = null;
  (async () => { for (let index = 0; index < files.length; index++) await uploadFile(files[index], index === 0 ? target : null); })().catch(reportError);
});
$('#workflow-input').addEventListener('change', event => {
  const file = event.target.files?.[0]; const target = workflowTarget; event.target.value = ''; if (!file) return;
  (async () => {
    if (file.size > 8 * 1024 * 1024) throw new Error('API 工作流最大为 8 MiB。');
    const parsed = JSON.parse(await file.text());
    const prompt = parsed.prompt && !parsed.class_type ? parsed.prompt : parsed;
    if (!prompt || typeof prompt !== 'object' || Array.isArray(prompt) || prompt.nodes || !Object.values(prompt).length || !Object.values(prompt).every(node => node && typeof node.class_type === 'string' && node.inputs && typeof node.inputs === 'object')) throw new Error('请导入 ComfyUI 的 API 格式 JSON，普通画布 JSON 不包含可执行节点。');
    if (getNode(target)) editNode(target, 'apiPrompt', prompt, true);
    toast('API 工作流已导入，原始节点与参数完整保留');
  })().catch(reportError);
});

async function initialize() {
  try {
    const cached = localStorage.getItem(STORAGE_KEY);
    if (cached) { const parsed = parseGraph(cached); graph = { nodes: parsed.nodes, edges: parsed.edges }; viewport = parsed.viewport; selected = new Set([graph.nodes.find(node => node.type === 'generation')?.id].filter(Boolean)); restored = true; }
    const cachedJobs = JSON.parse(localStorage.getItem(JOB_MAP_KEY) || '{}'); if (cachedJobs && typeof cachedJobs === 'object' && !Array.isArray(cachedJobs)) jobNodes = cachedJobs;
  } catch { toast('本地画布记录无效，已打开安全示例。可重新导入备份。', true); }
  renderAll();
  if (!restored) requestAnimationFrame(fitView);
  try {
    const bootstrap = await api('/api/bootstrap'); csrf = bootstrap.csrf; settings = { ...settings, ...bootstrap.settings };
    if (bootstrap.version) $('.alpha').textContent = bootstrap.version;
    await refreshEngine(); renderInspector(); await pollJobs();
  } catch (error) { $('#engine-label').textContent = '本地服务不可用'; $('#engine-status').classList.add('offline'); reportError(new Error(`无法连接 FrameWeave 本地服务：${error.message}`)); }
  setInterval(() => { if (!document.hidden) pollJobs(); }, 1800);
  setInterval(() => { if (!document.hidden) refreshEngine(); }, 15000);
}
initialize();
