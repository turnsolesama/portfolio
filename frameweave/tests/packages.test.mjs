import test from 'node:test';
import assert from 'node:assert/strict';
import { packageValues, fieldType, defaultValues, coerceFieldValue, validateValues, parsePackageDocument, publicChecksReport, redactLocalText } from '../web/packages.mjs';
import { createNode, createDemo, generationPayload, serializeGraph, parseGraph, canConnect } from '../web/graph.mjs';

test('workflow package nodes round-trip typed values and retain package identity', () => {
  const graph = { nodes: [createNode('generation', 30, 50, { kind: 'package', package_id: 'p-original', title: '海报生成', packageValues: { text: '清晨花园', seed: 42, enabled: false } })], edges: [] };
  const restored = parseGraph(serializeGraph(graph));
  assert.deepEqual(generationPayload(restored, graph.nodes[0].id), { kind: 'package', package_id: 'p-original', values: { text: '清晨花园', seed: 42, enabled: false } });
  assert.equal(restored.nodes[0].data.kind, 'package');
});

test('package nodes reject implicit prompt connections and missing package IDs', () => {
  const graph = createDemo(); graph.edges = []; graph.nodes[1].data.kind = 'package';
  assert.match(canConnect(graph, graph.nodes[0].id, graph.nodes[1].id).reason, /表单/);
  assert.equal(canConnect(graph, graph.nodes[1].id, graph.nodes[2].id).ok, true);
  assert.throws(() => generationPayload(graph, graph.nodes[1].id), /工作流包/);
});

test('previous canvas versions still import without package-only state leaking into H3 payloads', () => {
  const raw = JSON.parse(serializeGraph(createDemo()));
  delete raw.nodes[1].data.package_id; delete raw.nodes[1].data.packageValues;
  const restored = parseGraph(raw), payload = generationPayload(restored, restored.nodes[1].id);
  assert.equal(payload.kind, 'h3_t2v'); assert.equal('packageValues' in payload, false); assert.equal('package_id' in payload, false);
});

test('package input JSON rejects prototype keys, arrays and deep or non-finite data', () => {
  assert.throws(() => packageValues([]), /JSON 对象/);
  assert.throws(() => packageValues({ bad: Infinity }), /无效 JSON/);
  assert.throws(() => packageValues({ seed: 9007199254740992 }), /安全范围/);
  assert.throws(() => packageValues(JSON.parse('{"__proto__":{"polluted":true}}')), /字段名/);
  let deep = {}; for (let i = 0; i < 18; i++) deep = { value: deep };
  assert.throws(() => packageValues(deep), /过深/);
  const original = { fields: { prompt: 'a' }, values: [1, false, null] };
  assert.deepEqual(packageValues(original), original); assert.notEqual(packageValues(original), original);
});

test('typed fields preserve false and zero, validate safe integers, bounds and strict choices', () => {
  const fields = [{ id: 'seed', type: 'integer', default: 0, min: 0 }, { id: 'enabled', type: 'boolean', default: false }, { id: 'sampler', type: 'select', options: ['euler', 'heun'], default: 'euler' }];
  assert.deepEqual(defaultValues(fields), { seed: 0, enabled: false, sampler: 'euler' });
  assert.deepEqual(validateValues(fields, { seed: '123', enabled: true }), { seed: 123, enabled: true, sampler: 'euler' });
  assert.throws(() => coerceFieldValue(fields[0], '9007199254740993'), /整数/);
  assert.throws(() => coerceFieldValue(fields[0], -1), /范围/);
  assert.throws(() => coerceFieldValue(fields[1], 'false'), /开启或关闭/);
  assert.throws(() => coerceFieldValue(fields[2], 'invalid'), /可选值/);
  assert.throws(() => coerceFieldValue(fields[2], ''), /可选值/);
  assert.equal(fieldType({ type: 'INT' }), 'integer');
});

test('required image and text inputs cannot run blank', () => {
  assert.throws(() => coerceFieldValue({ type: 'image', required: true, label: '首帧' }, ''), /首帧/);
  assert.throws(() => coerceFieldValue({ type: 'text', required: true, label: '描述' }, '  '), /描述/);
  assert.equal(coerceFieldValue({ type: 'image', required: true }, 'input/portrait.png'), 'input/portrait.png');
});

test('package import accepts API JSON and versioned packages but explains ordinary ComfyUI exports', () => {
  const prompt = { '1': { class_type: 'CLIPTextEncode', inputs: { text: 'a flower' } } };
  assert.deepEqual(parsePackageDocument(JSON.stringify(prompt)), prompt);
  assert.deepEqual(parsePackageDocument(JSON.stringify({ prompt })), { prompt });
  const pack = { format: 'frameweave-workflow', version: 1, prompt, fields: [] };
  assert.deepEqual(parsePackageDocument(JSON.stringify(pack)), pack);
  assert.throws(() => parsePackageDocument('{"nodes":[],"links":[]}'), /导出 API/);
  assert.throws(() => parsePackageDocument('{"format":"frameweave-workflow","version":2}'), /版本/);
  assert.throws(() => parsePackageDocument(JSON.stringify({ prompt: 'not a workflow' })), /API/);
  assert.throws(() => parsePackageDocument('{"1":{"class_type":"KSampler","inputs":{"seed":18446744073709551615}}}'), /随机种子/);
  assert.throws(() => parsePackageDocument(' '.repeat(2 * 1024 * 1024 + 1)), /2 MiB/);
});

test('public diagnostics retain unknown states and drop machine paths and unexpected fields', () => {
  const checks = [{ category: 'models', name: '模型文件', status: 'unknown', detail: '未确认 C:\\Users\\Private Person\\models\\file.bin，需检查', root: 'secret-root', machine_id: 'private' }];
  const report = publicChecksReport(checks);
  assert.equal(report.counts.unknown, 1); assert.equal(report.ready, false);
  assert.deepEqual(Object.keys(report).sort(), ['checked_at', 'counts', 'mode', 'ready', 'repair_prompt', 'scope', 'summary']);
  assert.equal(JSON.stringify(report).includes('Private Person'), false); assert.equal('checks' in report, false);
  assert.equal(JSON.stringify(report).includes('secret-root'), false);
  assert.equal(redactLocalText('配置 /home/alex/private-models，已跳过').includes('alex'), false);
  assert.equal(redactLocalText('配置 \\\\host\\share\\model.bin').includes('host'), false);
  assert.equal(redactLocalText('模型 G:/AI/my files/model.safetensors').includes('my files'), false);
});
