"""Build a reproducible distribution using only reviewed program files."""
import hashlib
import json
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parent
FILES=('codex_switcher.pyw','switcher_core.py','switcher_curl.py','switcher_ui.py','test_switcher.py','test_switcher_curl.py','test_switcher_ui.py','Launcher.cs','build.py','package_release.py',
       'Codex Switcher.exe','switcher.ico','README.md','TEST_REPORT.md','AGENTS.md','.gitignore',
       'examples/provider.json','examples/codex.toml','examples/provider.env','examples/deepseek.curl')
def build():
    output=ROOT/'releases';output.mkdir(exist_ok=True)
    target=output/'Codex-Switcher-v2.2.0-Windows-x64.zip';manifest=[]
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name in FILES:
            path=ROOT/name
            if path.is_symlink() or not path.is_file():raise ValueError('Missing or linked release file: '+name)
            path.resolve().relative_to(ROOT.resolve())
            data=path.read_bytes();manifest.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
            info=zipfile.ZipInfo('Codex-Switcher/'+name,date_time=(2026,9,8,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
    info={'version':'2.2.0','package':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'contains_user_data':False,'files':manifest}
    (output/'manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'SHA256.txt').write_text(info['sha256']+'  '+target.name+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in info.items() if k!='files'},ensure_ascii=False))
if __name__=='__main__':build()
