const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

const source = readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
const helperSource = source.slice(source.indexOf('  const ICONS ='), source.indexOf('  // ---------- 抽屉'));
assert(helperSource.length > 1000, 'Read the actual application helpers');
function helpers(saved = '[]') {
  const context = { localStorage: { getItem: () => saved }, esc: text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) };
  vm.runInNewContext(helperSource + '\nthis.exports = { mdRender, loraIntro, readFavorites, classificationSummary, classificationSection };', context);
  return context.exports;
}
const { mdRender, loraIntro } = helpers();
test('Report content cannot inject markup', () => {
  const html = mdRender('<script>alert(1)</script>\n<img src=x onerror=alert(1)>');
  assert(!html.includes('<script>'));
  assert(!html.includes('<img'));
  assert(html.includes('&lt;script&gt;'));
});
test('Report links reject executable protocols', () => {
  const html = mdRender('[run](javascript:alert%281%29) [run](data:text/html,evil)', 'F:\\AI\\report.md');
  assert(!html.includes('href='));
});
test('Report links preserve external URLs and isolate their opener', () => {
  const html = mdRender('[source](https://example.com/model?a=1&b=2)');
  assert(html.includes('href="https://example.com/model?a=1&amp;b=2"'));
  assert(html.includes('rel="noopener noreferrer"'));
});
test('Relative report links route through the report allowlist', () => {
  assert(mdRender('[read](Reports/模型.md)', 'F:\\AI\\00_Management\\START_HERE.md').includes(encodeURIComponent('F:\\AI\\00_Management\\Reports\\模型.md')));
});
test('Code fences remain literal and tables remain structured', () => {
  const html = mdRender('```json\n<b>**literal**</b>\n```\n\n| A | B |\n| --- | --- |\n| one | two |');
  assert(html.includes('<pre><code>&lt;b&gt;**literal**&lt;/b&gt;</code></pre>'));
  assert(html.includes('<th>A</th><th>B</th>'));
  assert(html.includes('<td>one</td><td>two</td>'));
});
test('LoRA introduction shows training base, trigger and evidence without task comparisons', () => {
  const html = loraIntro({mtype:'LoRA', family:'SDXL', training_base:'A & B', trigger_words:'style-token', audit:{role:'Style_Other', family_confidence:'confirmed'}});
  assert(html.includes('A &amp; B'));
  assert(html.includes('style-token'));
  assert(html.includes('已有架构证据'));
  assert(html.includes('未做推理验证'));
  assert(!html.includes('版本对比'));
});
test('Unknown LoRA information is explicit and embedded descriptions are escaped', () => {
  const html = loraIntro({mtype:'LoRA', header_meta:{'modelspec.description':'<b>author text</b>'}});
  assert(html.includes('用途待补充'));
  assert(html.includes('没有可确认的触发词'));
  assert(html.includes('&lt;b&gt;author text&lt;/b&gt;'));
  assert.equal(loraIntro({mtype:'Checkpoint'}), '');
});
test('Catalog trigger candidates render their values and evidence instead of raw JSON', () => {
  const candidate = {value:'example style',evidence:'training tag frequency 1234; candidate, not validated'};
  const html = loraIntro({mtype:'LoRA',trigger_words:JSON.stringify(candidate),audit:{trigger_candidates:[candidate]}});
  assert(html.includes('<b>example style</b>'));
  assert(html.includes('训练标签中出现 1,234 次；仅为候选，尚未验证'));
  assert(!html.includes('&quot;value&quot;'));
  const legacy = loraIntro({mtype:'LoRA',trigger_words:JSON.stringify({value:'<style>',evidence:'<script>unsafe</script>'})});
  assert(legacy.includes('&lt;style&gt;'));
  assert(legacy.includes('&lt;script&gt;unsafe&lt;/script&gt;'));
  assert(!legacy.includes('<script>'));
});
test('Corrupt favorites do not prevent the application from starting', () => {
  assert.equal(helpers('invalid json').readFavorites().size, 0);
  assert.equal(helpers('{}').readFavorites().size, 0);
  assert.deepEqual([...helpers('[1,"2",null,3]').readFavorites()], [1,3]);
});
test('Classification badges escape labels and distinguish manual classification', () => {
  const html=helpers().classificationSummary({domain_label:'<img src=x>',purpose_labels:['<script>style</script>'],domain_source:'manual',purpose_source:'manual'});
  assert(html.includes('&lt;img src=x&gt;'));
  assert(html.includes('&lt;script&gt;style&lt;/script&gt;'));
  assert(html.includes('已手动分类'));
  assert(!html.includes('<img'));
});
test('Classification evidence does not render metadata as HTML', () => {
  const html=helpers().classificationSection({classification:{domain_label:'图片创作',purpose_labels:['光照氛围'],purpose_evidence:{lighting:'<script>unsafe</script>'},domain_evidence:'metadata',domain_source:'suggested',purpose_source:'suggested'},classification_options:{purposes:{lighting:'光照氛围'}}});
  assert(html.includes('调整分类'));
  assert(html.includes('自动建议'));
  assert(html.includes('&lt;script&gt;unsafe&lt;/script&gt;'));
  assert(!html.includes('<script>'));
});
