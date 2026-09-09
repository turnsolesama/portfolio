"""Extract provider metadata from a single cURL example. Never run shell or HTTP."""
import json
import re
import shlex
from urllib.parse import urlsplit, urlunsplit


def unwrap(text):
    text = text.lstrip('\ufeff').strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if len(lines) < 3 or lines[-1].strip() != '```':
            raise ValueError('代码块未闭合，请粘贴完整配置')
        text = '\n'.join(lines[1:-1]).strip()
    return text


def is_curl(text):
    return bool(re.match(r'(?i)^curl(?:\.exe)?(?:\s|$)', text))


def parse_curl(text):
    """Return one plain profile candidate plus safe, non-secret preview notes."""
    # Remove shell line continuations only, never evaluate shell syntax.
    text = re.sub(r'[\\^`]\r?\n', ' ', text)
    def markdown_url(match):
        if match[1] != match[2]:
            raise ValueError('链接显示地址与目标不一致，请粘贴原始 cURL 地址')
        return match[2]
    text = re.sub(r'\[(https?://[^\s\[\]]+)\]\((https?://[^\s()]+)\)', markdown_url, text)
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        raise ValueError('cURL 引号未闭合，请复制完整命令和 JSON 请求体') from None
    if not tokens or tokens[0].lower() not in {'curl', 'curl.exe'}:
        raise ValueError('请粘贴单条 curl 或 curl.exe 请求示例')
    urls, bodies, headers, methods = [], [], [], []
    options = {'-H': headers, '--header': headers, '-d': bodies, '--data': bodies,
               '--data-raw': bodies, '--data-binary': bodies, '--json': bodies,
               '--url': urls, '-X': methods, '--request': methods}
    cosmetic = {'-s', '-S', '-sS', '-N', '--silent', '--show-error', '--no-buffer'}
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token in cosmetic:
            i += 1
            continue
        option, equal, value = token.partition('=')
        if option.startswith('--') and equal and option in options:
            options[option].append(value)
        elif token in options:
            i += 1
            if i >= len(tokens):
                raise ValueError('cURL 参数缺少值，请粘贴完整示例')
            options[token].append(tokens[i])
        elif token[:2] in {'-H', '-d', '-X'} and len(token) > 2:
            options[token[:2]].append(token[2:])
        elif token.startswith(('https://', 'http://')):
            urls.append(token)
        else:
            raise ValueError('仅支持单条 JSON API 请求；请移除其他命令、重定向或高级 cURL 参数')
        i += 1
    if len(urls) != 1 or len(bodies) != 1 or len(methods) > 1:
        raise ValueError('需提供一个服务地址和一个内联 JSON 请求体，不能包含多个请求')
    if methods and methods[0].upper() != 'POST':
        raise ValueError('服务导入仅支持 POST 请求示例')
    body = bodies[0]
    if body.startswith('@'):
        raise ValueError('不读取 @文件或标准输入，请直接粘贴 JSON 请求体')
    # Rich-text copying sometimes escapes underscores in JSON field names.
    body = re.sub(r'"([A-Za-z_\\]+)"(?=\s*:)', lambda m: '"'+m[1].replace(r'\_', '_')+'"', body)
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        raise ValueError('cURL 请求体不是有效 JSON；请保留 JSON 的双引号') from None
    if not isinstance(data, dict) or not isinstance(data.get('model'), str) or not data['model'].strip():
        raise ValueError('JSON 请求体需要非空 model 字段')
    try:
        url = urlsplit(urls[0])
        port = url.port
    except ValueError:
        raise ValueError('cURL 服务地址无效') from None
    if (url.scheme not in {'https', 'http'} or not url.hostname or url.username or url.password
            or url.query or url.fragment or any(c.isspace() or ord(c) < 32 for c in urls[0])):
        raise ValueError('服务地址不能包含账号、密钥、查询参数或片段')
    path = url.path.rstrip('/')
    deepseek = (url.scheme == 'https' and url.hostname == 'api.deepseek.com' and port in {None, 443}
                and path in {'/chat/completions', '/v1/chat/completions', '/responses', '/v1/responses'})
    notes = []
    if deepseek:
        base_url = 'https://api.deepseek.com'
        if path.endswith('/chat/completions'):
            notes.append('DeepSeek 官方已支持 Responses：将 Chat Completions 示例转换为 Codex 的 Responses 服务配置。')
        else:
            notes.append('识别到 DeepSeek 官方 Responses 服务。')
        pid, name, env_key = 'deepseek', 'DeepSeek', 'DEEPSEEK_API_KEY'
    elif path.endswith('/responses'):
        base_url = urlunsplit((url.scheme, url.netloc, path[:-len('/responses')], '', ''))
        pid, name, env_key = 'curl-import', url.hostname, 'CODEX_CURL_API_KEY'
    elif path.endswith('/chat/completions'):
        raise ValueError('识别到 Chat Completions 示例，但尚未确认该服务支持 Responses。请提供服务商的 Responses 示例或兼容网关地址')
    else:
        raise ValueError('请提供 /responses 请求；DeepSeek 官方 /chat/completions 示例也可导入')
    secret, seen = '', set()
    for header in headers:
        key, colon, value = header.partition(':')
        key, value = key.strip().lower(), value.strip()
        if not colon or key in seen:
            raise ValueError('cURL 请求头无效或重复')
        seen.add(key)
        if key == 'content-type':
            if value.split(';')[0].strip().lower() != 'application/json':
                raise ValueError('仅支持 application/json 请求体')
        elif key == 'authorization':
            match = re.fullmatch(r'(?i)Bearer\s+(.+)', value)
            if not match:
                raise ValueError('仅支持 Bearer API Key 认证，请核对服务商配置')
            credential = match[1].strip()
            variable = credential.replace(r'\_', '_')
            variable_match = re.fullmatch(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)|%([A-Za-z_][A-Za-z0-9_]*)%|\$env:([A-Za-z_][A-Za-z0-9_]*)', variable)
            if variable_match:
                env_key = next(x for x in variable_match.groups() if x is not None)
                notes.append('密钥使用环境变量引用；未读取变量值。若本机尚未设置，请导入后编辑服务填写 API Key。')
            elif credential.startswith(('<', '${', '$', '%')) or '`' in credential:
                raise ValueError('密钥占位符无法识别；请使用 ${YOUR_API_KEY} 或直接填写 API Key')
            elif len(credential) > 8192 or any(c.isspace() or ord(c) < 32 for c in credential):
                raise ValueError('API Key 格式不合法')
            else:
                secret = credential
        else:
            raise ValueError('示例包含自定义请求头，无法完整导入；请使用标准 Bearer API Key 配置')
    if 'authorization' not in seen:
        notes.append('示例未包含 API Key；需要认证时，请在导入后编辑服务补充。')
    reasoning = data.get('reasoning', {})
    if not isinstance(reasoning, dict):
        raise ValueError('reasoning 字段必须是对象')
    effort = data.get('reasoning_effort', reasoning.get('effort', ''))
    if not isinstance(effort, str):
        raise ValueError('推理强度必须是文本')
    if 'reasoning_effort' in data and 'effort' in reasoning and effort != reasoning['effort']:
        raise ValueError('两处推理强度不一致，请保留一种配置')
    thinking = data.get('thinking')
    if thinking is not None and thinking != {'type': 'enabled'}:
        raise ValueError('此思考模式无法自动转换为 Codex 配置，请提供 Responses 示例')
    if thinking and not effort:
        raise ValueError('思考模式已开启，请同时指定 reasoning_effort 以便转换')
    profile = dict(id=pid, name=name, base_url=base_url, env_key=env_key, model=data['model'], wire_api='responses')
    if effort:
        profile['reasoning_effort'] = effort
    notes.append('只导入服务、模型、认证与推理强度；示例对话、stream 和其他单次请求参数由 Codex 管理，不会执行这条命令。')
    return {'profile': profile, 'secret': secret}, notes
