#!/usr/bin/env python3
from copy import deepcopy
import getpass
import hashlib
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import requests
import websocket
from runtime_context import browser_choices as runtime_browser_choices
from runtime_context import release_browser_runtime

BASE_URL = "https://cst.uf-tree.com"
LOGIN_URL = f"{BASE_URL}/login"
BILL_TEMPLATE_URL = f"{BASE_URL}/bill/bills"

BROWSERS = [
    {
        "name": "Edge",
        "port": 29523,
        "url": "http://localhost:29523/json",
        "binary": "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "profile_dir": str(Path.home() / ".finance-cst-erp" / "edge-cdp-profile"),
    },
    {
        "name": "Chrome",
        "port": 29580,
        "url": "http://localhost:29580/json",
        "binary": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "profile_dir": str(Path.home() / ".finance-cst-erp" / "chrome-cdp-profile"),
    },
]

STATIC_DEFAULT_BILL_MODELS = {
    "EXPENSE": {
        "businessType": "PRIVATE",
        "icon": "md-pricetag",
        "iconColor": "#4c7cc3",
        "type": "EXPENSE",
        "applyContentType": "FILLINTHESUM",
        "applyRelateFlag": True,
        "applyRelateNecessary": False,
        "requestScope": False,
        "payFlag": True,
        "feeScopeFlag": False,
        "componentJson": [
            {
                "id": 1,
                "name": "title",
                "label": "标题",
                "type": "j-text",
                "disableDel": True,
                "props": {
                    "min": 0,
                    "max": 14,
                    "defaultValue": "",
                    "canEdit": True,
                    "textType": 1,
                    "placeholder": "请输入标题",
                    "title": "标题",
                    "required": True,
                },
            },
            {
                "id": 2,
                "name": "submitter",
                "label": "提交人",
                "type": "j-submitter",
                "disableDel": True,
                "props": {
                    "placeholder": "请选择提交人",
                    "title": "提交人",
                    "defaultValueType": 1,
                    "required": True,
                },
            },
            {
                "id": 3,
                "name": "expenseTime",
                "label": "报销日期",
                "type": "j-date",
                "disableDel": True,
                "props": {
                    "defaultValueType": 1,
                    "placeholder": "请选择报销日期",
                    "canEdit": True,
                    "title": "报销日期",
                    "required": True,
                    "needInputTime": False,
                },
            },
            {
                "name": "shop",
                "id": 20,
                "label": "公司",
                "type": "j-shop",
                "disableDel": True,
                "props": {
                    "canEdit": True,
                    "placeholder": "请选择公司",
                    "defaultValueType": 1,
                    "title": "公司",
                    "required": True,
                },
            },
            {
                "name": "applyDepartment",
                "id": 12,
                "label": "报销部门",
                "type": "j-dept",
                "props": {
                    "scopeType": 1,
                    "defaultValue": 1,
                    "canEdit": True,
                    "placeholder": "请选择报销部门",
                    "defaultValueType": 1,
                    "title": "报销部门",
                    "required": False,
                },
            },
            {
                "name": "describe",
                "id": 32,
                "label": "描述",
                "type": "j-text",
                "props": {
                    "min": 0,
                    "max": 140,
                    "defaultValue": "",
                    "canEdit": True,
                    "textType": 2,
                    "placeholder": "请输入描述信息",
                    "title": "描述",
                    "required": False,
                },
            },
            {
                "id": 4,
                "name": "feeDetails",
                "label": "费用明细",
                "type": "j-fee-details",
                "disableDel": True,
                "props": {
                    "required": True,
                },
            },
            {
                "id": 6,
                "name": "receiveAccount",
                "label": "收款信息",
                "disableDel": True,
                "type": "j-account",
                "props": {
                    "required": True,
                    "title": "收款信息",
                    "placeholder": "请选择收款信息",
                    "defaultValueType": 1,
                },
            },
            {
                "id": 7,
                "name": "linkRequest",
                "label": "关联申请",
                "type": "j-request-bill",
                "disableDel": True,
                "props": {
                    "required": False,
                    "title": "关联申请",
                    "placeholder": "请选择关联申请单",
                    "defaultValueType": 1,
                },
            },
        ],
    },
    "PAYMENT": {
        "businessType": "PRIVATE",
        "icon": "md-pricetag",
        "iconColor": "#4c7cc3",
        "type": "PAYMENT",
        "applyContentType": "FILLINTHESUM",
        "applyRelateFlag": True,
        "applyRelateNecessary": False,
        "requestScope": False,
        "payFlag": True,
        "feeScopeFlag": False,
        "componentJson": [
            {
                "id": 1,
                "name": "title",
                "label": "标题",
                "type": "j-text",
                "disableDel": True,
                "props": {
                    "min": 0,
                    "max": 14,
                    "defaultValue": "",
                    "canEdit": True,
                    "textType": 1,
                    "placeholder": "请输入标题",
                    "title": "标题",
                    "required": True,
                },
            },
            {
                "id": 2,
                "name": "submitter",
                "label": "提交人",
                "type": "j-submitter",
                "disableDel": True,
                "props": {
                    "placeholder": "请选择提交人",
                    "title": "提交人",
                    "defaultValueType": 1,
                    "required": True,
                },
            },
            {
                "name": "shop",
                "id": 20,
                "label": "公司",
                "type": "j-shop",
                "disableDel": True,
                "props": {
                    "canEdit": True,
                    "placeholder": "请选择公司",
                    "defaultValueType": 1,
                    "title": "公司",
                    "required": True,
                },
            },
            {
                "id": 3,
                "name": "expenseTime",
                "label": "付款日期",
                "type": "j-date",
                "disableDel": False,
                "props": {
                    "defaultValueType": 1,
                    "placeholder": "请选择付款日期",
                    "canEdit": True,
                    "title": "付款日期",
                    "required": True,
                    "needInputTime": False,
                },
            },
            {
                "name": "describe",
                "id": 32,
                "label": "描述",
                "type": "j-text",
                "props": {
                    "min": 0,
                    "max": 140,
                    "defaultValue": "",
                    "canEdit": True,
                    "textType": 2,
                    "placeholder": "请输入描述信息",
                    "title": "描述",
                    "required": False,
                },
            },
            {
                "id": 4,
                "name": "feeDetails",
                "label": "费用明细",
                "type": "j-fee-details",
                "disableDel": True,
                "props": {
                    "required": True,
                },
            },
            {
                "id": 71,
                "name": "receiptAccount",
                "label": "收款信息",
                "disableDel": True,
                "type": "j-receipt-account",
                "props": {
                    "required": True,
                    "title": "收款信息",
                    "placeholder": "请上传收款信息",
                },
            },
        ],
    },
    "LOAN": {
        "businessType": "PRIVATE",
        "icon": "ios-paper",
        "iconColor": "#FADB14",
        "type": "LOAN",
        "requestScope": False,
        "payFlag": True,
        "refundDateFlag": True,
        "componentJson": [
            {
                "id": 1,
                "name": "title",
                "label": "标题",
                "type": "j-text",
                "disableDel": True,
                "props": {
                    "min": 0,
                    "max": 14,
                    "defaultValue": "",
                    "canEdit": True,
                    "textType": 1,
                    "placeholder": "请输入标题",
                    "title": "标题",
                    "required": True,
                },
            },
            {
                "id": 2,
                "name": "submitter",
                "label": "提交人",
                "type": "j-submitter",
                "disableDel": True,
                "props": {
                    "placeholder": "请选择提交人",
                    "title": "提交人",
                    "defaultValueType": 1,
                    "required": True,
                },
            },
            {
                "id": 3,
                "name": "expenseTime",
                "label": "借款日期",
                "disableDel": True,
                "type": "j-date",
                "props": {
                    "defaultValueType": 1,
                    "placeholder": "请选择借款日期",
                    "canEdit": True,
                    "title": "借款日期",
                    "required": False,
                    "needInputTime": False,
                },
            },
            {
                "id": 5,
                "name": "expensesAmount",
                "label": "借款金额",
                "type": "j-amount",
                "disableDel": True,
                "props": {
                    "defaultValueType": 1,
                    "title": "借款金额",
                    "placeholder": "请输入借款金额",
                    "required": True,
                    "maxValue": 1000000,
                    "minValue": 0.01,
                    "showRmb": False,
                },
            },
            {
                "id": 6,
                "name": "receiveAccount",
                "label": "收款信息",
                "disableDel": True,
                "type": "j-account",
                "props": {
                    "required": True,
                    "title": "收款信息",
                    "placeholder": "请选择收款信息",
                    "defaultValueType": 1,
                },
            },
            {
                "id": 8,
                "name": "refundDate",
                "label": "还款日期",
                "disableDel": True,
                "type": "j-date",
                "props": {
                    "defaultValueType": 2,
                    "placeholder": "请选择还款日期",
                    "canEdit": True,
                    "title": "还款日期",
                    "required": True,
                    "needInputTime": False,
                },
            },
            {
                "name": "applyDepartment",
                "id": 9,
                "disableDel": True,
                "label": "借款部门",
                "type": "j-dept",
                "props": {
                    "scopeType": 1,
                    "defaultValue": 1,
                    "canEdit": True,
                    "placeholder": "请选择借款部门",
                    "defaultValueType": 1,
                    "title": "借款部门",
                    "required": False,
                },
            },
            {
                "name": "shop",
                "id": 20,
                "label": "公司",
                "type": "j-shop",
                "disableDel": True,
                "props": {
                    "canEdit": True,
                    "placeholder": "请选择公司",
                    "defaultValueType": 1,
                    "title": "公司",
                    "required": True,
                },
            },
            {
                "name": "describe",
                "id": 32,
                "label": "描述",
                "type": "j-text",
                "props": {
                    "min": 0,
                    "max": 140,
                    "defaultValue": "",
                    "canEdit": True,
                    "textType": 2,
                    "placeholder": "请输入描述信息",
                    "title": "描述",
                    "required": False,
                },
            },
            {
                "id": 33,
                "name": "attachment",
                "label": "附件",
                "type": "j-attachment",
                "props": {
                    "title": "附件",
                    "required": False,
                },
            },
        ],
    },
    "REQUISITION": {
        "businessType": "PRIVATE",
        "icon": "md-plane",
        "iconColor": "#FF7A45",
        "type": "REQUISITION",
        "applyContentType": "SUMFEE",
        "feeScopeFlag": False,
        "componentJson": [
            {
                "id": 1,
                "name": "title",
                "label": "标题",
                "type": "j-text",
                "disableDel": True,
                "props": {
                    "min": 0,
                    "max": 14,
                    "defaultValue": "",
                    "canEdit": True,
                    "textType": 1,
                    "placeholder": "请输入标题",
                    "title": "标题",
                    "required": True,
                },
            },
            {
                "id": 2,
                "name": "submitter",
                "label": "提交人",
                "type": "j-submitter",
                "disableDel": True,
                "props": {
                    "placeholder": "请选择提交人",
                    "title": "提交人",
                    "defaultValueType": 1,
                    "required": True,
                },
            },
            {
                "name": "shop",
                "id": 20,
                "label": "公司",
                "type": "j-shop",
                "disableDel": True,
                "props": {
                    "canEdit": True,
                    "placeholder": "请选择公司",
                    "defaultValueType": 1,
                    "title": "公司",
                    "required": True,
                },
            },
            {
                "id": 3,
                "name": "expenseTime",
                "label": "申请日期",
                "type": "j-date",
                "disableDel": True,
                "props": {
                    "defaultValueType": 1,
                    "placeholder": "请选择申请日期",
                    "canEdit": True,
                    "title": "申请日期",
                    "required": True,
                    "needInputTime": False,
                },
            },
            {
                "name": "department",
                "id": 30,
                "label": "费用承担部门",
                "type": "j-dept",
                "props": {
                    "scopeType": 1,
                    "defaultValue": 1,
                    "canEdit": True,
                    "placeholder": "请选择费用承担部门",
                    "defaultValueType": 1,
                    "title": "费用承担部门",
                    "required": False,
                },
            },
            {
                "name": "describe",
                "id": 32,
                "label": "描述",
                "type": "j-text",
                "props": {
                    "min": 0,
                    "max": 140,
                    "defaultValue": "",
                    "canEdit": True,
                    "textType": 2,
                    "placeholder": "请输入描述信息",
                    "title": "描述",
                    "required": False,
                },
            },
            {
                "id": 4,
                "name": "feeDetails",
                "label": "费用明细",
                "type": "j-fee-details",
                "disableDel": True,
                "props": {
                    "required": True,
                },
            },
        ],
    },
}


def is_ok(resp):
    return resp.get("code") == 200 or resp.get("success") is True


def sha1_hex(value):
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def browser_choices(preferred="auto", task_id=None):
    return runtime_browser_choices(preferred=preferred, task_id=task_id)


def list_pages(browser):
    return requests.get(browser["url"], timeout=6).json()


def find_browser(preferred="auto", require_cst=False, task_id=None):
    available = []
    for browser in browser_choices(preferred, task_id=task_id):
        try:
            pages = list_pages(browser)
            has_cst = any("cst.uf-tree.com" in p.get("url", "") for p in pages)
            if not require_cst or has_cst:
                available.append({**browser, "has_cst": has_cst})
        except Exception:
            continue

    if not available:
        return None

    for browser in available:
        if browser.get("has_cst"):
            return browser
    return available[0]


def wait_for_browser(browser, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            list_pages(browser)
            return True
        except Exception:
            time.sleep(1)
    return False


def launch_browser(preferred="auto", target_url=LOGIN_URL, task_id=None):
    for browser in browser_choices(preferred, task_id=task_id):
        binary = Path(browser["binary"])
        if not binary.exists():
            continue

        profile_dir = Path(browser["profile_dir"])
        profile_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(binary),
            f"--remote-debugging-port={browser['port']}",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile_dir}",
            target_url,
        ]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if wait_for_browser(browser):
            return {**browser, "has_cst": True}
    return None


def find_or_launch_browser(preferred="auto", target_url=LOGIN_URL, task_id=None):
    browser = find_browser(preferred=preferred, require_cst=False, task_id=task_id)
    if browser:
        return browser
    return launch_browser(preferred=preferred, target_url=target_url, task_id=task_id)


def open_target(browser, url):
    encoded = quote(url, safe=":/?&=#")
    resp = requests.put(
        f"http://localhost:{browser['port']}/json/new?{encoded}",
        timeout=10,
    )
    return resp.json()


def activate_page(browser, page):
    page_id = (page or {}).get("id")
    if not page_id:
        return False
    try:
        requests.get(
            f"http://localhost:{browser['port']}/json/activate/{page_id}",
            timeout=6,
        )
        return True
    except Exception:
        return False


def close_page(browser, page):
    page_id = (page or {}).get("id")
    if not page_id:
        return False
    try:
        requests.get(
            f"http://localhost:{browser['port']}/json/close/{page_id}",
            timeout=6,
        )
        return True
    except Exception:
        return False


def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", int(port))) == 0


def list_browser_processes(browser):
    patterns = [
        browser["profile_dir"],
        f"--remote-debugging-port={browser['port']}",
    ]
    matches = {}
    result = subprocess.run(
        ["ps", "-axww", "-o", "pid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ps failed for {browser['name']}: {result.stderr.strip()}")
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pid_text, _, cmd = line.partition(" ")
        if not pid_text.isdigit():
            continue
        pid = int(pid_text)
        if pid == os.getpid():
            continue
        if any(pattern in cmd for pattern in patterns):
            matches[pid] = cmd
    return [{"pid": pid, "cmd": cmd} for pid, cmd in sorted(matches.items())]


def format_processes(processes):
    return "; ".join(f"{item['pid']} {item['cmd']}" for item in processes)


def wait_for_browser_exit(browser, timeout):
    deadline = time.time() + timeout
    latest_processes = list_browser_processes(browser)
    latest_port_open = is_port_open(browser["port"])
    clear_checks = 0
    while time.time() < deadline:
        latest_processes = list_browser_processes(browser)
        latest_port_open = is_port_open(browser["port"])
        if not latest_processes and not latest_port_open:
            clear_checks += 1
            if clear_checks >= 2:
                return True, latest_processes, latest_port_open
        else:
            clear_checks = 0
        time.sleep(0.25)
    latest_processes = list_browser_processes(browser)
    latest_port_open = is_port_open(browser["port"])
    return (not latest_processes and not latest_port_open), latest_processes, latest_port_open


def close_browser_instance(browser, timeout=5.0):
    before_processes = list_browser_processes(browser)
    before_port_open = is_port_open(browser["port"])
    if not before_processes and not before_port_open:
        return True, f"ℹ️ {browser['name']} ERP 自动化浏览器本来就是关闭状态"

    for process in before_processes:
        try:
            os.kill(process["pid"], signal.SIGTERM)
        except ProcessLookupError:
            continue

    closed, remaining_processes, remaining_port_open = wait_for_browser_exit(
        browser,
        timeout=min(max(timeout, 0.5), 3.0),
    )
    if not closed:
        for process in remaining_processes:
            try:
                os.kill(process["pid"], signal.SIGKILL)
            except ProcessLookupError:
                continue
        closed, remaining_processes, remaining_port_open = wait_for_browser_exit(browser, max(timeout, 0.5))

    if closed:
        return True, f"✅ 已关闭 {browser['name']} ERP 自动化浏览器"

    details = []
    if remaining_processes:
        details.append(f"残留进程: {format_processes(remaining_processes)}")
    if remaining_port_open:
        details.append(f"CDP端口 {browser['port']} 仍然可访问")
    return False, f"❌ 关闭 {browser['name']} 失败: {' | '.join(details) if details else '未通过关闭校验'}"


def get_cst_page(browser):
    pages = list_pages(browser)
    for page in pages:
        if "cst.uf-tree.com" in page.get("url", ""):
            return page
    return None


def ensure_cst_page(browser, url=LOGIN_URL):
    page = get_cst_page(browser)
    if page:
        activate_page(browser, page)
        return page
    open_target(browser, url)
    deadline = time.time() + 15
    while time.time() < deadline:
        page = get_cst_page(browser)
        if page:
            activate_page(browser, page)
            return page
        time.sleep(1)
    raise RuntimeError(f"{browser['name']} 未能打开财税通页面")


def cdp_eval(page, expression, return_by_value=True, await_promise=False):
    ws = websocket.create_connection(
        page["webSocketDebuggerUrl"],
        timeout=10,
        suppress_origin=True,
    )
    try:
        ws.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": return_by_value,
                        "awaitPromise": await_promise,
                    },
                }
            )
        )
        for _ in range(20):
            msg = json.loads(ws.recv())
            if msg.get("id") != 1:
                continue
            result = msg.get("result", {}).get("result", {})
            return result.get("value") if return_by_value else result
    finally:
        ws.close()
    return None


def get_page_by_url(browser, url_substring):
    pages = list_pages(browser)
    for page in pages:
        if url_substring in page.get("url", ""):
            return page
    return None


def cdp_navigate(page, url):
    ws = websocket.create_connection(
        page["webSocketDebuggerUrl"],
        timeout=10,
        suppress_origin=True,
    )
    try:
        ws.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Page.navigate",
                    "params": {"url": url},
                }
            )
        )
        for _ in range(20):
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                return msg
    finally:
        ws.close()
    return None


def wait_for_bill_template_page(page, timeout=20):
    def _ready():
        raw = cdp_eval(
            page,
            """
            (() => JSON.stringify({
              href: location.href,
              ready: !!(document.querySelector('#app') && document.querySelector('#app').__vue__)
            }))()
            """,
        )
        try:
            info = json.loads(raw or "{}")
        except Exception:
            return None
        if info.get("href", "").endswith("/bill/bills") and info.get("ready"):
            return page
        return None

    ready_page = wait_for(_ready, timeout=timeout, interval=1)
    if not ready_page:
        raise RuntimeError("单据模板页面未就绪")
    return ready_page


def ensure_bill_template_page(browser, reload_page=False):
    page = get_page_by_url(browser, "/bill/bills")
    if not page:
        open_target(browser, BILL_TEMPLATE_URL)
        time.sleep(1)
        page = get_page_by_url(browser, "/bill/bills")
    if not page:
        raise RuntimeError("未能打开单据模板页面")

    activate_page(browser, page)
    if reload_page:
        cdp_navigate(page, BILL_TEMPLATE_URL)

    return wait_for_bill_template_page(page)


def open_fresh_bill_template_page(browser):
    page = open_target(browser, BILL_TEMPLATE_URL)
    if not page:
        raise RuntimeError("未能新建单据模板页面")
    time.sleep(1)
    page["_temporary"] = True
    activate_page(browser, page)
    return wait_for_bill_template_page(page)


def get_static_default_bill_model(bill_type, group_id=0):
    model = deepcopy(STATIC_DEFAULT_BILL_MODELS.get(str(bill_type or "").upper(), {}))
    if model:
        model["groupId"] = int(group_id or 0)
        model["_source"] = "fallback"
    return model


def stabilize_default_bill_model(bill_type, model, group_id=0):
    fallback = get_static_default_bill_model(bill_type, group_id=group_id)
    if not model:
        return fallback

    merged = deepcopy(fallback)
    for key, value in (model or {}).items():
        if value is not None:
            merged[key] = deepcopy(value)

    if not merged.get("componentJson"):
        merged["componentJson"] = deepcopy(fallback.get("componentJson") or [])

    if group_id not in (None, ""):
        merged["groupId"] = int(group_id or 0)

    source = "browser"
    if merged.get("componentJson") == fallback.get("componentJson") and model.get("componentJson") != fallback.get("componentJson"):
        source = "browser+fallback"
    merged["_source"] = source
    return merged


def get_default_bill_model_on_page(page, bill_type, group_id=0):
    raw = cdp_eval(
        page,
        f"""
        (() => {{
          try {{
          function findVm(vm, predicate) {{
            if (!vm) return null;
            if (predicate(vm)) return vm;
            for (const child of (vm.$children || [])) {{
              const found = findVm(child, predicate);
              if (found) return found;
            }}
            return null;
          }}
          const root = document.querySelector('#app') && document.querySelector('#app').__vue__;
          const billsVm = findVm(root, vm => vm.$options && vm.$options.methods && typeof vm.$options.methods.fnClickAddBill === 'function');
          if (!billsVm) return JSON.stringify({{ ok: false, reason: 'billsVm-not-found' }});
          const state = billsVm.$store && billsVm.$store.state && billsVm.$store.state.bills;
          if (!state) return JSON.stringify({{ ok: false, reason: 'bills-state-not-found' }});

          billsVm.bIsEditedBill = false;
          state.bIsEditedBill = false;
          if (typeof billsVm.fnBsnResetBasicForm !== 'function') {{
            billsVm.fnBsnResetBasicForm = () => {{}};
          }}
          if (typeof billsVm.fnBsnResetTab !== 'function') {{
            billsVm.fnBsnResetTab = () => {{}};
          }}
          billsVm.oAddBillForm = {{
            groupId: {int(group_id or 0)},
            type: {json.dumps(bill_type, ensure_ascii=False)}
          }};

          const formRef = billsVm.$refs && billsVm.$refs.comAddBillForm;
          const originalValidate = formRef && formRef.validate;
          if (formRef) {{
            formRef.validate = cb => cb(true);
          }}

          try {{
            billsVm.fnClickAddBill();
          }} finally {{
            if (formRef && originalValidate) {{
              formRef.validate = originalValidate;
            }}
          }}

          const bill = state.bill ? JSON.parse(JSON.stringify(state.bill)) : null;
          billsVm.bIsEditedBill = false;
          state.bIsEditedBill = false;

          if (!bill) return JSON.stringify({{ ok: false, reason: 'bill-not-created' }});
          return JSON.stringify({{ ok: true, bill }});
          }} catch (err) {{
            return JSON.stringify({{
              ok: false,
              reason: 'exception',
              message: String(err),
              stack: err && err.stack ? String(err.stack) : null
            }});
          }}
        }})()
        """,
    )
    info = json.loads(raw or "{}")
    if not info.get("ok"):
        raise RuntimeError(f"读取默认单据模型失败：{info}")
    return info.get("bill") or {}


def get_default_bill_model(bill_type, preferred_browser="auto", group_id=0, fresh_page=False, task_id=None):
    browser = find_browser(preferred=preferred_browser, require_cst=True, task_id=task_id)
    if not browser:
        fallback = get_static_default_bill_model(bill_type, group_id=group_id)
        if fallback:
            return fallback
        raise RuntimeError("未找到已登录的财税通浏览器页面，无法读取默认单据模型")

    errors = []
    tried_existing = False
    for use_fresh in ([True, False] if fresh_page else [False, True]):
        if not use_fresh and tried_existing:
            continue
        page = None
        try:
            page = open_fresh_bill_template_page(browser) if use_fresh else ensure_bill_template_page(browser, reload_page=False)
            tried_existing = tried_existing or not use_fresh
            model = get_default_bill_model_on_page(page, bill_type=bill_type, group_id=group_id)
            return stabilize_default_bill_model(bill_type, model, group_id=group_id)
        except Exception as exc:
            errors.append({"fresh_page": use_fresh, "message": str(exc)})
        finally:
            if use_fresh and page:
                close_page(browser, page)

    fallback = get_static_default_bill_model(bill_type, group_id=group_id)
    if fallback:
        fallback["_errors"] = errors
        return fallback
    raise RuntimeError(f"读取默认单据模型失败：{errors}")


def get_vuex_raw(page):
    return cdp_eval(page, "localStorage.getItem('vuex')")


def parse_vuex(raw_value):
    if not raw_value:
        return {}
    try:
        return json.loads(raw_value)
    except Exception:
        return {}


def extract_auth(page):
    data = parse_vuex(get_vuex_raw(page))
    user = data.get("user", {})
    token = user.get("token")
    company = user.get("company") or {}
    company_id = company.get("id")
    user_id = user.get("id")
    return token, company_id, user_id, data


def validate_auth(token, company_id):
    if not token or not company_id:
        return False
    headers = {"x-token": token, "Content-Type": "application/json"}
    try:
        resp = requests.post(
            f"{BASE_URL}/api/member/department/queryCompany",
            headers=headers,
            json={"companyId": company_id},
            timeout=12,
        ).json()
        return is_ok(resp)
    except Exception:
        return False


def normalize_company_id(company_id):
    if company_id in (None, "", 0):
        return None
    return int(company_id)


def normalize_company_name(company_name):
    if company_name in (None, ""):
        return None
    return "".join(str(company_name).split()).strip() or None


def read_credentials(username=None, password=None, company_id=None, prompt=False):
    username = username or os.getenv("CST_USERNAME")
    password = password or os.getenv("CST_PASSWORD")
    company_id = company_id or os.getenv("CST_COMPANY_ID")
    if company_id not in (None, "", 0):
        company_id = int(company_id)

    if prompt and not username:
        username = input("财税通手机号: ").strip()
    if prompt and not password:
        password = getpass.getpass("财税通密码: ").strip()
    return username, password, company_id


def wait_for(condition, timeout=20, interval=1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(interval)
    return None


def wait_for_login_form(page, timeout=20):
    def _ready():
        state = cdp_eval(
            page,
            """
            JSON.stringify({
              url: location.href,
              ready: [...document.querySelectorAll('input')].some(i => (i.placeholder || '').includes('手机号'))
                && [...document.querySelectorAll('input')].some(i => (i.placeholder || '').includes('密码'))
                && [...document.querySelectorAll('button')].some(b => (b.innerText || '').includes('登录'))
            })
            """,
        )
        try:
            info = json.loads(state or "{}")
        except Exception:
            return None
        return info if info.get("ready") else None

    return wait_for(_ready, timeout=timeout, interval=1)


def force_login_page(page):
    return cdp_eval(
        page,
        f"""
        (() => {{
          try {{
            localStorage.removeItem('vuex');
            sessionStorage.clear();
          }} catch (e) {{}}
          location.replace({json.dumps(LOGIN_URL)});
          return true;
        }})()
        """,
    )


def submit_login(page, username, password):
    payload = {
        "username": username,
        "password": password,
    }
    script = f"""
    (() => {{
      function setNativeValue(el, value) {{
        const proto = Object.getPrototypeOf(el);
        const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
        if (descriptor && descriptor.set) {{
          descriptor.set.call(el, value);
        }} else {{
          el.value = value;
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
      }}

      const payload = {json.dumps(payload, ensure_ascii=False)};
      const pwdTab = [...document.querySelectorAll('.el-tabs__item')]
        .find(el => (el.innerText || '').includes('密码'));
      if (pwdTab && !pwdTab.classList.contains('is-active')) {{
        pwdTab.click();
      }}
      const usernameInput = [...document.querySelectorAll('input')]
        .find(i => (i.placeholder || '').includes('手机号'));
      const passwordInput = [...document.querySelectorAll('input')]
        .find(i => (i.placeholder || '').includes('密码'));
      const button = [...document.querySelectorAll('button')]
        .find(b => (b.innerText || '').includes('登录'));
      if (!usernameInput || !passwordInput || !button) {{
        return JSON.stringify({{ ok: false, reason: 'login-form-not-found' }});
      }}
      setNativeValue(usernameInput, payload.username);
      setNativeValue(passwordInput, payload.password);
      button.click();
      return JSON.stringify({{ ok: true }});
    }})()
    """
    result = cdp_eval(page, script)
    return json.loads(result or "{}")


def query_user_companies(token):
    headers = {"x-token": token, "Content-Type": "application/json"}
    resp = requests.post(
        f"{BASE_URL}/api/member/userCompanyInfo/queryUserCompany",
        headers=headers,
        json={},
        timeout=12,
    ).json()
    if not is_ok(resp):
        return []
    return resp.get("result") or []


def choose_company(companies, desired_company_id=None, desired_company_name=None):
    desired_company_id = normalize_company_id(desired_company_id)
    desired_company_name = normalize_company_name(desired_company_name)
    if desired_company_id:
        for company in companies:
            if int(company.get("id")) == desired_company_id:
                return company
        raise RuntimeError(f"未在企业列表中找到 companyId={desired_company_id}")
    if desired_company_name:
        exact_matches = []
        fuzzy_matches = []
        for company in companies:
            names = [
                normalize_company_name(company.get("name")),
                normalize_company_name(company.get("shortName")),
            ]
            names = [name for name in names if name]
            if desired_company_name in names:
                exact_matches.append(company)
                continue
            if any(
                desired_company_name in name or name in desired_company_name
                for name in names
            ):
                fuzzy_matches.append(company)
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            raise RuntimeError(f"企业名称 {desired_company_name} 匹配到多个企业，请改用 company-id")
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0]
        if len(fuzzy_matches) > 1:
            raise RuntimeError(f"企业名称 {desired_company_name} 模糊匹配到多个企业，请改用 company-id")
        raise RuntimeError(f"未在企业列表中找到名称匹配 {desired_company_name} 的企业")
    if len(companies) == 1:
        return companies[0]
    raise RuntimeError("检测到多个企业，请通过 --company-id、CST_COMPANY_ID，或提供集团名称/公司名称 指定导入企业")


def click_company_entry(page, company_name):
    script = f"""
    (() => {{
      const targetName = {json.dumps(company_name, ensure_ascii=False)};
      const companyCard = [...document.querySelectorAll('.comp')]
        .find(card => (card.innerText || '').includes(targetName));
      if (!companyCard) {{
        return JSON.stringify({{ ok: false, reason: 'company-card-not-found' }});
      }}
      const button = [...companyCard.querySelectorAll('button')]
        .find(btn => (btn.innerText || '').includes('进入企业'));
      if (!button) {{
        return JSON.stringify({{ ok: false, reason: 'enter-button-not-found' }});
      }}
      button.click();
      return JSON.stringify({{ ok: true }});
    }})()
    """
    result = cdp_eval(page, script)
    return json.loads(result or "{}")


def force_company_picker_page(page):
    return cdp_eval(
        page,
        f"""
        (() => {{
          try {{
            const raw = JSON.parse(localStorage.getItem('vuex') || '{{}}');
            if (raw.user) {{
              raw.user.company = {{}};
            }}
            localStorage.setItem('vuex', JSON.stringify(raw));
          }} catch (e) {{}}
          location.replace({json.dumps(LOGIN_URL)});
          return true;
        }})()
        """,
    )


def wait_for_company_picker(page, timeout=20):
    def _ready():
        raw = cdp_eval(
            page,
            """
            (() => {
              const hasCompanyCards = [...document.querySelectorAll('.comp button')]
                .some(btn => (btn.innerText || '').includes('进入企业'));
              const vuex = JSON.parse(localStorage.getItem('vuex') || '{}');
              const token = (((vuex || {}).user || {}).token) || null;
              const companyId = ((((vuex || {}).user || {}).company || {}).id) || null;
              return JSON.stringify({
                href: location.href,
                hasCompanyCards,
                token: !!token,
                companyId
              });
            })()
            """,
        )
        try:
            info = json.loads(raw or "{}")
        except Exception:
            return None
        if info.get("hasCompanyCards"):
            return info
        if info.get("token") and not info.get("companyId"):
            return info
        return None

    return wait_for(_ready, timeout=timeout, interval=1)


def ensure_company_selected(page, desired_company_id=None, desired_company_name=None):
    token, current_company_id, _, data = extract_auth(page)
    current_company = ((data or {}).get("user") or {}).get("company") or {}
    companies = query_user_companies(token)
    company = choose_company(
        companies,
        desired_company_id=desired_company_id,
        desired_company_name=desired_company_name,
    )
    if current_company_id and int(current_company_id) == int(company["id"]):
        return token, current_company_id
    if current_company_id:
        force_company_picker_page(page)
        if not wait_for_company_picker(page, timeout=20):
            raise RuntimeError(
                f"已登录企业 {current_company.get('name') or current_company_id} 与目标企业 {company.get('name')} 不一致，且未能进入企业选择页"
            )
    click = click_company_entry(page, company["name"])
    if not click.get("ok"):
        raise RuntimeError(f"进入企业失败：{click}")

    def _selected():
        token2, company_id2, _, _ = extract_auth(page)
        if token2 and company_id2 and int(company_id2) == int(company["id"]):
            return token2, int(company_id2)
        return None

    selected = wait_for(_selected, timeout=20, interval=1)
    if not selected:
        raise RuntimeError("企业选择后未能读取到有效 companyId")
    return selected


def ui_save_bill_template_on_page(page, doc_name):
    def _tree_ready():
        raw = cdp_eval(
            page,
            """
            (() => {
              function findVm(vm, predicate) {
                if (!vm) return null;
                if (predicate(vm)) return vm;
                for (const child of (vm.$children || [])) {
                  const found = findVm(child, predicate);
                  if (found) return found;
                }
                return null;
              }
              const root = document.querySelector('#app') && document.querySelector('#app').__vue__;
              const billsVm = findVm(root, vm => vm.$options && vm.$options.methods && typeof vm.$options.methods.fnClickBillItem === 'function');
              const tree = billsVm && billsVm.$store && billsVm.$store.state && billsVm.$store.state.bills
                ? (billsVm.$store.state.bills.tmplTreeData || [])
                : [];
              return JSON.stringify({ ready: tree.length > 0, count: tree.length });
            })()
            """,
        )
        try:
            info = json.loads(raw or "{}")
        except Exception:
            return None
        return info if info.get("ready") else None

    if not wait_for(_tree_ready, timeout=20, interval=1):
        raise RuntimeError("单据模板树未加载完成")

    open_result = cdp_eval(
        page,
        f"""
        (() => {{
          function findVm(vm, predicate) {{
            if (!vm) return null;
            if (predicate(vm)) return vm;
            for (const child of (vm.$children || [])) {{
              const found = findVm(child, predicate);
              if (found) return found;
            }}
            return null;
          }}
          function findItem(nodes, name) {{
            for (const node of (nodes || [])) {{
              const nodeName = node.name || node.title || '';
              if (nodeName === name) return node;
              const found = findItem(node.children || [], name);
              if (found) return found;
            }}
            return null;
          }}
          const targetName = {json.dumps(doc_name, ensure_ascii=False)};
          const root = document.querySelector('#app') && document.querySelector('#app').__vue__;
          if (!root) return JSON.stringify({{ ok: false, reason: 'vue-root-not-found' }});
          const billsVm = findVm(root, vm => vm.$options && vm.$options.methods && typeof vm.$options.methods.fnClickBillItem === 'function');
          if (!billsVm || !billsVm.$store) return JSON.stringify({{ ok: false, reason: 'bills-component-not-found' }});
          const tree = (((billsVm.$store || {{}}).state || {{}}).bills || {{}}).tmplTreeData || [];
          const item = findItem(tree, targetName);
          if (!item) return JSON.stringify({{ ok: false, reason: 'template-not-found' }});
          billsVm.fnClickBillItem(item, true);
          return JSON.stringify({{ ok: true, id: item.id, name: item.name || item.title }});
        }})()
        """,
    )
    open_info = json.loads(open_result or "{}")
    if not open_info.get("ok"):
        raise RuntimeError(f"打开模板失败：{open_info}")

    template_id = open_info.get("id")
    template_name = open_info.get("name")

    def _opened():
        raw = cdp_eval(
            page,
            """
            (() => {
              function findVm(vm, predicate) {
                if (!vm) return null;
                if (predicate(vm)) return vm;
                for (const child of (vm.$children || [])) {
                  const found = findVm(child, predicate);
                  if (found) return found;
                }
                return null;
              }
              const root = document.querySelector('#app') && document.querySelector('#app').__vue__;
              const billsVm = findVm(root, vm => vm.$options && vm.$options.methods && typeof vm.$options.methods.fnClickBillItem === 'function');
              const store = billsVm && billsVm.$store;
              const bill = store && store.state && store.state.bills ? store.state.bills.bill : null;
              return JSON.stringify({
                id: bill ? bill.id : null,
                name: bill ? bill.name : null
              });
            })()
            """,
        )
        try:
            info = json.loads(raw or "{}")
        except Exception:
            return None
        if info.get("id") == template_id and info.get("name") == template_name:
            return info
        return None

    if not wait_for(_opened, timeout=20, interval=1):
        raise RuntimeError(f"模板打开后未加载完成：{doc_name}")

    save_result = cdp_eval(
        page,
        """
        (async () => {
          function findVm(vm, predicate) {
            if (!vm) return null;
            if (predicate(vm)) return vm;
            for (const child of (vm.$children || [])) {
              const found = findVm(child, predicate);
              if (found) return found;
            }
            return null;
          }
          const root = document.querySelector('#app') && document.querySelector('#app').__vue__;
          if (!root) return JSON.stringify({ ok: false, reason: 'vue-root-not-found' });
          const ctrlVm = findVm(root, vm => vm.$options && vm.$options.methods
            && typeof vm.$options.methods.fnBsnAddTmpl === 'function'
            && typeof vm.$options.methods.fnNetUBill === 'function');
          if (!ctrlVm) return JSON.stringify({ ok: false, reason: 'save-control-not-found' });
          await ctrlVm.fnBsnAddTmpl('ACTIVE');
          return JSON.stringify({ ok: true });
        })()
        """,
        await_promise=True,
    )
    save_info = json.loads(save_result or "{}")
    if not save_info.get("ok"):
        raise RuntimeError(f"执行页面保存失败：{save_info}")

    def _message():
        raw = cdp_eval(
            page,
            """
            (() => JSON.stringify(
              [...document.querySelectorAll('.el-message, .ivu-message')]
                .map(el => ({
                  text: (el.innerText || el.textContent || '').trim(),
                  cls: el.className || ''
                }))
            ))()
            """,
        )
        try:
            messages = json.loads(raw or "[]")
        except Exception:
            return None
        for message in messages:
            text = message.get("text", "")
            if "成功" in text:
                return {"ok": True, "message": text}
            if "失败" in text or "错误" in text:
                return {"ok": False, "message": text}
        return None

    result = wait_for(_message, timeout=8, interval=0.5)
    if result is None:
        return {
            "ok": True,
            "templateId": template_id,
            "templateName": template_name,
            "message": "页面已触发保存",
        }
    if not result.get("ok"):
        raise RuntimeError(f"页面保存提示失败：{result.get('message')}")
    return {
        "ok": True,
        "templateId": template_id,
        "templateName": template_name,
        "message": result.get("message"),
    }


def ui_save_bill_template(doc_name, preferred_browser="auto", reload_page=False, task_id=None):
    browser = find_browser(preferred=preferred_browser, require_cst=True, task_id=task_id)
    if not browser:
        raise RuntimeError("未找到已登录的财税通浏览器页面，无法执行页面保存")
    page = ensure_bill_template_page(browser, reload_page=reload_page)
    return ui_save_bill_template_on_page(page, doc_name)


def ensure_login(
    preferred_browser="auto",
    username=None,
    password=None,
    company_id=None,
    company_name=None,
    force_relogin=False,
    task_id=None,
    prompt=False,
):
    browser = find_or_launch_browser(preferred=preferred_browser, target_url=LOGIN_URL, task_id=task_id)
    if not browser:
        raise RuntimeError("未能自动打开 Edge/Chrome，请确认本机已安装浏览器")

    page = ensure_cst_page(browser, url=LOGIN_URL)
    token, selected_company_id, user_id, _ = extract_auth(page)
    if validate_auth(token, selected_company_id) and not force_relogin:
        if selected_company_id and (company_id or company_name):
            token, selected_company_id = ensure_company_selected(
                page,
                desired_company_id=company_id,
                desired_company_name=company_name,
            )
        return token, selected_company_id, user_id, browser["name"]

    username, password, company_id = read_credentials(
        username=username,
        password=password,
        company_id=company_id,
        prompt=prompt,
    )
    if not username or not password:
        raise RuntimeError(
            "当前登录态失效，且未提供账号密码。可加 --auto-login，并通过 --username + 终端隐藏输入，或设置 CST_USERNAME/CST_PASSWORD。"
        )

    force_login_page(page)
    if not wait_for_login_form(page, timeout=20):
        raise RuntimeError("登录页未就绪，无法自动填写账号密码")

    submit = submit_login(page, username=username, password=password)
    if not submit.get("ok"):
        raise RuntimeError(f"自动提交登录失败：{submit}")

    def _login_ready():
        token2, company_id2, user_id2, _ = extract_auth(page)
        if token2:
            return token2, company_id2, user_id2
        return None

    logged_in = wait_for(_login_ready, timeout=20, interval=1)
    if not logged_in:
        raise RuntimeError("自动登录后未能读取到 token，请检查账号密码是否正确")

    token, selected_company_id, user_id = logged_in
    if company_id or company_name or not selected_company_id:
        token, selected_company_id = ensure_company_selected(
            page,
            desired_company_id=company_id,
            desired_company_name=company_name,
        )

    if not validate_auth(token, selected_company_id):
        raise RuntimeError("自动登录完成，但登录态校验未通过")

    return token, selected_company_id, user_id, browser["name"]


def get_auth(
    auto_login=False,
    preferred_browser="auto",
    username=None,
    password=None,
    company_id=None,
    company_name=None,
    force_relogin=False,
    task_id=None,
    prompt=False,
):
    browser = find_or_launch_browser(preferred=preferred_browser, target_url=LOGIN_URL, task_id=task_id)
    if not browser:
        raise RuntimeError(
            "未检测到可用的浏览器。请安装 Edge 或 Chrome，或使用 --auto-login 让脚本自动打开浏览器。"
        )

    page = ensure_cst_page(browser, url=LOGIN_URL)
    token, selected_company_id, user_id, _ = extract_auth(page)
    if validate_auth(token, selected_company_id) and not force_relogin:
        if selected_company_id and (company_id or company_name):
            token, selected_company_id = ensure_company_selected(
                page,
                desired_company_id=company_id,
                desired_company_name=company_name,
            )
        return token, selected_company_id, user_id, browser["name"]

    if not auto_login:
        raise RuntimeError(
            "浏览器中的财税通登录态已失效。请重新登录，或使用 --auto-login 让脚本自动登录。"
        )

    return ensure_login(
        preferred_browser=preferred_browser,
        username=username,
        password=password,
        company_id=company_id,
        company_name=company_name,
        force_relogin=force_relogin,
        task_id=task_id,
        prompt=prompt,
    )
