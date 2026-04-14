#!/usr/bin/env python3
import argparse
import sys

from browser_session import close_browser_instance
from runtime_context import browser_choices
from runtime_context import release_browser_runtime


def main():
    parser = argparse.ArgumentParser(description="关闭 finance.ERP 专用自动化浏览器并验证结果")
    parser.add_argument(
        "--browser",
        choices=["auto", "edge", "chrome"],
        default="auto",
        help="关闭哪个浏览器；默认 auto",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="关闭后校验秒数，默认 5",
    )
    parser.add_argument(
        "--task-id",
        help="任务隔离 ID；传入后只关闭该任务对应的浏览器实例",
    )
    args = parser.parse_args()

    messages = []
    all_ok = True
    target_browsers = browser_choices(args.browser, task_id=args.task_id, create=False)
    if not target_browsers and args.task_id:
        print(f"ℹ️ taskId={args.task_id} 当前没有已登记的 ERP 浏览器实例")
        return 0

    for browser in target_browsers:
        ok, message = close_browser_instance(browser, timeout=max(args.timeout, 0.5))
        messages.append(message)
        all_ok = all_ok and ok
        if ok and args.task_id:
            release_browser_runtime(args.task_id, browser_id=browser["id"])

    for message in messages:
        print(message)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
