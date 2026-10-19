# 小蕾米引擎（remi_od）

绝区零日常自动化**迷你引擎**——用干净实现复刻「绝区零一条龙」的架构思想（状态机应用 +
画面-区域模板识别 + 窗口控制器 + HTTP 后端），专为「小蕾米AI助理」桌宠定制，可零改动替换
GPL 原版引擎。

- 依赖仅 4 个：opencv-python / numpy / pywin32 / PyYAML（HTTP 用标准库，无 FastAPI）
- 识别资源（截图模板、区域坐标）全部自建，放在 `assets/`
- 兼容桌宠全部对接面：8 个 HTTP 路由、3 个被桌宠读写的 YAML、
  `python -m zzz_od.backend.entry.server` 启动契约、`src\zzz_od` 已安装判据

## 目录

```
src/remi_od/
  core/     状态机引擎(@node/@from_node)、应用基类、运行记录(4点游戏日重置)、配置
  vision/   画面-区域 YAML 加载、模板匹配(含纯色模板/平坦区域防误报)
  control/  窗口查找(精确标题)、BitBlt/PrintWindow 截图、SendInput 键鼠、游戏启动
  apps/     enter_game + 每日签到/咖啡/体力计划/活跃奖励/录像店 + 一条龙编排
  server/   HTTP 后端(23001) + 单跑道运行槽
  tools/    调试 CLI（截屏/标注/裁模板/试配）
src/zzz_od/backend/entry/server.py   兼容 shim（桌宠启动契约）
assets/screen_info/*.yml             画面建档（实测会补充）
assets/template/<子目录>/<id>/raw.png 模板图
config/01/…                          与桌宠读写路径完全一致
tests/                               离线测试 + 冒烟脚本
```

## 运行

```bash
# 开发（引擎根目录）
.venv/Scripts/python.exe -m remi_od.server.main --host 127.0.0.1 --port 23099

# 桌宠方式（兼容入口，同原版引擎）
.venv/Scripts/python.exe -m zzz_od.backend.entry.server --host 127.0.0.1 --port 23001
```

桌宠切换到迷你引擎：把桌宠目录的 `绝区零配置.json` 的 `engine_dir` 改为本目录即可
（切回原版改回 `D:\ZenlessZoneZero-OneDragon`）。改任务设置无需重启引擎（配置按需读盘）。

## 部署分发（给别人装）

两种分发形态，一键安装.bat 双模式自适应：

- **最终用户**：打含 runtime/ 的整目录 zip（压缩后约 150-200MB），对方解压双击
  一键安装.bat，UAC 点一次【是】即完成——零安装、零联网、零输入
- **开发者（git clone）**：仓库不含 runtime/ 与 config/（体积/个人数据），
  克隆后双击 一键安装.bat 会自动退回"本机 Python 3.10+ → venv → 清华镜像装依赖"流程
- 之后代码更新：双击 重启引擎.bat 免管理员热重启（/service/reload）

开发机注意：改了依赖要同步进 runtime（pip 装 .venv 后拷贝 site-packages 对应包）。

## 测试

```bash
.venv/Scripts/python.exe -m pytest tests/ -q          # 离线测试（含契约/状态机/模板/窗口实测）
.venv/Scripts/python.exe tests/smoke_pet_client.py    # 冒烟：桌宠真实客户端代码连本引擎
```

## 已验证的关键事实（2026-09-23 真机跑通）

- **DPI 谎报**：高分屏（2560×1600@150%）下，非 DPI 感知进程拿到的窗口坐标/尺寸是缩水假值
  （1920×1080 会谎报成 1280×720），屏幕截图抓错区域。引擎启动即启用 DPI 感知。
- **绝区零屏蔽 PrintWindow**；前台渲染走 MPO 硬件叠加层，窗口 DC 的 BitBlt 也全黑；
  **只有屏幕 DC 按客户区坐标 BitBlt 能截到真实画面**（已实现，截图链第三级）。
- **世界内点击三件套**：①游戏可能把光标 ClipCursor 钉死（需解锁）②大世界是锁鼠标画面，
  点击必须**按住 ALT**（画面 YAML 的 `alt: true`）③视角模式需先发 mouse_event 微移触发
  Raw Input 切回键鼠。
- **提权运行**：游戏若被 MOD 装载器以管理员权限启动，Windows UIPI 会静默拦截普通权限
  进程的全部注入输入（键鼠全无效、无任何报错）。此时引擎必须同级提权：
  `scripts/run_engagement_elevated.py`（UAC）。若由引擎自己启动游戏（非提权）则无此问题。
- 模板匹配两个坑已修：NCC 在纯色平坦区给虚假 1.0 分（像素级校验）；纯色模板 NCC 无定义
  （TM_SQDIFF 像素差）。
- **资产来源**：坐标与部分模板来自原 OneDragon 项目（GPL，分发时注意保持开源可获取）；
  其余模板从官方测试仓 `zzz-od-test` 的归档真实截图裁剪；`tests/test_offline_screens.py`
  用归档截图做离线回归，`tests/smoke_pet_client.py` 用桌宠真实客户端代码做契约冒烟。

## 当前状态

- ✅ 框架全量 + 62 测试通过 + 桌宠客户端冒烟全过
- ✅ **四个日常任务真机端到端跑通**（2026-09-23，含真实开张/点单验证）：
  活跃奖励 9s / 吼吼饼铺签到 78s / 咖啡 18s（真点单）/ 录像店 43s（真开张）
- ✅ OCR（RapidOCR）+ 地图传送系统（区域选择/传送点横条/确认）
- ✅ **OCR 升级 PP-OCRv6 + 帧内缓存**（2026-10-06）：rapidocr 3.x（模型 wheel 自带，
  无需联网），小裁剪固定开销 ~1s → ~0.2s；OcrEngine 按"帧+区域"缓存结果、启动期
  后台预热；签到 collect 合并为每轮单次 OCR。离线基准：`scripts/bench_ocr.py`
- ✅ **引擎自提权修复**（2026-10-15）：非提权启动的 UAC 重启改经守卫脚本
  （脚本方式直跑 main.py 缺 src 路径会静默死亡）；桌宠拉起引擎改为计划任务
  优先（免 UAC 必提权），子进程退出不再误判为启动失败
- ✅ **活跃奖励导航改按钮路由**（2026-10-06）：点「快捷手册」按钮 → 验证 → 点「日常」
  TAB → 验证的闭环路线（每步 ~0.5s），开页动画有宽限期防误关；F2 降为按钮连续
  失配的兜底。对标原版画面路由（OneDragon 同环节 6.6s）
- ⏳ 体力计划（需战斗自动化，最难）
- ⏳ 桌宠/安装包集成

## 对话交互经验（真机踩出来的）

- **对话状态中按 F 无效**：推进对话必须点击（标题/对话主体）；
  F 只用于"还没进对话"的场景，且要 0.2 秒长按。
- **易混文案要收紧 OCR 阈值**：正在营业/开始营业（差一字）、上架/下架/换下——
  相似度阈值必须 ≥0.85，否则误判跳过整个开张流程。
- 传送点横条 OCR 必须全图识别再过滤（裁剪会连读吞字）；
  同名传送点（如"录像店营业点"多区域都有）必须先选定区域再选点。
- **点单问句会重新弹出**（2026-10-07）：按 1 点单后有约 6s 无 UI 转场，之后
  "想要喝点什么？"问句带选项重新出现——选项挂着时点对话文字永远无反应，
  必须选「不喝了」退出；且按 1 前必须确认今日免费额度未用（日程卡 0/1），
  否则盲按 1 = 误购付费咖啡（coffee 的 _card_ok/_ordered 双保险）。

## 画面建档流程（实测会用）

游戏开着、画面停到目标界面时：

```bash
# 1. 截图（存 debug/capture.png，1920x1080 标准）
python -m remi_od.tools.capture
# 2. 量坐标：标注并输出 rect 片段（多试几个矩形）
python -m remi_od.tools.mark debug/capture.png x1 y1 x2 y2 --label 名字
# 3. 裁模板：生成 assets/template/<画面>/<名字>/raw.png + YAML 片段
python -m remi_od.tools.make_template debug/capture.png x1 y1 x2 y2 <画面>/<名字>
# 4. 把 YAML 片段贴进 assets/screen_info/<画面>.yml（id_mark=画面判定区）
# 5. 验证：重新截图后试配
python -m remi_od.tools.match debug/capture.png <画面>/<名字>
```

## 运行要求（与原版一致）

- 游戏窗口 **1920×1080 窗口化**（设置-显示-显示模式），简中客户端
- 运行期间**双手离开键鼠**，别把其他窗口盖在游戏上；关闭标题含"绝区零"的其他窗口
  （MOD 管理器等——引擎按窗口标题精确找窗口）
- 游戏以管理员权限运行时（MOD 装载器启动的典型情况），引擎需同级提权运行（UAC），
  否则输入会被 Windows 静默拦截
