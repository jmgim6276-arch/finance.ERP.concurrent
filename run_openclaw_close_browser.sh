#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BROWSER="auto"
TIMEOUT="5"
TASK_ID=""

usage() {
  cat <<'EOF'
用法：
  bash run_openclaw_close_browser.sh [选项]

选项：
  --browser NAME       可选，auto|edge|chrome，默认 auto
  --timeout SECONDS    可选，关闭后验证秒数，默认 5
  --task-id VALUE      可选，任务隔离 ID；传入后只关闭该任务对应的 ERP 浏览器实例
  --help               显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --browser)
      BROWSER="${2:-}"
      shift 2
      ;;
    --timeout)
      TIMEOUT="${2:-}"
      shift 2
      ;;
    --task-id)
      TASK_ID="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$REPO_DIR"
echo "==> 当前版本: $(git log -1 --oneline 2>/dev/null || echo '非 git 仓库')"
echo "==> 关闭 finance.ERP 自动化浏览器..."
CMD=(
  python3
  "$REPO_DIR/scripts/close_cst_browser.py"
  --browser "$BROWSER"
  --timeout "$TIMEOUT"
)

if [[ -n "$TASK_ID" ]]; then
  CMD+=(--task-id "$TASK_ID")
fi

"${CMD[@]}"
echo "==> 关闭流程完成"
