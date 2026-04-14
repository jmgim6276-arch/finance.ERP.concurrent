#!/usr/bin/env python3

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path


def resolve_browser_session_dir():
    candidates = [
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parent / "scripts",
        Path("/Users/mac/Documents/Playground/agent2-import-run/agent2.2-caishui-fymb-czai-agent2.2-fyong-czai/scripts"),
    ]
    env_path = Path(sys.argv[0]).resolve().parent if sys.argv and sys.argv[0] else None
    if env_path is not None:
        candidates.insert(0, env_path)
    for candidate in candidates:
        if (candidate / "browser_session.py").exists():
            return candidate
    raise RuntimeError("找不到 browser_session.py。请把它放到脚本同目录，或放到 scripts/ 子目录。")


SCRIPT_DIR = resolve_browser_session_dir()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from browser_session import (  # noqa: E402
    cdp_eval,
    close_browser_instance,
    ensure_cst_page,
    extract_auth,
    find_browser,
    find_or_launch_browser,
    get_auth,
    normalize_company_name,
)
from runtime_context import normalize_task_id  # noqa: E402
from runtime_context import release_browser_runtime  # noqa: E402


BASE_URL = "https://cst.uf-tree.com"


def normalize_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).strip()


def unique_index(items, key_fn):
    buckets = defaultdict(list)
    for item in items:
        key = key_fn(item)
        if key:
            buckets[key].append(item)
    return {key: values[0] for key, values in buckets.items() if len(values) == 1}


def choose_parallel_exact_candidate(short_value, full_value, master_index):
    short_key = normalize_text(short_value)
    full_key = normalize_text(full_value)
    short_candidate = master_index.get(short_key) if short_key else None
    full_candidate = master_index.get(full_key) if full_key else None

    if short_candidate and full_candidate and short_candidate["id"] != full_candidate["id"]:
        return None, "ambiguous"
    if full_candidate:
        return full_candidate, "full_exact"
    if short_candidate:
        return short_candidate, "name_exact"
    return None, "no_match"


class CSTBrowserRunner:
    def __init__(
        self,
        browser_name="edge",
        settle_seconds=5,
        auto_login=False,
        username=None,
        password=None,
        company_id=None,
        company_name=None,
        erp_accounting_id=None,
        force_relogin=False,
        task_id=None,
        prompt_credentials=False,
    ):
        effective_force_relogin = bool(
            force_relogin or (auto_login and (username or password or company_id or company_name))
        )
        get_auth(
            auto_login=auto_login,
            preferred_browser=browser_name,
            username=username,
            password=password,
            company_id=company_id,
            company_name=company_name,
            force_relogin=effective_force_relogin,
            task_id=task_id,
            prompt=prompt_credentials,
        )
        self.browser = find_or_launch_browser(preferred=browser_name, target_url=f"{BASE_URL}/index", task_id=task_id)
        if not self.browser:
            raise RuntimeError("未找到可用浏览器。")
        self.page = ensure_cst_page(self.browser, url=f"{BASE_URL}/index")
        self.settle_seconds = settle_seconds
        self.erp_accounting_id = erp_accounting_id
        self.task_id = normalize_task_id(task_id)
        self.requested_company_id = company_id
        self.requested_company_name = company_name
        self.login_account = username
        self.current_company = {}
        self.current_user = {}
        self.current_accounting = None
        self.ensure_home_ready()
        self.refresh_auth_context()
        self.assert_company_context()

    def refresh_auth_context(self):
        _, _, _, data = extract_auth(self.page)
        user = (data or {}).get("user") or {}
        self.current_user = user
        self.current_company = user.get("company") or {}
        if not self.login_account:
            self.login_account = user.get("mobile") or user.get("phone") or user.get("username")
        return self.current_company

    def assert_company_context(self):
        self.refresh_auth_context()
        actual_company = self.current_company or {}
        actual_company_id = actual_company.get("id")
        actual_names = {
            normalize_company_name(actual_company.get("name")),
            normalize_company_name(actual_company.get("shortName")),
        }
        actual_names = {name for name in actual_names if name}

        if self.requested_company_id not in (None, "", 0):
            if int(actual_company_id or 0) != int(self.requested_company_id):
                raise RuntimeError(
                    f"实际登录企业ID={actual_company_id}，与要求的 company-id={self.requested_company_id} 不一致"
                )

        if self.requested_company_name:
            requested = normalize_company_name(self.requested_company_name)
            if requested and actual_names and requested not in actual_names:
                if not any(requested in name or name in requested for name in actual_names):
                    raise RuntimeError(
                        f"实际登录企业为 {actual_company.get('name') or actual_company_id}，与要求的公司 {self.requested_company_name} 不一致"
                    )

    def ensure_home_ready(self):
        target_url = f"{BASE_URL}/index"
        self.eval(
            f"""
(() => {{
  if (location.href !== {json.dumps(target_url)}) {{
    location.href = {json.dumps(target_url)};
  }}
  return 'ok';
}})()
"""
        )
        deadline = time.time() + 30
        last_state = None
        while time.time() < deadline:
            last_state = self.eval(
                """
(() => {
  const root = document.querySelector('#app');
  const vue = root && root.__vue__;
  return {
    href: location.href,
    title: document.title,
    readyState: document.readyState,
    hasVueRoot: !!vue,
    hasRouter: !!(vue && vue.$router),
    bodyTextLength: ((document.body && document.body.innerText) || '').trim().length
  };
})()
"""
            )
            if (
                isinstance(last_state, dict)
                and "/index" in str(last_state.get("href", ""))
                and last_state.get("readyState") == "complete"
                and last_state.get("hasRouter")
            ):
                time.sleep(self.settle_seconds)
                return
            time.sleep(0.5)
        raise RuntimeError(f"财税通首页未就绪: {json.dumps(last_state, ensure_ascii=False)}")

    def navigate(self, route_name):
        accounting = self.ensure_erp_archive_context()
        route_url = f"{BASE_URL}/erp/erpArchiveSetting?name={route_name}"
        route_result = self.eval(
            f"""
(() => {{
  const path = '/erp/erpArchiveSetting';
  const queryName = {json.dumps(route_name)};
  const params = {{ accountingId: {json.dumps((accounting or {}).get("id"))} }};
  const target = path + '?name=' + encodeURIComponent(queryName);
  const nodes = Array.from(document.querySelectorAll('*'));
  for (const el of nodes) {{
    const vm = el && el.__vue__;
    if (vm && vm.$router && typeof vm.$router.push === 'function') {{
      vm.$router.push({{ name: 'erp-archive-setting', params, query: {{ name: queryName }} }}).catch(() => {{}});
      return {{ ok: true, mode: 'router', href: location.href, target }};
    }}
  }}
  location.href = {json.dumps(route_url)};
  return {{ ok: true, mode: 'href', href: location.href, target }};
}})()
"""
        )
        deadline = time.time() + 30
        last_state = route_result
        while time.time() < deadline:
            last_state = self.eval(
                """
(() => ({
  href: location.href,
  title: document.title,
  readyState: document.readyState,
  bodyTextLength: ((document.body && document.body.innerText) || '').trim().length
}))()
"""
            )
            if f"name={route_name}" in str((last_state or {}).get("href", "")):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"ERP 页面跳转失败: {json.dumps(last_state, ensure_ascii=False)}")
        self.activate_archive_menu(route_name)
        time.sleep(self.settle_seconds)

    def activate_archive_menu(self, route_name):
        result = self.eval(
            f"""
(() => {{
  const root = document.querySelector('#app');
  const vue = root && root.__vue__;
  function find(vm, seen = new Set()) {{
    if (!vm || seen.has(vm)) return null;
    seen.add(vm);
    const methods = (vm.$options && vm.$options.methods) || {{}};
    if ((vm.$options && vm.$options.name) === 'erp-settings' && typeof methods.fnClickMenuItem === 'function') {{
      return vm;
    }}
    for (const child of (vm.$children || [])) {{
      const found = find(child, seen);
      if (found) return found;
    }}
    return null;
  }}
  const vm = find(vue);
  if (!vm) {{
    return {{ ok: false, reason: 'erp-settings-not-found', href: location.href }};
  }}
  vm.fnClickMenuItem({json.dumps(route_name)});
  return {{
    ok: true,
    currentItem: vm.currentItem,
    href: location.href
  }};
}})()
"""
        )
        if not isinstance(result, dict) or not result.get("ok"):
            raise RuntimeError(f"切换ERP档案菜单失败: {json.dumps(result, ensure_ascii=False)}")
        deadline = time.time() + 20
        last_state = result
        while time.time() < deadline:
            last_state = self.eval(
                """
(() => {
  const root = document.querySelector('#app');
  const vue = root && root.__vue__;
  function find(vm, seen = new Set()) {
    if (!vm || seen.has(vm)) return null;
    seen.add(vm);
    if ((vm.$options && vm.$options.name) === 'erp-settings') {
      return vm;
    }
    for (const child of (vm.$children || [])) {
      const found = find(child, seen);
      if (found) return found;
    }
    return null;
  }
  const vm = find(vue);
  return {
    href: location.href,
    currentItem: vm && vm.currentItem,
    bodyTextLength: ((document.body && document.body.innerText) || '').trim().length
  };
})()
"""
            )
            if (last_state or {}).get("currentItem") == route_name:
                return
            time.sleep(0.5)
        raise RuntimeError(f"ERP档案菜单未切换成功: {json.dumps(last_state, ensure_ascii=False)}")

    def get_store_context(self):
        return self.eval(
            """
(() => {
  const root = document.querySelector('#app');
  const vue = root && root.__vue__;
  const store = vue && vue.$store;
  const accounting = store && store.getters ? store.getters.accounting : null;
  return {
    href: location.href,
    title: document.title,
    readyState: document.readyState,
    accounting: accounting ? {
      id: accounting.id,
      accountingName: accounting.accountingName,
      accountVersionName: accounting.accountVersionName,
      version: accounting.version
    } : null
  };
})()
"""
        )

    def open_erp_accounting_page(self):
        accounting_url = f"{BASE_URL}/erp/erpAccounting"
        route_result = self.eval(
            f"""
(() => {{
  const nodes = Array.from(document.querySelectorAll('*'));
  for (const el of nodes) {{
    const vm = el && el.__vue__;
    if (vm && vm.$router && typeof vm.$router.push === 'function') {{
      vm.$router.push({{ name: 'erp-accounting' }}).catch(() => {{}});
      return {{ ok: true, mode: 'router', href: location.href }};
    }}
  }}
  location.href = {json.dumps(accounting_url)};
  return {{ ok: true, mode: 'href', href: location.href }};
}})()
"""
        )
        deadline = time.time() + 30
        last_state = route_result
        while time.time() < deadline:
            last_state = self.eval(
                """
(() => ({
  href: location.href,
  title: document.title,
  readyState: document.readyState
}))()
"""
            )
            if "/erp/erpAccounting" in str((last_state or {}).get("href", "")):
                time.sleep(self.settle_seconds)
                return
            time.sleep(0.5)
        raise RuntimeError(f"ERP账套页面跳转失败: {json.dumps(last_state, ensure_ascii=False)}")

    def choose_erp_accounting(self, rows, current=None):
        if not rows:
            raise RuntimeError("ERP账套列表为空，无法进入档案配置。")
        if self.erp_accounting_id is not None:
            for row in rows:
                if int(row.get("id")) == int(self.erp_accounting_id):
                    return row
            raise RuntimeError(f"未在ERP账套列表中找到 id={self.erp_accounting_id}")
        current_id = (current or {}).get("id")
        if current_id is not None:
            for row in rows:
                if int(row.get("id")) == int(current_id):
                    return row
        if len(rows) == 1:
            return rows[0]
        brief = [
            {
                "id": row.get("id"),
                "accountingName": row.get("accountingName"),
                "version": row.get("version"),
            }
            for row in rows
        ]
        raise RuntimeError(
            f"检测到多个ERP账套，请通过 --erp-accounting-id 指定要操作的账套: {json.dumps(brief, ensure_ascii=False)}"
        )

    def enter_archive_settings_via_accounting(self):
        self.open_erp_accounting_page()
        info = self.vm_eval(
            "archiveSetting",
            """
if (typeof vm.fnNetRTableData === 'function') {
  await vm.fnNetRTableData();
}
const rows = (((vm.accountingResult || {}).data) || vm.aList || []).map(item => JSON.parse(JSON.stringify(item)));
const current = vm.$store && vm.$store.getters && vm.$store.getters.accounting
  ? JSON.parse(JSON.stringify(vm.$store.getters.accounting))
  : null;
return { rows, current };
""",
        )
        rows = info.get("rows") or []
        chosen = self.choose_erp_accounting(rows, current=info.get("current"))
        self.vm_eval(
            "archiveSetting",
            f"""
if (typeof vm.fnNetRTableData === 'function') {{
  await vm.fnNetRTableData();
}}
const targetId = {json.dumps(chosen.get("id"))};
const rows = (((vm.accountingResult || {{}}).data) || vm.aList || []).map(item => JSON.parse(JSON.stringify(item)));
const row = rows.find(item => Number(item.id) === Number(targetId));
if (!row) {{
  return {{ __error: 'erp accounting row not found', targetId, rows }};
}}
vm.archiveSetting(row);
return {{
  chosen: {{
    id: row.id,
    accountingName: row.accountingName,
    version: row.version
  }}
}};
""",
        )
        deadline = time.time() + 30
        last_state = None
        while time.time() < deadline:
            last_state = self.get_store_context()
            accounting = (last_state or {}).get("accounting") or {}
            href = str((last_state or {}).get("href", ""))
            if (
                int(accounting.get("id") or 0) == int(chosen.get("id") or 0)
                and "/erp/erpArchiveSetting" in href
            ):
                self.current_accounting = accounting
                time.sleep(self.settle_seconds)
                return accounting
            time.sleep(0.5)
        raise RuntimeError(f"进入ERP档案配置失败: {json.dumps(last_state, ensure_ascii=False)}")

    def ensure_erp_archive_context(self):
        context = self.get_store_context()
        accounting = (context or {}).get("accounting")
        if (
            accounting
            and accounting.get("id")
            and (
                self.erp_accounting_id is None
                or int(accounting.get("id")) == int(self.erp_accounting_id)
            )
        ):
            self.current_accounting = accounting
            return accounting
        return self.enter_archive_settings_via_accounting()

    def eval(self, expression, await_promise=False):
        return cdp_eval(self.page, expression, return_by_value=True, await_promise=await_promise)

    def vm_eval(self, marker_method, body, await_promise=True, timeout_seconds=30):
        script = f"""
(async () => {{
  try {{
    const vmEntries = new Map();
    const methodSamples = [];

    function noteVm(v, source, el = null) {{
      if (!v) return;
      let entry = vmEntries.get(v);
      if (!entry) {{
        const methods = Object.keys((v.$options && v.$options.methods) || {{}});
        entry = {{
          vm: v,
          methods,
          name: (v.$options && v.$options.name) || null,
          childCount: (v.$children || []).length,
          sources: [],
          visible: false,
          score: 0
        }};
        vmEntries.set(v, entry);
        if (methodSamples.length < 12) {{
          methodSamples.push(methods.slice(0, 12));
        }}
      }}
      if (!entry.sources.includes(source)) {{
        entry.sources.push(source);
      }}
      const targetEl = el || v.$el || null;
      if (!targetEl || !targetEl.getClientRects) return;
      const style = window.getComputedStyle(targetEl);
      const visible = style && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0' && targetEl.getClientRects().length > 0;
      const score = (visible ? 100000 : 0) + ((targetEl.innerText || '').length) + entry.childCount * 10;
      if (score >= entry.score) {{
        entry.visible = visible;
        entry.score = score;
      }}
    }}

    function walk(vm, seen = new Set()) {{
      if (!vm || seen.has(vm)) return;
      seen.add(vm);
      noteVm(vm, 'tree', vm.$el || null);
      for (const child of (vm.$children || [])) {{
        walk(child, seen);
      }}
    }}

    const root = document.querySelector('#app');
    const rootVue = root && root.__vue__;
    walk(rootVue);

    for (const el of Array.from(document.querySelectorAll('*'))) {{
      noteVm(el && el.__vue__, 'dom', el);
    }}

    const candidates = Array.from(vmEntries.values()).filter(entry => entry.methods.includes({json.dumps(marker_method)}));
    let vm = null;
    if (candidates.length) {{
      candidates.sort((a, b) => b.score - a.score);
      vm = candidates[0].vm;
    }}
    if (!vm) return {{
      __pending: true,
      reason: 'vm not found',
      href: location.href,
      title: document.title,
      readyState: document.readyState,
      marker: {json.dumps(marker_method)},
      vueCount: vmEntries.size,
      candidateSamples: candidates.slice(0, 5).map(item => ({{
        name: item.name,
        sources: item.sources,
        visible: item.visible,
        score: item.score
      }})),
      routeName: rootVue && rootVue.$route ? rootVue.$route.name : null,
      routePath: rootVue && rootVue.$route ? rootVue.$route.fullPath : null,
      menuCurrentItem: (() => {{
        const seen = new Set();
        function findMenu(current) {{
          if (!current || seen.has(current)) return null;
          seen.add(current);
          if ((current.$options && current.$options.name) === 'erp-settings') {{
            return current.currentItem || null;
          }}
          for (const child of (current.$children || [])) {{
            const found = findMenu(child);
            if (found) return found;
          }}
          return null;
        }}
        return findMenu(rootVue);
      }})(),
      methodSamples
    }};
    {body}
  }} catch (error) {{
    return {{ __error: String((error && error.stack) || error) }};
  }}
}})()
"""
        deadline = time.time() + timeout_seconds
        last_pending = None
        while time.time() < deadline:
            result = self.eval(script, await_promise=await_promise)
            if isinstance(result, dict):
                if result.get("__error"):
                    raise RuntimeError(result["__error"])
                if result.get("__pending"):
                    last_pending = result
                    time.sleep(0.5)
                    continue
            return result
        if last_pending:
            raise RuntimeError(f"vm not found after wait: {json.dumps(last_pending, ensure_ascii=False)}")
        raise RuntimeError(f"vm not found after wait: marker={marker_method}")


def route_vm_eval(runner, route_name, marker_method, body, await_promise=True, timeout_seconds=30, retries=1):
    last_error = None
    for attempt in range(retries + 1):
        runner.navigate(route_name)
        try:
            return runner.vm_eval(
                marker_method,
                body,
                await_promise=await_promise,
                timeout_seconds=timeout_seconds,
            )
        except RuntimeError as exc:
            last_error = exc
            if "vm not found after wait" not in str(exc) or attempt >= retries:
                raise
            time.sleep(1)
    raise last_error


def build_financial_sync_js(master_expr, button_text="从财务系统同步"):
    return f"""
const __readMasterCount = () => ((({master_expr}) || []).length);
function __isVisible(el) {{
  if (!el || !el.getClientRects) return false;
  const style = window.getComputedStyle(el);
  return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0' && el.getClientRects().length > 0;
}}
function __normalizeButtonText(el) {{
  return ((el && (el.innerText || el.textContent)) || '').replace(/\\s+/g, ' ').trim();
}}
function __findButton(text) {{
  const buttons = Array.from(document.querySelectorAll('button, .el-button, [role="button"]'));
  return buttons.find(el => __isVisible(el) && __normalizeButtonText(el) === text)
    || buttons.find(el => __normalizeButtonText(el) === text)
    || null;
}}
if (typeof vm.fnClickAdd === 'function' && !vm.bIsShowModal) {{
  vm.fnClickAdd();
  await new Promise(resolve => setTimeout(resolve, 300));
}}
const __syncButton = __findButton({json.dumps(button_text)});
if (__syncButton) {{
  __syncButton.click();
  let __lastMasterCount = __readMasterCount();
  let __stableTicks = 0;
  const __deadline = Date.now() + 12000;
  while (Date.now() < __deadline) {{
    await new Promise(resolve => setTimeout(resolve, 300));
    const __currentMasterCount = __readMasterCount();
    if (__currentMasterCount !== __lastMasterCount) {{
      __lastMasterCount = __currentMasterCount;
      __stableTicks = 0;
      continue;
    }}
    __stableTicks += 1;
    if (__stableTicks >= 3) break;
  }}
}}
if (vm.bIsShowModal) {{
  const __cancelButton = __findButton('取消');
  if (__cancelButton) {{
    __cancelButton.click();
    const __closeDeadline = Date.now() + 5000;
    while (vm.bIsShowModal && Date.now() < __closeDeadline) {{
      await new Promise(resolve => setTimeout(resolve, 200));
    }}
  }}
}}
"""


def fetch_department_data(runner):
    return route_vm_eval(
        runner,
        "department",
        "fnNetRelateItems",
        """
await vm.fnNetRRelationList();
await vm.fnNetRList();
"""
        + build_financial_sync_js("vm.aAllList || vm.aList")
        + """
return {
  relation: vm.aRelationList,
  master: vm.aAllList || vm.aList
};
""",
    )


def save_department_mappings(runner, payload):
    return route_vm_eval(
        runner,
        "department",
        "fnNetRelateItems",
        f"""
vm.aRelateItems = {json.dumps(payload, ensure_ascii=False)};
await vm.fnNetRelateItems();
await vm.fnNetRRelationList();
return vm.aRelationList;
""",
    )


def fetch_project_data(runner):
    return route_vm_eval(
        runner,
        "project",
        "fnNetRelateItems",
        """
await vm.fnNetRRelationList();
await vm.fnNetRList();
"""
        + build_financial_sync_js("vm.aAllList || vm.aList")
        + """
return {
  relation: vm.aRelationList,
  master: vm.aAllList || vm.aList
};
""",
    )


def save_project_mappings(runner, payload):
    return route_vm_eval(
        runner,
        "project",
        "fnNetRelateItems",
        f"""
vm.aRelateItems = {json.dumps(payload, ensure_ascii=False)};
await vm.fnNetRelateItems();
await vm.fnNetRRelationList();
return vm.aRelationList;
""",
    )


def fetch_staff_data(runner):
    return route_vm_eval(
        runner,
        "staff",
        "fnNetRelateItems",
        """
await vm.fnNetRRelationList();
await vm.fnNetRList();
"""
        + build_financial_sync_js("vm.aAllList || vm.aList")
        + """
return {
  relation: vm.aRelationList,
  master: vm.aAllList || vm.aList
};
""",
    )


def save_staff_mappings(runner, payload):
    return route_vm_eval(
        runner,
        "staff",
        "fnNetRelateItems",
        f"""
vm.aRelateItems = {json.dumps(payload, ensure_ascii=False)};
await vm.fnNetRelateItems();
await vm.fnNetRRelationList();
return vm.aRelationList;
""",
    )


def fetch_provider_data(runner):
    return route_vm_eval(
        runner,
        "provider",
        "fnSaveCustomerRelation",
        """
vm.cur = 'relation';
await vm.fnNetRRelationList();
await vm.fnNetRList();
"""
        + build_financial_sync_js("vm.providerAllList")
        + """
const bankRelation = vm.aRelationList;
vm.cur = 'receivePayAccount';
await vm.fnNetRRelationList();
const payRelation = vm.aRelationList;
await vm.fnNetCustomerRelationList();
return {
  bankRelation,
  payRelation,
  customerRelation: vm.cRelationList,
  providerMaster: vm.providerAllList,
  customerMaster: vm.customerAllList
};
""",
    )


def save_provider_bank_mappings(runner, payload, receive_type):
    cur = "relation" if receive_type == "BANKCARD" else "receivePayAccount"
    return route_vm_eval(
        runner,
        "provider",
        "fnSaveCustomerRelation",
        f"""
vm.cur = {json.dumps(cur)};
vm.aRelateItems = {json.dumps(payload, ensure_ascii=False)};
await vm.fnNetRelateItems();
await vm.fnNetRRelationList();
return vm.aRelationList;
""",
    )


def save_provider_customer_rows(runner, rows):
    return route_vm_eval(
        runner,
        "provider",
        "fnSaveCustomerRelation",
        f"""
const rows = {json.dumps(rows, ensure_ascii=False)};
for (const row of rows) {{
  await vm.fnSaveCustomerRelation(row);
}}
await vm.fnNetCustomerRelationList();
return vm.cRelationList;
""",
    )


def fetch_subject_data(runner):
    return route_vm_eval(
        runner,
        "subject",
        "fnNetSavePayRelateItems",
        """
await vm.fnNetPayRelationList(1);
await vm.fnNetIncomeRelationList(1);
await vm.fnSyncAllSubject();

async function loadPay(nodes, path = [], out = []) {
  for (const row of nodes || []) {
    const nextPath = path.concat([row.feeTemplateName]);
    out.push({ path: nextPath, row });
    if (row.hasChildren) {
      const kids = await vm.loadPayFeeRelation(row.feeTemplateId);
      for (const item of kids) item.hasChildren = item.parentFlag === '1';
      await loadPay(kids, nextPath, out);
    }
  }
  return out;
}

async function loadIncome(nodes, path = [], out = []) {
  for (const row of nodes || []) {
    const nextPath = path.concat([row.feeTemplateName]);
    out.push({ path: nextPath, row });
    if (row.hasChildren) {
      const kids = await vm.loadIncomeFeeRelation(row.feeTemplateId);
      for (const item of kids) item.hasChildren = !!item.parentFlag;
      await loadIncome(kids, nextPath, out);
    }
  }
  return out;
}

function walkSubjects(nodes, path = [], out = []) {
  for (const node of nodes || []) {
    const nextPath = path.concat([node.subjectName]);
    out.push({
      path: nextPath,
      subject: {
        id: node.id,
        subjectName: node.subjectName,
        subjectCode: node.subjectCode,
        subjectFullName: node.subjectFullName
      }
    });
    walkSubjects(node.children || [], nextPath, out);
  }
  return out;
}

const subjectResp = await vm.$dc.erp.fnNetQueryAllSubjectTree({ accountingId: vm.accountingId });
const subjectTree = (subjectResp && subjectResp.result) || [];

return {
  pay: await loadPay(vm.payRelationList || []),
  income: await loadIncome(vm.incomeRelationList || []),
  subjects: walkSubjects(subjectTree)
};
""",
    )


def save_subject_mappings(runner, pay_rows, income_rows):
    return route_vm_eval(
        runner,
        "subject",
        "fnNetSavePayRelateItems",
        f"""
const payRows = {json.dumps(pay_rows, ensure_ascii=False)};
const incomeRows = {json.dumps(income_rows, ensure_ascii=False)};
vm.payRelateItems = {{}};
vm.incomeRelateItems = {{}};
for (const row of payRows) vm.payRelateItems[row.feeTemplateId] = row;
for (const row of incomeRows) vm.incomeRelateItems[row.feeTemplateId] = row;
if (payRows.length) await vm.fnNetSavePayRelateItems();
if (incomeRows.length) await vm.fnNetSaveIncomeRelateItems();
await vm.fnNetPayRelationList(1);
await vm.fnNetIncomeRelationList(1);
return {{
  pay: vm.payRelationList,
  income: vm.incomeRelationList
}};
""",
    )


def build_department_payload(data):
    master_index = unique_index(data["master"], lambda item: normalize_text(item.get("deptName")))
    payload = []
    skipped = []
    for row in data["relation"]:
        ec = row["eccloudData"]
        current_id = (row.get("financialData") or {}).get("id")
        candidate, reason = choose_parallel_exact_candidate(ec.get("name"), ec.get("fullPathName"), master_index)
        if candidate is None:
            if current_id is not None:
                payload.append(
                    {
                        "eccloudId": ec["id"],
                        "financialId": None,
                        "accountingId": data["master"][0]["accountingId"] if data["master"] else None,
                        "_reason": f"clear_{reason}",
                        "_eccloudName": ec.get("fullPathName") or ec.get("name"),
                        "_financialName": None,
                    }
                )
            skipped.append({"name": ec.get("fullPathName") or ec.get("name"), "reason": reason})
            continue
        if current_id == candidate["id"]:
            continue
        payload.append(
            {
                "eccloudId": ec["id"],
                "financialId": candidate["id"],
                "accountingId": candidate["accountingId"],
                "_reason": reason,
                "_eccloudName": ec.get("fullPathName") or ec.get("name"),
                "_financialName": candidate.get("deptName"),
            }
        )
    return payload, skipped


def build_project_payload(data):
    master_index = unique_index(data["master"], lambda item: normalize_text(item.get("projectName")))
    payload = []
    skipped = []
    for row in data["relation"]:
        ec = row["eccloudData"]
        current_id = (row.get("financialData") or {}).get("id")
        candidate, reason = choose_parallel_exact_candidate(ec.get("name"), ec.get("fullPathName"), master_index)
        if candidate is None:
            if current_id is not None:
                payload.append(
                    {
                        "eccloudId": ec["id"],
                        "financialId": None,
                        "accountingId": data["master"][0]["accountingId"] if data["master"] else None,
                        "_eccloudName": ec.get("fullPathName") or ec.get("name"),
                        "_financialName": None,
                        "_reason": f"clear_{reason}",
                    }
                )
            skipped.append({"name": ec.get("fullPathName") or ec.get("name"), "reason": reason})
            continue
        if current_id == candidate["id"]:
            continue
        payload.append(
            {
                "eccloudId": ec["id"],
                "financialId": candidate["id"],
                "accountingId": candidate["accountingId"],
                "_eccloudName": ec.get("fullPathName") or ec.get("name"),
                "_financialName": candidate.get("projectName"),
            }
        )
    return payload, skipped


def build_staff_payload(data):
    master_index = unique_index(data["master"], lambda item: normalize_text(item.get("userName")))
    payload = []
    skipped = []
    for row in data["relation"]:
        ec = row["eccloudData"]
        current_id = (row.get("financialData") or {}).get("id")
        candidate = master_index.get(normalize_text(ec.get("name")))
        if candidate is None:
            if current_id is not None:
                payload.append(
                    {
                        "eccloudId": ec["id"],
                        "financialId": 0,
                        "accountingId": data["master"][0]["accountingId"] if data["master"] else None,
                        "_eccloudName": ec.get("name"),
                        "_financialName": None,
                        "_reason": "clear_no_match",
                    }
                )
            skipped.append({"name": ec.get("name"), "reason": "no_match"})
            continue
        if current_id == candidate["id"]:
            continue
        payload.append(
            {
                "eccloudId": ec["id"],
                "financialId": candidate["id"],
                "accountingId": candidate["accountingId"],
                "_eccloudName": ec.get("name"),
                "_financialName": candidate.get("userName"),
            }
        )
    return payload, skipped


def build_provider_payloads(data):
    provider_index = unique_index(
        [item for item in data["providerMaster"] if item.get("providerType") == "PROVIDER"],
        lambda item: normalize_text(item.get("providerName")),
    )
    customer_index = unique_index(data["customerMaster"], lambda item: normalize_text(item.get("providerName")))

    bank_payload = []
    bank_skipped = []
    for row in data["bankRelation"]:
        ec = row["eccloudData"]
        candidate = provider_index.get(normalize_text(ec.get("name")))
        if candidate is None:
            bank_skipped.append({"name": ec.get("name"), "reason": "no_match"})
            continue
        current_id = (row.get("financialData") or {}).get("id")
        if current_id == candidate["id"]:
            continue
        bank_payload.append(
            {
                "eccloudId": ec["id"],
                "financialId": candidate["id"],
                "providerType": candidate["providerType"],
                "accountingId": candidate["accountingId"],
                "_eccloudName": ec.get("name"),
                "_financialName": candidate.get("providerName"),
            }
        )

    pay_payload = []
    pay_skipped = []
    for row in data["payRelation"]:
        ec = row["eccloudData"]
        candidate = provider_index.get(normalize_text(ec.get("name")))
        if candidate is None:
            pay_skipped.append({"name": ec.get("name"), "reason": "no_match"})
            continue
        current_id = (row.get("financialData") or {}).get("id")
        if current_id == candidate["id"]:
            continue
        pay_payload.append(
            {
                "eccloudId": ec["id"],
                "financialId": candidate["id"],
                "providerType": candidate["providerType"],
                "accountingId": candidate["accountingId"],
                "_eccloudName": ec.get("name"),
                "_financialName": candidate.get("providerName"),
            }
        )

    customer_rows = []
    customer_skipped = []
    for row in data["customerRelation"]:
        candidate = customer_index.get(normalize_text(row.get("customerName")))
        current_id = row.get("financaProviderId")
        if candidate is None:
            if current_id is not None:
                updated = dict(row)
                updated["financaProviderId"] = None
                updated["financaProviderName"] = None
                customer_rows.append(updated)
            customer_skipped.append({"name": row.get("customerName"), "reason": "no_match"})
            continue
        if current_id == candidate["id"]:
            continue
        updated = dict(row)
        updated["financaProviderId"] = candidate["id"]
        updated["financaProviderName"] = candidate["providerName"]
        customer_rows.append(updated)

    return {
        "bank_payload": bank_payload,
        "bank_skipped": bank_skipped,
        "pay_payload": pay_payload,
        "pay_skipped": pay_skipped,
        "customer_rows": customer_rows,
        "customer_skipped": customer_skipped,
    }


def build_subject_payloads(data):
    subject_index = unique_index(
        data["subjects"],
        lambda item: tuple(normalize_text(part) for part in item["path"]),
    )

    def find_best_subject(path):
        normalized_path = [normalize_text(part) for part in path]
        matches = []
        for start in range(len(normalized_path)):
            key = tuple(normalized_path[start:])
            candidate = subject_index.get(key)
            if candidate is not None:
                matches.append((len(key), candidate))
        if not matches:
            return None
        max_len = max(length for length, _ in matches)
        best = [candidate for length, candidate in matches if length == max_len]
        if len(best) != 1:
            return None
        return best[0]

    def update_rows(rows, current_name_key, current_id_key, target_id_key, target_name_key):
        payload = []
        skipped = []
        for item in sorted(rows, key=lambda row: len(row["path"]), reverse=True):
            candidate = find_best_subject(item["path"])
            if candidate is None:
                skipped.append({"path": item["path"], "reason": "no_match"})
                continue
            row = dict(item["row"])
            if row.get(current_id_key) == candidate["subject"]["id"]:
                continue
            row[target_id_key] = candidate["subject"]["id"]
            row[target_name_key] = candidate["subject"]["subjectName"]
            payload.append(row)
        return payload, skipped

    pay_payload, pay_skipped = update_rows(
        data["pay"], "debitSubjectName", "debitSubjectId", "debitSubjectId", "debitSubjectName"
    )
    income_payload, income_skipped = update_rows(
        data["income"], "creditSubjectName", "creditSubjectId", "creditSubjectId", "creditSubjectName"
    )
    return {
        "pay_payload": pay_payload,
        "pay_skipped": pay_skipped,
        "income_payload": income_payload,
        "income_skipped": income_skipped,
    }


def strip_meta(items):
    return [{k: v for k, v in item.items() if not k.startswith("_")} for item in items]


def summarize_rows(rows, name_key):
    return [row.get(name_key) for row in rows]


def run(
    apply_changes=False,
    browser_name="edge",
    report_path=None,
    auto_login=False,
    username=None,
    password=None,
    company_id=None,
    company_name=None,
    erp_accounting_id=None,
    force_relogin=False,
    task_id=None,
    close_browser=False,
    close_timeout=5.0,
    prompt_credentials=False,
):
    runner = None
    report = None
    error = None
    try:
        runner = CSTBrowserRunner(
            browser_name=browser_name,
            auto_login=auto_login,
            username=username,
            password=password,
            company_id=company_id,
            company_name=company_name,
            erp_accounting_id=erp_accounting_id,
            force_relogin=force_relogin,
            task_id=task_id,
            prompt_credentials=prompt_credentials,
        )
        runner.ensure_erp_archive_context()
        report = {
            "applied": apply_changes,
            "task_id": runner.task_id,
            "login_account": runner.login_account,
            "login_company": runner.current_company,
            "requested_company_name": company_name,
            "erp_accounting": runner.current_accounting,
            "browser": runner.browser["name"],
            "steps": [],
        }

        subject_data = fetch_subject_data(runner)
        subject_plan = build_subject_payloads(subject_data)
        subject_step = {
            "step": "subject",
            "pay_apply_count": len(subject_plan["pay_payload"]),
            "pay_skip_count": len(subject_plan["pay_skipped"]),
            "income_apply_count": len(subject_plan["income_payload"]),
            "income_skip_count": len(subject_plan["income_skipped"]),
            "pay_paths": [item["path"] for item in subject_plan["pay_skipped"]],
            "income_paths": [item["path"] for item in subject_plan["income_skipped"]],
        }
        if apply_changes and (subject_plan["pay_payload"] or subject_plan["income_payload"]):
            save_subject_mappings(runner, subject_plan["pay_payload"], subject_plan["income_payload"])
            subject_step["saved"] = True
        report["steps"].append(subject_step)

        provider_data = fetch_provider_data(runner)
        provider_plan = build_provider_payloads(provider_data)
        provider_step = {
            "step": "provider",
            "bank_apply_count": len(provider_plan["bank_payload"]),
            "bank_skip_count": len(provider_plan["bank_skipped"]),
            "pay_apply_count": len(provider_plan["pay_payload"]),
            "pay_skip_count": len(provider_plan["pay_skipped"]),
            "customer_apply_count": len(provider_plan["customer_rows"]),
            "customer_skip_count": len(provider_plan["customer_skipped"]),
            "customer_skipped": provider_plan["customer_skipped"],
        }
        if apply_changes and provider_plan["bank_payload"]:
            save_provider_bank_mappings(runner, strip_meta(provider_plan["bank_payload"]), "BANKCARD")
            provider_step["bank_saved"] = True
        if apply_changes and provider_plan["pay_payload"]:
            save_provider_bank_mappings(runner, strip_meta(provider_plan["pay_payload"]), "PAYACCOUNT")
            provider_step["pay_saved"] = True
        if apply_changes and provider_plan["customer_rows"]:
            save_provider_customer_rows(runner, provider_plan["customer_rows"])
            provider_step["customer_saved"] = True
        report["steps"].append(provider_step)

        staff_data = fetch_staff_data(runner)
        staff_payload, staff_skipped = build_staff_payload(staff_data)
        staff_step = {
            "step": "staff",
            "apply_count": len(staff_payload),
            "skip_count": len(staff_skipped),
            "skipped": staff_skipped,
        }
        if apply_changes and staff_payload:
            save_staff_mappings(runner, strip_meta(staff_payload))
            staff_step["saved"] = True
        report["steps"].append(staff_step)

        project_data = fetch_project_data(runner)
        project_payload, project_skipped = build_project_payload(project_data)
        project_step = {
            "step": "project",
            "apply_count": len(project_payload),
            "skip_count": len(project_skipped),
            "skipped": project_skipped,
        }
        if apply_changes and project_payload:
            save_project_mappings(runner, strip_meta(project_payload))
            project_step["saved"] = True
        report["steps"].append(project_step)

        department_data = fetch_department_data(runner)
        department_payload, department_skipped = build_department_payload(department_data)
        department_step = {
            "step": "department",
            "apply_count": len(department_payload),
            "skip_count": len(department_skipped),
            "skipped": department_skipped,
        }
        if apply_changes and department_payload:
            save_department_mappings(runner, strip_meta(department_payload))
            department_step["saved"] = True
        report["steps"].append(department_step)
    except Exception as exc:
        error = exc
        if report is None:
            report = {
                "applied": apply_changes,
                "task_id": normalize_task_id(task_id),
                "login_account": (runner.login_account if runner is not None else username),
                "login_company": (runner.current_company if runner is not None else {}),
                "requested_company_name": company_name,
                "erp_accounting": (runner.current_accounting if runner is not None else None),
                "browser": (runner.browser["name"] if runner is not None else browser_name),
                "steps": [],
                "error": str(exc),
            }
    finally:
        if close_browser:
            target_browser = runner.browser if runner is not None else find_browser(
                preferred=browser_name,
                require_cst=False,
                task_id=task_id,
            )
            if target_browser:
                close_ok, close_message = close_browser_instance(target_browser, timeout=close_timeout)
                if close_ok and normalize_task_id(task_id):
                    release_browser_runtime(task_id, browser_id=target_browser["id"])
            else:
                close_ok, close_message = True, "ℹ️ 未发现 ERP 自动化浏览器需要关闭"
            if report is not None:
                report["browser_close"] = {
                    "ok": close_ok,
                    "message": close_message,
                }
        if report_path and report is not None:
            Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2))

    if error is not None:
        raise error
    return report


def main():
    parser = argparse.ArgumentParser(description="Configure 财税通 ERP archive mappings from the current Edge session.")
    parser.add_argument("--apply", action="store_true", help="actually save mappings")
    parser.add_argument("--browser", default="edge", help="browser to attach to")
    parser.add_argument("--auto-login", action="store_true", help="launch browser and login automatically if needed")
    parser.add_argument("--username", help="财税通登录手机号; defaults to CST_USERNAME")
    parser.add_argument("--password", help="财税通登录密码; defaults to CST_PASSWORD")
    parser.add_argument("--company-id", type=int, help="企业 ID; only needed when the account can enter multiple enterprises")
    parser.add_argument("--company-name", help="企业名称; 无法提供 company-id 时用于强制选定企业")
    parser.add_argument("--erp-accounting-id", type=int, help="ERP账套 ID; required only when the account has multiple ERP账套")
    parser.add_argument("--task-id", help="任务隔离 ID；同一 taskId 会复用同一浏览器实例")
    parser.add_argument("--fresh-login", action="store_true", help="忽略当前登录态，强制重新登录")
    parser.add_argument("--close-browser", action="store_true", help="执行完成后关闭 finance.ERP 专用自动化浏览器")
    parser.add_argument("--close-timeout", type=float, default=5.0, help="关闭浏览器后的校验秒数，默认 5")
    parser.add_argument(
        "--prompt-credentials",
        action="store_true",
        help="prompt in terminal for missing username/password",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="where to write the JSON summary",
    )
    args = parser.parse_args()
    normalized_task_id = normalize_task_id(args.task_id)
    default_report = Path(__file__).resolve().parent.parent / "reports"
    default_report.mkdir(parents=True, exist_ok=True)
    report_path = args.report
    if not report_path:
        suffix = normalized_task_id or "default"
        report_path = str(default_report / f"cst_live_mapper_report_{suffix}.json")

    report = run(
        apply_changes=args.apply,
        browser_name=args.browser,
        report_path=report_path,
        auto_login=args.auto_login,
        username=args.username,
        password=args.password,
        company_id=args.company_id,
        company_name=args.company_name,
        erp_accounting_id=args.erp_accounting_id,
        task_id=args.task_id,
        force_relogin=args.fresh_login,
        close_browser=args.close_browser,
        close_timeout=args.close_timeout,
        prompt_credentials=args.prompt_credentials,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
