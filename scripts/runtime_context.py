#!/usr/bin/env python3
import contextlib
import fcntl
import hashlib
import json
import re
import socket
import time
from pathlib import Path

RUNTIME_ROOT = Path.home() / ".finance-cst-erp-concurrent"
TASK_ROOT = RUNTIME_ROOT / "tasks"
LOCK_PATH = RUNTIME_ROOT / ".browser-runtime.lock"
REGISTRY_PATH = RUNTIME_ROOT / "browser-runtimes.json"

BASE_BROWSERS = [
    {
        "id": "edge",
        "name": "Edge",
        "binary": "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "legacy_port": 29523,
        "legacy_profile_dir": str(Path.home() / ".finance-cst-erp" / "edge-cdp-profile"),
        "port_range": (30523, 30722),
    },
    {
        "id": "chrome",
        "name": "Chrome",
        "binary": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "legacy_port": 29580,
        "legacy_profile_dir": str(Path.home() / ".finance-cst-erp" / "chrome-cdp-profile"),
        "port_range": (30800, 30999),
    },
]


def normalize_task_id(task_id):
    if task_id in (None, ""):
        return None
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(task_id).strip())
    cleaned = cleaned.strip("-.")[:80]
    return cleaned or None


def base_browser_choices(preferred="auto"):
    preferred = (preferred or "auto").lower()
    if preferred == "edge":
        return [browser for browser in BASE_BROWSERS if browser["id"] == "edge"]
    if preferred == "chrome":
        return [browser for browser in BASE_BROWSERS if browser["id"] == "chrome"]
    return list(BASE_BROWSERS)


def browser_choices(preferred="auto", task_id=None, create=True):
    normalized_task_id = normalize_task_id(task_id)
    if not normalized_task_id:
        return [legacy_browser(browser) for browser in base_browser_choices(preferred)]
    if not create:
        return list_registered_runtimes(preferred=preferred, task_id=normalized_task_id)
    return [get_or_allocate_runtime(browser["id"], normalized_task_id) for browser in base_browser_choices(preferred)]


def legacy_browser(base_browser):
    return {
        "id": base_browser["id"],
        "name": base_browser["name"],
        "binary": base_browser["binary"],
        "port": base_browser["legacy_port"],
        "url": f"http://localhost:{base_browser['legacy_port']}/json",
        "profile_dir": base_browser["legacy_profile_dir"],
        "task_id": None,
        "runtime_root": str(Path(base_browser["legacy_profile_dir"]).parent),
    }


def get_or_allocate_runtime(browser_id, task_id):
    normalized_task_id = normalize_task_id(task_id)
    if not normalized_task_id:
        raise ValueError("task_id 不能为空")
    base_browser = get_base_browser(browser_id)
    with locked_registry() as registry:
        task_entry = registry.setdefault(normalized_task_id, {})
        runtime = task_entry.get(browser_id)
        if runtime:
            return build_runtime_browser(base_browser, normalized_task_id, runtime["port"])

        port = allocate_port(registry, base_browser, normalized_task_id)
        task_entry[browser_id] = {"port": port, "allocatedAt": int(time.time())}
        return build_runtime_browser(base_browser, normalized_task_id, port)


def list_registered_runtimes(preferred="auto", task_id=None):
    normalized_task_id = normalize_task_id(task_id)
    if not normalized_task_id:
        return []

    registry = read_registry()
    task_entry = registry.get(normalized_task_id) or {}
    runtimes = []
    for browser in base_browser_choices(preferred):
        runtime = task_entry.get(browser["id"])
        if runtime:
            runtimes.append(build_runtime_browser(browser, normalized_task_id, runtime["port"]))
    return runtimes


def release_browser_runtime(task_id, browser_id=None):
    normalized_task_id = normalize_task_id(task_id)
    if not normalized_task_id:
        return

    with locked_registry() as registry:
        task_entry = registry.get(normalized_task_id)
        if not task_entry:
            return
        if browser_id:
            task_entry.pop(browser_id, None)
        else:
            registry.pop(normalized_task_id, None)
            return
        if not task_entry:
            registry.pop(normalized_task_id, None)


def task_runtime_dir(task_id):
    normalized_task_id = normalize_task_id(task_id)
    if not normalized_task_id:
        raise ValueError("task_id 不能为空")
    return TASK_ROOT / normalized_task_id


def build_runtime_browser(base_browser, task_id, port):
    runtime_dir = task_runtime_dir(task_id)
    profile_dir = runtime_dir / f"{base_browser['id']}-profile"
    return {
        "id": base_browser["id"],
        "name": base_browser["name"],
        "binary": base_browser["binary"],
        "port": port,
        "url": f"http://localhost:{port}/json",
        "profile_dir": str(profile_dir),
        "task_id": normalize_task_id(task_id),
        "runtime_root": str(runtime_dir),
    }


def get_base_browser(browser_id):
    for browser in BASE_BROWSERS:
        if browser["id"] == browser_id:
            return browser
    raise KeyError(f"未知浏览器: {browser_id}")


def allocate_port(registry, base_browser, task_id):
    start_port, end_port = base_browser["port_range"]
    size = end_port - start_port + 1
    digest = hashlib.sha1(f"{base_browser['id']}:{task_id}".encode("utf-8")).hexdigest()
    offset = int(digest, 16) % size
    used_ports = {
        info.get("port")
        for task_entry in registry.values()
        for info in task_entry.values()
        if isinstance(info, dict) and info.get("port")
    }
    for step in range(size):
        port = start_port + ((offset + step) % size)
        if port in used_ports:
            continue
        if is_port_open(port):
            continue
        return port
    raise RuntimeError(f"{base_browser['name']} 端口池已用尽，无法为任务 {task_id} 分配独立实例")


def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", int(port))) == 0


@contextlib.contextmanager
def locked_registry():
    ensure_runtime_dirs()
    with LOCK_PATH.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        registry = read_registry()
        try:
            yield registry
        finally:
            write_registry(registry)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def ensure_runtime_dirs():
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    TASK_ROOT.mkdir(parents=True, exist_ok=True)


def read_registry():
    if not REGISTRY_PATH.exists():
        return {}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_registry(registry):
    ensure_runtime_dirs()
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
