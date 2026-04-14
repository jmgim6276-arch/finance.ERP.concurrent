# finance.ERP.concurrent

财税通 ERP 档案关系配置并发版。

这一版单独维护，不影响现有稳定版 `finance.ERP`。核心目标是让 ERP 匹配也支持按任务隔离执行：
- 每个任务独立 `task-id`
- 每个任务独立浏览器 profile
- 每个任务独立 CDP 端口
- 每个任务独立报告文件
- 关闭浏览器时只关闭当前任务自己的实例

## Files

- `scripts/cst_live_mapper.py`
  支持按 `task-id` 隔离的 ERP 档案关系匹配脚本，自动处理:
  - 科目费用类型对应关系
  - 往来单位对应关系
  - 人员对应关系
  - 项目对应关系
  - 部门对应关系
- `scripts/browser_session.py`
  浏览器会话接管工具，负责连接任务隔离后的本机浏览器 DevTools，会被主脚本调用。
- `scripts/runtime_context.py`
  任务隔离运行时，负责给每个 `task-id` 分配独立端口和 profile。
- `run_openclaw_match.sh`
  ERP 并发版推荐入口，会自动生成 `task-id` 和唯一报告路径。
- `run_openclaw_login.sh`
  只登录不匹配时的并发版入口。
- `run_openclaw_close_browser.sh`
  关闭单个 `task-id` 对应 ERP 浏览器实例。

## Requirements

- macOS
- Python 3
- Microsoft Edge 或 Google Chrome
- 本机安装依赖:

```bash
python3 -m pip install -r requirements.txt
```

## Usage

最推荐的并发版用法：

```bash
bash run_openclaw_match.sh \
  --company-name "北京公司" \
  --username "13620260402" \
  --password "你的密码"
```

同一时间跑第二家公司时，传不同 `task-id` 即可：

```bash
bash run_openclaw_match.sh \
  --task-id "erp-shanghai-001" \
  --company-name "上海公司" \
  --username "13720260402" \
  --password "你的密码"
```

如果你只想预览、不写入：

```bash
bash run_openclaw_match.sh \
  --task-id "erp-preview-001" \
  --company-name "北京公司" \
  --username "13620260402" \
  --password "你的密码" \
  --preview
```

如果你想保留页面排查，不要自动关闭浏览器：

```bash
bash run_openclaw_match.sh \
  --task-id "erp-debug-001" \
  --company-name "北京公司" \
  --username "13620260402" \
  --password "你的密码" \
  --keep-browser
```

如果只想先登录并保留这个任务的浏览器实例：

```bash
bash run_openclaw_login.sh \
  --task-id "erp-login-001" \
  --company-name "北京公司" \
  --username "13620260402" \
  --password "你的密码"
```

匹配完成后，默认报告会写到：

```text
reports/cst_live_mapper_report_<task-id>.json
```

也可以手动关闭某个任务的浏览器：

```bash
bash run_openclaw_close_browser.sh --task-id "erp-debug-001"
```

脚本默认会：
- 自动登录
- 强制 fresh login，不复用旧登录态
- 按 `company-name` 或 `company-id` 锁定企业
- 任务结束后只关闭当前任务自己的 ERP 浏览器

它不会自动放宽匹配规则。

脚本会先进入 `ERP账套`，把当前账套写入前端 store，再进入 `ERP档案关系配置`。如果当前账号下有多个 ERP账套，需要额外指定：

```bash
bash run_openclaw_match.sh \
  --company-name "北京公司" \
  --username "13620260402" \
  --password "你的密码" \
  --erp-accounting-id 账套ID
```

如果你想直接调用 Python 入口，也可以：

```bash
python3 scripts/cst_live_mapper.py \
  --auto-login \
  --fresh-login \
  --close-browser \
  --task-id "erp-beijing-001" \
  --company-name "北京公司" \
  --username "13620260402" \
  --password "你的密码" \
  --apply
```

## Concurrency Notes

- 不同 `task-id` 会使用不同浏览器实例，可以并发运行。
- 同一个 `task-id` 会复用同一实例，适合失败后回到同一现场继续排查。
- 并发版解决的是“浏览器/报告/登录态互相串”的问题。
- 如果两个任务同时改同一公司同一账套里的同一批关系，业务数据层面仍可能互相覆盖；最稳的做法仍然是“跨公司并发、同公司串行”。

## Matching Rules

- 项目、部门:
  只允许精确命中两列中的某一列。
- 如果两列各自命中不同候选:
  视为歧义，留空。
- 科目:
  按当前脚本里的最长后缀链精确匹配。
- 没有可靠匹配时:
  留空，不猜。

## OpenClaw Prompt

在另一台电脑上，可以直接对 OpenClaw 说:

```text
忽略旧版 finance.ERP，只处理并发版 finance.ERP.concurrent。
进入当前仓库目录，优先运行 `bash run_openclaw_match.sh`。
给每个 ERP 任务生成独立 task-id，不要复用别的任务浏览器。
如果我提供了集团名称、账号、密码，就用它们自动登录并执行匹配。
执行完成后读取对应的 reports/cst_live_mapper_report_<task-id>.json。
不要放宽匹配规则。
```
