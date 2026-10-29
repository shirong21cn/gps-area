#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
离线行政区划查询（国内版）—— 桌面启动器

与 launcher.py（全球版）共用同一份页面与逻辑，区别只有两点：
  1. 打包时不带 data/world_admin0.js / world_admin1.js（国外数据）
  2. 横幅上标注"国内版"

页面 offline_map.html 检测到没有国外数据时会自动降级：
隐藏"世界视图"按钮、跳过国界图层、境外坐标不参与判定。

作者：老皮  QQ：30922884  github：shirong21cn  网站：www.2pascal.com
Copyright © 2026 老皮. All rights reserved.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import launcher

launcher.APP_NAME = "离线行政区划查询（国内版）"
launcher.EDITION = "国内版：仅中国（含台湾省、香港、澳门）县级数据"


if __name__ == "__main__":
    sys.exit(launcher.main())
