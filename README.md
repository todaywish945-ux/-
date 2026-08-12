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
