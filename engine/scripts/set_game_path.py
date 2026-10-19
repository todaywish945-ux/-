"""设置游戏主程序路径到 config/01/game_account.yml（部署脚本用）。

用法：
  python scripts/set_game_path.py                # 自动探测（各盘 miHoYo Launcher 默认布局）
  python scripts/set_game_path.py "D:\\...\\ZenlessZoneZero.exe"

探测不到时以退出码 2 结束并打印 AUTO_DETECT_MISS，由一键安装.bat 转人工输入。
"""

import string
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / 'src'))

GAME_EXE = 'ZenlessZoneZero.exe'


def detect() -> Path | None:
    """按米哈游启动器默认目录布局逐盘探测（本机实测命中 D:\\miHoYo Launcher\\...）。"""
    for drive in string.ascii_uppercase:
        root = Path(f'{drive}:\\')
        if not root.exists():
            continue
        candidate = root / 'miHoYo Launcher' / 'games' / 'ZenlessZoneZero Game' / GAME_EXE
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    from remi_od.core import config as config_mod

    paths = config_mod.EnginePaths(ENGINE_ROOT)
    if len(sys.argv) > 1:
        exe = Path(sys.argv[1].strip('"'))
        if not exe.exists():
            print(f'路径不存在: {exe}')
            return 1
    else:
        exe = detect()
        if exe is None:
            print('AUTO_DETECT_MISS')
            return 2
    data = config_mod.game_account(paths)
    data['game_path'] = str(exe)
    config_mod.save_game_account(paths, data)
    print(f'已写入 game_path: {exe}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
