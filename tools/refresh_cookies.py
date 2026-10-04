# -*- coding: utf-8 -*-
"""刷新抖音等平台 cookies：用真实浏览器访问站点，导出 Netscape 格式 cookies.txt
用法：python tools/refresh_cookies.py [url]
默认访问抖音首页。依赖项目 venv 中的 playwright + 本机已有 Chromium。
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
COOKIES_FILE = BASE_DIR / "cookies.txt"
CHROME_EXE = r"C:\Users\lyj\.agent-browser\browsers\chrome-154.0.8037.57\chrome.exe"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.douyin.com/"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_EXE, headless=True)
        ctx = browser.new_context(user_agent=UA)
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(6000)  # 等风控 JS 写完 cookie（ttwid 等）
        cookies = ctx.cookies()
        browser.close()

    now = int(time.time()) + 86400 * 30
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        if not c.get("name"):
            continue
        domain = c["domain"] if c["domain"].startswith(".") else "." + c["domain"]
        expires = int(c.get("expires") or 0)
        lines.append("\t".join([
            domain, "TRUE", c.get("path") or "/",
            "TRUE" if c.get("secure") else "FALSE",
            str(expires if expires > 0 else now),
            c["name"], c["value"],
        ]))
    COOKIES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入 {len(cookies)} 条 cookies -> {COOKIES_FILE}")
    print("包含字段:", ", ".join(c["name"] for c in cookies))


if __name__ == "__main__":
    main()
