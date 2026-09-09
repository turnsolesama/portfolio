"""Local profile import and loss-checked Codex configuration changes. No network."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import tomllib
from urllib.parse import urlsplit
from switcher_curl import unwrap, is_curl, parse_curl
from switcher_sdk import language, parse_sdk

VERSION = '2.4.0'
FIELDS = ('id', 'name', 'base_url', 'env_key', 'model', 'wire_api')
OPTIONAL_FIELDS = ('reasoning_effort',)
EFFORTS = ('minimal', 'low', 'medium', 'high', 'xhigh')
BEGIN = '# >>> codex-switcher:begin >>>'
END = '# <<< codex-switcher:end <<<'
ID = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
ENV = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,127}\Z')
RESERVED = {'PATH','HOME','USERPROFILE','CODEX_HOME','SYSTEMROOT','COMSPEC','PYTHONPATH','PYTHONHOME','TEMP','TMP'}

def validate(p):
    if not isinstance(p, dict):
        raise ValueError('配置项必须是对象')
    out = {k: p.get(k, '') for k in FIELDS}
    out.update({k:p[k] for k in OPTIONAL_FIELDS if k in p})
    if any(not isinstance(v, str) for v in out.values()):
        raise ValueError('配置字段必须是文本')
    out = {k:v.strip() for k,v in out.items()}
    if not ID.fullmatch(out['id']):
        raise ValueError('ID 需以小写字母开头，使用字母、数字、横线或下划线，最长 64 位')
    out['name'] = out['name'] or out['id']
    if any(ord(c)<32 for k,v in out.items() for c in v) or any(len(v)>500 for v in out.values()):
        raise ValueError('字段含控制字符或超过长度限制')
    try:
        url = urlsplit(out['base_url'])
        _ = url.port
        valid = url.scheme in {'https','http'} and url.hostname and not url.username and not url.password and not url.query and not url.fragment
    except ValueError:
        valid = False
    if not valid or any(c.isspace() for c in out['base_url']):
        raise ValueError('服务地址需为 HTTP(S) URL，不能包含账号、密钥、查询参数或片段')
    if url.scheme=='http' and url.hostname not in {'localhost','127.0.0.1','::1'}:
        raise ValueError('远程服务请使用 HTTPS；HTTP 仅用于本地服务')
    if not ENV.fullmatch(out['env_key']) or out['env_key'].upper() in RESERVED:
        raise ValueError('密钥变量名不合法或是系统保留变量')
    if out['wire_api'] not in {'','responses'}:
        raise ValueError('此工具支持 Responses 协议；Chat Completions 配置需先确认服务商兼容性')
    out['wire_api']='responses'
    if out.get('reasoning_effort', '') not in ('', *EFFORTS):
        raise ValueError('推理强度需为 minimal / low / medium / high / xhigh，或留空沿用当前配置')
    if not out.get('reasoning_effort'):out.pop('reasoning_effort',None)
    out['base_url']=out['base_url'].rstrip('/')
    return out

def slug(value):
    value=re.sub('[^a-z0-9_-]+','-',str(value).lower()).strip('-_')[:50]
    return value if value and value[0].isalpha() else 'provider-'+(value or 'imported')

def atomic_write(path, text):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
            f.write(text);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def load_profiles(path):
    path=Path(path)
    if not path.exists():return []
    try:
        raw=json.loads(path.read_text(encoding='utf-8-sig'))
        records=raw['profiles']
        if not isinstance(records,list):raise ValueError()
        # Legacy records remain visible for repair; activation is always validated.
        profiles=[]
        for p in records:
            if not isinstance(p,dict):raise ValueError()
            item={k:p.get(k,'responses' if k=='wire_api' else '') for k in FIELDS}
            item.update({k:p[k] for k in OPTIONAL_FIELDS if k in p})
            if any(not isinstance(v,str) or len(v)>500 or any(ord(c)<32 for c in v) for v in item.values()):raise ValueError()
            if not ID.fullmatch(item['id']):raise ValueError()
            profiles.append(item)
        if len({p['id'] for p in profiles})!=len(profiles):raise ValueError()
        return profiles
    except (ValueError,KeyError,TypeError):
        raise ValueError('配置列表无效；原文件未被覆盖，请先恢复备份') from None

def export_profiles(profiles):
    return _serialize_profiles([validate(p) for p in profiles])

def _serialize_profiles(profiles):
    return json.dumps({'version':VERSION,'contains_secrets':False,'profiles':[{k:p[k] for k in FIELDS+OPTIONAL_FIELDS if k in p} for p in profiles]},ensure_ascii=False,indent=2)

def profile_issue(profile):
    try:validate(profile)
    except ValueError as error:return str(error)
    return ''

def save_profiles(path,profiles,expected=None):
    existing=load_profiles(path)
    checked=[]
    for p in profiles:
        try:checked.append(validate(p))
        except ValueError:
            # Only preserve an exactly unchanged record already on this device.
            if p not in existing:raise
            checked.append(p)
    text=_serialize_profiles(checked)
    if len({p['id'] for p in profiles})!=len(profiles):raise ValueError('ID 重复')
    if expected is not None and file_hash(path)!=expected:raise ValueError('配置被其他窗口修改，请刷新后重试')
    backup(path)
    atomic_write(path,text)

def file_hash(path):
    p=Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else 'missing'

def backup(path):
    path=Path(path)
    if not path.exists():return None
    directory=path.parent/'switcher-backups'
    directory.mkdir(exist_ok=True)
    target=directory/(path.name+'.'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()%1000000000)+'.bak')
    target.write_bytes(path.read_bytes())
    return target

def import_text(text):
    """JSON, TOML, env, wrapped exports, or a locally parsed cURL example."""
    if len(text.encode('utf-8'))>2*1024*1024:raise ValueError('导入文件上限为 2 MiB')
    text=unwrap(text)
    if is_curl(text):
        record,warnings=parse_curl(text)
        record['profile']=validate(record['profile'])
        return [record],warnings
    source=language(text)
    if source:
        records,warnings=parse_sdk(text,source)
        for record in records:record['profile']=validate(record['profile'])
        return records,warnings
    try:raw=json.loads(text)
    except ValueError:
        try:raw=tomllib.loads(text)
        except ValueError:
            raw={}
            for line in text.splitlines():
                line=line.strip()
                if not line or line.startswith('#'):continue
                match=re.fullmatch(r'(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)',line)
                if not match:raise ValueError('无法解析文件，请使用 Python、Node.js、cURL、JSON、TOML 或 .env 文本') from None
                value=match[2].strip()
                if len(value)>=2 and value[0]==value[-1] and value[0] in '\"\'':value=value[1:-1]
                raw[match[1]]=value
    records=[]
    warnings=[]
    def visit(obj, hint='', inherited=None, depth=0):
        if depth>8:raise ValueError('导入结构嵌套过深')
        inherited=inherited or {}
        if isinstance(obj,list):
            for i,x in enumerate(obj):visit(x,str(i+1),inherited,depth+1)
            return
        if not isinstance(obj,dict):return
        settings=obj.get('settingsConfig')
        if isinstance(settings,dict):
            env=settings.get('env',{})
            if not isinstance(env,dict):env={}
            config=settings.get('config')
            if isinstance(config,str):
                try:parsed=tomllib.loads(config)
                except ValueError:raise ValueError('嵌入的 Codex TOML 无效') from None
                visit(parsed,obj.get('id',hint),{**env,'name':obj.get('name','')},depth+1)
            else:visit({**settings,**env,'id':obj.get('id',hint),'name':obj.get('name','')},hint,{},depth+1)
            return
        providers=obj.get('model_providers')
        if isinstance(providers,dict):
            for pid,p in providers.items():
                if isinstance(p,dict):visit({**p,'id':pid,'model':obj.get('model',''),'reasoning_effort':obj.get('model_reasoning_effort','')},pid,inherited,depth+1)
            return
        url=obj.get('base_url',obj.get('baseUrl',obj.get('apiHost',obj.get('OPENAI_BASE_URL',obj.get('OPENAI_API_BASE','')))))
        if url:
            pid=slug(obj.get('id') or obj.get('name') or hint or 'imported')
            env=obj.get('env_key') or obj.get('envKey') or 'CODEX_'+pid.upper().replace('-','_')+'_API_KEY'
            p=validate({'id':pid,'name':obj.get('name') or inherited.get('name') or pid,'base_url':url,
                        'env_key':env,'model':obj.get('model',obj.get('OPENAI_MODEL','')),
                        'wire_api':obj.get('wire_api','responses'),'reasoning_effort':obj.get('reasoning_effort','')})
            secret=obj.get('api_key') or obj.get('apiKey') or obj.get('OPENAI_API_KEY') or inherited.get(env) or inherited.get('OPENAI_API_KEY') or ''
            if not isinstance(secret,str) or '\n' in secret or '\r' in secret or '\0' in secret or len(secret)>8192:
                raise ValueError('API Key 格式不合法')
            records.append({'profile':p,'secret':secret.strip()})
            ignored=set(obj)-set(FIELDS+OPTIONAL_FIELDS)-{'baseUrl','apiHost','apiKey','api_key','OPENAI_API_KEY','OPENAI_BASE_URL','OPENAI_API_BASE','OPENAI_MODEL','envKey'}
            if ignored:warnings.append('已忽略额外字段（例如自定义请求头、查询参数）；请核对服务商要求')
            return
        for key in ('profiles','providers','codex'):
            child=obj.get(key)
            if isinstance(child,list):visit(child,hint,inherited,depth+1);return
            if isinstance(child,dict):
                if key=='codex' or 'providers' in child:visit(child,hint,inherited,depth+1)
                else:
                    for pid,p in child.items():visit(p,str(pid),inherited,depth+1)
                return
    try:visit(raw)
    except (RecursionError,TypeError):raise ValueError('导入结构无效') from None
    if not records:raise ValueError('没有找到服务地址配置。登录会话、OAuth Token 和 auth.json 不属于可导入的 API 服务配置')
    if len(records)>200:raise ValueError('单次最多导入 200 项')
    return records,list(dict.fromkeys(warnings))

def merge_profiles(existing, records):
    """Add-only merge. Duplicate endpoints/models do not overwrite existing keys."""
    profiles=copy.deepcopy(existing)
    ids={p['id'] for p in profiles}
    identities={(p['base_url'],p.get('model','')) for p in profiles}
    additions=[];skipped=0
    for item in records:
        p=validate(item['profile'])
        identity=(p['base_url'],p.get('model',''))
        if identity in identities:skipped+=1;continue
        stem=p['id'];index=2
        while p['id'] in ids:
            p['id']=stem[:56]+'-'+str(index);index+=1
        # Imported values get isolated variable names; never replace an existing key.
        if item.get('secret'):
            p['env_key']='CODEX_IMPORT_'+p['id'].upper().replace('-','_')+'_API_KEY'
        ids.add(p['id']);identities.add(identity);profiles.append(p)
        additions.append({'profile':p,'secret':item.get('secret','')})
    return profiles,additions,skipped

def render_config(text,profile):
    try:before=tomllib.loads(text)
    except ValueError:raise ValueError('当前 config.toml 无效，未修改') from None
    expected=copy.deepcopy(before)
    blocks=re.findall(re.escape(BEGIN)+r'.*?'+re.escape(END),text,re.S)
    for block in blocks:
        try:managed=tomllib.loads(block)
        except ValueError:raise ValueError('旧托管区域无效，未修改') from None
        if set(managed)-{'model_providers'}:raise ValueError('托管区域含其他设置，未修改')
        for pid in managed.get('model_providers',{}):expected.get('model_providers',{}).pop(pid,None)
    result=re.sub(re.escape(BEGIN)+r'.*?'+re.escape(END)+r'\n?','',text,flags=re.S)
    # Only root assignments are replaced; round-trip equality protects unusual TOML.
    split=re.search(r'(?m)^\s*\[',result)
    head,tail=(result[:split.start()],result[split.start():]) if split else (result,'')
    head=re.sub(r'(?m)^\s*(?:model_provider|"model_provider"|\'model_provider\')\s*=.*\n?','',head)
    expected.pop('model_provider',None)
    block=''
    if profile:
        p=validate(profile)
        pid='switcher_'+p['id']
        if pid in expected.get('model_providers',{}):raise ValueError('同名服务商已在非托管区域定义，请更换 ID')
        provider={'name':p['name'],'base_url':p['base_url'],'env_key':p['env_key'],'wire_api':'responses'}
        expected.setdefault('model_providers',{})[pid]=provider
        expected['model_provider']=pid
        head='model_provider = '+json.dumps(pid)+'\n'+head
        if p['model']:
            head=re.sub(r'(?m)^\s*(?:model|"model"|\'model\')\s*=.*\n?','',head)
            head='model = '+json.dumps(p['model'],ensure_ascii=False)+'\n'+head
            expected['model']=p['model']
        if p.get('reasoning_effort'):
            head=re.sub(r'(?m)^\s*(?:model_reasoning_effort|"model_reasoning_effort"|\'model_reasoning_effort\')\s*=.*\n?','',head)
            head='model_reasoning_effort = '+json.dumps(p['reasoning_effort'])+'\n'+head
            expected['model_reasoning_effort']=p['reasoning_effort']
        block='\n'+BEGIN+'\n[model_providers.'+pid+']\n'+''.join(k+' = '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in provider.items())+END+'\n'
    result=head.rstrip()+'\n\n'+tail.rstrip()+block+'\n'
    def clean(d):
        if d.get('model_providers')=={}:d.pop('model_providers')
        return d
    try:after=tomllib.loads(result)
    except ValueError:raise ValueError('无法安全处理此配置布局，原文件未修改') from None
    if clean(after)!=clean(expected):raise ValueError('保护检查发现其他设置可能改变，原文件未修改')
    return result

def apply_config(path,profile,expected_hash=None):
    path=Path(path)
    old=path.read_text(encoding='utf-8-sig') if path.exists() else ''
    digest=file_hash(path)
    if expected_hash is not None and digest!=expected_hash:raise ValueError('Codex 配置已变化，请刷新预览')
    new=render_config(old,profile)
    if file_hash(path)!=digest:raise ValueError('Codex 配置已变化，未覆盖')
    backup(path);atomic_write(path,new)

def restore_backup(path,source,expected_hash):
    path,source=Path(path),Path(source)
    if source.resolve().parent!=(path.parent/'switcher-backups').resolve() or not source.name.startswith(path.name+'.') or source.suffix!='.bak':
        raise ValueError('请选择此配置文件的备份')
    text=source.read_text(encoding='utf-8-sig')
    try:tomllib.loads(text)
    except ValueError:raise ValueError('备份不是合法 TOML') from None
    if file_hash(path)!=expected_hash:raise ValueError('配置已变化，请刷新')
    backup(path);atomic_write(path,text)
