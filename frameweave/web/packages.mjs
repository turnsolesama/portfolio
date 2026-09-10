/** Workflow package form helpers. No scripts or external resources are evaluated. */
export const PACKAGE_LIMIT = 2 * 1024 * 1024;
const dangerousKeys = new Set(['__proto__', 'prototype', 'constructor']);

export function packageValues(value = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('工作流包输入必须是 JSON 对象');
  let count = 0;
  const check = (item, depth = 0) => {
    if (++count > 10000 || depth > 16) throw new Error('工作流包输入过大或嵌套过深');
    if (item === null || ['string', 'boolean'].includes(typeof item)) return;
    if (typeof item === 'number' && Number.isFinite(item)) {
      if (Number.isInteger(item) && !Number.isSafeInteger(item)) throw new Error('随机种子或整数超出浏览器安全范围，请使用不超过 9007199254740991 的整数');
      return;
    }
    if (item && typeof item === 'object') {
      for (const [key, child] of Object.entries(item)) {
        if (dangerousKeys.has(key)) throw new Error('工作流包输入含有不支持的字段名');
        check(child, depth + 1);
      }
      return;
    }
    throw new Error('工作流包输入包含无效 JSON 值');
  };
  check(value);
  const text = JSON.stringify(value);
  if (new TextEncoder().encode(text).length > PACKAGE_LIMIT) throw new Error('工作流包输入最大为 2 MiB');
  return JSON.parse(text);
}

export function fieldType(field) {
  const type = String(field.type || 'text').toLowerCase();
  if (['integer', 'int'].includes(type)) return 'integer';
  if (['number', 'float'].includes(type)) return 'number';
  if (['boolean', 'bool'].includes(type)) return 'boolean';
  if (type === 'image') return 'image';
  if (Array.isArray(field.options) || ['select', 'choice', 'enum'].includes(type)) return 'select';
  return 'text';
}

export function defaultValues(fields = []) {
  return Object.fromEntries(fields.filter(field => typeof field.id === 'string' && !dangerousKeys.has(field.id)).map(field => [field.id,
    field.default !== undefined ? field.default : fieldType(field) === 'boolean' ? false : '']));
}

export function coerceFieldValue(field, raw) {
  const label = field.label || field.id || '输入';
  const type = fieldType(field);
  if (type === 'boolean') {
    if (typeof raw !== 'boolean') throw new Error(`「${label}」必须选择开启或关闭`);
    return raw;
  }
  if (type === 'select') {
    if (!(field.options || []).some(option => Object.is(option, raw))) throw new Error(`「${label}」不在可选值中`);
    return raw;
  }
  if (raw === '' || raw === null || raw === undefined) {
    if (field.required) throw new Error(`请填写「${label}」`);
    return raw === undefined ? '' : raw;
  }
  if (type === 'number' || type === 'integer') {
    const value = typeof raw === 'number' ? raw : Number(raw);
    if (!Number.isFinite(value) || type === 'integer' && !Number.isSafeInteger(value)) throw new Error(`「${label}」必须是${type === 'integer' ? '安全范围内的整数' : '有效数字'}`);
    if (field.min !== undefined && value < Number(field.min) || field.max !== undefined && value > Number(field.max)) throw new Error(`「${label}」超出允许范围`);
    return value;
  }
  if (typeof raw !== 'string') throw new Error(`「${label}」必须是文本`);
  if (field.required && !raw.trim()) throw new Error(`请填写「${label}」`);
  if (raw.length > 100000) throw new Error(`「${label}」内容过长`);
  return raw;
}

export function validateValues(fields, values) {
  const source = packageValues(values);
  return Object.fromEntries(fields.map(field => [field.id, coerceFieldValue(field,
    Object.hasOwn(source, field.id) ? source[field.id] : field.default)]));
}

export function parseJSONWithSafeNumbers(text) {
  return JSON.parse(text, (_key, value) => {
    if (typeof value === 'number' && (!Number.isFinite(value) || Number.isInteger(value) && !Number.isSafeInteger(value))) throw new Error('随机种子或整数超出浏览器安全范围，请先改为不超过 9007199254740991 的整数');
    return value;
  });
}

export function parsePackageDocument(text) {
  if (new TextEncoder().encode(text).length > PACKAGE_LIMIT) throw new Error('工作流包 / API JSON 最大为 2 MiB');
  const document = parseJSONWithSafeNumbers(text);
  if (!document || typeof document !== 'object' || Array.isArray(document)) throw new Error('请导入工作流包或 ComfyUI API JSON 对象');
  if (document.format === 'frameweave-workflow') {
    if (document.version !== 1) throw new Error('此工作流包版本暂不支持');
    return document;
  }
  if (Array.isArray(document.nodes) || Array.isArray(document.links)) throw new Error('这是普通 ComfyUI 画布。请在 ComfyUI 开启开发者模式，选择「Save (API Format) / 导出 API」，再导入这里。');
  const prompt = document.prompt || document;
  if (!prompt || Array.isArray(prompt) || typeof prompt !== 'object' || !Object.keys(prompt).length || !Object.values(prompt).every(node => node && typeof node.class_type === 'string' && node.inputs && typeof node.inputs === 'object' && !Array.isArray(node.inputs))) throw new Error('未识别到可执行的 ComfyUI API 节点。请使用「导出 API」JSON。');
  return document;
}

/** Local path redaction is a second layer for backend-generated repair text. */
export function redactLocalText(value, knownPaths = []) {
  let text = String(value ?? '');
  for (const path of [...knownPaths].filter(path => typeof path === 'string' && path.length > 3).sort((a, b) => b.length - a.length)) {
    text = text.split(path).join('[本机路径]').split(path.replaceAll('\\', '/')).join('[本机路径]');
  }
  return text.replace(/[A-Za-z]:[\\/][^\n\r"'<>|，。；]*/g, '[本机路径]')
    .replace(/\\\\[^\n\r"'<>|，。；]+/g, '[本机路径]')
    .replace(/\/(?:Users|home|mnt|media|Volumes)\/[^\n\r"'<>|，。；]+/g, '[本机路径]');
}

export function publicChecksReport(checks = [], knownPaths = [], options = {}) {
  const states = ['ok', 'missing', 'error', 'warning', 'unknown'];
  const counts = Object.fromEntries(states.map(state => [state, 0]));
  for (const check of checks) counts[states.includes(check.status) ? check.status : 'unknown']++;
  const mode = ['h3_t2v', 'h3_i2v', 'h3_ref', 'sdxl', 'krea', 'api', 'package'].includes(options.mode) ? options.mode : 'unknown';
  return {
    checked_at: new Date().toISOString(), mode, counts,
    ready: checks.length > 0 && !counts.missing && !counts.error && !counts.unknown,
    summary: `共检查 ${checks.length} 项；${counts.ok} 项就绪，${counts.missing} 项缺失，${counts.error} 项错误，${counts.warning} 项提醒，${counts.unknown} 项待确认。`,
    scope: '状态摘要与后端生成的修复提示词；未导出本机路径、设备标识、原始检查明细或工作流内容。就绪状态不代表完成真实生成验证。',
    repair_prompt: redactLocalText(options.repair_prompt || '请检查本机推理服务、Python 依赖、节点插件与所需模型。没有结果的项目仍待确认；先核对本地环境，再给出补齐和验证步骤。', knownPaths),
  };
}
