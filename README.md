# 离线 GPS 行政区划查询

仓库：<https://github.com/shirong21cn/gps-area>

完全离线的经纬度 → 行政区划归属判定工具。输入一个 GPS 坐标，判定它落在**哪个国家、哪个省/州、哪个区县**，同时给出 WGS-84 / GCJ-02 / BD-09 三套坐标。

不联网、不依赖任何 CDN、不需要密钥，全部数据打包在本地。适用于取证分析、外业核查、涉密环境。

---

## 一、快速开始

### 方式 1：直接运行 exe（推荐，无需 Python）

有两个版本，数据范围不同，页面与操作完全一致：

| exe | 数据 | 体积 | 适用 |
|---|---|---|---|---|
| `dist/离线gps行政区划查询.exe` | **全球版**：中国县级 + 国外一级区 + 国界 | 23.7 MB | 需要判定境外坐标 |
| `dist/离线gps行政区划查询（国内版）.exe` | **国内版**：仅中国（含台湾省、香港、澳门） | 11.1 MB | 只判国内，体积小、启动快 |

- 双击后自动找空闲端口起本地服务并打开浏览器
- 按界面提示输入坐标，点「定位并查询所属行政区」
- 用完在本窗口按 **回车** 关闭服务退出
- 命令行可查版本：`离线gps行政区划查询.exe --version`

页面共用同一个 `offline_map.html`，它会自己检测有没有国外数据：没有就自动隐藏「世界视图」按钮、跳过国界图层，境外坐标提示"本版本仅含中国数据"。

### 方式 2：Python 运行网页版

```bash
python launcher.py          # 全球版（当前 data/ 里有什么数据就用什么）
python launcher_cn.py       # 国内版（横幅标注数据范围）
```

或直接双击 `offline_map.html`（部分浏览器对本地 `file://` 加载 JS 有限制，推荐用 launcher）。

---

## 二、能查什么

| 范围 | 粒度 | 要素数 | 坐标系 |
|---|---|---|---|
| 中国（含台湾省、香港、澳门） | **县级**（区/县/旗/县级市） | 2875 | GCJ-02 |
| 中国 | 省级 | 34 | GCJ-02 |
| 国外 | **一级区**（美国的州、日本的都道府县…） | 3216（192 国） | WGS-84 |
| 国外 | 国家界 | 254 | WGS-84 |

国内结果示例：`广东省 / 东莞市 / 东莞市`，附 12 位行政区划代码。
境外结果示例：`日本 [JPN] / Tokyo (JP-13)`。

**已覆盖的边界情况**（这些是同类工具最容易漏的）：

- 直筒子市：东莞、中山、儋州、嘉峪关（无下级区县）
- 省直辖县级行政区：济源、仙桃、天门、潜江、神农架等 30 个
- 三沙市：西沙区、南沙区（含岛礁，永兴岛可命中）
- 台湾省、香港 18 区、澳门 8 堂区
- 南海十段线单独保留

---

## 三、坐标系处理（核心，别搞错）

国内边界数据是 **GCJ-02**（火星坐标），GPS 原始输出是 **WGS-84**，两者差 300–600 米。直接拿 WGS-84 去匹配国内边界会**判错区县**（实测：天安门直判会得到"西城区"，正确是"东城区"）。

所以判定链是：

```
输入 WGS-84
   ↓ 转 GCJ-02
查国内 2875 个县级要素 → 命中：中国 / 省 / 市 / 县 + adcode
   ↓ 未命中（说明在境外或海域）
用原始 WGS-84 查国外：先查一级区 → 再查国界
```

三条硬规则：

1. **国内优先**。藏南、阿克赛钦这类争议区会被国内数据吃掉，绝不会判成印度。
2. **坐标系分治**。国内 GCJ-02、国外 WGS-84，两条链不混用；境外点不做任何偏移，GCJ-02 / BD-09 栏显示"境外不适用"。
3. **台湾不是国家**。国外数据包里已剔除 `CHN / TWN / HKG / MAC` 条目，台湾坐标命中时输出"中国 / 台湾省"。

页面左上角可选输入坐标系：WGS-84（推荐）/ GCJ-02（高德腾讯）/ BD-09（百度）。

---

## 四、文件说明

```
离线行政区划查询/
├── offline_map.html          离线地图主页面（Canvas 渲染，零依赖）
├── launcher.py               启动器：起本地 HTTP 服务 + 开浏览器（全球版）
├── launcher_cn.py            国内版启动器（复用 launcher.py，只改横幅与版本说明）
├── gps_marker.py             联网版：调百度地图 URI API 生成标注页
├── fetch_datav.py            下载国内县级边界（DataV.GeoAtlas）→ counties.js / provinces.js
├── fetch_world.py            下载国外边界（geoBoundaries + Natural Earth）→ world_admin*.js
├── version_info.txt          exe 的 Windows 版本资源（版权/产品名/版本号）
├── version_info_cn.txt       国内版 exe 的版本资源
├── 离线行政区划查询.spec      全球版打包配置
├── 离线行政区划查询国内版.spec 国内版打包配置（不含 world_admin*.js）
├── data/
│   ├── counties.js           国内县级边界  11 MB
│   ├── provinces.js          国内省级边界  0.5 MB
│   ├── world_admin0.js       世界国界      4.1 MB（国内版不打包）
│   └── world_admin1.js       国外一级区    30 MB（国内版不打包）
└── dist/
    ├── 离线gps行政区划查询.exe              23.7 MB，全球版
    └── 离线gps行政区划查询（国内版）.exe     11.1 MB，仅中国数据
```

---

## 五、更新数据

### 国内

```bash
python fetch_datav.py
```

数据源：阿里云 DataV.GeoAtlas（`geo.datav.aliyun.com/areas_v3/bound/{adcode}.json`），坐标系 GCJ-02。
脚本用 `curl` 子进程优先、urllib 兜底（本机有代理时 urllib 会出现 404）。

### 国外

```bash
python fetch_world.py --all                    # 全球 199 国（约 14 分钟）
python fetch_world.py --iso VNM,THA,LAO        # 只下/追加指定国家
python fetch_world.py --adm0-only              # 只下国界
python fetch_world.py --all --tol 0.02         # 更激进简化，体积更小
```

数据源：
- 一级区：**geoBoundaries gbOpen ADM1**，WGS-84，许可 **CC-BY 4.0**（可商用，需署名）
- 国界：**Natural Earth 1:10m Admin-0**，WGS-84，**公共领域**（商用无需署名），自带中文国名字段

下载带断点续传 + 重试（GitHub 大文件极易断流），下载缓存放在 `data/.world_cache/`，生成完 js 后可删除（本次已删，释放 143 MB）。
简化算法为 Douglas-Peucker，默认容差 `0.01°`（约 1 km）。

---

## 六、配套用法

### 联网版百度标注（gps_marker.py）

```bash
python gps_marker.py 39.907375,116.391349 --title 天安门
python gps_marker.py 39.907375,116.391349 --ak 你的AK --zoom 17
python gps_marker.py 39.9,116.4 --no-open        # 只生成不打开浏览器
```

注意：百度 URI API **只支持 `coord_type=bd09ll`**，传 `wgs84ll` 会被解析成 `latlng=-0,0`。所以脚本本地把 WGS-84 转成 BD-09 再传。
BD-09 的纬度偏移常数是 **0.006**（网上流传的 0.0036 是错的，会导致约 266 米偏差）；已与 `gcoord` 交叉验证，误差 0.00 米。

### 批量判定取证数据

弘连火眼等取证系统导出的定位数据（照片 EXIF、微信位置、APP 轨迹）可用本工具的数据包批量判定区县归属：导出 CSV/Excel/GPX/KML/JSON 后逐点走同一条判定链即可。

但**必须先确认每个点的坐标系**——照片 EXIF / GPX 是 WGS-84，微信、高德系是 GCJ-02，百度系是 BD-09；基站/WiFi 定位精度常在几百米到几公里，这类点的区县归属只能作参考。

---

## 七、重新打包 exe

```bash
python -m PyInstaller 离线行政区划查询国内版.spec --noconfirm --distpath dist --workpath build_cn
python -m PyInstaller 离线行政区划查询.spec --noconfirm --distpath dist --workpath build
```

两者共用同一份 `offline_map.html` 与国内数据，差别只在 spec 的 `datas`（国内版不带 `world_admin*.js`）和入口脚本（`launcher_cn.py`）。

- 单文件 `--onefile` + 控制台（`--console`），数据是文本，压缩率高：35 MB 数据只让全球版从 11 MB 增到 23.7 MB
- 版本信息（右键 exe → 属性 → 详细信息）由 `version_info.txt` / `version_info_cn.txt` 写入，UTF-8 编码，中文安全
- 打包后删除 `build/`、`build_cn/`、`build.log`、`build_cn.log`、`__pycache__/` 即可

---

## 八、数据许可与合规

| 数据 | 来源 | 许可 |
|---|---|---|
| 中国县级/省级边界 | 阿里云 DataV.GeoAtlas | 免费使用，需注明来源 |
| 国外一级区 | geoBoundaries gbOpen | CC-BY 4.0，可商用，**需署名** |
| 世界国界 | Natural Earth 1:10m | 公共领域，可商用，无需署名 |

**主权表述**：本工具的国外数据包不含台湾、香港、澳门条目；台湾、香港、澳门一律作为中国的一部分，通过国内数据判定。地图渲染时中国始终使用国内省界画法。若你自行引入其他境外数据源（GADM、Natural Earth 原包等），务必先剔除 `TWN` 独立条目，否则会出现"坐标在台湾 → 国家：台湾"的错误表述。

---

## 九、已知限制

- 国内县界为简化数据，微小岛礁（如三沙部分礁盘）点击命中依赖容差，极小礁盘可能需放大后点击
- 国外只到一级区（州/省），未覆盖 county 二级；需要二级可跑 ADM2（体积会增到 60–90 MB）
- 国界数据为 1:10m 精度（约 1:10,000,000），不适合作为边界争议依据

---

## 十、版权

作者：老皮
QQ：30922884
GitHub：shirong21cn
网站：www.2pascal.com

Copyright © 2026 老皮

页面四处在显著位置标注：标题栏、页脚版权条、地图水印、`<meta name="author">`；exe 的启动横幅、`--version` 输出与 Windows 文件属性中同样包含完整版权信息。
