#!/usr/bin/env python3
"""One-click launcher: start the server, wait for /ping, then open the browser.

The old .bat opened the browser first, so the first page load raced the server
and usually showed "connection refused". This launcher keeps the server in the
foreground (its logs stay visible), polls the readiness endpoint, and only then
opens the default browser.

Usage:
    python scripts/launch.py                # localhost:8000, opens the browser
    python scripts/launch.py --port 8080
    python scripts/launch.py --no-browser   # server only
    python scripts/launch.py --reload       # dev auto-reload
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 8000
STARTUP_TIMEOUT = 90.0


def build_url(host: str, port: int) -> str:
    """Return a browser-safe URL (0.0.0.0/:: are not navigable)."""
    browser_host = "127.0.0.1" if host in {"", "0.0.0.0", "::", "[::]"} else host
    return f"http://{browser_host}:{port}"


def is_app_ready(base_url: str, timeout: float = 1.0) -> bool:
    """True only when /ping answers with the app's JSON payload."""
    try:
        with urllib.request.urlopen(f"{base_url}/ping", timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("status") == "ok"


def wait_for_ready(
    base_url: str,
    timeout: float = STARTUP_TIMEOUT,
    interval: float = 0.5,
    probe=is_app_ready,
    clock=time.monotonic,
    sleep=time.sleep,
) -> bool:
    """Poll until the app answers /ping, or the timeout expires."""
    deadline = clock() + timeout
    while True:
        if probe(base_url):
            return True
        if clock() >= deadline:
            return False
        sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动 SpoilerShield 并等待服务就绪")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=STARTUP_TIMEOUT, help="等待就绪的秒数")
    parser.add_argument("--reload", action="store_true", help="代码改动自动重载（开发用）")
    parser.add_argument("--no-browser", action="store_true", help="不打开浏览器")
    args = parser.parse_args(argv)

    url = build_url(args.host, args.port)

    if is_app_ready(url):
        print(f"检测到已有实例正在运行：{url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        command.append("--reload")

    print(f"正在启动 SpoilerShield：{url}")
    print("首次启动需要加载依赖，通常 10–20 秒；日志会留在本窗口。", flush=True)

    try:
        process = subprocess.Popen(command, cwd=str(ROOT))
    except OSError as exc:
        print(f"无法启动服务：{exc}")
        return 1

    try:
        if not wait_for_ready(url, timeout=args.timeout):
            if process.poll() is not None:
                print("服务进程提前退出，请查看上面的错误信息。")
            else:
                print(f"等待 {args.timeout:.0f} 秒后服务仍未就绪。")
            return 1

        print(f"服务已就绪：{url}")
        if not args.no_browser:
            opened = webbrowser.open(url)
            if not opened:
                print(f"浏览器未能自动打开，请手动访问：{url}")
        return process.wait()
    except KeyboardInterrupt:
        print("\n正在停止服务…")
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
