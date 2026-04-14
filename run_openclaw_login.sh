#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BROWSER="edge"
USERNAME_ARG=""
PASSWORD_ARG=""
COMPANY_ID_ARG=""
COMPANY_NAME_ARG=""
TASK_ID=""
AUTO_UPDATE=0
INSTALL_DEPS=0

usage() {
  cat <<'EOF'
用法：
  bash run_openclaw_login.sh [选项]

选项：
  --browser NAME       可选，edge|chrome|auto，默认 edge
  --username VALUE     可选，财税通手机号；不传则优先用环境变量 CST_USERNAME
  --password VALUE     可选，财税通密码；不传则优先用环境变量 CST_PASSWORD
  --company-id VALUE   可选，多企业账号时指定 companyId；不传则优先用 CST_COMPANY_ID
  --company-name VALUE 可选，期望进入的集团/公司名称；用于校验和多企业切换
  --task-id VALUE      可选，任务隔离 ID；不传则自动生成独立浏览器实例标识
  --update             可选，执行前显式 git 拉取最新代码
  --install            可选，执行前显式安装/校验依赖
  --no-update          可选，兼容旧参数；当前默认就不拉取
  --skip-install       可选，兼容旧参数；当前默认就不安装
  --help               显示帮助

环境变量：
  CST_USERNAME
  CST_PASSWORD
  CST_COMPANY_ID

本地配置文件：
  可在仓库根目录创建 .openclaw.env，脚本会自动加载
EOF
}

ensure_local_no_proxy() {
  local suffix="localhost,127.0.0.1"
  if [[ -n "${NO_PROXY:-}" ]]; then
    export NO_PROXY="${NO_PROXY},${suffix}"
  else
    export NO_PROXY="${suffix}"
  fi
  if [[ -n "${no_proxy:-}" ]]; then
    export no_proxy="${no_proxy},${suffix}"
  else
    export no_proxy="${suffix}"
  fi
}

disable_proxy_for_python_step() {
  unset HTTPS_PROXY HTTP_PROXY ALL_PROXY https_proxy http_proxy all_proxy
}

default_task_id() {
  printf 'login-%s-%s' "$(date +%Y%m%d_%H%M%S)" "$$"
}

sanitize_task_id() {
  printf '%s' "$1" | tr -cs 'A-Za-z0-9._-' '-' | sed 's/^-*//; s/-*$//' | cut -c1-80
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --browser)
      BROWSER="${2:-}"
      shift 2
      ;;
    --username)
      USERNAME_ARG="${2:-}"
      shift 2
      ;;
    --password)
      PASSWORD_ARG="${2:-}"
      shift 2
      ;;
    --company-id)
      COMPANY_ID_ARG="${2:-}"
      shift 2
      ;;
    --company-name)
      COMPANY_NAME_ARG="${2:-}"
      shift 2
      ;;
    --task-id)
      TASK_ID="${2:-}"
      shift 2
      ;;
    --update)
      AUTO_UPDATE=1
      shift
      ;;
    --install)
      INSTALL_DEPS=1
      shift
      ;;
    --no-update)
      AUTO_UPDATE=0
      shift
      ;;
    --skip-install)
      INSTALL_DEPS=0
      shift
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

if [[ -f "$REPO_DIR/.openclaw.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_DIR/.openclaw.env"
  set +a
fi

if [[ -z "$TASK_ID" ]]; then
  TASK_ID="$(default_task_id)"
fi
TASK_ID="$(sanitize_task_id "$TASK_ID")"
if [[ -z "$TASK_ID" ]]; then
  TASK_ID="$(default_task_id)"
fi

cd "$REPO_DIR"
ensure_local_no_proxy()

if [[ "$AUTO_UPDATE" -eq 1 ]]; then
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git remote get-url origin >/dev/null 2>&1; then
    echo "==> 拉取最新 main..."
    git fetch origin main
    git pull --ff-only origin main
  else
    echo "==> 当前目录未配置 origin，跳过自动更新"
  fi
fi

echo "==> 当前版本: $(git log -1 --oneline 2>/dev/null || echo '非 git 仓库')"
echo "==> 任务隔离 ID: $TASK_ID"

if [[ "$INSTALL_DEPS" -eq 1 ]]; then
  echo "==> 安装/校验依赖..."
  python3 -m pip install -r "$REPO_DIR/requirements.txt"
fi

disable_proxy_for_python_step

CMD=(
  python3
  "$REPO_DIR/scripts/ensure_browser_login.py"
  --browser "$BROWSER"
  --task-id "$TASK_ID"
)

if [[ -n "$USERNAME_ARG" ]]; then
  CMD+=(--username "$USERNAME_ARG")
fi

if [[ -n "$PASSWORD_ARG" ]]; then
  CMD+=(--password "$PASSWORD_ARG")
fi

if [[ -n "$COMPANY_ID_ARG" ]]; then
  CMD+=(--company-id "$COMPANY_ID_ARG")
fi

if [[ -n "$COMPANY_NAME_ARG" ]]; then
  CMD+=(--company-name "$COMPANY_NAME_ARG")
fi

echo "==> 开始登录财税通..."
"${CMD[@]}"
echo "==> 登录完成"
