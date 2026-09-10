"""映序本地启动器：复用已验证的后台，无控制台窗口。"""
import argparse
import ctypes
from ctypes import wintypes
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from yingxu import __version__
from yingxu.paths import default_data_root, default_project_root, instance_id

ROOT = Path(__file__).resolve().parent
DATA = default_data_root()
PROJECTS = default_project_root()


def health(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        if response.status != 200:
            return None
        raw = response.read(65537)
        if len(raw) > 65536:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) and data.get("app") == "yingxu" and data.get("ok") is True and data.get("instance_id") == instance_id(DATA) else None
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        connection.close()


def port_busy(port):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def acquire_mutex(port, timeout):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.CreateMutexW(None, False, f"Local\\YingXu-launch-{port}")
    if not handle:
        raise OSError("无法创建映序启动锁。")
    result = kernel.WaitForSingleObject(handle, int(timeout * 1000))
    if result not in (0, 0x80):
        kernel.CloseHandle(handle)
        raise RuntimeError("另一个启动过程尚未完成，请稍后重新打开映序。")
    return kernel, handle


def require_current_service(info):
    if info and info.get('version') != __version__:
        raise RuntimeError('旧版映序后台仍在运行。请保存编辑、等待导入完成，关闭窗口并运行 Stop-YingXu.ps1，再打开新版。')
    return info


def ensure_running(port, timeout=22):
    if require_current_service(health(port)):
        return {"status": "reused", "port": port}
    kernel, handle = acquire_mutex(port, timeout)
    try:
        if require_current_service(health(port)):
            return {"status": "reused", "port": port}
        if port_busy(port):
            raise RuntimeError(f"端口 {port} 已被其他服务占用。映序没有接管该服务；请释放此端口后重试。")
        server = ROOT / "server.py"
        if not server.is_file():
            raise FileNotFoundError("缺少 server.py，请保留完整的映序程序文件夹。")
        DATA.mkdir(parents=True, exist_ok=True)
        log_path = DATA / "server.log"
        if log_path.exists() and log_path.stat().st_size > 5 * 1024 * 1024:
            log_path.replace(DATA / "server.previous.log")
        interpreter = Path(sys.executable)
        if interpreter.name.lower() == "pythonw.exe" and interpreter.with_name("python.exe").is_file():
            interpreter = interpreter.with_name("python.exe")
        environment = os.environ.copy()
        environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                [str(interpreter), "-B", "-u", str(server), "--port", str(port), "--data", str(DATA), "--projects-root", str(PROJECTS)],
                cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=environment)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if require_current_service(health(port)):
                record = {"pid": process.pid, "port": port, "root": str(ROOT), "app": "yingxu"}
                temporary = DATA / "server.pid.json.tmp"
                temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(DATA / "server.pid.json")
                return {"status": "started", "port": port, "pid": process.pid}
            if process.poll() is not None:
                raise RuntimeError(f"映序后台未能启动。详细原因请查看：{log_path}")
            time.sleep(0.2)
        raise RuntimeError(f"映序后台启动超时。请查看 {log_path}；稍后重新打开会复用已启动的服务。")
    finally:
        kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--no-browser", action="store_true", help="仅启动后台，不打开映序窗口")
    parser.add_argument("--no-dialog", action="store_true", help="仅写入错误日志")
    args = parser.parse_args(argv)
    try:
        if not 1024 <= args.port <= 65535:
            raise ValueError("端口必须是 1024 至 65535 之间的整数。")
        result = ensure_running(args.port)
        if not args.no_browser:
            executable = ROOT / "YingXu.exe"
            if not executable.is_file():
                raise FileNotFoundError("缺少 YingXu.exe，请保留完整的映序程序目录。")
            if args.port != 8791:
                raise ValueError("桌面入口使用固定端口 8791。其他端口仅用于开发测试。")
            subprocess.Popen([str(executable)], cwd=str(ROOT))
        if sys.stdout:
            print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        message = str(error)
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            with (DATA / "launcher.log").open("a", encoding="utf-8") as log:
                log.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")
        except OSError:
            pass
        if sys.stderr:
            print(message, file=sys.stderr)
        if not args.no_dialog:
            ctypes.windll.user32.MessageBoxW(None, message, "映序 · 启动提示", 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
