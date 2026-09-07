'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const source = readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');

function pageHarness(start, end, exports) {
  const nodes = new Map(), requests = [], delayed = [];
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, { value: '', classList: { remove() {}, toggle() {} }, replaceChildren() {} });
    return nodes.get(selector);
  };
  const context = {
    pages: {}, URLSearchParams, Object, Set, Number,
    $: node, $$: () => [], esc: value => String(value ?? ''),
    heading: () => '', icon: () => '', empty: () => '', pager: () => ({}),
    bindModelLinks() {}, favorites: new Set(), scopes: {},
    debounce: fn => { delayed.push(fn); return () => {}; },
    api: async url => {
      requests.push(url);
      return { total: 500, page: 3, size: 40, items: [], dirs: [], facets: { types: [], families: [] } };
    },
  };
  vm.runInNewContext(source.slice(source.indexOf(start), source.indexOf(end)) + '\nthis.subject = {' + exports + '};', context);
  return { context, requests, delayed, node, el: { isConnected: true }, ...context.subject };
}

test('restored model filters and page take precedence over the old URL parameters', async () => {
  const h = pageHarness('  const modelState=', '  // ---------- 模型详情抽屉', 'pages, modelState');
  await h.pages.models(h.el, new URLSearchParams('q=old-url&page=1&type=Checkpoint'),
    { q: 'saved-search', page: 3, type: 'LoRA', family: 'SDXL', sort: 'usage', domain:'image', purpose:'lighting' });
  const query = new URLSearchParams(h.requests[0].split('?')[1]);
  assert.equal(query.get('q'), 'saved-search');
  assert.equal(query.get('page'), '3');
  assert.equal(query.get('type'), 'LoRA');
  assert.equal(query.get('family'), 'SDXL');
  assert.equal(query.get('sort'), 'usage');
  assert.equal(query.get('domain'), 'image');
  assert.equal(query.get('purpose'), 'lighting');
  h.node('#f-q').oninput({ target: { value: 'just typed' } });
  assert.equal(h.modelState.q, 'just typed'); // Capturable even before debounce fires.
  h.el.isConnected = false; h.delayed.forEach(fn => fn());
  assert.equal(h.requests.length, 1);
});

test('restored gallery pagination survives the model filter URL and new links clear unrelated filters', async () => {
  const h = pageHarness('  const imgState=', '  // ================= 大模型', 'pages, imgState');
  await h.pages.images(h.el, new URLSearchParams('model=old-path'),
    { page: 3, q: 'saved-image', model: 'saved-model', dir: 'saved-dir', density: 'compact', sort: 'oldest' });
  let query = new URLSearchParams(h.requests[0].split('?')[1]);
  assert.equal(query.get('page'), '3');
  assert.equal(query.get('model'), 'saved-model');
  assert.equal(query.get('q'), 'saved-image');
  assert.equal(query.get('dir'), 'saved-dir');
  assert.match(h.el.innerHTML, /class="gallery compact"/);
  h.node('#im-q').oninput({ target: { value: 'new text' } });
  assert.equal(h.imgState.q, 'new text');
  h.el.isConnected = false; h.delayed.forEach(fn => fn());
  assert.equal(h.requests.length, 1);
  h.el = { isConnected: true };
  await h.pages.images(h.el, new URLSearchParams('model=new-model'));
  query = new URLSearchParams(h.requests.at(-1).split('?')[1]);
  assert.equal(query.get('model'), 'new-model');
  assert.equal(query.get('page'), '1');
  assert.equal(query.has('q'), false);
  assert.equal(query.has('dir'), false);
});

test('a model request finishing after close/navigation cannot reopen its drawer', async () => {
  let resolve, reject;
  const opened = [];
  const context = {
    api: () => new Promise((yes, no) => { resolve = yes; reject = no; }),
    openDrawer: html => opened.push(html),
    $: () => ({}), esc: value => String(value),
  };
  const drawerSource = source.slice(source.indexOf('  async function openModelDrawer('), source.indexOf('  // ================= 更新中心'));
  vm.runInNewContext('let activeDrawerId = null, drawerRequest = 0;\n' + drawerSource +
    '\nthis.open = openModelDrawer; this.close = () => { activeDrawerId = null; drawerRequest++; };', context);
  const first = context.open(1); context.close(); resolve({}); await first;
  assert.equal(opened.length, 1);
  const second = context.open(2); context.close(); reject(new Error('old request failed')); await second;
  assert.equal(opened.length, 2);
  assert.ok(opened.every(html => html.includes('加载中')));
});
