# 小蕾米桌宠（源码版 · PyQt6）

技术栈：Python 3.13 + PyQt6，可用 PyInstaller 打包发布。

## 为什么用 PyQt6 而不是 PyQt5？

原版用 PyQt5（Qt 5.15.2）。在较新的 Windows 11 系统上，Qt 5.15.2 会出现
**"无法初始化 Qt 平台插件"** 而无法启动（本机已验证：原版 exe 与 pip 的 PyQt5
都会崩溃，而 Qt 6.11 完全正常）。因此本源码版已迁移到 PyQt6，API 与 Qt5 几乎一致。

## 运行

```bash
pip install -r requirements.txt
python pet.py
```

依赖：`PyQt6`（界面）+ `pynput`（全局键盘监听，用于"打字时小蕾米连续绘制"）。
若 `pynput` 安装失败或缺失，程序会静默跳过该功能，不影响其他功能。

## Linux 运行

桌宠本体是跨平台的（Python 3.13 + PyQt6），Linux 一样能跑：

```bash
./run.sh          # 自动建虚拟环境、装依赖并启动（需 python3-venv）
```

或手动：

```bash
pip install -r requirements.txt
python pet.py
```

Linux 上的差异：

- **绝区零每日任务是 Windows 专属**（游戏客户端与一条龙引擎均为 Windows 程序），
  Linux 上该窗口会显示"引擎：未安装"，其他功能（聊天/游戏/画画/提醒）不受影响；
- 开机自启（注册表）与 `*.bat` 定时任务为 Windows 专属，菜单自动隐藏；
- 闹钟提示音依赖 `winsound`，Linux 上无提示音，弹窗提醒照常；
- pynput 全局键盘监听需要 X11，Wayland 下"打字连续绘制"动画自动跳过；
- AI 的音量调节工具在 Linux 上通过 `pactl`（PulseAudio/PipeWire）执行，
  缺失时回退 `amixer`（ALSA）。

## 操作

| 操作 | 效果 |
| --- | --- |
| 左键拖拽 | 移动桌宠位置 |
| 左键单击 | 随机表情互动（得意/思考/期待），2 秒后恢复 |
| 左键双击 | 在默认状态与选定的「双击动作」之间切换（可自选动作） |
| 鼠标滚轮 | 缩放大小（0.5x ~ 2x） |
| 任意键盘输入 | 全局监听：在任何程序中打字，小蕾米表演「连续绘制」动画 |
| 右键菜单 | 和小蕾米聊天 / 画画 / 和小蕾米玩游戏 / 开机自启 / 双击动作 / 更换称呼 / 作者信息 / 退出 |

### 右键菜单

- **开机自启**：勾选后 Windows 开机自动启动（写注册表 `HKCU\...\Run`）
- **双击动作**：自选双击时要播放的 GIF（待机/得意/思考/拿笔待机/期待/连续绘制/间歇绘制）
- **更换称呼（性别）**：男「我的共犯先生」/ 女「我的共犯小姐」

## 小游戏

右键桌宠 → **和小蕾米玩游戏**，可玩五个小游戏：

| 游戏 | 玩法 |
| --- | --- |
| 猜数字 | 蕾米想一个 1~100 的数，你猜，提示大了/小了 |
| 石头剪刀布 | 和蕾米对战，计分定输赢 |
| 打地鼠 | 30 秒内点击冒头的小蕾米（待机动画）得分，点空减分 |
| 吃豆人 | 方向键控制蕾米在红色迷宫里吃豆，躲开幽灵吃完所有豆子通关 |

## 绝区零每日任务（自带启动器）

右键桌宠 → **🎮 绝区零每日任务**，小蕾米可以帮你自动完成游戏内日常：
**吼吼饼铺签到（刮刮卡）→ 咖啡店 → 体力刷本 → 活跃度奖励**，也可单独执行某一项。

工作原理：桌宠本身就是启动器。它通过本机 HTTP 接口（`127.0.0.1:23001`）驱动
独立安装的开源项目 [ZenlessZoneZero-OneDragon](https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon)
（GPL-3.0，与本项目进程隔离，互不影响协议）作为**无界面后台引擎**：
点「一键日常」后自动启动引擎 → 自动打开游戏 → 跑完全部启用任务 → 气泡汇报，
全程不需要打开一条龙自己的界面。引擎装在 `D:\ZenlessZoneZero-OneDragon`。

### ⚙ 任务设置（都在桌宠窗口里）

- **任务开关**：勾选一条龙要跑哪些应用（签到/咖啡/体力/活跃已预置启用）；
- **每日签到方式**：吼吼饼铺 / 卦象集录 / 刮刮卡（默认吼吼饼铺）；
- **体力计划**：副本类型 + 每次运行刷几把（默认实战模拟室-调查专项 ×1）；
- 保存后桌宠会自动重启引擎使配置生效（约半分钟）。

### 首次注意（一次性）

- 游戏路径已预置：`D:\miHoYo Launcher\games\ZenlessZoneZero Game`；
- 游戏内设置为 **1920x1080 窗口化（16:9）、简体中文、关闭 HDR**；
- 游戏客户端保持登录状态（引擎会自动启动游戏并进入，但不会替你输密码登录）。

### 日常使用

- **桌宠菜单**：右键 → 🎮 绝区零每日任务 → 点「一键日常」。跑的时候小蕾米会切思考表情，
  完成后弹气泡汇报；
- **每天定时自动**：双击 `注册每日定时任务.bat`（默认每天 08:00，可改脚本里的时间），
  `取消每日定时任务.bat` 可取消；
- **手动**：`python zzz_daily.py chain`（命令行），`status`/`apps`/`stop` 查状态/列任务/停止。

### 相关文件

| 文件 | 作用 |
| --- | --- |
| `zzz_daily.py` | 引擎 HTTP 客户端 + 配置读写 + 服务启停 + 命令行 |
| `zzz_daily_window.py` | 桌宠里的任务窗口与 ⚙ 任务设置对话框 |
| `绝区零配置.json` | 引擎路径/端口等（一般不用改） |
| `绝区零引擎服务.log` / `绝区零定时.log` | 运行日志 |
| 引擎侧 `config\01\one_dragon\_group.yml` | 一条龙任务清单（桌宠设置会改写它） |

> 注意：定时执行时会真的打开游戏窗口并接管键鼠，请避开你用电脑的时间段；
> 识别偶发失败属正常（游戏更新后等引擎项目跟进修复，游戏大版本后在
> `D:\ZenlessZoneZero-OneDragon` 重新运行 `.tools\uv.exe sync --group dev` 更新引擎）。

### 发给其他玩家用（引擎已内置离线包）

桌宠自带 **`引擎离线包/`** 文件夹（约 350MB：引擎主包 + 便携 Python 3.11 + 配置模板），
其他玩家把**整个文件夹**（含 `引擎离线包`）拿走后，双击 **`安装绝区零引擎.bat`** 即可：
脚本自动定位游戏客户端、解压引擎、用离线包里的 Python 创建环境、从国内镜像装
依赖（约 2GB，唯一需要网络的步骤，走清华源）、预置任务配置。
**全程不需要访问 GitHub**，可重复运行断点续装。
装完打开桌宠即可一键日常。

- 不装引擎：桌宠其他功能（聊天/游戏/画画/提醒）完全不受影响，
  绝区零窗口会显示「引擎：未安装」；
- 协议：引擎项目为 GPL-3.0，本桌宠通过进程隔离调用，分发桌宠代码无需随之开源；
- 若仓库分发（git）时不便携带 `引擎离线包/`（已列入 .gitignore），
  可单独网盘分发该文件夹，或删掉离线包让安装脚本回退到 GitHub 在线下载模式。

## AI 聊天

程序支持任意 OpenAI 兼容接口。仓库只提交 `AI配置.json.example`（不含密钥），
首次运行若没有 `AI配置.json` 会自动从该示例生成；默认配置用的是**智谱 AI 免费模型**
（`glm-4-flash` 文字 / `glm-4v-flash` 视觉，均免费）：

```json
{
  "base_url": "https://open.bigmodel.cn/api/paas/v4",
  "api_key": "你的 key",
  "model": "glm-4-flash",
  "vision_model": "glm-4v-flash",
  "system_prompt": "角色设定……",
  "max_history": 10
}
```

1. 复制 `AI配置.json.example` 为 `AI配置.json`，填入你自己的 `api_key`
   （`base_url`/`model` 可换成任意 OpenAI 兼容服务，如 DeepSeek、硅基流动、Groq 等）；
2. 右键桌宠 → **和小蕾米聊天**，回车发送问题；
3. 回复时桌宠上方会弹出短气泡，点击气泡可打开完整聊天窗口；
4. 点聊天窗口里的 **图片** 按钮可上传题目截图，蕾米会调用 `vision_model` 看图解题；
5. 全部走标准库 `urllib`，无需额外安装依赖，回答不会阻塞界面。

> 首次启动会弹窗询问你的性别，称谓随性别变化（男「兄弟」/女「姐妹」），
> 存于 `使用者.json`，可随时在右键菜单「更换称呼（性别）」里修改。

## 保护你的 API Key

`AI配置.json`、`使用者.json`、`设置.json`、`闹钟配置.json` 等个人数据已列入
`.gitignore`，**不要提交真实 key 到仓库**。开源自用即可：本地保留真实
`AI配置.json`，仓库里只带 `AI配置.json.example`。

## 目录结构

```
pet.py              桌宠主窗口（DesktopPet），入口文件
constants.py        常量配置（GIF 列表、画画序列、性别称谓、AI 模板）
ai.py               AI 后台请求线程（AIWorker）+ 消息历史裁剪
chat.py             AI 聊天（短气泡 SpeechBubble + 聊天窗口 AIChatWindow）
games.py            小游戏（猜数字 / 石头剪刀布 / 打地鼠 / 吃豆人）
alarm.py            定时提醒（闹钟 + 倒计时）
zzz_daily.py        绝区零每日任务引擎客户端（HTTP 调用 + 命令行）
zzz_daily_window.py 绝区零每日任务窗口（一键日常 / 单项执行 / 实时日志）
draw.py             画画结果弹窗
test_logic.py       离线逻辑测试（mock Qt 跑通，无需显示器）
gif/                7 个状态 GIF（待机/得意/思考/拿笔待机/期待/连续绘制/间歇绘制）
pics/               15 张"画画"结果图
favicon.ico         程序图标
AI配置.json.example  AI 配置模板（无密钥，首次运行会复制成 AI配置.json）
坐标配置.json        每个 GIF 的绘制偏移（缺失时使用默认值 0）
设置.json           记忆上次位置/大小（退出时自动生成）
使用者.json         记忆你的性别（首次启动选择后生成）
```

## 打包成 exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "小蕾米AI助理" --icon favicon.ico \
  --add-data "gif;gif" --add-data "pics;pics" --add-data "favicon.ico;." \
  --add-data "AI配置.json.example;." --add-data "作者.jpg;." pet.py
```

单文件输出在 `dist/小蕾米AI助理.exe`。把 `AI配置.json.example` 复制成
`AI配置.json` 放到 exe 同目录并填好 key 即可使用。

> 依赖含 `pynput`（全局键盘监听打字动画），requirements.txt 已列出。
> 打包后**开机自启**会写入 exe 的真实路径（PyInstaller 下用 `sys.argv[0]`，
> 而非 `sys.executable`——后者在 onefile 模式下指向临时解压目录，会导致自启失效）。

## 改造为其他角色

1. 把角色素材按同样命名替换到 `gif/`（`待机.gif` 必须存在，作为默认状态）；
2. 需要"画画"动画就准备 `拿笔待机/连续绘制/间歇绘制` 三个 GIF；
3. 修改 `GIF_NAMES` / `DRAW_SEQUENCE` / `SPECIAL_DURATIONS` 适配新角色的动作。
