#!/usr/bin/env python3
import argparse

from browser_session import get_auth


def main():
    parser = argparse.ArgumentParser(description="自动打开浏览器并登录财税通")
    parser.add_argument("--username", help="财税通登录手机号；不传则优先读取 CST_USERNAME，仍缺失时终端提示输入")
    parser.add_argument("--password", help="财税通登录密码；不传则优先读取 CST_PASSWORD，仍缺失时终端隐藏输入")
    parser.add_argument("--company-id", type=int, help="多企业账号时指定 companyId；也可用环境变量 CST_COMPANY_ID")
    parser.add_argument("--company-name", help="期望进入的集团/公司名称；用于校验和多企业切换")
    parser.add_argument("--task-id", help="任务隔离 ID；同一 taskId 会复用同一浏览器实例")
    parser.add_argument(
        "--browser",
        choices=["auto", "edge", "chrome"],
        default="auto",
        help="优先使用的浏览器",
    )
    args = parser.parse_args()

    token, company_id, user_id, browser_name = get_auth(
        auto_login=True,
        preferred_browser=args.browser,
        username=args.username,
        password=args.password,
        company_id=args.company_id,
        company_name=args.company_name,
        prompt=True,
        task_id=args.task_id,
    )
    print(f"✅ 已登录 {browser_name}")
    if args.task_id:
        print(f"✅ taskId={args.task_id}")
    print(f"✅ companyId={company_id}")
    print(f"✅ userId={user_id}")
    print(f"✅ token 前12位: {token[:12]}")


if __name__ == "__main__":
    main()
