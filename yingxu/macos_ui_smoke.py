"""Hidden real WKWebView probe with temporary data, including dirty-draft close refusal."""
from pathlib import Path
import json
import os
import tempfile
import threading
import time
import traceback


def run():
    import webview
    from server import Application, Server
    from macos_app import Desktop, Bridge, stop_server
    result={'ok':False,'checks':[],'real_user_data_used':False}
    with tempfile.TemporaryDirectory(prefix='yingxu-webkit-') as temporary:
        root=Path(temporary).resolve()
        os.environ.update(HOME=str(root/'user'),USERPROFILE=str(root/'user'))
        app=Application(root/'data',root/'projects')
        service=Server(('127.0.0.1',0),app)
        threading.Thread(target=service.serve_forever,daemon=True).start()
        host=Desktop(app,f'http://127.0.0.1:{service.server_port}')
        window=webview.create_window('映序隔离测试',host.origin+'/?desktop=macos',
                                    js_api=Bridge(host),hidden=True,width=1280,height=800)
        host.window=window
        window.events.closing+=host.closing
        def wait(predicate):
            for _ in range(150):
                if predicate():return
                time.sleep(.1)
            raise AssertionError('WebKit check timed out')
        def exercise():
            try:
                wait(lambda:host.ready)
                assert window.evaluate_js("window.yingxuMac === true && document.querySelector('#connectionState').textContent === '本地连接正常'")
                result['checks'].append('Frozen app loads local frontend in WKWebView')
                assert host.post_message({'action':'exit-response','allow':True},'wrong-token') is False
                window.evaluate_js("(async () => { const p=await api('/api/projects',{method:'POST',body:{name:'WebKit合成项目'}}); await refreshProjects(); const n=await api('/api/items',{method:'POST',body:{project_id:p.id,category:'scripts',name:'合成笔记',content:'# 初始正文'}}); await openItem(n.id); return true; })()")
                wait(lambda:window.evaluate_js('state.tabs.length === 1 && !state.tabs[0].loading'))
                assert window.evaluate_js("Boolean(window.YingXuMarkdown || document.querySelector('#editorContent'))")
                result['checks'].append('Chinese project and document open in frozen WebKit')
                window.evaluate_js("settingsDialog(); true")
                wait(lambda:window.evaluate_js("document.querySelector('#dialogTitle').textContent === '设置'"))
                assert window.evaluate_js("!document.querySelector('[name=capture_enabled]') && !document.querySelector('[name=close_to_tray]')")
                window.evaluate_js("document.querySelector('#closeDialog').click(); true")
                window.evaluate_js("state.tabs[0].draft += '\\n未保存草稿'; state.tabs[0].dirty = true; true")
                assert host.closing() is False
                wait(lambda:window.evaluate_js("document.querySelector('#appDialog').open"))
                assert not host.guard.allowed
                window.evaluate_js("document.querySelector('#closeDialog').click(); true")
                wait(lambda:host.guard.request_id is None)
                assert window.evaluate_js('state.tabs[0].dirty === true')
                result['checks'].append('Native close prompts for dirty draft; cancel preserves draft and window')
                result['ok']=True
            except Exception:
                result['error']=traceback.format_exc()
            finally:
                host.guard.allowed=True
                window.destroy()
        try:webview.start(exercise,private_mode=True)
        finally:stop_server(service,app)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    if not result['ok']:raise SystemExit(1)


if __name__=='__main__':run()
