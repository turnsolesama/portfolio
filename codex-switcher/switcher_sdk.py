"""Static OpenAI SDK example import. No execution, imports, files, env or HTTP."""
import ast
from dataclasses import dataclass
import json
import re
import shlex
from switcher_curl import parse_curl


@dataclass(frozen=True)
class Symbol:
    name: str


@dataclass(frozen=True)
class Env:
    name: str


@dataclass
class Client:
    options: object


def fail():
    raise ValueError('示例含动态计算、重复赋值或不支持的语法；请保留 OpenAI 初始化与请求，并将地址、模型等参数改为明确值')


def language(text):
    text=text.lstrip()
    while text.startswith(('#','//','/*')):
        if text.startswith('/*'):
            end=text.find('*/')
            if end<0:return 'Node.js'
            text=text[end+2:].lstrip()
        else:text=text.partition('\n')[2].lstrip()
    if re.match(r'(?:from\s+(?:openai|os)\s+import|import\s+(?:openai|os)\b)', text):
        return 'Python'
    if re.match(r'(?:(?:import|const|let|var)\s|(?:async\s+)?function\s)', text):
        return 'Node.js'
    return None


class Reader:
    def __init__(self):
        self.bindings = {'process': ('symbol', 'process')}
        self.calls = []
        self.blocked = set()

    def bind(self, name, value):
        if name in self.bindings: self.blocked.add(name)
        self.bindings[name] = value

    def guard_mutations(self):
        for call in self.calls:
            node=call[1]
            if node[0]=='get' and node[2][0]=='lit' and node[2][1] in {'update','setdefault','pop','clear','append','extend','insert','push','splice','assign','defineProperty'}:
                root=node[1]
                while root[0]=='get':root=root[1]
                if root[0]=='name':self.blocked.add(root[1])
                for arg in call[2]:
                    if arg[0]=='name':self.blocked.add(arg[1])
        # Changes through an alias also invalidate the original static binding.
        for _ in range(len(self.bindings)+1):
            old=len(self.blocked)
            for name,node in self.bindings.items():
                if node[0]=='name' and (name in self.blocked or node[1] in self.blocked):
                    self.blocked.update((name,node[1]))
            if old==len(self.blocked):break

    def resolve(self, node, seen=()):
        if len(seen) > 40: fail()
        if node[0] == 'name':
            name = node[1]
            if name in seen or name in self.blocked or name not in self.bindings: fail()
            return self.resolve(self.bindings[name], (*seen, name))
        return node

    def fields(self, node, seen=()):
        if len(seen) > 40: fail()
        original = node
        node = self.resolve(node, seen)
        if original[0] == 'name': seen = (*seen, original[1])
        if node[0] != 'obj': fail()
        result = {}
        for key, value in node[1]:
            fields = self.fields(value, seen) if key is None else {key: value}
            if not all(isinstance(k, str) for k in fields) or result.keys() & fields.keys(): fail()
            result.update(fields)
        return result

    def value(self, node, seen=(), depth=0):
        if depth > 40: fail()
        if node[0] == 'name':
            name = node[1]
            if name in seen or name in self.blocked or name not in self.bindings: fail()
            return self.value(self.bindings[name], (*seen, name), depth+1)
        kind = node[0]
        if kind == 'lit': return node[1]
        if kind == 'symbol': return Symbol(node[1])
        if kind == 'obj': return {k:self.value(v, seen, depth+1) for k,v in self.fields(node, seen).items()}
        if kind == 'arr': return [self.value(v, seen, depth+1) for v in node[1]]
        if kind == 'get':
            obj, key = self.value(node[1], seen, depth+1), self.value(node[2], seen, depth+1)
            if not isinstance(key, str): fail()
            if isinstance(obj, Symbol):
                if obj.name in {'os.environ', 'process.env'} and key not in {'get'}: return Env(key)
                return Symbol(obj.name+'.'+key)
            if isinstance(obj, dict) and key in obj: return obj[key]
            fail()
        if kind == 'call':
            target = self.value(node[1], seen, depth+1)
            if not isinstance(target, Symbol): fail()
            if target.name in {'openai.OpenAI', 'openai.AsyncOpenAI', 'openai.OpenAI.OpenAI'}:
                options = node[3] if node[3] is not None else (node[2][0] if len(node[2]) == 1 else ('obj', []))
                if node[3] is not None and node[2] or len(node[2]) > 1: fail()
                return Client(options)
            args = [self.value(v, seen, depth+1) for v in node[2]]
            if node[3] not in (None, ('obj', [])): fail()
            if target.name in {'os.getenv', 'os.environ.get'} and len(args) in {1, 2}:
                if len(args) == 2 and args[1] is not None: fail()
                if not isinstance(args[0], str): fail()
                return Env(args[0])
            if target.name == 'require' and args == ['openai']: return Symbol('openai.OpenAI')
            fail()
        fail()


def py_node(node, reader, depth=0):
    if depth > 60: fail()
    child = lambda x: py_node(x, reader, depth+1)
    if isinstance(node, ast.Constant): return ('lit', node.value)
    if isinstance(node, ast.Name): return ('name', node.id)
    if isinstance(node, ast.Attribute): return ('get', child(node.value), ('lit', node.attr))
    if isinstance(node, ast.Subscript): return ('get', child(node.value), child(node.slice))
    if isinstance(node, ast.Await): return child(node.value)
    if isinstance(node, ast.Dict):
        pairs = []
        for k,v in zip(node.keys, node.values):
            if k is not None and (not isinstance(k, ast.Constant) or not isinstance(k.value, str)): fail()
            pairs.append((None if k is None else k.value, child(v)))
        return ('obj', pairs)
    if isinstance(node, (ast.List, ast.Tuple)): return ('arr', [child(x) for x in node.elts])
    if isinstance(node, ast.Call):
        return ('call', child(node.func), [child(x) for x in node.args], ('obj', [(x.arg, child(x.value)) for x in node.keywords]))
    return ('dynamic',)


def read_python(text):
    try: tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        raise ValueError('Python 语法无法解析，请粘贴完整示例；不会执行代码') from None
    nodes = list(ast.walk(tree))
    if len(nodes) > 50000: fail()
    reader = Reader()
    def root_name(node):
        while isinstance(node, (ast.Attribute, ast.Subscript)): node = node.value
        return node.id if isinstance(node, ast.Name) else None
    for node in nodes:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                reader.bind(alias.asname or alias.name, ('symbol', node.module+'.'+alias.name) if node.module in {'openai','os'} else ('dynamic',))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                reader.bind(alias.asname or alias.name, ('symbol', alias.name) if alias.name in {'openai','os'} else ('dynamic',))
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and not isinstance(node, ast.AugAssign) and node.value is not None:
                    reader.bind(target.id, py_node(node.value, reader))
                else:
                    name = root_name(target)
                    if name: reader.blocked.add(name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            if hasattr(node, 'name'): reader.blocked.add(node.name)
            for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]: reader.blocked.add(arg.arg)
            for arg in (node.args.vararg,node.args.kwarg):
                if arg:reader.blocked.add(arg.arg)
        elif isinstance(node, ast.ClassDef): reader.blocked.add(node.name)
        elif isinstance(node, (ast.For,ast.AsyncFor,ast.comprehension,ast.Delete,ast.withitem)):
            targets = node.targets if isinstance(node,ast.Delete) else [node.optional_vars if isinstance(node,ast.withitem) else node.target]
            for target in targets:
                if target is not None:
                    for part in ast.walk(target):
                        if isinstance(part,ast.Name):reader.blocked.add(part.id)
        elif isinstance(node, ast.Call): reader.calls.append(py_node(node, reader))
    return reader


# Small, closed JavaScript grammar for SDK examples. No JS runtime is involved.
TOKEN = re.compile(r'\s+|//[^\r\n]*|/\*[\s\S]*?\*/|(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`)|[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|\.\.\.|=>|[{}\[\]().,:;=+\-]', re.UNICODE)


def js_string(token):
    raw = token[1:-1]
    if token[0] == '`' and '${' in raw: return ('dynamic',)
    result, i = [], 0
    escapes = {'n':'\n', 'r':'\r', 't':'\t', 'b':'\b', 'f':'\f', 'v':'\v', '0':'\0', '\\':'\\', "'":"'", '"':'"', '`':'`', '/':'/'}
    while i < len(raw):
        c = raw[i]; i += 1
        if c != '\\': result.append(c); continue
        if i >= len(raw): fail()
        c = raw[i]; i += 1
        if c in escapes: result.append(escapes[c])
        elif c in {'u','x'}:
            width = 4 if c == 'u' else 2
            part = raw[i:i+width]
            if len(part) != width or not re.fullmatch('[a-fA-F0-9]+', part): fail()
            result.append(chr(int(part,16))); i += width
        else: fail()
    return ('lit', ''.join(result))


class JSReader(Reader):
    def __init__(self, text):
        super().__init__()
        self.bindings['require'] = ('symbol', 'require')
        self.tokens, pos = [], 0
        for match in TOKEN.finditer(text):
            if match.start() != pos: fail()
            pos = match.end(); token = match[0]
            if token.isspace() or token.startswith(('//','/*')): continue
            self.tokens.append(token)
        if pos != len(text) or len(self.tokens) > 50000: fail()
        self.i = 0
        self.statements()

    def peek(self): return self.tokens[self.i] if self.i < len(self.tokens) else ''
    def pop(self):
        token = self.peek()
        if not token: fail()
        self.i += 1
        return token
    def take(self, token):
        if self.peek() == token: self.i += 1; return True
        return False
    def need(self, token):
        if not self.take(token): fail()
    def identifier(self):
        value = self.pop()
        if not re.fullmatch(r'[A-Za-z_$][\w$]*', value): fail()
        return value

    def statements(self, end='', depth=0):
        if depth > 40: fail()
        while self.peek() and self.peek() != end:
            if self.take(';'): continue
            if self.take('import'):
                aliases = []
                if self.take('{'):
                    while not self.take('}'):
                        original = self.identifier(); local = self.identifier() if self.take('as') else original
                        aliases.append((local, original))
                        if not self.take(','): self.need('}'); break
                else: aliases.append((self.identifier(), 'OpenAI'))
                self.need('from'); module = js_string(self.pop())
                if module != ('lit','openai'): fail()
                for local, original in aliases: self.bind(local, ('symbol','openai.'+original))
                self.take(';'); continue
            async_prefix = self.take('async')
            if self.take('function'):
                self.blocked.add(self.identifier()); self.need('(')
                while not self.take(')'):
                    self.blocked.add(self.identifier())
                    if not self.take(','): self.need(')'); break
                self.need('{'); self.statements('}',depth+1); self.need('}'); continue
            if async_prefix: fail()
            declaration = self.peek() in {'const','let','var'}
            if declaration:
                self.pop(); name = self.identifier(); self.need('=')
                start=self.i
                self.take('async')
                arrow=False
                if self.peek()=='(':
                    close=self.i+1
                    while close<len(self.tokens) and self.tokens[close]!=')':close+=1
                    arrow=close+1<len(self.tokens) and self.tokens[close+1]=='=>'
                if arrow:
                    self.need('(')
                    while not self.take(')'):
                        self.blocked.add(self.identifier())
                        if not self.take(','):self.need(')');break
                    self.need('=>');self.need('{');self.statements('}',depth+1);self.need('}')
                    value=('dynamic',)
                else:
                    self.i=start;value = self.expression()
                self.bind(name, value)
            else:
                self.take('return')
                value = self.expression()
                if self.take('='):
                    self.expression()
                    while value[0] == 'get': value = value[1]
                    if value[0] == 'name': self.blocked.add(value[1])
                    else: fail()
            self.take(';')
        if end and not self.peek(): fail()

    def expression(self, depth=0):
        if depth > 60: fail()
        if self.peek() in {'await', 'new'}: self.pop()
        token = self.pop()
        if token[0] in "\"'`": value = js_string(token)
        elif token in {'true','false','null'}: value = ('lit', {'true':True,'false':False,'null':None}[token])
        elif re.fullmatch(r'\d+(?:\.\d+)?', token): value = ('lit', float(token) if '.' in token else int(token))
        elif token == '{':
            pairs = []
            while not self.take('}'):
                if self.take('...'): pairs.append((None, self.expression(depth+1)))
                else:
                    key = self.pop()
                    if key[0] in "\"'": key = js_string(key)[1]
                    elif not re.fullmatch(r'[A-Za-z_$][\w$]*', key): fail()
                    pairs.append((key, self.expression(depth+1) if self.take(':') else ('name',key)))
                if not self.take(','): self.need('}'); break
            value = ('obj', pairs)
        elif token == '[':
            items = []
            while not self.take(']'):
                items.append(self.expression(depth+1))
                if not self.take(','): self.need(']'); break
            value = ('arr', items)
        elif token == '(':
            value = self.expression(depth+1); self.need(')')
        elif re.fullmatch(r'[A-Za-z_$][\w$]*', token): value = ('name',token)
        else: fail()
        while True:
            if self.take('.'):
                value = ('get',value,('lit',self.identifier()))
            elif self.take('['):
                value = ('get',value,self.expression(depth+1)); self.need(']')
            elif self.take('('):
                args = []
                while not self.take(')'):
                    args.append(self.expression(depth+1))
                    if not self.take(','): self.need(')'); break
                value = ('call',value,args,None); self.calls.append(value)
            else: break
        if self.peek() in {'+','-'}:
            self.pop(); self.expression(depth+1); return ('dynamic',)
        return value


def request_parts(call):
    node, names = call[1], []
    while node[0] == 'get' and node[2][0] == 'lit':
        names.insert(0,node[2][1]); node = node[1]
    if names == ['responses','create']: return node, 'responses'
    if names == ['chat','completions','create']: return node, 'chat/completions'
    return None


def parse_sdk(text, source):
    try:
        reader = read_python(text) if source == 'Python' else JSReader(text)
        reader.guard_mutations()
        records, warnings = [], []
        for call in reader.calls:
            parts = request_parts(call)
            if parts is None: continue
            client_expr, endpoint = parts
            client = reader.value(client_expr)
            if not isinstance(client, Client): fail()
            options = reader.fields(client.options)
            if set(options)-{'base_url','baseURL','api_key','apiKey','timeout','max_retries','maxRetries'}:
                raise ValueError('SDK 初始化含自定义认证、请求头或其他选项，无法完整转换，请使用标准 API Key 配置')
            if ('base_url' in options and 'baseURL' in options) or ('api_key' in options and 'apiKey' in options): fail()
            base = reader.value(options.get('base_url',options.get('baseURL',('lit','https://api.openai.com/v1'))))
            key = reader.value(options.get('api_key',options.get('apiKey',('get',('symbol','process.env'),('lit','OPENAI_API_KEY')))))
            if not isinstance(base,str): fail()
            if call[3] is not None:
                if call[2]: fail()
                args = reader.fields(call[3])
            else:
                if len(call[2]) != 1: fail()
                args = reader.fields(call[2][0])
            if set(args) & {'extra_headers','extra_query','headers'}:
                raise ValueError('SDK 请求含自定义请求头或查询参数，无法完整转换')
            data = {k:reader.value(v) for k,v in args.items() if k in {'model','reasoning','reasoning_effort','thinking'}}
            if 'extra_body' in args:
                extra = reader.fields(args['extra_body'])
                for k,v in extra.items():
                    if k in {'model','reasoning','reasoning_effort','thinking'}:
                        if k in data: fail()
                        data[k] = reader.value(v)
            if isinstance(key,Env):
                if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}',key.name): fail()
                credential = '${'+key.name+'}'
            elif isinstance(key,str): credential = key
            else: fail()
            tokens = ['curl',base.rstrip('/')+'/'+endpoint,'-H','Authorization: Bearer '+credential,'-d',json.dumps(data,ensure_ascii=False)]
            record, notes = parse_curl(' '.join(shlex.quote(x) for x in tokens))
            if record['profile']['id'] == 'curl-import':
                record['profile']['id'] = 'sdk-import'
            records.append(record); warnings.extend(notes)
        if not records:
            raise ValueError('未找到 OpenAI SDK 请求。请同时粘贴客户端初始化与 responses.create / chat.completions.create 调用')
        if len(records) > 200: raise ValueError('单次最多导入 200 项')
        warnings.insert(0,source+' 示例已静态解析；不会运行代码、导入模块、读取环境变量或发送请求。')
        return records, list(dict.fromkeys(warnings))
    except (RecursionError, TypeError, IndexError, UnicodeError):
        raise ValueError('SDK 示例结构过深或字段无法解析，请使用简化的完整示例') from None
