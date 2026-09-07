'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../frontend/navigation.js');

function browser(initial = '#/overview') {
  const location = { hash: initial };
  const records = [{ hash: initial, state: { unrelated: true } }];
  let cursor = 0, queued = null, screen = {}, renders = [], pushes = 0;
  const history = {
    length: 50, // Includes unrelated/external history; it must not enable app Back.
    get state() { return records[cursor].state; },
    replaceState(state, title, hash) { records[cursor] = { state, hash }; location.hash = hash; },
    pushState(state, title, hash) {
      records.splice(cursor + 1); records.push({ state, hash }); cursor++; location.hash = hash; pushes++;
    },
    go(delta) { assert.equal(queued, null); queued = delta; },
  };
  const app = create({
    history, location,
    capture: () => structuredClone(screen),
    render: (hash, snapshot) => {
      screen = structuredClone(snapshot || {});
      renders.push({ hash, snapshot: structuredClone(snapshot) });
    },
    update: () => {},
  });
  app.start();
  return {
    app, location, history,
    screen: value => { screen = value; },
    get view() { return renders.at(-1); },
    get renders() { return renders.length; },
    get pushes() { return pushes; },
    settle() {
      assert.notEqual(queued, null); cursor += queued; queued = null;
      location.hash = records[cursor].hash; app.sync(); app.sync();
    },
    native(delta) { history.go(delta); this.settle(); },
    deepLink(hash) { history.pushState(null, '', hash); app.sync(); },
  };
}

test('fresh/deep-linked window never uses external browser history for its Back button', () => {
  const b = browser('#/images?model=example');
  assert.equal(b.app.status().canBack, false);
  assert.equal(b.app.back(), false);
  assert.equal(b.view.hash, '#/images?model=example');
});

test('model → gallery → back restores filter, pagination, scroll, drawer and unsaved notes', () => {
  const b = browser('#/models?type=LoRA');
  const original = {
    state: { type: 'LoRA', family: 'SDXL', page: 3, q: 'style', sort: 'usage' },
    top: 542, left: 0, scrolls: [[[140, 0]]],
    drawer: { id: 12, top: 875, notes: '尚未保存的笔记', rating: 8, expanded: [true] },
  };
  b.screen(original);
  b.app.navigate('#/images?model=F%3A%5Cmodels%5Cexample.safetensors');
  assert.deepEqual(b.app.status().previous.snapshot, original);
  b.screen({ state: { page: 2, q: 'portrait', density: 'compact' }, top: 700 });
  assert.equal(b.app.back(), true); b.settle();
  assert.deepEqual(b.view.snapshot, original);
  assert.equal(b.view.hash, '#/models?type=LoRA');
  assert.equal(b.app.forward(), true); b.settle();
  assert.equal(b.view.snapshot.state.page, 2);
  assert.equal(b.view.snapshot.state.density, 'compact');
});

test('same route with different entries keeps separate state, and branching drops forward history', () => {
  const b = browser('#/models');
  b.screen({ state: { q: 'first' } });
  b.app.navigate('#/models', { force: true });
  b.screen({ state: { q: 'second' } });
  b.app.navigate('#/reports?path=A');
  b.app.back(); b.settle(); assert.equal(b.view.snapshot.state.q, 'second');
  b.app.back(); b.settle(); assert.equal(b.view.snapshot.state.q, 'first');
  b.app.navigate('#/workflows');
  assert.equal(b.app.forward(), false);
  b.app.back(); b.settle(); assert.equal(b.view.snapshot.state.q, 'first');
});

test('browser Back and Forward render once when popstate and hashchange both fire', () => {
  const b = browser();
  b.screen({ top: 290 }); b.app.navigate('#/files?path=F%3A%5CAI');
  const before = b.renders;
  b.native(-1);
  assert.equal(b.renders, before + 1);
  assert.equal(b.view.snapshot.top, 290);
  b.native(1); assert.equal(b.renders, before + 2);
});

test('rapid back clicks cannot overshoot the internal trail', () => {
  const b = browser(); b.app.navigate('#/models');
  assert.equal(b.app.back(), true);
  assert.equal(b.app.status().canBack, false);
  assert.equal(b.app.back(), false);
  b.app.navigate('#/settings'); // An in-flight history traversal owns the next transition.
  b.settle();
  assert.equal(b.view.hash, '#/overview');
  assert.equal(b.app.back(), false);
});

test('refresh and repeated current-page links preserve state without adding history', () => {
  const b = browser(); b.app.navigate('#/images');
  b.screen({ state: { page: 4, dir: 'outputs' }, top: 900 });
  const pushes = b.pushes;
  b.app.refresh(); b.app.navigate('#/images');
  assert.equal(b.pushes, pushes);
  assert.equal(b.view.snapshot.state.page, 4);
  assert.equal(b.view.snapshot.top, 900);
});

test('unrecognized history state starts a safe new trail, and external URLs are ignored', () => {
  const b = browser(); b.app.navigate('#/models');
  b.deepLink('#/reports?path=readme');
  assert.equal(b.app.back(), false);
  const before = b.pushes;
  b.app.navigate('https://example.com/');
  assert.equal(b.pushes, before);
  assert.equal(b.view.hash, '#/reports?path=readme');
});
