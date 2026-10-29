#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 作者：老皮   QQ：30922884   github：shirong21cn   网站：www.2pascal.com
"""
fetch_datav.py —— 批量下载阿里云 DataV.GeoAtlas 行政区划边界数据，生成本地离线数据包。

产出（供 offline_map.html 使用，纯离线、无需联网、无需密钥）：
    data/counties.js   —— window.COUNTY_DATA = { provinces, cities, counties }
    data/provinces.js  —— window.PROVINCE_DATA = 省级轮廓（小比例尺时绘制）

重要：DataV 数据是 GCJ-02 坐标系（已实测验证），不是 WGS-84。
      GPS 原始坐标必须先转 GCJ-02 才能与本数据的边界正确匹配。

用法：
    python fetch_datav.py                 # 全量下载全国（省/市/县三级）
    python fetch_datav.py --limit 3       # 只下 3 个省，快速测试
    python fetch_datav.py --tol 0.002     # 调整化简容差（度），越大体积越小
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen

BASE = "https://geo.datav.aliyun.com/areas_v3/bound/{}.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


# ----------------------------------------------------------- 几何化简 #

def _perp_dist(p, a, b):
    """点 p 到线段 ab 的垂直距离（平面近似，够用）"""
    x, y = p
    x1, y1 = a
    x2, y2 = b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def simplify(points, tol):
    """Douglas-Peucker 化简（迭代实现，避免深递归）"""
    n = len(points)
    if n < 3:
        return points
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        max_d, idx = -1.0, i
        for k in range(i + 1, j):
            d = _perp_dist(points[k], points[i], points[j])
            if d > max_d:
                max_d, idx = d, k
        if max_d > tol:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    out = [p for p, k in zip(points, keep) if k]
    return out if len(out) >= 4 else points


def simplify_geometry(geom, tol, precision=5):
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return geom

    def round_pt(p):
        return [round(p[0], precision), round(p[1], precision)]

    def do_ring(ring):
        s = simplify([tuple(p) for p in ring], tol)
        if len(s) < 4:
            s = [tuple(p) for p in ring]
        s = [round_pt(p) for p in s]
        # 闭合
        if s and (s[0][0] != s[-1][0] or s[0][1] != s[-1][1]):
            s.append(list(s[0]))
        # 去重相邻点
        out = [s[0]]
        for p in s[1:]:
            if p != out[-1]:
                out.append(p)
        return out if len(out) >= 4 else None

    if gtype == "Polygon":
        rings = [do_ring(r) for r in coords]
        rings = [r for r in rings if r]
        geom["coordinates"] = rings
    elif gtype == "MultiPolygon":
        polys = []
        for poly in coords:
            rings = [do_ring(r) for r in poly]
            rings = [r for r in rings if r]
            if rings:
                polys.append(rings)
        geom["coordinates"] = polys
    return geom


# --------------------------------------------------------------- 下载 #

def _curl_get(url, timeout=40):
    """优先用 curl 下载。

    实测：本机有代理（http_proxy=127.0.0.1:5533），curl 走代理能正常取到
    100000_full.json（582KB），而 urllib 走同一代理却返回 404。所以 curl 为主、
    urllib 兜底，两者任一成功即可。
    """
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), "-A", UA, url],
            capture_output=True,
        )
        if r.returncode == 0 and r.stdout:
            return json.loads(r.stdout.decode("utf-8"))
    except Exception:
        pass
    return None


def _urllib_get(url, timeout=40):
    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def fetch(adcode, full=False, retries=3, timeout=40):
    url = BASE.format(f"{adcode}_full" if full else adcode)
    for i in range(retries):
        data = _curl_get(url, timeout) or _urllib_get(url, timeout)
        if data:
            return data
        time.sleep(0.6 * (i + 1))
    return None


def parallel_fetch(adcodes, workers=8, full=False):
    """并发下载，返回 {adcode: data}"""
    result = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, a, full): a for a in adcodes}
        done = 0
        for fut in as_completed(futures):
            a = futures[fut]
            data = fut.result()
            if data:
                result[a] = data
            done += 1
            print(f"\r   下载进度 {done}/{len(adcodes)}", end="", flush=True)
    print()
    return result


# ---------------------------------------------------------------- 主流程 #

def main():
    ap = argparse.ArgumentParser(description="下载 DataV 行政区划边界，生成离线数据包")
    ap.add_argument("--limit", type=int, default=0, help="只下载前 N 个省（测试用）")
    ap.add_argument("--tol", type=float, default=0.002, help="化简容差（度），默认 0.002≈200m")
    ap.add_argument("--workers", type=int, default=8, help="并发下载线程数")
    args = ap.parse_args()

    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)

    print("[1/4] 下载省级列表 ...")
    root = fetch(100000, full=True)
    if not root or not root.get("features"):
        print("[失败] 无法获取省级列表，请检查网络")
        return 1
    provinces = {}
    boundary_lines = []      # 非行政区的界线要素（十段线）
    for f in root["features"]:
        p = f["properties"]
        code = p.get("adcode")
        if str(code).isdigit():
            provinces[code] = p.get("name") or ""
        else:
            # DataV 用 100000_JD 表示南海诸岛十段线（MultiPolygon，10 段）。
            # 它不是行政区，不能参与下钻，单独作为界线图层保留。
            p["name"] = p.get("name") or "南海诸岛界线"
            boundary_lines.append(f)
    pcodes = list(provinces.keys())
    if boundary_lines:
        print(f"      界线要素 {len(boundary_lines)} 个："
              f"{'、'.join(f['properties']['name'] for f in boundary_lines)}")
    if args.limit:
        pcodes = pcodes[: args.limit]
    print(f"      共 {len(provinces)} 个省级单位，本次处理 {len(pcodes)} 个")

    print("[2/4] 下载市级（含直辖市的区县） ...")
    prov_subs = parallel_fetch(pcodes, args.workers, full=True)

    cities, city_parent = {}, {}
    direct_parent = {}           # 省直辖县级行政区 -> 所属省
    counties = []
    city_codes = []
    direct_codes = []
    for pcode, data in prov_subs.items():
        for f in data.get("features", []):
            p = f["properties"]
            code, name, lvl = p["adcode"], p["name"], p.get("level")
            if lvl == "city":
                # 关键：DataV 把「省直辖县级行政区」也标成 level=city（如五指山 469001、
                # 仙桃 429004、石河子 659001）。用 adcode 末两位区分：
                #   末两位 == 00 -> 地级市/州/盟，需继续下钻取区县
                #   末两位 != 00 -> 省直辖县级行政区，本身即县级，直接取自身边界
                if code % 100 == 0:
                    cities[code] = name
                    city_parent[code] = pcode
                    city_codes.append(code)
                else:
                    direct_codes.append(code)
                    direct_parent[code] = pcode
            elif lvl == "district":
                # 直辖市/特别行政区下直接是区县级
                f["properties"]["province"] = provinces.get(pcode, "")
                f["properties"]["city"] = provinces.get(pcode, "")
                f["properties"]["province_code"] = pcode
                f["properties"]["city_code"] = pcode
                counties.append(f)
    print(f"      地级 {len(cities)} 个，省直辖县级 {len(direct_codes)} 个，"
          f"直辖市/特区直属区县 {len(counties)} 个")

    if direct_codes:
        # 省直辖县级行政区要用 {code}.json（自身边界），{code}_full.json 返回 0 个子级
        direct_subs = parallel_fetch(direct_codes, args.workers, full=False)
        for code, data in direct_subs.items():
            pcode = direct_parent.get(code)
            for f in data.get("features", []):
                p = f["properties"]
                p["province"] = provinces.get(pcode, "")
                p["city"] = provinces.get(pcode, "")     # 直属省，无地级市
                p["province_code"] = pcode
                p["city_code"] = pcode
                counties.append(f)
        print(f"      省直辖县级边界已收录，累计县级 {len(counties)} 个")

    print("[3/4] 下载区县级边界 ...")
    city_subs = parallel_fetch(city_codes, args.workers, full=True)
    for ccode, data in city_subs.items():
        pcode = city_parent.get(ccode)
        cname = cities.get(ccode, "")
        for f in data.get("features", []):
            p = f["properties"]
            if p.get("level") != "district":
                continue
            p["province"] = provinces.get(pcode, "")
            p["city"] = cname
            p["province_code"] = pcode
            p["city_code"] = ccode
            counties.append(f)
    print(f"      地级下辖县级 {len(counties)} 个（累计）")

    # 关键兜底：少数地级市「不设市辖区」（直筒子市），{code}_full.json 直接 404，
    # 下钻拿不到任何 district，会被整批漏掉。实测全国共 4 个：
    #   东莞市 441900、中山市 442000、儋州市 460400、嘉峪关市 620200
    # 这些必须改用 {code}.json 取自身边界，作为县级要素收录。
    barrel = [c for c in city_codes
              if not sum(1 for f in (city_subs.get(c) or {}).get("features", [])
                         if f["properties"].get("level") == "district")]
    if barrel:
        own = parallel_fetch(barrel, args.workers, full=False)
        for ccode, data in own.items():
            pcode = city_parent.get(ccode)
            for f in data.get("features", []):
                p = f["properties"]
                p["province"] = provinces.get(pcode, "")
                p["city"] = p.get("name", "")        # 直筒子市：市与县同名
                p["province_code"] = pcode
                p["city_code"] = ccode
                counties.append(f)
        print(f"      补录不设区的地级市 {len(barrel)} 个："
              f"{'、'.join(cities.get(c, str(c)) for c in sorted(barrel))}")

    # 兜底：个别省级单位在 DataV 只有省级轮廓、没有下级数据 —— 实测台湾省
    # 710000 的 {code}_full.json 返回 404。不能让整个省级单位在县级图层消失，
    # 用省级轮廓本身作为一个要素收录，保证放大后点击仍可查到归属。
    no_sub = [p for p in pcodes if not (prov_subs.get(p) or {}).get("features")]
    if no_sub:
        own = parallel_fetch(no_sub, args.workers, full=False)
        for pcode, data in own.items():
            for f in data.get("features", []):
                p = f["properties"]
                p["province"] = provinces.get(pcode, "")
                p["city"] = p.get("name", "")
                p["province_code"] = pcode
                p["city_code"] = pcode
                counties.append(f)
        print(f"      补录无下级数据的省级单位 {len(no_sub)} 个："
              f"{'、'.join(provinces.get(c, str(c)) for c in sorted(no_sub))}")

    print(f"      县级要素合计 {len(counties)} 个")

    print(f"[4/4] 化简几何（容差 {args.tol}°）并写入 {OUT_DIR} ...")
    kept = []
    for f in counties:
        try:
            f["geometry"] = simplify_geometry(f["geometry"], args.tol)
        except Exception:
            continue
        g = f.get("geometry") or {}
        c = g.get("coordinates")
        if g.get("type") == "Polygon" and c:
            kept.append(f)
        elif g.get("type") == "MultiPolygon" and c:
            kept.append(f)

    slim = []
    for f in kept:
        p = f["properties"]
        slim.append({
            "type": "Feature",
            "properties": {
                "adcode": p.get("adcode"),
                "name": p.get("name"),
                "province": p.get("province", ""),
                "city": p.get("city", ""),
                "province_code": p.get("province_code"),
                "city_code": p.get("city_code"),
                "center": [round(v, 5) for v in (p.get("center") or p.get("centroid") or [0, 0])],
            },
            "geometry": f["geometry"],
        })

    # 省级轮廓（用省级要素本身，供小比例尺绘制）+ 界线要素（十段线）
    prov_feats = []
    for f in root["features"]:
        p = f["properties"]
        code = p.get("adcode")
        is_line = not str(code).isdigit()
        if not is_line and args.limit and code not in pcodes:
            continue
        # 十段线每段是细长窄多边形，用常规容差会被化简掉，这里用极小容差
        tol = 0.0002 if is_line else args.tol
        try:
            geom = simplify_geometry(json.loads(json.dumps(f["geometry"])), tol)
        except Exception:
            geom = f["geometry"]
        prov_feats.append({
            "type": "Feature",
            "properties": {"adcode": code, "name": p.get("name") or "南海诸岛界线",
                           "is_boundary_line": is_line},
            "geometry": geom,
        })

    def dump_js(filename, varname, obj):
        path = os.path.join(OUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(f"window.{varname} = ")
            json.dump(obj, fp, ensure_ascii=False, separators=(",", ":"))
            fp.write(";\n")
        return os.path.getsize(path)

    s1 = dump_js("counties.js", "COUNTY_DATA", {
        "source": "阿里云 DataV.GeoAtlas（GCJ-02 坐标系）",
        "updated": time.strftime("%Y-%m-%d"),
        "provinces": provinces,
        "cities": cities,
        "features": slim,
    })
    s2 = dump_js("provinces.js", "PROVINCE_DATA", {
        "source": "阿里云 DataV.GeoAtlas（GCJ-02 坐标系）",
        "features": prov_feats,
    })

    print()
    print("完成：")
    print(f"  data/counties.js   {s1/1024/1024:.2f} MB   县级要素 {len(slim)} 个")
    print(f"  data/provinces.js  {s2/1024/1024:.2f} MB   省级要素 {len(prov_feats)} 个")
    print(f"  耗时 {time.time()-t0:.1f} 秒")
    print()
    print("提示：数据是 GCJ-02。GPS(WGS-84) 坐标必须先转 GCJ-02 才能正确匹配边界。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
