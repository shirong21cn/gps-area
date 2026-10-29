#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
离线行政区划查询 —— 桌面启动器

把 offline_map.html 与 data/ 下的边界数据打包进单个 exe。
运行后在本机起一个只监听 127.0.0.1 的临时 HTTP 服务，
自动用默认浏览器打开页面；关闭时按回车即可退出。

全程离线：不联网、不加载任何 CDN、不需要密钥。

作者：老皮  QQ：30922884  github：shirong21cn  网站：www.2pascal.com
Copyright © 2026 老皮. All rights reserved.
"""

import os
import socket
import sys
import threading
import time
import webbrowser

# ------------------------------------------------------------- 版权信息 #
APP_NAME = "离线行政区划查询"
APP_VERSION = "1.0.0"
# 版本说明（国内版启动器会覆盖这一行：仅打包中国数据）
EDITION = "全球版：中国县级 + 国外一级区"
AUTHOR = "老皮"
QQ = "30922884"
GITHUB = "shirong21cn"
SITE = "www.2pascal.com"
COPYRIGHT = "Copyright © 2026 老皮 · QQ：30922884 · github：shirong21cn · www.2pascal.com"
HOMEPAGE = "https://www.2pascal.com"

# Windows 控制台中文输出保护
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def resource_path(rel):
    """兼容 PyInstaller onefile（资源解压在 _MEIPASS）与源码直接运行。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def find_free_port(start=8000, tries=100):
    for p in range(start, start + tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return 0


def main():
    args = [a for a in sys.argv[1:]]
    if any(a in ("-v", "--version") for a in args):
        print("%s v%s" % (APP_NAME, APP_VERSION))
        print(COPYRIGHT)
        return 0

    # 控制台窗口标题带上版权
    if os.name == "nt":
        try:
            os.system("title %s v%s - %s" % (APP_NAME, APP_VERSION, COPYRIGHT))
        except Exception:
            pass

    root = resource_path(".")
    html = os.path.join(root, "offline_map.html")
    data = os.path.join(root, "data")

    if not os.path.exists(html):
        print("找不到页面文件：%s" % html)
        print("请确认 exe 与资源完整。")
        return 2
    if not os.path.exists(os.path.join(data, "counties.js")):
        print("找不到边界数据：%s" % data)
        print("请确认 data 目录完整。")
        return 2

    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, fmt, *args):      # 静音访问日志
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    port = find_free_port()
    if not port:
        print("没有可用端口（8000-8100 都被占用）")
        return 3

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    url = "http://127.0.0.1:%d/offline_map.html" % port
    print("=" * 62)
    print("  %s  v%s" % (APP_NAME, APP_VERSION))
    print("=" * 62)
    print("  服务地址：%s" % url)
    print("  数据文件：%s" % data)
    print("  数据范围：%s" % EDITION)
    print("  正在打开浏览器...")
    print()
    print("  作者：%s   QQ：%s" % (AUTHOR, QQ))
    print("  GitHub：%s   网站：%s" % (GITHUB, SITE))
    print(COPYRIGHT)
    print()
    print("  使用完毕后，在本窗口按 回车 即可关闭服务并退出。")
    print("=" * 62)

    try:
        webbrowser.open(url)
    except Exception as e:
        print("自动打开浏览器失败：%s" % e)
        print("请手动访问：%s" % url)

    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass

    print("正在关闭服务...")
    try:
        httpd.shutdown()
        httpd.server_close()
    except Exception:
        pass
    time.sleep(0.3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
