#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 作者：老皮   QQ：30922884   github：shirong21cn   网站：www.2pascal.com
"""
fetch_world.py —— 下载「国外」行政区划边界，打包成离线网页可直接用的 JS 数据包。

设计前提（重要）：
1. 中国（含台湾、香港、澳门）一律使用现有的 DataV 国内数据（data/counties.js，GCJ-02），
   本脚本下载的国外数据里会剔除 CHN / TWN / HKG / MAC 条目，避免出现"台湾是国家"的表述。
2. 国外数据为 WGS-84，判定境外点时不做任何 GCJ-02 偏移转换。
3. 判定顺序（由网页端实现）：WGS-84 输入 -> 转 GCJ-02 -> 先查国内县级 -> 未命中再查国外。

数据源：
  * 一级行政区（州/省）：geoBoundaries gbOpen ADM1，CC-BY 4.0，WGS-84
  * 国界：Natural Earth 1:10m Admin-0，公共领域，WGS-84（含中文名字段 name_zh）

产出：
  data/world_admin0.js  -> window.WORLD_ADMIN0 = { updated, source, features: [...] }
  data/world_admin1.js  -> window.WORLD_ADMIN1 = { updated, source, features: [...] }

用法：
    python fetch_world.py --iso VNM,THA,LAO          # 只下指定国家（增量追加）
    python fetch_world.py --all                      # 全球（199 个国家的 ADM1）
    python fetch_world.py --all --tol 0.02           # 更激进的简化（体积更小）
    python fetch_world.py --adm0-only                # 只下国界
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, ".world_cache")
API = "https://www.geoboundaries.org/api/current/gbOpen/ALL/ADM1/"

# 中国相关：一律走国内数据，国外数据包里剔除
EXCLUDE = {"CHN", "TWN", "HKG", "MAC"}

NE_ADM0_SOURCES = [
    "https://github.com/nvkelso/natural-earth-vector/raw/master/geojson/ne_10m_admin_0_countries.geojson",
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson",
]


# ------------------------------------------------------------ 下载（续传+重试）
def curl_download(url, path, tries=5, max_time=120):
    """带断点续传的下载，返回 True/False。GitHub 大文件容易断流，必须续传。"""
    for i in range(tries):
        subprocess.run(["curl", "-sL", "-C", "-", "--retry", "2", "--retry-all-errors",
                        "--max-time", str(max_time), "-o", path, url],
                       capture_output=True)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                with open(path, encoding="utf-8") as f:
                    json.load(f)
                return True
            except Exception:
                pass
        time.sleep(1)
    return False


def fetch_json(url, tries=4):
    for _ in range(tries):
        p = subprocess.run(["curl", "-s", "--max-time", "60", url], capture_output=True, text=True)
        try:
            return json.loads(p.stdout)
        except Exception:
            time.sleep(1)
    return None


# ------------------------------------------------------------ 几何：DP 简化
def perp_dist(p, a, b):
    x, y = p[0], p[1]
    x1, y1 = a[0], a[1]
    x2, y2 = b[0], b[1]
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def dp(points, tol):
    """Douglas-Peucker（迭代版，避免递归深度问题）。"""
    if len(points) < 3:
        return points[:]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        maxd, idx = -1.0, i
        for k in range(i + 1, j):
            d = perp_dist(points[k], points[i], points[j])
            if d > maxd:
                maxd, idx = d, k
        if maxd > tol:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring, tol):
    out = dp(ring, tol)
    if len(out) < 4:                      # 简化到不成面就退回原环
        return ring
    if out[0] != out[-1]:
        out.append(out[0][:])
    return out


def simplify_geom(geom, tol):
    g = geom
    if not g:
        return g
    t = g.get("type")
    if t == "Polygon":
        g["coordinates"] = [simplify_ring(r, tol) for r in g["coordinates"]]
    elif t == "MultiPolygon":
        g["coordinates"] = [[simplify_ring(r, tol) for r in poly] for poly in g["coordinates"]]
    return g


def bbox_of(geom):
    x0 = y0 = 1e9
    x1 = y1 = -1e9
    rings = []
    g = geom
    if g:
        if g.get("type") == "Polygon":
            rings = g["coordinates"]
        elif g.get("type") == "MultiPolygon":
            rings = [r for poly in g["coordinates"] for r in poly]
    for r in rings:
        for p in r:
            if p[0] < x0: x0 = p[0]
            if p[0] > x1: x1 = p[0]
            if p[1] < y0: y0 = p[1]
            if p[1] > y1: y1 = p[1]
    if x0 > x1:
        return None
    return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]


def write_js(path, varname, obj):
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.%s = " % varname)
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print("  写出 %s（%.1f KB）" % (path, os.path.getsize(path) / 1024))


# ------------------------------------------------------------ ADM1（一级行政区）
def build_adm1(isos, tol):
    os.makedirs(CACHE, exist_ok=True)
    idx_path = os.path.join(CACHE, "gb_ADM1.json")
    if os.path.exists(idx_path):
        meta = json.load(open(idx_path, encoding="utf-8"))
    else:
        print("拉取 geoBoundaries ADM1 索引 ...")
        meta = fetch_json(API)
        if not meta:
            print("[失败] 无法获取索引：%s" % API)
            return
        json.dump(meta, open(idx_path, "w", encoding="utf-8"), ensure_ascii=False)

    todo = [e for e in meta if e["boundaryISO"] not in EXCLUDE]
    if isos:
        want = set(s.strip().upper() for s in isos.split(",") if s.strip())
        todo = [e for e in todo if e["boundaryISO"] in want]
    print("待下载国家：%d（已剔除 %s）" % (len(todo), "/".join(sorted(EXCLUDE))))

    out_path = os.path.join(DATA, "world_admin1.js")
    feats = []
    if os.path.exists(out_path):
        old = json.loads(open(out_path, encoding="utf-8").read().split("=", 1)[1].rstrip().rstrip(";"))
        feats = old.get("features", [])
        print("已有要素 %d 个，做增量追加" % len(feats))

    done_iso = set(f["properties"]["g"] for f in feats)
    ok = fail = 0
    for n, e in enumerate(todo, 1):
        iso = e["boundaryISO"]
        if iso in done_iso:
            continue
        url = e.get("simplifiedGeometryGeoJSON")
        if not url:
            continue
        fp = os.path.join(CACHE, "%s_ADM1.geojson" % iso)
        if not os.path.exists(fp):
            good = curl_download(url, fp)
        else:
            good = True
        if not good:
            print("  [%d/%d] %s 下载失败，跳过" % (n, len(todo), iso))
            fail += 1
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            print("  [%d/%d] %s 文件损坏，跳过" % (n, len(todo), iso))
            fail += 1
            continue
        for f in d["features"]:
            p = f.get("properties", {})
            geom = simplify_geom(f.get("geometry"), tol)
            bb = bbox_of(geom)
            if not bb:
                continue
            feats.append({
                "type": "Feature",
                "properties": {
                    "n": p.get("shapeName", ""),          # 一级区名称（英文）
                    "iso": p.get("shapeISO", ""),         # ISO 3166-2 代码
                    "g": iso,                             # 所属国家 ISO3
                    "cn": p.get("shapeGroup", iso),
                },
                "bbox": bb,
                "geometry": geom,
            })
        ok += 1
        print("  [%d/%d] %s 完成，累计要素 %d" % (n, len(todo), iso, len(feats)))

    obj = {
        "updated": time.strftime("%Y-%m-%d"),
        "source": "geoBoundaries gbOpen ADM1 (CC-BY 4.0, WGS-84)",
        "note": "已剔除 CHN/TWN/HKG/MAC，中国及台港澳请使用国内数据 data/counties.js",
        "crs": "WGS-84",
        "level": "ADM1",
        "features": feats,
    }
    write_js(out_path, "WORLD_ADMIN1", obj)
    print("ADM1：成功 %d 国，失败 %d 国，要素 %d 个" % (ok, fail, len(feats)))


# ------------------------------------------------------------ ADM0（国界）
def build_adm0(tol):
    os.makedirs(CACHE, exist_ok=True)
    fp = os.path.join(CACHE, "ne_admin0.geojson")
    if not os.path.exists(fp):
        for url in NE_ADM0_SOURCES:
            print("下载国界：%s" % url)
            if curl_download(url, fp, tries=4, max_time=180):
                break
        else:
            print("[失败] 国界数据下载失败，可稍后重试或手动放置到 %s" % fp)
            return
    d = json.load(open(fp, encoding="utf-8"))
    feats = []
    skipped = []
    for f in d["features"]:
        p = f.get("properties", {})
        iso = p.get("ISO_A3") or p.get("ADM0_A3") or ""
        admin = p.get("ADMIN") or p.get("NAME") or ""
        # 剔除中国相关：中国、台湾、香港、澳门（归属判定一律走国内数据）
        if iso in EXCLUDE or admin in ("China", "Taiwan", "Hong Kong S.A.R.", "Macao S.A.R."):
            skipped.append(admin)
            continue
        geom = simplify_geom(f.get("geometry"), tol)
        bb = bbox_of(geom)
        if not bb:
            continue
        feats.append({
            "type": "Feature",
            "properties": {
                "n": p.get("NAME", ""),                  # 英文国名
                "zh": p.get("NAME_ZH") or p.get("name_zh") or "",   # 中文国名
                "iso": iso,
                "c": p.get("CONTINENT", ""),
            },
            "bbox": bb,
            "geometry": geom,
        })
    obj = {
        "updated": time.strftime("%Y-%m-%d"),
        "source": "Natural Earth 1:10m Admin-0 (public domain, WGS-84)",
        "note": "已剔除中国/台湾/香港/澳门，中国部分使用国内数据 data/counties.js",
        "crs": "WGS-84",
        "level": "ADM0",
        "features": feats,
    }
    write_js(os.path.join(DATA, "world_admin0.js"), "WORLD_ADMIN0", obj)
    print("ADM0：国家/地区 %d 个（剔除 %s）" % (len(feats), "、".join(skipped)))


def main():
    ap = argparse.ArgumentParser(description="下载国外行政区划边界，打包为离线 JS 数据包")
    ap.add_argument("--iso", default="", help="只下指定国家，逗号分隔，如 VNM,THA,LAO")
    ap.add_argument("--all", action="store_true", help="下载全球所有国家的 ADM1")
    ap.add_argument("--adm0-only", action="store_true", help="只下载/更新国界数据")
    ap.add_argument("--tol", type=float, default=0.01, help="简化容差（度），默认 0.01（约 1km）")
    args = ap.parse_args()

    if args.adm0_only:
        build_adm0(args.tol)
        return 0
    build_adm0(args.tol)
    if args.all or args.iso:
        build_adm1(args.iso or None if not args.all else None, args.tol)
    else:
        print("\n提示：加 --all 下载全球一级行政区，或 --iso VNM,THA 只下指定国家")
    return 0


if __name__ == "__main__":
    sys.exit(main())
