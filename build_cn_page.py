#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 offline_map.html 生成国内版页面 offline_map_cn.html。

保持单一来源：全球版页面是唯一手工维护的文件，国内版由本脚本派生，
避免两份 HTML 各自漂移。改动点：
  1. 去掉 world_admin0.js / world_admin1.js 两个 script 引用（不加载国外数据）
  2. HAS_WORLD 固定为 false（不画国界图层、隐藏「世」按钮、境外不判定）
  3. 标题、状态栏、说明文案里去掉与国外数据相关的内容

用法：
    python build_cn_page.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "offline_map.html")
DST = os.path.join(ROOT, "offline_map_cn.html")


def main():
    s = open(SRC, encoding="utf-8").read()

    # 1) 标题加「国内版」
    s = s.replace(
        "<title>离线行政区划地图 · GPS 坐标定位与坐标转换 · 老皮</title>",
        "<title>离线行政区划地图（国内版）· GPS 坐标定位与坐标转换 · 老皮</title>",
    )

    # 2) 去掉国外数据的 script 引用
    s = s.replace('<script src="data/world_admin0.js"></script>\n', "")
    s = s.replace('<script src="data/world_admin1.js"></script>\n', "")

    # 2b) 去掉「世界视图」按钮（国内版没有国外数据可看）
    s = s.replace('            <button id="zworld" title="世界视图">世</button>\n', "")

    # 3) HAS_WORLD 固定为 false
    old = "    var HAS_WORLD = W0.length > 0 || W1.length > 0;"
    new = "    var HAS_WORLD = false;            // 国内版：打包时不含国外数据，固定关闭"
    if old not in s:
        print("!! 未找到 HAS_WORLD 定义，请检查 offline_map.html")
        return 1
    s = s.replace(old, new)

    # 4) 说明文案：删掉「国外边界为 WGS-84…」整段
    seg = ('            <div style="margin-top:8px">国外边界为 <b>WGS-84</b>'
           '（geoBoundaries / Natural Earth），境外点不偏移；\n'
           '            判定顺序为「先国内、后国外」，因此中国及台港澳一律由国内数据给出。</div>\n')
    if seg in s:
        s = s.replace(seg, "")
    else:
        print("!! 未匹配到国外边界说明段落，跳过该步")

    # 5) 操作提示去掉「世」按钮说明
    s = s.replace("「中」回到全国，「世」看世界。", "「中」回到全国。")
    s = s.replace("「中」回到全国，「世」看世界", "「中」回到全国")

    # 6) 状态栏文案
    s = s.replace(
        "'境外坐标不参与判定。需要全球版请运行 python fetch_world.py --all 后重新打包。</span>'",
        "'境外坐标不参与判定。需要判定境外坐标请使用全球版 offline_map.html。</span>'",
    )

    open(DST, "w", encoding="utf-8").write(s)
    print("已生成 %s（%d 字节，源 %d 字节）" % (DST, len(s), len(open(SRC, encoding="utf-8").read())))
    print("  含 world_admin 引用:", s.count("world_admin"))
    print("  HAS_WORLD:", re.search(r"var HAS_WORLD = [^;]+;", s).group(0).strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
