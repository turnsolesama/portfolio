"""Isolated smoke checks runnable from the frozen macOS executable."""
from pathlib import Path
import hashlib
import http.client
import json
import os
import tempfile
import threading
import time


def run():
    from server import Application, Server, ROOT
    from macos_app import stop_server, PREVIEW
    from yingxu.macos import rename_exclusive, recycle
    from yingxu.runtime import ffmpeg_path
    from PIL import Image
    import subprocess
    checks=[]
    with tempfile.TemporaryDirectory(prefix='yingxu-macos-smoke-') as temporary:
        root=Path(temporary).resolve()
        os.environ.update(USERPROFILE=str(root/'user'),HOME=str(root/'user'),
                          YINGXU_DATA_DIR=str(root/'data'),YINGXU_PROJECTS_DIR=str(root/'projects'))
        app=Application(root/'data',root/'projects')
        service=Server(('127.0.0.1',0),app)
        thread=threading.Thread(target=service.serve_forever,daemon=True);thread.start()
        def request(method,path,data=None):
            c=http.client.HTTPConnection('127.0.0.1',service.server_port,timeout=10)
            body=json.dumps(data).encode() if data is not None else None
            headers={'Content-Type':'application/json','X-YingXu-Token':app.token}
            try:
                c.request(method,path,body,headers);r=c.getresponse();raw=r.read()
                assert r.status==200 or r.status==201,(r.status,path,raw[:300])
                return json.loads(raw)
            finally:c.close()
        try:
            assert request('GET','/api/health')['version']=='0.3.7'
            project=request('POST','/api/projects',{'name':'Mac 合成项目'})
            item=request('POST','/api/items',{'project_id':project['id'],'category':'scripts','name':'测试文稿','content':'# 中文\n正文'})
            original=Path(item['path']).read_bytes()
            changed=app.store.rename_file(item['id'],'改名成功')
            assert Path(changed['path']).read_bytes()==original
            folder=app.organize.create_folder(project['id'],'scripts','初始目录')
            app.organize.rename_folder(folder['id'],'已改名目录')
            checks.append('HTTP project/document creation, original file and folder rename')
            source=root/'source.txt';target=root/'target.txt'
            source.write_text('source');target.write_text('destination')
            try:rename_exclusive(source,target)
            except FileExistsError:pass
            else:raise AssertionError('Rename replaced destination')
            assert source.read_text()=='source' and target.read_text()=='destination'
            checks.append('Darwin exclusive rename refuses existing destination')
            target.unlink()
            result=recycle(source)
            recovered=Path(result['recycle_path'])
            assert not source.exists() and recovered.read_text()=='source'
            # Recover only the unique synthetic fixture created by this check.
            recovered.rename(source)
            checks.append('Native macOS Trash round trip preserves synthetic file bytes')
            picture=root/'fixture.png';Image.new('RGB',(320,180),'green').save(picture)
            ffmpeg=ffmpeg_path()
            if not ffmpeg:
                import sys
                assert not getattr(sys,'frozen',False), 'Frozen app is missing FFmpeg'
                import imageio_ffmpeg
                ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
            video=root/'fixture.mp4'
            subprocess.run([ffmpeg,'-nostdin','-loglevel','error','-loop','1','-i',str(picture),'-t','0.2',
                '-c:v','libx264','-pix_fmt','yuv420p','-threads','1',str(video)],check=True,timeout=30,capture_output=True)
            assert video.stat().st_size>100
            checks.append('Bundled Pillow and FFmpeg create PNG and H.264 without downloads')
            manifest=json.loads((ROOT/'frontend/live-markdown.manifest.json').read_text())
            assert hashlib.sha256((ROOT/'frontend/live-markdown.js').read_bytes()).hexdigest()==manifest['sha256']
            assert (ROOT/'frontend/macos.js').is_file()
            checks.append('Offline frontend and Markdown bundle integrity')
        finally:stop_server(service,app)
    print(json.dumps({'ok':True,'version':PREVIEW,'checks':checks,'real_user_data_used':False},ensure_ascii=False))


if __name__=='__main__':run()
