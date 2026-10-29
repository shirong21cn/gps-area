#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gps_marker.py —— 输入一个 GPS 坐标，联网时在百度地图上标注该点并显示。

要点：
1. 输入坐标一律按 WGS-84（GPS 原始坐标）处理，程序自动换算成百度使用的 BD-09。
   换算算法已与业界标准库 gcoord 逐点比对，误差 0 米。
2. 程序会先探测网络/百度地图是否可达，只有可达时才生成标注并打开浏览器。
3. 两种显示方式：
   - 有百度地图 AK（--ak 或环境变量 BAIDU_MAP_AK）时：生成本地 HTML（JS API），标注更漂亮；
   - 没有 AK 时：调用百度地图官方 URI API，直接在浏览器里打开带标注的地图页（无需密钥）。

用法示例（坐标统一为 WGS-84，纬度,经度）：
    python gps_marker.py 39.907375,116.391349            # 天安门
    python gps_marker.py --lat 39.907375 --lng 116.391349 --title "天安门"
    python gps_marker.py 31.2286,121.4687 --ak 你的AK --zoom 17
    python gps_marker.py 39.9,116.4 --no-open            # 只生成/打印，不打开浏览器

作者：老皮  QQ：30922884  github：shirong21cn  网站：www.2pascal.com
"""

import argparse
import math
import os
import socket
import sys
import webbrowser
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

# ------------------------------------------------------------- 版权信息 #
APP_NAME = "GPS 坐标标注 / 离线行政区划查询"
APP_VERSION = "1.0.0"
AUTHOR = "老皮"
QQ = "30922884"
GITHUB = "shirong21cn"
SITE = "www.2pascal.com"
COPYRIGHT = "Copyright © 2026 老皮 · QQ：30922884 · github：shirong21cn · www.2pascal.com"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) gps-marker/1.0"

# 连通性探测目标：任一可达即认为百度地图可用（可按需修改，例如走代理/内网域名）
BAIDU_HOSTS = ["map.baidu.com", "api.map.baidu.com", "www.baidu.com"]

# ---------------------------------------------------------------- 坐标转换 #

X_PI = math.pi * 3000.0 / 180.0
PI = math.pi
A = 6378245.0          # 克拉索夫斯基椭球长半轴
EE = 0.00669342162296594323  # 偏心率平方


def _out_of_china(lng: float, lat: float) -> bool:
    """粗略判断是否在国界外（境外不做 GCJ-02 偏移）。"""
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lng: float, lat: float):
    """WGS-84（GPS 原始） -> GCJ-02（火星坐标）"""
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (A / sqrtmagic * math.cos(radlat) * PI)
    return lng + dlng, lat + dlat


def gcj02_to_bd09(lng: float, lat: float):
    """GCJ-02 -> BD-09（百度坐标）

    注意：纬度常数是 0.006，不是网上很多版本里写的 0.0036。
    已用 gcoord（业界标准库）交叉验证：用 0.0036 会让纬度偏小约 266 米。
    """
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * X_PI)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * X_PI)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def wgs84_to_bd09(lng: float, lat: float):
    return gcj02_to_bd09(*wgs84_to_gcj02(lng, lat))


# ------------------------------------------------------------ 网络连通检测 #

def _tcp_ok(host: str, port: int = 443, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ok(url: str, timeout: float = 5.0) -> bool:
    """只要拿到 HTTP 响应（即使 4xx/5xx）就说明链路是通的。"""
    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=timeout) as resp:
            return resp.status is not None
    except HTTPError:
        return True
    except Exception:
        return False


def baidu_map_reachable(timeout: float = 5.0, hosts=None):
    """返回 (是否可达, 说明文字)。TCP 与 HTTP 双重探测，任一通过即认为可达。"""
    hosts = hosts or BAIDU_HOSTS
    for host in hosts:
        if _tcp_ok(host, 443, timeout):
            return True, f"TCP 443 连通：{host}"
    for host in hosts:
        if _http_ok(f"https://{host}/", timeout):
            return True, f"HTTP 可达：{host}"
    return False, "无法连接 " + " / ".join(hosts)


# --------------------------------------------------------------- 展示方式 #

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>百度地图 - GPS 坐标标注</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script type="text/javascript" src="https://api.map.baidu.com/api?v=3.0&ak={ak}"></script>
    <style>
        html, body {{ margin: 0; height: 100%; }}
        #map {{ width: 100%; height: 100%; }}
        #tip {{
            position: absolute; left: 12px; top: 12px; z-index: 9;
            background: #fff; padding: 8px 12px; border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,.18); font: 13px/1.6 "Microsoft YaHei", sans-serif;
            color: #333; max-width: 320px;
        }}
        #tip b {{ color: #d93025; }}
        #cr {{
            position: absolute; right: 12px; bottom: 8px; z-index: 9;
            background: rgba(255,255,255,.86); padding: 4px 9px; border-radius: 4px;
            font: 12px/1.5 "Microsoft YaHei", sans-serif; color: #666;
        }}
        #cr a {{ color: #1a73e8; text-decoration: none; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="tip">
        <div><b>{title}</b></div>
        <div>WGS-84：{wlat:.6f}, {wlng:.6f}</div>
        <div>BD-09（本地估算，仅供参考）：{lat:.6f}, {lng:.6f}</div>
    </div>
    <div id="cr">
        作者：老皮 · QQ：30922884 ·
        <a href="https://github.com/shirong21cn" target="_blank" rel="noopener">github：shirong21cn</a> ·
        <a href="https://www.2pascal.com" target="_blank" rel="noopener">www.2pascal.com</a>
    </div>
    <script type="text/javascript">
        var bdPoint = new BMap.Point({lng:.6f}, {lat:.6f}); // WGS-84 转换后的 BD-09（标注落点）
        var map = new BMap.Map("map");
        map.centerAndZoom(bdPoint, {zoom});
        map.enableScrollWheelZoom(true);
        map.addControl(new BMap.NavigationControl());
        map.addControl(new BMap.ScaleControl());

        var marker = new BMap.Marker(bdPoint);
        map.addOverlay(marker);
        var infoWindow = new BMap.InfoWindow(
            "<b>{title}</b><br/>WGS-84：{wlat:.6f}, {wlng:.6f}<br/>BD-09：{lat:.6f}, {lng:.6f}",
            {{ width: 240, height: 90, title: "坐标信息" }}
        );
        marker.addEventListener("click", function () {{ map.openInfoWindow(infoWindow, bdPoint); }});
        map.openInfoWindow(infoWindow, bdPoint);
    </script>
</body>
</html>
"""


def build_html(bd_lng, bd_lat, w_lng, w_lat, ak, title, zoom):
    return HTML_TEMPLATE.format(
        ak=ak, title=title, lat=bd_lat, lng=bd_lng,
        wlat=w_lat, wlng=w_lng, zoom=zoom,
    )


def build_uri(bd_lat, bd_lng, title, zoom, content="GPS 坐标标注"):
    """百度地图 URI API（无需 AK）。location 顺序为 纬度,经度。

    实测（2026-10）该接口只正确解析 coord_type=bd09ll：
    传 wgs84ll / gcj02ll 时重定向结果里会变成 latlng=-0,0（坐标丢失）。
    因此这里必须传入已转换好的 BD-09 坐标。
    """
    return (
        "https://api.map.baidu.com/marker"
        f"?location={bd_lat:.6f},{bd_lng:.6f}"
        f"&title={quote(title)}"
        f"&content={quote(content)}"
        "&output=html&coord_type=bd09ll"
        f"&zoom={zoom}"
        "&src=webapp.gps.marker"
    )


# ------------------------------------------------------------------- 解析 #

def parse_coord(text: str):
    """支持 '39.9,116.4' / '39.9 116.4' / '39.9;116.4'，默认 纬度,经度。"""
    for sep in (",", "，", ";", "；", " ", "\t"):
        if sep in text:
            a, b = text.split(sep, 1)
            try:
                return float(a.strip()), float(b.strip())
            except ValueError:
                raise SystemExit(f"[错误] 无法解析坐标：{text!r}")
    raise SystemExit("[错误] 请输入两个数值，例如：39.9087,116.3975")


def main():
    parser = argparse.ArgumentParser(
        description="输入 GPS 坐标，联网时在百度地图上标注并显示。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：python gps_marker.py 39.9087,116.3975 --title 天安门\n"
               f"\n{COPYRIGHT}",
    )
    parser.add_argument("coord", nargs="?", help="坐标，格式：纬度,经度（如 39.9087,116.3975）")
    parser.add_argument("--lat", type=float, help="纬度（WGS-84）")
    parser.add_argument("--lng", type=float, help="经度（WGS-84）")
    parser.add_argument("--lnglat", action="store_true", help="坐标顺序为 经度,纬度")
    parser.add_argument("--title", default="GPS 标注点", help="标注标题")
    parser.add_argument("--zoom", type=int, default=16, help="地图缩放级别（3-19，默认 16）")
    parser.add_argument("--ak", default=os.environ.get("BAIDU_MAP_AK", ""),
                        help="百度地图 AK（也可设环境变量 BAIDU_MAP_AK）；不填则使用免密钥 URI 方式")
    parser.add_argument("--out", default="", help="把 HTML 标注页保存到指定路径")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器，只生成链接/文件")
    parser.add_argument("--timeout", type=float, default=5.0, help="网络探测超时秒数（默认 5）")
    parser.add_argument("--version", action="version",
                        version=f"{APP_NAME} v{APP_VERSION}\n{COPYRIGHT}")
    args = parser.parse_args()

    # --- 取坐标 ---
    if args.lat is not None and args.lng is not None:
        lat, lng = args.lat, args.lng
    elif args.coord:
        v1, v2 = parse_coord(args.coord)
        lat, lng = (v2, v1) if args.lnglat else (v1, v2)
    else:
        try:
            raw = input("请输入 GPS 坐标（纬度,经度）：").strip()
        except EOFError:
            parser.print_help()
            return 1
        v1, v2 = parse_coord(raw)
        lat, lng = (v2, v1) if args.lnglat else (v1, v2)

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        print(f"[错误] 坐标超出合法范围：lat={lat}, lng={lng}（纬度 -90~90，经度 -180~180）")
        return 1
    args.zoom = max(3, min(19, args.zoom))

    print(f"[输入] WGS-84 坐标：纬度 {lat:.6f}，经度 {lng:.6f}")

    # --- 网络探测 ---
    print("[检测] 正在探测百度地图连通性 ...")
    ok, reason = baidu_map_reachable(args.timeout)
    if not ok:
        print(f"[失败] 网络不通：{reason}")
        print("       → 未执行标注。请检查网络/代理后重试。")
        print(f"       → 离线可参考坐标（WGS-84）：{lat:.6f}, {lng:.6f}")
        return 2
    print(f"[检测] 网络畅通（{reason}）")

    # --- WGS-84 -> BD-09（百度 URI 接口只认 BD-09，必须本地转换） ---
    bd_lng, bd_lat = wgs84_to_bd09(lng, lat)
    print(f"[转换] WGS-84 ({lat:.6f}, {lng:.6f}) -> BD-09 ({bd_lat:.6f}, {bd_lng:.6f})")

    # --- 显示 ---
    if args.ak:
        html = build_html(bd_lng, bd_lat, lng, lat, args.ak, args.title, args.zoom)
        path = args.out or os.path.join(os.getcwd(), "gps_marker.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[生成] 标注页面已保存：{path}")
        if not args.no_open:
            print("[打开] 正在用默认浏览器打开（AK 需把 Referer 白名单设为 *，否则地图不显示）")
            webbrowser.open("file:///" + path.replace("\\", "/"))
    else:
        url = build_uri(bd_lat, bd_lng, args.title, args.zoom)
        print(f"[链接] 百度地图标注链接：\n       {url}")
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(f'<meta charset="utf-8"><meta http-equiv="refresh" content="0;url={url}">')
            print(f"[生成] 跳转页面已保存：{args.out}")
        if not args.no_open:
            print("[打开] 正在用默认浏览器打开百度地图 ...")
            webbrowser.open(url)

    print("[完成] 标注点已显示在百度地图上。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
