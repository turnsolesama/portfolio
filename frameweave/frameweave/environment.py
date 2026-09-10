"""Bounded, read-only discovery of existing local ComfyUI environments.

Never execute a discovered interpreter, import its packages, install software or
walk a model tree. Package metadata is evidence of files, not runtime health.
"""

import concurrent.futures
import csv
import datetime
import http.client
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse

from .backend import local_url


PORTS = (8188, 8189, 8190, 8000)
MAX_CANDIDATES = 12
MAX_INSTALLATIONS = 12
PACKAGES = ("torch", "torchvision", "torchaudio", "safetensors", "numpy", "comfyui_frontend_package")
PROCESS_SCRIPT = (
    "$ErrorActionPreference='Stop'; "
    "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
    "@(Get-CimInstance Win32_Process -Filter "
    "\"Name='python.exe' OR Name='pythonw.exe' OR Name='YUH Studio.exe' OR Name='ComfyUI.exe'\" "
    "| Select-Object -First 96 Name,ExecutablePath,CommandLine) | ConvertTo-Json -Compress"
)


def _text(value, limit=200):
    if not isinstance(value, str):
        return ""
    return "".join(c for c in value[:limit] if c.isprintable()).strip()


def _path(value):
    if not isinstance(value, (str, Path)):
        return None
    value = str(value)
    if not value or len(value) > 2048 or "\x00" in value or value.startswith(("\\\\", "//")):
        return None
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            return None
        # No resolve(): opening junction targets or inaccessible paths is unnecessary.
        return Path(os.path.normpath(path))
    except (ValueError, OSError, RuntimeError):
        return None


def _exists(path, directory=False):
    try:
        return path.is_dir() if directory else path.is_file()
    except (OSError, ValueError):
        return False


def _key(path):
    return os.path.normcase(str(path))


def _run_fixed(argv, timeout):
    """Only callers below construct argv from fixed switches; never shell=True."""
    return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=timeout, check=False,
                          encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _processes():
    if os.name != "nt":
        return [], "unknown"
    system = _path(os.environ.get("SystemRoot", "C:/Windows"))
    powershell = system / "System32/WindowsPowerShell/v1.0/powershell.exe" if system else None
    if not powershell or not _exists(powershell):
        return [], "unknown"
    try:
        result = _run_fixed([str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive",
                             "-Command", PROCESS_SCRIPT], 3)
        if result.returncode or len(result.stdout) > 1024 * 1024:
            return [], "unknown"
        records = json.loads(result.stdout.lstrip("\ufeff"))
        records = [records] if isinstance(records, dict) else records
        if not isinstance(records, list):
            return [], "unknown"
        return [r for r in records[:96] if isinstance(r, dict)], "ok"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return [], "unknown"


def _tokens(command):
    # Windows command lines need backslashes preserved. This bounded tokenizer
    # intentionally ignores unmatched quotes instead of guessing executable code.
    if not isinstance(command, str) or len(command) > 32768 or "\x00" in command:
        return []
    if command.count('"') % 2:
        return []
    return [m[1:-1] if m.startswith('"') and m.endswith('"') else m
            for m in re.findall(r'"[^"]*"|[^\s"]+', command)[:256]]


def _option(tokens, name):
    for i, token in enumerate(tokens):
        if token == name and i + 1 < len(tokens):
            return tokens[i + 1]
        if token.startswith(name + "="):
            return token[len(name) + 1:]
    return None


def _installation_root(path):
    return bool(path and _exists(path / "main.py") and _exists(path / "comfy", directory=True))


def _process_hints(records):
    installations, ports = [], []
    for record in records[:96]:
        name = _text(record.get("Name")).lower()
        exe = _path(record.get("ExecutablePath"))
        if name in ("yuh studio.exe", "comfyui.exe") and exe:
            for suffix in ("resources/engine/ComfyUI", "resources/ComfyUI"):
                root = exe.parent / suffix
                if _installation_root(root):
                    installations.append((root, "正在运行的桌面宿主", None, None))
            continue
        if name not in ("python.exe", "pythonw.exe", "python", "python3") or not exe:
            continue
        tokens = _tokens(record.get("CommandLine"))
        main = next((_path(token) for token in tokens if token.replace("\\", "/").lower().endswith("/main.py")), None)
        candidates = [main.parent] if main else []
        # A relative main.py is accepted only when adjacent installation files
        # independently prove this is a ComfyUI interpreter layout.
        if "main.py" in tokens or "./main.py" in tokens:
            candidates += [exe.parent / "ComfyUI", exe.parent.parent / "ComfyUI",
                           exe.parent.parent, exe.parent.parent.parent]
        root = next((p for p in candidates if _installation_root(p)), None)
        if root is None:
            continue
        config = _option(tokens, "--extra-model-paths-config")
        installations.append((root, "正在运行的 ComfyUI Python 进程", exe, config))
        value = _option(tokens, "--port")
        if isinstance(value, str) and re.fullmatch(r"[0-9]{1,5}", value) and 1 <= int(value) <= 65535:
            ports.append(int(value))
    return installations, ports


def _common_roots():
    try:
        home = Path.home()
    except (OSError, RuntimeError):
        return []
    return [home / suffix for suffix in (
        "ComfyUI", "ComfyUI_windows_portable/ComfyUI", "Documents/ComfyUI",
        "Desktop/ComfyUI", "Downloads/ComfyUI", "Desktop/ComfyUI_windows_portable/ComfyUI",
        "Downloads/ComfyUI_windows_portable/ComfyUI")]


def _registry_roots():
    """Read only two known uninstall branches, with a fixed entry cap."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    found = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall") as key:
                for index in range(min(winreg.QueryInfoKey(key)[0], 256)):
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, index)) as item:
                            name = str(winreg.QueryValueEx(item, "DisplayName")[0]).lower()
                            if name not in ("yuh studio", "comfyui"):
                                continue
                            root = _path(winreg.QueryValueEx(item, "InstallLocation")[0])
                            if root:
                                found += [root, root / "resources/engine/ComfyUI", root / "resources/ComfyUI"]
                    except OSError:
                        continue
        except OSError:
            continue
    return found[:12]


def _yaml_scalar(value):
    value = value.strip()
    if not value or value.startswith(("!", "&", "*", "{", "[", "|", ">")):
        return None
    if value[:1] in ("'", '"'):
        if len(value) < 2 or value[-1:] != value[:1]:
            return None
        return value[1:-1]
    return value.split(" #", 1)[0].strip()


def _config_roots(config, root):
    """Read plain base_path scalars only; no YAML evaluator or variable expansion.

    This deliberately omits complex YAML mappings/anchors and nested per-role
    relative paths. Users can add those paths explicitly in client settings.
    """
    if not config:
        return []
    file = _path(config)
    if file is None:
        # Relative config paths refer to a process cwd, which we cannot prove.
        return []
    try:
        with file.open("r", encoding="utf-8-sig") as stream:
            text = stream.read(65537)
        if len(text) > 65536:
            return []
    except (OSError, UnicodeError):
        return []
    result = []
    for line in text.splitlines()[:1024]:
        match = re.fullmatch(r"[ ]{0,16}base_path:[ ]+(.+)", line)
        if match:
            path = _path(_yaml_scalar(match.group(1)))
            if path and _exists(path, directory=True) and _key(path) not in {_key(p) for p in result}:
                result.append(path)
                if len(result) >= 12:
                    break
    return result


def _python_paths(root, interpreter):
    candidates = [interpreter] if interpreter else []
    for env in (root / ".venv", root / "venv", root / "env",
                root.parent / "python_embeded", root.parent / "python_embedded",
                root / "python_embeded", root / "python_embedded"):
        candidates += [env / "Scripts/python.exe", env / "python.exe", env / "bin/python"]
    # YUH runtime lives outside the application resource directory. This path
    # is a known host layout, not an inferred global Python installation.
    if (root.as_posix().lower().endswith("/resources/engine/comfyui")
            and _exists(root.parents[2] / "YUH Studio.exe")):
        appdata = _path(os.environ.get("APPDATA"))
        if appdata:
            for version in range(11, 16):
                candidates.append(appdata / f"YUH Studio/runtime/venv3{version}/Scripts/python.exe")
            for env in ("venv", ".venv"):
                candidates.append(appdata / "YUH Studio/h3-runtime" / env / "Scripts/python.exe")
    unique = []
    for value in candidates:
        if value and _exists(value) and _key(value) not in {_key(p) for p in unique}:
            unique.append(value)
    return unique[:8]


def _package_metadata(interpreter):
    packages = {name: {"name": name, "version": None, "status": "unknown"} for name in PACKAGES}
    if interpreter is None:
        return list(packages.values())
    # Use only the selected interpreter's install prefix; never sys.path or
    # importlib.metadata, which would inspect FrameWeave's own Python instead.
    prefixes = [interpreter.parent]
    if interpreter.parent.name.lower() in ("scripts", "bin"):
        prefixes = [interpreter.parent.parent]
    sites = [p / "Lib/site-packages" for p in prefixes]
    # Unix venv support remains bounded to explicit CPython 3.11-3.15 layouts.
    sites += [p / f"lib/python3.{v}/site-packages" for p in prefixes for v in range(11, 16)]
    scanned = False
    seen = set()
    for site in sites:
        try:
            if not site.is_dir():
                continue
            entries = []
            with os.scandir(site) as directory:
                for index, entry in enumerate(directory):
                    if index >= 4096:
                        break
                    if entry.name.endswith(".dist-info"):
                        entries.append(entry)
                else:
                    scanned = True
            for entry in entries:
                match = re.fullmatch(r"([A-Za-z0-9_.]+)-([A-Za-z0-9_.+!-]{1,100})\.dist-info", entry.name)
                if not match or match.group(1).lower().replace("-", "_") not in packages:
                    continue
                name = match.group(1).lower().replace("-", "_")
                seen.add(name)
                metadata = Path(entry.path) / "METADATA"
                try:
                    with metadata.open("r", encoding="utf-8") as stream:
                        content = stream.read(16384)
                    version = re.search(r"^Version: ([^\r\n]{1,100})$", content, re.MULTILINE)
                    declared = re.search(r"^Name: ([^\r\n]{1,100})$", content, re.MULTILINE)
                    if version and declared and declared.group(1).lower().replace("-", "_") == name:
                        packages[name].update(version=_text(version.group(1), 100), status="ok")
                except (OSError, UnicodeError):
                    pass
        except OSError:
            continue
    if scanned:
        for item in packages.values():
            if item["status"] == "unknown" and item["name"] not in seen:
                item["status"] = "missing"
    return list(packages.values())


def _installation(hint):
    root, source, interpreter, config = hint
    interpreters = _python_paths(root, interpreter)
    selected = interpreters[0] if interpreters else None
    roots = [root / "models"] if _exists(root / "models", directory=True) else []
    roots += _config_roots(config, root)
    unique_roots = list(dict.fromkeys(str(p) for p in roots))[:12]
    return {"root": str(root), "source": source,
            "python": {"path": str(selected) if selected else None,
                       "status": "ok" if selected else "unknown",
                       "detail": "已找到关联解释器文件；未执行" if selected else "未定位关联解释器，不能据此判定未安装"},
            "model_roots": unique_roots, "packages": _package_metadata(selected),
            "detail": "安装目录结构与包元数据仅证明文件存在，未执行 Python 或导入 torch；不代表可推理"}


def _request_stats(url, timeout=1, limit=131072):
    """Use a socket shutdown deadline, including slow headers or body trickles.

    A normal socket timeout is per read and can be extended indefinitely by a
    slowly responding unrelated service. Discovery has a total response budget.
    Direct HTTPConnection also bypasses proxies and never follows redirects.
    """
    parsed = urllib.parse.urlsplit(local_url(url))
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    deadline = time.monotonic() + timeout
    timer = None
    try:
        connection.connect()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("本机服务探测超时")
        sock = connection.sock
        sock.settimeout(remaining)

        def expire():
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        timer = threading.Timer(remaining, expire)
        timer.daemon = True
        timer.start()
        connection.request("GET", "/system_stats", headers={"Accept": "application/json", "Connection": "close"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("不是有效的服务状态响应")
        length = response.getheader("Content-Length")
        if length and (not length.isdigit() or int(length) > limit):
            raise ValueError("服务状态响应过大或长度无效")
        body = response.read(limit + 1)
        if time.monotonic() > deadline:
            raise TimeoutError("本机服务探测超时")
        if len(body) > limit:
            raise ValueError("服务状态响应过大")
        return json.loads(body)
    finally:
        if timer:
            timer.cancel()
        connection.close()


def _probe(candidate):
    result = {**candidate, "online": False, "version": None, "devices": [], "status": "unknown",
              "detail": "未收到有效 ComfyUI 响应；服务可能未启动、超时或端口不同"}
    try:
        stats = _request_stats(candidate["url"], timeout=1, limit=131072)
        if not isinstance(stats, dict):
            return result
        system, devices = stats.get("system"), stats.get("devices")
        if (not isinstance(system, dict) or not isinstance(devices, list) or len(devices) > 32
                or not _text(system.get("comfyui_version"), 100)
                or not _text(system.get("python_version"), 200)):
            return result
        cleaned = []
        for device in devices:
            if not isinstance(device, dict) or not _text(device.get("name")):
                return result
            row = {"name": _text(device["name"]), "type": _text(device.get("type"), 30)}
            for name in ("vram_total", "vram_free", "torch_vram_total", "torch_vram_free"):
                value = device.get(name)
                if type(value) is int and 0 <= value <= 2 ** 60:
                    row[name] = value
            cleaned.append(row)
        result.update(online=True, version=_text(system["comfyui_version"], 100), devices=cleaned,
                      status="ok", detail="ComfyUI system_stats 结构校验通过；仍需实际生成验证")
    except (http.client.HTTPException, OSError, ValueError, TypeError, RecursionError):
        pass
    return result


def _gpu():
    unknown = {"gpus": [], "status": "unknown", "detail": "未获得 NVIDIA 驱动查询结果；不能断言显卡或驱动未安装"}
    candidates = []
    if os.name == "nt":
        for variable, fallback, suffix in (
            ("SystemRoot", "C:/Windows", "System32/nvidia-smi.exe"),
            ("ProgramFiles", "C:/Program Files", "NVIDIA Corporation/NVSMI/nvidia-smi.exe")):
            base = _path(os.environ.get(variable, fallback))
            if base:
                candidates.append(base / suffix)
    try:
        found = shutil.which("nvidia-smi")
    except OSError:
        found = None
    if found and _path(found):
        candidates.append(Path(found))
    executable = next((p for p in candidates if _exists(p)), None)
    if not executable:
        return unknown
    try:
        result = _run_fixed([str(executable), "--query-gpu=name,memory.total,driver_version",
                             "--format=csv,noheader,nounits"], 3)
        if result.returncode or len(result.stdout) > 16384:
            return unknown
        gpus = []
        for row in list(csv.reader(io.StringIO(result.stdout)))[:32]:
            if len(row) != 3 or not _text(row[0]) or not row[1].strip().isdigit():
                return unknown
            memory = int(row[1].strip())
            if not 0 < memory <= 16 * 1024 * 1024:
                return unknown
            gpus.append({"name": _text(row[0]), "memory_total_mb": memory, "driver": _text(row[2], 80)})
        if gpus:
            return {"gpus": gpus, "status": "ok", "detail": "NVIDIA 驱动工具已响应；未验证目标 Python 的 CUDA / torch 可用性"}
    except (OSError, ValueError, subprocess.TimeoutExpired, csv.Error):
        pass
    return unknown


def discover_environment(settings):
    """Discover a small allowlist of local endpoints and existing installations.

    Invalid settings produce unknown checks. Returned checks/notes deliberately
    omit absolute paths and process command lines so they can enter repair text.
    """
    started = time.monotonic()
    settings = settings if isinstance(settings, dict) else {}
    checks, notes, candidates = [], [], []

    def check(identifier, category, name, status, detail, action=None):
        row = {"id": identifier, "category": category, "name": name, "status": status, "detail": detail}
        if action:
            row["action"] = action
        checks.append(row)

    def add_candidate(value, source):
        try:
            url = local_url(value)
        except (TypeError, ValueError):
            return False
        if len(candidates) < MAX_CANDIDATES and not any(item["url"] == url for item in candidates):
            candidates.append({"url": url, "source": source})
        return True

    if not add_candidate(settings.get("backend_url"), "当前设置"):
        check("backend_setting", "backend", "当前后端地址", "unknown", "地址未设置或格式无效；仅探测本机回环 HTTP", "在设置中填写本机 ComfyUI 地址")
    # GPU and process queries can each take three seconds; execute independently.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as system_pool:
        process_future = system_pool.submit(_processes)
        gpu_future = system_pool.submit(_gpu)
        records, process_state = process_future.result()
        hardware = gpu_future.result()
    hints, ports = _process_hints(records)
    for port in ports[:MAX_CANDIDATES]:
        add_candidate(f"http://127.0.0.1:{port}", "ComfyUI 进程端口")
    for port in PORTS:
        add_candidate(f"http://127.0.0.1:{port}", "常见本机端口")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        probed = list(pool.map(_probe, candidates))
    explicit = settings.get("comfy_roots", [])
    if not isinstance(explicit, list):
        explicit = []
    for value in explicit[:12]:
        root = _path(value)
        if _installation_root(root):
            hints.append((root, "用户指定的安装目录", None, None))
    for root in _common_roots() + _registry_roots():
        if _installation_root(root):
            hints.append((root, "常见目录或安装登记", None, None))
    # Prefer process interpreter/config evidence when the same root is also
    # exposed by a desktop host. Paths remain private in the local response.
    unique = {}
    for hint in hints:
        key = _key(hint[0])
        if key not in unique or (hint[2] and not unique[key][2]):
            unique[key] = hint
    installations = [_installation(h) for h in list(unique.values())[:MAX_INSTALLATIONS]]
    online = [item for item in probed if item["online"]]
    check("backend_discovery", "backend", "本地 ComfyUI 服务", "ok" if online else "unknown",
          f"已确认 {len(online)} 个本机服务" if online else "有限端口探测未发现在线服务；不代表 ComfyUI 未安装",
          None if online else "启动已有 ComfyUI，或填写它的实际本机端口后重新检测")
    check("process_discovery", "environment", "运行进程识别", process_state,
          "已只读检查相关应用进程" if process_state == "ok" else "系统进程信息不可获取；安装目录识别可能不完整")
    check("installation_discovery", "environment", "ComfyUI 安装目录", "ok" if installations else "unknown",
          f"发现 {len(installations)} 个符合 main.py 与 comfy 目录结构的安装" if installations else "未在有限位置定位安装目录；没有进行全盘扫描",
          None if installations else "可手动添加已有安装目录，或先启动已有推理程序再检测")
    check("gpu_driver", "hardware", "NVIDIA GPU 与驱动", hardware["status"], hardware["detail"],
          None if hardware["status"] == "ok" else "通过系统设备管理器与显卡官方工具核实硬件和驱动；其他 GPU 仍需后端确认")
    for index, installation in enumerate(installations, 1):
        missing = [p["name"] for p in installation["packages"] if p["status"] == "missing"]
        known = [p for p in installation["packages"] if p["status"] == "ok"]
        check(f"python_{index}", "environment", f"环境 {index} · Python 文件", installation["python"]["status"], installation["python"]["detail"])
        check(f"packages_{index}", "environment", f"环境 {index} · 依赖元数据", "warning" if missing else "ok" if known else "unknown",
              "关联环境未发现以下包的元数据：" + "、".join(missing) + "；不能据此确认包不可导入"
              if missing else f"识别 {len(known)} 项关联包元数据；未导入 torch 或验证 CUDA" if known else "未读取到完整的关联包元数据，不能判断依赖是否缺失",
              "使用该推理环境自己的安装说明核实依赖，不要安装到 FrameWeave 的 Python" if missing else None)
    notes.extend(["只读有限端口、安装目录、包元数据与显卡驱动；没有安装、下载、全盘扫描或执行发现的 Python。",
                  "在线服务、解释器文件、依赖元数据与 GPU 驱动是独立证据，均不能替代一次真实生成。",
                  "复杂模型路径 YAML 与未运行的自定义安装可能无法自动定位；可手动补充模型目录。"])
    return {"candidates": probed, "installations": installations, "hardware": hardware,
            "checks": checks, "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "elapsed_ms": round((time.monotonic() - started) * 1000), "notes": notes}
