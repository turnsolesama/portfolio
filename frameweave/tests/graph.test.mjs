import test from 'node:test';
import assert from 'node:assert/strict';
import { createNode, createDemo, connect, canConnect, removeNodes, duplicateNodes, generationPayload, serializeGraph, parseGraph, stableStringify, progressPercent } from '../web/graph.mjs';

test('canvas serialization is stable and retains all generation controls', () => {
  const graph = createDemo();
  const generation = graph.nodes.find(node => node.type === 'generation');
  Object.assign(generation.data, { sampler: 'dpmpp_2m', scheduler: 'karras', lora_strength: .65, denoise: .8, seed: 9007199254740000, models: { lora: 'h3-style.safetensors', dit: 'h3-fl2va.safetensors' } });
  const initial = serializeGraph(graph, { x: -121.5, y: 202, scale: .7 });
  const restored = parseGraph(initial);
  assert.equal(serializeGraph(restored, restored.viewport), initial);
  assert.deepEqual(restored.nodes.find(node => node.id === generation.id).data, generation.data);
  assert.equal(stableStringify({ z: 2, a: { y: 4, x: 1 } }), stableStringify({ a: { x: 1, y: 4 }, z: 2 }));
});

test('removing any node cleans both incoming and outgoing edges', () => {
  const graph = createDemo();
  const generation = graph.nodes.find(node => node.type === 'generation');
  assert.equal(graph.edges.length, 2);
  removeNodes(graph, [generation.id]);
  assert.equal(graph.nodes.length, 2);
  assert.deepEqual(graph.edges, []);
});

test('connections reject self loops, duplicates, invalid directions and cycles', () => {
  const graph = createDemo();
  const [prompt, generation, result] = graph.nodes;
  assert.throws(() => connect(graph, prompt.id, prompt.id), /自身/);
  assert.throws(() => connect(graph, prompt.id, generation.id), /已存在/);
  assert.throws(() => connect(graph, result.id, prompt.id), /连接顺序/);
  const polluted = { nodes: [prompt, generation], edges: [{ id: 'reverse', source: generation.id, target: prompt.id }] };
  assert.equal(canConnect(polluted, prompt.id, generation.id).ok, false);
  assert.match(canConnect(polluted, prompt.id, generation.id).reason, /循环/);
});

test('duplicate preserves selected internal connections and isolates result jobs', () => {
  const graph = createDemo();
  graph.nodes[2].data.outputs = [{ type: 'image', url: '/api/media/example', filename: 'test.png' }];
  graph.nodes[2].data.jobId = 'existing-job';
  const sourceIds = graph.nodes.map(node => node.id);
  const ids = duplicateNodes(graph, sourceIds);
  assert.equal(ids.length, 3);
  assert.equal(new Set([...sourceIds, ...ids]).size, 6);
  const clones = graph.nodes.filter(node => ids.includes(node.id));
  assert.equal(graph.edges.filter(edge => ids.includes(edge.source) && ids.includes(edge.target)).length, 2);
  assert.equal(graph.edges.filter(edge => sourceIds.includes(edge.source) && ids.includes(edge.target)).length, 0);
  assert.deepEqual(clones.find(node => node.type === 'result').data.outputs, []);
  assert.equal(clones.find(node => node.type === 'result').data.jobId, '');
});

test('payload combines connected prompts and preserves explicit reference roles', () => {
  const graph = createDemo(); const generation = graph.nodes[1];
  generation.data.kind = 'h3_i2v'; generation.data.positive = '缓慢推进';
  const end = createNode('reference', 0, 0, { role: 'end', name: 'end.png' });
  const start = createNode('reference', 0, 0, { role: 'start', name: 'start.png' });
  graph.nodes.push(end, start); connect(graph, end.id, generation.id); connect(graph, start.id, generation.id);
  const payload = generationPayload(graph, generation.id);
  assert.deepEqual(payload.references, ['start.png', 'end.png']);
  assert.deepEqual(payload.reference_roles, ['start', 'end']);
  assert.match(payload.positive, /温室/); assert.match(payload.positive, /缓慢推进/);
  assert.equal(payload.seed, 42); assert.equal(payload.fps, 24); assert.equal(payload.sampler, 'euler');
  assert.equal('title' in payload, false);
});

test('API format workflows round-trip without dropping advanced node inputs', () => {
  const graph = createDemo(); const node = graph.nodes[1];
  node.data.kind = 'api'; node.data.apiPrompt = { '7': { class_type: 'CustomNode', inputs: { nested: { values: [1, 'test', true] }, model: ['9', 0] }, _meta: { title: '用户节点' } } };
  const restored = parseGraph(serializeGraph(graph));
  assert.deepEqual(generationPayload(restored, node.id), { kind: 'api', prompt: node.data.apiPrompt });
});

test('invalid imports reject missing nodes, duplicate ids, unsupported types and NaN positions', () => {
  const original = JSON.parse(serializeGraph(createDemo()));
  const missing = structuredClone(original); missing.edges[0].source = 'missing'; assert.throws(() => parseGraph(missing), /不存在/);
  const duplicate = structuredClone(original); duplicate.nodes[1].id = duplicate.nodes[0].id; assert.throws(() => parseGraph(duplicate), /重复/);
  const type = structuredClone(original); type.nodes[0].type = 'script'; assert.throws(() => parseGraph(type), /不支持/);
  const position = structuredClone(original); position.nodes[0].x = 'Infinity'; assert.throws(() => parseGraph(position), /坐标/);
});

test('pending jobs keep null progress unknown and safely accept real backend counters', () => {
  assert.equal(progressPercent(null), null);
  assert.equal(progressPercent(undefined), null);
  assert.equal(progressPercent({ value: 1, max: 0 }), null);
  assert.equal(progressPercent({ value: 3, max: 20 }), 15);
  assert.equal(progressPercent({ value: 0, max: 20 }), 0);
  assert.equal(progressPercent(100), 100);
  assert.equal(progressPercent(NaN), null);
  assert.equal(progressPercent('25'), null);
});
