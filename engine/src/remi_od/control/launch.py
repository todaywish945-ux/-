"""游戏启动：按 game_account.yml 的 game_path 拉起游戏（1920x1080 窗口化）。

必须窗口化：全屏模式 Unity 不理会 -screen-width/height，会按显示器原生
分辨率渲染（2560x1600），缩放后小字识别崩溃（2026-10-01 实测任务全挂）。
"""

import subprocess
from pathlib import Path

import win32con
import win32gui

from remi_od.core.log import log

LAUNCH_WIDTH = 1920
LAUNCH_HEIGHT = 1080


def launch_game(game_path: str) -> bool:
    exe = Path(game_path)
    if not exe.exists():
        log('启动', f'游戏路径不存在: {game_path}')
        return False
    try:
        # CREATE_BREAKAWAY_FROM_JOB：不随父进程（引擎）退出而被杀
        subprocess.Popen(
            [str(exe), '-screen-width', str(LAUNCH_WIDTH), '-screen-height',
             str(LAUNCH_HEIGHT), '-screen-fullscreen', '0'],
            cwd=str(exe.parent),
            creationflags=0x01000000,
        )
        log('启动', f'游戏已拉起: {exe.name}')
        return True
    except Exception as e:
        log('启动', f'游戏拉起失败: {e}')
        return False


def close_game(window_hwnd: int | None = None) -> bool:
    """尝试优雅关闭游戏窗口。"""
    if window_hwnd:
        try:
            win32gui.PostMessage(window_hwnd, win32con.WM_CLOSE, 0, 0)
            return True
        except Exception:
            return False
    return False
